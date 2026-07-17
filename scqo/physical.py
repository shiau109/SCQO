"""Instrument-independent physical parameters of the SAMPLE — the measured-physics ledger.

The instrument config (:mod:`scqo.config`) answers "how do I drive this qubit *on this
setup*"; this store answers "what IS this qubit" — coherence times, transmon arch
parameters, dispersive-fit quantities. Every value is a measurement of the sample
**through a setup, in a cooldown** (a noisy drive line shortens the measured T2
through no fault of the sample; ``dv_phi0_v`` is volts at the DAC, wiring-dependent),
so the store is PER (cooldown, setup) — one context, flat values, with the change
history in an append-only sidecar (:mod:`scqo._state_io`)::

    <data_root>/<device>/<cooldown>/<setup>/scqo/physical.json
        {"values": {"q0": {"t1_s": 2.5e-05}}}
    <data_root>/<device>/<cooldown>/<setup>/scqo/physical.history.jsonl
        one ChangeRecord JSON object per line   # rows also carry setup=

A setup's estimate never overwrites another's — they are different files. Compare
across setups/cooldowns by querying the run index (every run stamps cooldown + setup)
or the trends page. The setup-INDEPENDENT sample truth is Phase-3 *inference* over
these measurements (``sample.json``, a separate future per-sample output).

Values are written through the same suggest -> review -> accept flow as calibration
knobs (see :mod:`scqo.suggestions`): an experiment's ``update()`` *proposes*, a human
(or an explicitly auto-applying caller) accepts, and every accepted value lands here
with full provenance (experiment / run_id / operator / setup ChangeRecords, exactly
like the instrument-config history). Nothing in this module ever touches a vendor
object. ``save()`` merges under a lock file rather than blindly rewriting — two
same-context sessions cannot erase each other's rows.

Instrument-DEPENDENT measured values (readout_fidelity, thermal population) do NOT
belong here — they stay in the instrument state / run records with ``backend``
provenance, compared across instruments by query.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

from . import config as _config
from ._state_io import _file_lock, read_history, write_history
from .config import FIELDS, ChangeRecord, FieldSpec, _now

#: File name inside a context's ``.../<cooldown>/<setup>/scqo/`` folder (per context).
#: The change history lives beside it in ``physical.history.jsonl``
#: (:mod:`scqo._state_io`).
PHYSICAL_FILE = "physical.json"

#: The physical (sample-owned, instrument-independent) fields SCQO tracks.
#: Adding one requires an entry here and nothing else — no ABC, no driver code.
#: ``push`` is always False: there is no vendor knob for sample physics.
PHYSICAL_FIELDS: dict[str, FieldSpec] = {
    "t1_s": FieldSpec("s", "Energy-relaxation time T1.", push=False),
    "t2_star_s": FieldSpec("s", "Ramsey dephasing time T2*.", push=False),
    "t2_echo_s": FieldSpec("s", "Hahn-echo coherence time T2_echo.", push=False),
    "sweet_spot_flux_v": FieldSpec("V", "Flux bias of the qubit's sweet spot on its own flux line.", push=False),
    "dv_phi0_v": FieldSpec("V", "Flux period: volts per flux quantum on the qubit's flux line.", push=False),
    "ej_sum_ghz": FieldSpec("GHz", "Total Josephson energy EJ1+EJ2 (transmon arch fit).", push=False),
    "f_q_max_hz": FieldSpec("Hz", "Qubit 0-1 frequency at the sweet spot (arch top).", push=False),
    "f_r0_hz": FieldSpec("Hz", "Bare resonator frequency (dispersive fit).", push=False),
    "g_hz": FieldSpec("Hz", "Qubit-resonator coupling (dispersive fit).", push=False),
    "f_r_hz": FieldSpec("Hz", "Dressed resonator frequency: the spectroscopy dip position.", push=False),
    "kappa_hz": FieldSpec("Hz", "Resonator linewidth kappa (power-Lorentzian FWHM): the photon decay rate.", push=False),
}

# A field name must resolve to exactly ONE store (suggestion routing + the shared
# QubitView surface in scqo.suggestions depend on it).
_overlap = set(PHYSICAL_FIELDS) & set(FIELDS)
assert not _overlap, f"PHYSICAL_FIELDS must not overlap config.FIELDS: {sorted(_overlap)}"
del _overlap


def _clean_values(raw: dict) -> dict[str, dict[str, float]]:
    """Sanitize a file's ``values`` block to ``{qubit: {field: float}}`` — keep only
    numeric leaves (a stray dict from an older nested layout is dropped; fresh start,
    no migration — history rows are never rewritten)."""
    return {
        qubit: {field: v for field, v in fields.items() if isinstance(v, (int, float))}
        for qubit, fields in raw.items() if isinstance(fields, dict)
    }


class PhysicalStore:
    """One (cooldown, setup) context's measured physics + change history.

    The store's file (``<device>/<cooldown>/<setup>/scqo/physical.json``, or
    ``path=None`` for in-memory) holds a single context, so values are flat
    ``{qubit: {field: value}}``. Mirrors the RecordingDevice contract — finite-value
    guard, ChangeRecord provenance, ``None`` until first measured — minus everything
    vendor-related. ``setup`` is stamped onto each ChangeRecord (self-describing rows
    for a future ``sample.json`` roll-up); the context is otherwise implied by the
    file's path.
    """

    def __init__(self, path: str | Path | None = None, *, setup: str | None = None) -> None:
        self._path = Path(path) if path is not None else None
        self._setup = setup or ""
        self._values: dict[str, dict[str, float]] = {}
        self._history: list[ChangeRecord] = []
        #: merge-on-save baseline: rows [:_saved] were loaded/merged from the file,
        #: rows [_saved:] are ours and not yet persisted.
        self._saved = 0
        #: (qubit, field) pairs we wrote since the last load/save — the only value
        #: keys `save()` may overwrite (a co-running same-context writer keeps its own).
        self._dirty: set[tuple[str, str]] = set()
        if self._path is not None:
            if self._path.is_file():
                data = json.loads(self._path.read_text(encoding="utf-8"))
                self._values = _clean_values(data.get("values", {}))
            # sidecar first; pre-split files with an embedded "history" load too
            self._history = [ChangeRecord(**r) for r in read_history(self._path)]
            self._saved = len(self._history)

    def get(self, qubit: str, field: str) -> float | None:
        """The current value (None until first measured in this context)."""
        return self._values.get(qubit, {}).get(field)

    def record(
        self,
        qubit: str,
        field: str,
        value: float,
        *,
        experiment: str | None = None,
        run_id: str | None = None,
    ) -> None:
        """Record a measured physical value: history + values, never any vendor."""
        if field not in PHYSICAL_FIELDS:  # a typo must not silently become ledger truth
            raise ValueError(
                f"unknown physical field {field!r} for {qubit} — known: {', '.join(PHYSICAL_FIELDS)}"
            )
        value = float(value)
        if not math.isfinite(value):  # the JSON must stay strictly parseable
            raise ValueError(f"refusing to record non-finite {field}={value!r} for {qubit}")
        self._history.append(
            ChangeRecord(
                timestamp=_now(), qubit=qubit, field=field,
                old=self.get(qubit, field), new=value,
                experiment=experiment, run_id=run_id,
                # via the module (not a name import) so tests/tools can monkeypatch
                # scqo.config._current_operator once for every stamping site
                operator=_config._current_operator() or None,
                setup=self._setup or None,
            )
        )
        self._values.setdefault(qubit, {})[field] = value
        self._dirty.add((qubit, field))

    def snapshot(self) -> dict:
        """This context's values, flat ``{qubit: {field: value}}`` (deep-copied) —
        the shape staleness guards and ``Session.physical_state()`` reason about."""
        return {q: dict(fields) for q, fields in self._values.items()}

    def history(self) -> list[ChangeRecord]:
        """Every recorded change in this context (rows also carry ``setup=``)."""
        return list(self._history)

    def save(self) -> None:
        """Merge-persist under a lock (no-op in-memory).

        The files are one (cooldown, setup) context, but two same-context sessions
        (two terminals) could still race, so a blind rewrite could erase rows the
        other appended. Under the lock the on-disk state is re-read; its history
        plus OUR unsaved rows are unioned (ordered by timestamp — ISO strings with
        the lab's fixed UTC offset sort chronologically, the
        :func:`scqo.config._now` guarantee) and only the value keys WE wrote
        overwrite the file's.

        Two writes, history sidecar FIRST: a failed sidecar write commits nothing
        (our rows stay pending for the next save() to retry — never a silently
        dropped accept). Once the sidecar lands the merge is committed to memory,
        so a failure of the values write cannot re-append the rows on retry; the
        values then briefly lag the durable history and the next save() recomputes
        them from it (self-healing — provenance's strict-match rule reports the
        lag as "external" at worst, never a false credit).
        """
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with _file_lock(self._path):
            file_values: dict = {}
            if self._path.is_file():
                data = json.loads(self._path.read_text(encoding="utf-8"))
                file_values = _clean_values(data.get("values", {}))
            file_history = [ChangeRecord(**r) for r in read_history(self._path)]
            ours = self._history[self._saved:]
            merged = sorted(file_history + ours, key=lambda r: r.timestamp)  # stable
            # Write 1 — the history sidecar (also splits a pre-split file's
            # embedded history out; the values rewrite below drops the old key).
            write_history(self._path, [r.as_dict() for r in merged])
            self._history = merged
            self._saved = len(merged)
            # For each key WE wrote, the persisted value is the LATEST-timestamp
            # record for it across the merged history — not blindly our own. So if a
            # concurrent same-context session recorded a newer value for the same
            # (qubit, field), that newer value wins and the persisted value always
            # matches its crediting record (no "external"/older-save-wins). Every
            # dirty key has a record in `ours`, so it is present in `merged`.
            latest: dict[tuple[str, str], float] = {}
            for r in merged:  # ascending timestamp -> last write per key wins
                latest[(r.qubit, r.field)] = r.new
            for qubit, field in self._dirty:
                file_values.setdefault(qubit, {})[field] = latest[(qubit, field)]
            # Write 2 — the values file, values-only.
            payload = {"values": file_values}
            tmp = self._path.with_suffix(f"{self._path.suffix}.{os.getpid()}.tmp")
            try:
                tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                os.replace(tmp, self._path)
            except OSError:
                tmp.unlink(missing_ok=True)  # no orphan temp; values self-heal next save
                raise
            self._values = file_values
            self._dirty.clear()
