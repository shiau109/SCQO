"""Experiment — one experiment, split into a shared physics half and a backend half.

* physics half (defined here / in ``scqo.experiments``, shared by every backend):
  ``define_sweep`` -> ``simulate`` (optional) -> ``estimate`` -> ``update``.
* backend half (implemented by a driver subclass, e.g. LCHQBDriver):
  ``probe`` -> turns ``params`` + device state into a native program.

A driver subclass therefore only writes ``probe``; Parameters, Result, the fit in
``estimate`` and the writeback in ``update`` are inherited unchanged. Because the
simulated backend never calls ``probe``, the physics half is fully runnable and
testable with no instrument installed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
import xarray as xr

from .backend import Backend
from .contract import DatasetContract
from .parameters import Parameters
from .result import Result


class Experiment(ABC):
    """Base class for every experiment."""

    #: Stable identifier used in the registry and shown to humans/AI.
    name: ClassVar[str]
    #: One-line description of what the experiment does and what it updates.
    description: ClassVar[str]
    #: pydantic schema for this experiment's inputs.
    Parameters: ClassVar[type[Parameters]]
    #: pydantic schema for this experiment's structured output.
    Result: ClassVar[type[Result]]
    #: canonical dataset every backend's probe must emit (and estimate() consumes).
    Contract: ClassVar[DatasetContract]
    #: instrument category the targets must have (roster-validated pre-probe).
    target_category: ClassVar[str] = "ReadableTransmon"
    #: operations every target must declare in the roster (e.g. ("rx", "readout")).
    required_operations: ClassVar[tuple[str, ...]] = ()
    #: instrument categories a ``flux_component`` Parameter may name (experiments
    #: whose probe can only sweep a qubit z-line narrow this to ReadableTransmon;
    #: irrelevant unless the experiment's Parameters carry ``flux_component``).
    flux_component_categories: ClassVar[tuple[str, ...]] = ("ReadableTransmon", "TransmonPair")
    #: attach the stored |0>/|1> readout blob centers (``readout_pos_*`` monitor
    #: fields, measured by single_shot_readout) to the acquired dataset as
    #: per-target ``ref_pos_*`` variables — the stored reference scqat's IQ->1D
    #: reductions prefer over per-run statistics (radial ref / axial positions).
    #: Set True only by experiments whose estimator consumes them.
    attach_readout_positions: ClassVar[bool] = False

    def __init__(self, backend: Backend, params: Parameters) -> None:
        self.backend = backend
        self.params = params
        #: run tags appended by design-seeded anchors ("seeded:<comp>.<field>");
        #: Session.run merges them into the persisted tags.
        self.seed_tags: list[str] = []
        #: device state experiments read/write. Defaults to the backend's vendor device
        #: (standalone use, unrecorded); the Session swaps in a RecordingDevice so its
        #: runs are recorded into the authoritative SCQO config + history.
        self.device = backend.device
        self.sweep_axes: dict[str, np.ndarray] = {}
        self.dataset: xr.Dataset | None = None
        self.result: Result | None = None
        #: where estimate() writes analysis artifacts (scqat metadata/plotdata/figures).
        #: Set by the Session when a datastore is configured; None keeps analysis
        #: in-memory only (standalone use, tests without persistence).
        self.artifact_dir: Path | None = None

    # ------------------------------------------------------------------ physics
    @abstractmethod
    def define_sweep(self) -> dict[str, np.ndarray]:
        """Return the swept axes as ``{axis_name: 1d array}`` (no backend calls)."""

    @abstractmethod
    def estimate(self) -> Result:
        """Fit ``self.dataset`` and return a structured :class:`Result`."""

    def update(self) -> None:
        """Write fitted quantities back into ``self.device``. Default: no-op."""

    def simulate(self, coords: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        """Return synthetic ``{var: ndarray}`` of shape ``(n_qubits, *sweep)``.

        Optional. Enables the simulated backend, offline tests, and AI dry-runs.
        """
        raise NotImplementedError(f"{type(self).__name__} provides no simulator.")

    # ------------------------------------------------------------------ anchors
    def anchor(self, name: str, field: str) -> float:
        """The sweep anchor for one instrument field: the STANDING value if set,
        else the DESIGN fallback declared by the field's ``design_source``
        (bring-up on a fresh chip: the resonator search window centers on the
        design ``f_r_hz`` before anything is measured). A design-seeded anchor
        tags the run ``"seeded:<component>.<field>"`` — searchable via
        ``scqo find --tag``. Raises when neither exists (a clear bring-up
        instruction beats a sweep around garbage)."""
        view = self.device.component(name)
        try:
            value = getattr(view, field)
        except (KeyError, AttributeError):
            value = None
        if value is not None:
            return float(value)
        spec = None
        roster = getattr(self.device, "roster", None)
        if roster is not None:
            try:
                _side, spec = roster.resolve(name, field)
            except KeyError:
                spec = None
        source = getattr(spec, "design_source", None) if spec else None
        if source is not None:
            src_cat, src_field = source
            src_name = name if src_cat is None else self.device.one(name, src_cat)
            design = self.device.design(src_name, src_field)
            if design is not None:
                tag = f"seeded:{src_name}.{src_field}"
                if tag not in self.seed_tags:
                    self.seed_tags.append(tag)
                return float(design)
        raise ValueError(
            f"{name}.{field} has no standing value and no design fallback — set it "
            f"(scqo set {name}.{field}=...) or declare a design value in components.toml")

    # ------------------------------------------------------------------ backend
    @abstractmethod
    def probe(self) -> Any:
        """Compile ``params`` + device state into a native program (QUA / Schedule)."""

    # ------------------------------------------------------------ orchestration
    #: (dataset variable, device monitor field) pairs of the stored blob centers
    _POSITION_FIELDS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("ref_pos_g_i", "readout_pos_g_i"), ("ref_pos_g_q", "readout_pos_g_q"),
        ("ref_pos_e_i", "readout_pos_e_i"), ("ref_pos_e_q", "readout_pos_e_q"),
    )

    def _attach_reference_positions(self) -> None:
        """Attach the stored readout blob centers to the acquired dataset.

        Copies each target's ``readout_pos_*`` monitor fields onto ``self.dataset``
        as per-target ``ref_pos_*`` variables — an ACQUISITION-TIME snapshot, so
        the persisted ``dataset.nc`` replays offline with the reference that was
        in force at measurement (never read from device state at analysis time).
        Targets without a complete finite set get NaN (scqat falls back to
        median/PCA per target); nothing is attached when no target has one
        (bring-up) or the dataset carries no ``I`` (state mode: pre-reduced).
        """
        assert self.dataset is not None
        if not self.attach_readout_positions or "I" not in self.dataset.data_vars:
            return
        targets = [str(t) for t in self.dataset["target"].values]
        columns = {var: np.full(len(targets), np.nan) for var, _ in self._POSITION_FIELDS}
        for k, name in enumerate(targets):
            view = self.device.component(name)
            vals = {}
            for var, field in self._POSITION_FIELDS:
                try:
                    value = getattr(view, field)
                except (KeyError, AttributeError):
                    value = None
                vals[var] = float(value) if value is not None else float("nan")
            if all(np.isfinite(v) for v in vals.values()):
                for var, _ in self._POSITION_FIELDS:
                    columns[var][k] = vals[var]
        if any(np.isfinite(col).any() for col in columns.values()):
            for var, col in columns.items():
                self.dataset[var] = ("target", col)

    def run(self) -> Result:
        """define_sweep -> acquire -> verify contract -> estimate. Does not auto-update."""
        self.sweep_axes = self.define_sweep()
        self.dataset = self.backend.acquire(self)
        # Certify the probe emitted the method's canonical dataset before analysing it:
        # this is the runtime form of "the instrument supports this method".
        self.Contract.validate(self.dataset)
        self._attach_reference_positions()
        self.result = self.estimate()
        return self.result
