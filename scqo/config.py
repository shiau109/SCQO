"""SCQO-native device config + change history — the loop's durable memory.

SCQO owns a **neutral calibration config** (a peer to the vendor configs — QM
``state.json``/``wiring.json``, Qblox ``HardwareAgent`` — not derived from them) and
**records every change** to it. :class:`RecordingDevice` wraps a backend's
:class:`~scqo.device.DeviceModel`:

* reads are served from the SCQO config (authoritative);
* writes append a :class:`ChangeRecord`, update the SCQO config, then **push** the value
  to the vendor device so the instrument runs calibrated.

On construction it **seeds** the config from the vendor (pull). If a saved SCQO state
exists, what happens depends on ``on_load``:

* ``"pull"`` (default, safe while another tool may also write the vendor config — e.g.
  unmigrated qualibrate nodes on QM): the vendor wins at startup; only the saved
  **history** is loaded so provenance stays continuous.
* ``"push"`` (for devices SCQO fully owns, e.g. simulated): the saved SCQO config is
  loaded **and pushed to the vendor** — SCQO wins for the tracked calibration fields.

Either way, a *write* during a run always records + pushes: a fresh fit result is
always legitimate. Wiring/hardware stays vendor-owned and is never modelled here.

**Two classes of fields** (see :data:`FIELDS`): *pushed* calibration knobs
(readout_freq, drive_freq, pi_amp, readout_amp) behave as above; *record-only*
measured physics (t1_s, t2_star_s, t2_echo_s, readout_fidelity) is recorded into the
SCQO config + history but NEVER pushed — the instrument has no such knob, and drivers
need no code for these. Pull-mode startup merges saved record-only values back in
(the vendor snapshot cannot carry them). Every change record is stamped with the
**operator** (OS login) — attribution works for manual notebook writes too.
"""

from __future__ import annotations

import getpass
import json
import math
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from .device import DeviceModel, QubitView


def _current_operator() -> str:
    """OS login name of whoever is running this process ("" if undeterminable)."""
    try:
        return getpass.getuser()
    except Exception:  # pragma: no cover - no login name in exotic environments
        return ""

@dataclass(frozen=True)
class FieldSpec:
    """Descriptor of one neutral device field SCQO owns."""

    unit: str
    doc: str
    #: True = calibration knob, pushed to the vendor instrument on write/load.
    #: False = measured physics — recorded into state + history, NEVER pushed
    #: (the instrument has no such knob; drivers need no code for these).
    push: bool


#: The neutral device fields SCQO owns. Adding a PUSHED field still requires the
#: QubitView ABC + each backend's view; adding a RECORD-ONLY field requires an entry
#: here and nothing else.
FIELDS: dict[str, FieldSpec] = {
    # pushed calibration (vendor-backed; each backend's QubitView implements them)
    "readout_freq": FieldSpec("Hz", "Resonator readout frequency.", push=True),
    "drive_freq": FieldSpec("Hz", "Qubit 0->1 drive frequency.", push=True),
    "pi_amp": FieldSpec("", "Amplitude of the calibrated pi (x180) pulse.", push=True),
    "readout_amp": FieldSpec("", "Amplitude of the readout pulse (dimensionless, within "
                                 "the backend's current output-power configuration).", push=True),
    # record-only measured physics (no vendor knob exists; drivers untouched).
    # p_e_given_g (thermal population) deliberately stays run-record-only: it is
    # instrument-dependent — compare across instruments by query, never as state.
    "t1_s": FieldSpec("s", "Energy-relaxation time T1.", push=False),
    "t2_star_s": FieldSpec("s", "Ramsey dephasing time T2*.", push=False),
    "t2_echo_s": FieldSpec("s", "Hahn-echo coherence time T2_echo.", push=False),
    "readout_fidelity": FieldSpec("", "Single-shot assignment fidelity (0.5..1).", push=False),
}

#: The vendor-backed subset — the only fields ever setattr'd on a driver's QubitView.
PUSHED_FIELDS = tuple(f for f, s in FIELDS.items() if s.push)


def _now() -> str:
    """ISO-8601 timestamp in local time WITH the UTC offset (e.g. ``...+08:00``).

    Local (not UTC) so that the date prefix matches the datastore's run folders and
    what a human types into ``find_runs(since=..., until=...)``; the explicit offset
    keeps it machine-unambiguous. Lexicographic order == chronological order as long
    as the lab's UTC offset is fixed (no DST in the lab's timezone).
    """
    return datetime.now(timezone.utc).astimezone().isoformat()


@dataclass(frozen=True)
class ChangeRecord:
    """One recorded change to the SCQO config (provenance for the AI loop's memory)."""

    timestamp: str
    qubit: str
    field: str
    old: float | None
    new: float
    experiment: str | None = None
    #: run_id of the datastore run that caused this change (links history <-> run folder).
    run_id: str | None = None
    #: OS login of whoever made the change (None only when undeterminable).
    operator: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _tracked_property(field: str, spec: FieldSpec) -> property:
    """A read/write property routing one device field through the RecordingDevice.

    Pushed fields keep strict reads and vendor-coupled writes; record-only fields
    read as None until first measured and never touch the vendor.
    """
    if spec.push:

        def getter(self: "_RecordingQubitView") -> float:
            return self._parent._get(self.name, field)

        def setter(self: "_RecordingQubitView", value: float) -> None:
            self._parent._set(self.name, field, value)

    else:

        def getter(self: "_RecordingQubitView") -> float | None:  # type: ignore[misc]
            return self._parent._get_recorded(self.name, field)

        def setter(self: "_RecordingQubitView", value: float) -> None:
            self._parent._record(self.name, field, value)

    return property(getter, setter, doc=f"{spec.doc} [{spec.unit}]" if spec.unit else spec.doc)


class _RecordingQubitView(QubitView):
    """QubitView that reads/writes the parent :class:`RecordingDevice`'s SCQO config.

    One read/write property per :data:`FIELDS` entry is generated in the class body.
    Adding a PUSHED field still needs each backend's own QubitView and the ABC;
    adding a RECORD-ONLY field needs only its :data:`FIELDS` entry.
    """

    def __init__(self, parent: "RecordingDevice", name: str) -> None:
        self.name = name
        self._parent = parent

    # Generate one property per FIELDS entry. Assigning into the class namespace
    # (vars()) makes them real properties; the pushed subset satisfies the QubitView
    # ABC's abstract members, the record-only ones are additive.
    for _field, _spec in FIELDS.items():
        vars()[_field] = _tracked_property(_field, _spec)
    del _field, _spec


class RecordingDevice(DeviceModel):
    """Authoritative SCQO config + change history over a backend's vendor device.

    Reads serve the SCQO config; writes record + update the config + push to the vendor.
    """

    def __init__(
        self,
        inner: DeviceModel,
        *,
        state_path: str | None = None,
        on_load: Literal["push", "pull"] = "pull",
    ) -> None:
        self._inner = inner
        self._state_path = state_path
        self._config: dict[str, dict[str, float | None]] = {}
        self._history: list[ChangeRecord] = []
        self._experiment: str | None = None  # set by the Session around a run
        self._run_id: str | None = None

        if state_path is not None and os.path.exists(state_path):
            saved = self._load_state(state_path)
            if on_load == "push":
                # SCQO fully owns this device: load the saved config and push it to the
                # vendor so the instrument matches SCQO for the pushed fields.
                self._config = saved
                self._push_config()
            else:
                # "pull" (safe default while another tool may also write the vendor
                # config, e.g. unmigrated qualibrate nodes on QM): the vendor wins at
                # startup for the pushed fields, the saved history is kept so
                # provenance is continuous — and saved RECORD-ONLY values (measured
                # physics) are merged back in: the vendor knows nothing about them,
                # so without the merge every session start would erase them.
                self._config = _merge_pull_seed(inner.snapshot(), saved)
        else:
            self._config = inner.snapshot()  # first time: seed (pull) from the vendor

    # ---------------------------------------------------------------- DeviceModel
    def qubit(self, name: str) -> _RecordingQubitView:
        return _RecordingQubitView(self, name)

    def snapshot(self) -> dict:
        """The authoritative SCQO config (deep-copied)."""
        return {q: dict(fields) for q, fields in self._config.items()}

    def save(self) -> None:
        """Persist the vendor config (push) and the SCQO config + history (own format)."""
        self._inner.save()
        if self._state_path is not None:
            self._persist(self._state_path)

    # ---------------------------------------------------------------- SCQO-native
    def history(self) -> list[ChangeRecord]:
        """The recorded change history (the loop's memory)."""
        return list(self._history)

    def set_context(self, experiment: str | None, run_id: str | None = None) -> None:
        """Tag subsequent changes with the experiment (and datastore run) causing them."""
        self._experiment = experiment
        self._run_id = run_id

    def _get(self, qubit: str, field: str) -> float:
        return self._config[qubit][field]  # type: ignore[return-value]

    def _get_recorded(self, qubit: str, field: str) -> float | None:
        """Record-only fields read as None until first measured (pushed stay strict)."""
        return self._config.get(qubit, {}).get(field)

    def _record(self, qubit: str, field: str, value: float) -> None:
        """Record a measured value: history + SCQO config, NO vendor push."""
        value = float(value)
        if not math.isfinite(value):  # the state JSON must stay strictly parseable
            raise ValueError(f"refusing to record non-finite {field}={value!r} for {qubit}")
        old = self._config.get(qubit, {}).get(field)
        self._history.append(
            ChangeRecord(
                timestamp=_now(), qubit=qubit, field=field, old=old, new=value,
                experiment=self._experiment, run_id=self._run_id,
                # Stamped here (not via set_context) so manual writes outside a run —
                # a notebook tweaking pi_amp — are attributed too.
                operator=_current_operator() or None,
            )
        )
        self._config.setdefault(qubit, {})[field] = value          # SCQO config (authoritative)

    def _set(self, qubit: str, field: str, value: float) -> None:
        value = float(value)
        if not math.isfinite(value):  # never hand the instrument a NaN/Inf
            raise ValueError(f"refusing to push non-finite {field}={value!r} for {qubit}")
        # Push to the vendor FIRST: if the instrument rejects the value (e.g. an
        # out-of-range amplitude), neither the SCQO config nor the history may claim
        # a change that never reached the hardware.
        setattr(self._inner.qubit(qubit), field, value)
        self._record(qubit, field, value)

    # ---------------------------------------------------------------- persistence
    def _persist(self, path: str) -> None:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)  # a config'd path must not fail on first save
        data = {"config": self._config, "history": [r.as_dict() for r in self._history]}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _load_state(self, path: str) -> dict:
        """Load a saved state file: installs the history, returns the saved config."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self._history = [ChangeRecord(**r) for r in data.get("history", [])]
        return data.get("config", {})

    def _push_config(self) -> None:
        """Push the PUSHED fields of the SCQO config into the vendor device (SCQO is
        authoritative in push mode). Record-only fields have no vendor knob and are
        never pushed; wiring/hardware is left untouched."""
        for qubit, fields in self._config.items():
            for field, value in fields.items():
                if value is not None and field in PUSHED_FIELDS:
                    setattr(self._inner.qubit(qubit), field, value)


def _merge_pull_seed(vendor: dict, saved: dict) -> dict:
    """Pull-mode startup seed. The vendor snapshot is authoritative for the qubit set
    and every PUSHED field; saved values of non-pushed fields (record-only measured
    physics) are retained for qubits the vendor still reports. Qubits only in the
    saved config are dropped (their history rows remain untouched)."""
    merged = {qubit: dict(fields) for qubit, fields in vendor.items()}
    for qubit, fields in saved.items():
        if qubit not in merged:
            continue
        for field, value in fields.items():
            if field not in PUSHED_FIELDS:
                merged[qubit][field] = value
    return merged
