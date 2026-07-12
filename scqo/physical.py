"""Instrument-independent physical parameters of the SAMPLE — the measured-physics ledger.

The instrument config (:mod:`scqo.config`) answers "how do I drive this qubit *on this
setup*"; this store answers "what IS this qubit" — coherence times, transmon arch
parameters, dispersive-fit quantities. These facts belong to the physical sample and
follow it across instruments and cooldowns, so they live in their own per-sample file::

    <data_root>/<device>/physical.json
        {"values":  {"q0": {"t1_s": 2.5e-05, "ej_sum_ghz": 21.3}},
         "history": [ChangeRecord, ...]}

Values are written through the same suggest -> review -> accept flow as calibration
knobs (see :mod:`scqo.suggestions`): an experiment's ``update()`` *proposes*, a human
(or an explicitly auto-applying caller) accepts, and every accepted value lands here
with full provenance (experiment / run_id / operator ChangeRecords, exactly like the
instrument-config history). Nothing in this module ever touches a vendor object.

Instrument-DEPENDENT measured values (readout_fidelity, thermal population) do NOT
belong here — they stay in the instrument state / run records with ``backend``
provenance, compared across instruments by query.

``sample.json`` (Phase-3 *inferred* physics — EJ/EC, anharmonicity from fits-of-fits)
remains a separate future output; this file holds directly *measured* quantities.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

from . import config as _config
from .config import FIELDS, ChangeRecord, FieldSpec, _now

#: File name under ``<data_root>/<device>/`` (a peer of ``scqo_state.json``).
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
}

# A field name must resolve to exactly ONE store (suggestion routing + the shared
# QubitView surface in scqo.suggestions depend on it).
_overlap = set(PHYSICAL_FIELDS) & set(FIELDS)
assert not _overlap, f"PHYSICAL_FIELDS must not overlap config.FIELDS: {sorted(_overlap)}"
del _overlap


class PhysicalStore:
    """Per-sample values + change history for :data:`PHYSICAL_FIELDS`.

    ``path=None`` runs in-memory (a Session without a ``data_root``): values are
    usable within the process but nothing persists. Mirrors the RecordingDevice
    contract — finite-value guard, ChangeRecord provenance, ``None`` until first
    measured — minus everything vendor-related.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path is not None else None
        self._values: dict[str, dict[str, float]] = {}
        self._history: list[ChangeRecord] = []
        if self._path is not None and self._path.is_file():
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._values = data.get("values", {})
            self._history = [ChangeRecord(**r) for r in data.get("history", [])]

    def get(self, qubit: str, field: str) -> float | None:
        """The current value (None until first measured)."""
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
            )
        )
        self._values.setdefault(qubit, {})[field] = value

    def snapshot(self) -> dict:
        """The current physical parameters (deep-copied, JSON-able)."""
        return {q: dict(fields) for q, fields in self._values.items()}

    def history(self) -> list[ChangeRecord]:
        """Every recorded change (the sample's measured-physics provenance)."""
        return list(self._history)

    def save(self) -> None:
        """Persist atomically (no-op in-memory). Safe against concurrent writers
        the same way the datastore is: unique temp file + ``os.replace``."""
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {"values": self._values, "history": [r.as_dict() for r in self._history]}
        tmp = self._path.with_suffix(f"{self._path.suffix}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)
