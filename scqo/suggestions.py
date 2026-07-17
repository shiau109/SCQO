"""Suggested updates — captured from ``update()``, decided by a human.

Since v0.6 an experiment's ``update()`` no longer writes anything: ``Session.run``
swaps a :class:`SuggestionCapture` shadow device in around the call, so every
``self.device.qubit(q).<field> = value`` becomes a :class:`Suggestion` — qubit,
field, owning store, before/after values — instead of a live write. The captured
list is stored on the run record (``record.json`` — the truth, so decisions survive
any index rebuild) with per-item status:

* ``pending``  — proposed, nothing applied (the default fate of every suggestion);
* ``accepted`` — applied through the real stores (vendor-push-first for calibration
  knobs, :class:`~scqo.physical.PhysicalStore` for sample physics) with ChangeRecords
  stamped to the ORIGINATING run_id;
* ``rejected`` — explicitly declined (metadata only, no instrument needed).

Deciding happens interactively right after ``scqo run``, later via
``scqo accept <run_id>`` (partial accepts are first-class), or immediately at run
time with ``update="apply"`` — which routes through the exact same capture+apply
path, so even auto-applied runs carry their suggestion audit trail.

Suggestions have two **origins**: ``estimator`` (captured from ``update()``, the
default) and ``operator`` (a human read the value off the run's figure — e.g. the
estimator failed on a clearly visible dip — and attached it via ``Session.suggest``
/ ``scqo suggest``). Operator items carry ``proposed_by``/``proposed_at`` and flow
through the exact same accept flow, so the applied value is credited to the run
whose data justified it.

The capture surface exposes one property per ``FIELDS`` ∪ ``PHYSICAL_FIELDS`` entry,
so ``update()`` implementations (core, driver, contrib) address calibration knobs
and physical parameters identically and need no code change; routing is by
descriptor lookup. Unknown field names raise loudly — a typo'd field in a contrib
``update()`` must not silently vanish.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel

from . import config as _config
from .config import FIELDS, FieldSpec, _now
from .device import DeviceModel, QubitView
from .physical import PHYSICAL_FIELDS, PhysicalStore


class Suggestion(BaseModel):
    """One proposed field update, as stored on the run record."""

    qubit: str
    field: str
    #: which store owns the field: "instrument" (scqo.config FIELDS, may push to the
    #: vendor) or "physical" (scqo.physical PHYSICAL_FIELDS, never touches a vendor).
    store: Literal["instrument", "physical"]
    #: value at capture time (None = not measured before); the staleness guard
    #: compares this against the store's CURRENT value at accept time.
    before: float | None
    after: float  # capture refuses NaN/Inf, so this is always finite
    status: Literal["pending", "accepted", "rejected"] = "pending"
    decided_at: str | None = None  # ISO timestamp of the accept/reject decision
    decided_by: str | None = None  # OS login of whoever decided
    #: the decision comment; a failed apply also notes its error here (status stays
    #: pending so the item remains decidable once the cause is fixed).
    comment: str = ""
    #: who proposed the value: "estimator" (captured from update()) or "operator"
    #: (a human attached it to the run via Session.suggest / `scqo suggest` — e.g.
    #: the estimator failed but the figure clearly shows the value). Records from
    #: before this field existed default truthfully to "estimator".
    origin: Literal["estimator", "operator"] = "estimator"
    proposed_by: str | None = None  # OS login of the proposer (operator-authored only)
    proposed_at: str | None = None  # when it was attached (a suggest can be days after the run)


def field_spec(field: str) -> FieldSpec | None:
    """The descriptor for a field of either store (None if unknown)."""
    return FIELDS.get(field) or PHYSICAL_FIELDS.get(field)


def pending_count(suggestions: list[dict] | list[Suggestion]) -> int:
    """How many suggestions are still undecided (works on models or plain dicts)."""
    return sum(1 for s in suggestions if _get(s, "status") == "pending")


def select_suggestions(
    suggestions: list[Suggestion],
    *,
    qubits: list[str] | None = None,
    fields: list[str] | None = None,
    indices: list[int] | None = None,
    include_decided: bool = False,
) -> list[int]:
    """0-based positions of the PENDING suggestions matching the filters.

    ``indices`` are 0-based positions into the FULL stored list (the list order is
    stable — records are never reordered); a decided index is simply not selected.
    ``qubits``/``fields`` narrow the match; no filters = every pending item.
    ``include_decided=True`` (the ``--reapply`` mode) lifts the pending-only rule so
    an already-accepted value can be re-applied (rollback) or a rejected one
    accepted after all.
    """
    out = []
    for i, s in enumerate(suggestions):
        if s.status != "pending" and not include_decided:
            continue
        if indices is not None and i not in indices:
            continue
        if qubits is not None and s.qubit not in qubits:
            continue
        if fields is not None and s.field not in fields:
            continue
        out.append(i)
    return out


def _get(s: dict | Suggestion, key: str):
    return s.get(key) if isinstance(s, dict) else getattr(s, key)


def decision_editor(touched: dict[int, dict]):
    """Editor for :meth:`~scqo.datastore.DataStore.edit_suggestions` that replaces
    ONLY the rows a decision touched. The stored list is append-only (suggest
    appends, decisions mutate in place), so positions are stable across writers —
    rows appended or decided by a concurrent session since our load are preserved
    instead of being clobbered by a stale whole-list snapshot."""

    def _apply(fresh: list[dict]) -> list[dict]:
        merged = list(fresh)
        for i, item in touched.items():
            if i < len(merged):  # can only fail on a hand-truncated record
                merged[i] = item
        return merged

    return _apply


def reject_suggestions(
    store,
    run_id: str,
    *,
    qubits: list[str] | None = None,
    fields: list[str] | None = None,
    indices: list[int] | None = None,
    comment: str = "",
) -> dict:
    """Decline pending suggestions on a saved run — metadata only, no instrument.

    ``store`` is a :class:`~scqo.datastore.DataStore` (duck-typed: ``load_run`` +
    ``edit_suggestions``); rejecting needs no backend, so ``scqo accept --reject``
    works anywhere the data drive is mounted. Same selection semantics as
    ``Session.accept``. The decision is persisted on the run record via the
    index-targeted editor, so a concurrent suggest/accept is never clobbered.
    """
    record = store.load_run(run_id)["record"]
    suggestions = [Suggestion(**s) for s in record.get("suggestions", [])]
    selected = select_suggestions(suggestions, qubits=qubits, fields=fields, indices=indices)
    for i in selected:
        s = suggestions[i]
        s.status = "rejected"
        s.decided_at = _now()
        s.decided_by = _config._current_operator() or None
        s.comment = comment
    stored = store.edit_suggestions(
        run_id, decision_editor({i: suggestions[i].model_dump(mode="json") for i in selected})
    )
    return {
        "run_id": run_id,
        "rejected": [
            {"qubit": suggestions[i].qubit, "field": suggestions[i].field} for i in selected
        ],
        "pending_left": pending_count(stored["suggestions"]),
    }


def _capture_property(field: str, store: str, spec: FieldSpec) -> property:
    """A property that reads the real store but turns writes into Suggestions."""

    def getter(self: "_CaptureQubitView") -> float | None:
        return self._parent._current(self.name, field, store)

    def setter(self: "_CaptureQubitView", value: float) -> None:
        self._parent._suggest(self.name, field, store, value)

    return property(getter, setter, doc=f"{spec.doc} [{spec.unit}]" if spec.unit else spec.doc)


class _CaptureQubitView(QubitView):
    """QubitView whose writes append Suggestions on the parent SuggestionCapture."""

    def __init__(self, parent: "SuggestionCapture", name: str) -> None:
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "_parent", parent)

    # One property per field of EITHER store: update() implementations write
    # calibration knobs and physical parameters through the same surface.
    for _field, _spec in FIELDS.items():
        vars()[_field] = _capture_property(_field, "instrument", _spec)
    for _field, _spec in PHYSICAL_FIELDS.items():
        vars()[_field] = _capture_property(_field, "physical", _spec)
    del _field, _spec

    def __setattr__(self, attr: str, value) -> None:
        # A typo'd field in an update() must fail LOUDLY (it used to vanish into the
        # instance dict); Session.run turns this into a structured capture error.
        if isinstance(getattr(type(self), attr, None), property):
            object.__setattr__(self, attr, value)  # routes through the property setter
            return
        known = ", ".join(sorted([*FIELDS, *PHYSICAL_FIELDS]))
        raise AttributeError(
            f"unknown device field {attr!r} in update() for {self.name} — known fields: {known}"
        )


class SuggestionCapture(DeviceModel):
    """Shadow device swapped in around ``update()``: reads pass through, writes
    become :class:`Suggestion` entries. Never touches a vendor, never persists."""

    def __init__(self, device: DeviceModel, physical: PhysicalStore) -> None:
        self._device = device
        self._physical = physical
        self.suggestions: list[Suggestion] = []

    def qubit(self, name: str) -> _CaptureQubitView:
        return _CaptureQubitView(self, name)

    def snapshot(self) -> dict:
        return self._device.snapshot()

    def save(self) -> None:
        """No-op: update() proposes; only an accept persists anything."""

    def _current(self, qubit: str, field: str, store: str) -> float | None:
        if store == "physical":
            return self._physical.get(qubit, field)
        return getattr(self._device.qubit(qubit), field)

    def _suggest(self, qubit: str, field: str, store: str, value: float) -> None:
        value = float(value)
        if not math.isfinite(value):  # a NaN fit output is not a proposable value
            raise ValueError(f"refusing to suggest non-finite {field}={value!r} for {qubit}")
        self.suggestions.append(
            Suggestion(
                qubit=qubit, field=field, store=store,  # type: ignore[arg-type]
                before=self._current(qubit, field, store), after=value,
            )
        )
