"""Qubit DRAG equator — 3-line symmetric beta calibration, greenfield.

Port of :mod:`scqo.experiments.qubit_drag_equator`. The physics half is
byte-for-byte; what moved is the device surface: ``drag_beta`` keeps its
name but now lives on the target's DRIVE CHANNEL
(``self.device.channel(t, "drive").drag_beta``), written in ``update()``.
"""

from __future__ import annotations

from typing import ClassVar, Literal

import numpy as np
from pydantic import Field, field_validator

from ..contract import DatasetContract
from ._capabilities.qubit_reset import QubitResetParameters, reset_step
from ._diagrams import DRIVE_READOUT
from ._gate_target import drag_knob, is_x90
from ._requires import CALIBRATED_READOUT
from ._sim import stable_seed
from ..parameters import AveragingParameters, TargetSelection
from ..requirements import Requirement
from ..result import Outcome, Result
from ..experiment import Experiment
from ..sequence_diagram import Block, SequenceDiagram
from . import register


class QubitDragEquatorParameters(TargetSelection, AveragingParameters, QubitResetParameters):
    """Inputs for a 3-line symmetric equator DRAG calibration experiment."""

    min_beta: float = Field(-0.5, description="Minimum DRAG beta coefficient.")
    max_beta: float = Field(0.5, description="Maximum DRAG beta coefficient.")
    num_beta_points: int = Field(41, gt=1, description="Number of beta sweep points.")
    pulse_repetitions: int = Field(
        3, gt=0,
        description="Not realized: no probe reads it, and both sequences play ONE pi "
        "pulse (two pi/2 for target_gate='x90') whatever its value (BACKLOG I19). "
        "Must be odd.")
    target_gate: Literal["x180", "x90"] = Field(
        "x180",
        description="Gate to calibrate: 'x180' writes drag_beta, 'x90' writes drag_beta_x90.",
    )


    @field_validator("pulse_repetitions")
    @classmethod
    def check_odd(cls, val: int) -> int:
        if val % 2 == 0:
            raise ValueError("pulse_repetitions must be an odd number (1, 3, 5...) to land on the equator.")
        return val


class QubitDragEquatorResult(Result):
    """Fitted optimal DRAG beta parameters."""


@register
class QubitDragEquator(Experiment):
    """Calibrate DRAG beta parameter using the 3-line symmetric equator method."""

    name: ClassVar[str] = "qubit_drag_equator"
    writes: ClassVar[tuple[str, ...]] = ("drag_beta", "drag_beta_x90")
    #: only the pi pulse's amplitude is neutral here. The closing pi/2 pulse is
    #: in every sequence, and which knob holds its amplitude differs per
    #: backend (BACKLOG I19), so each driver's subclass adds its own.
    requires: ClassVar[tuple[Requirement, ...]] = (
        Requirement("drive_freq_hz",
                    "the pulses have to be on resonance: a detuning tilts the final "
                    "state the same way a wrong DRAG coefficient does"),
        Requirement("pi_amp", "the pi pulse that opens each sequence has to be a full "
                              "rotation", when=("target_gate", "x180")),
        *CALIBRATED_READOUT,
    )
    extracts: ClassVar[dict[str, str]] = {
        "opt_beta": "the coefficient at which the two fitted lines cross; proposed as "
                    "drag_beta, or drag_beta_x90 for target_gate='x90'",
        "beta": "the DRAG coefficients that were swept",
        "seq0": "the signal of sequence 0 (x180 then y90) at each coefficient",
        "seq1": "the signal of sequence 1 (y180 then x90) at each coefficient",
    }
    #: the x90 target plays a different sequence and writes the other knob
    doc_variants: ClassVar[dict[str, dict]] = {"x90": {"target_gate": "x90"}}

    @classmethod
    def sequence_diagram(cls, params: QubitDragEquatorParameters) -> SequenceDiagram:
        # the two sequences differ only in which axis each pulse is about, so
        # one picture shows both: sequence 0 left of the slash, sequence 1 right
        first = "x90 x90 / y90 y90" if is_x90(params.target_gate) else "x180 / y180"
        diagram = SequenceDiagram(dict(DRIVE_READOUT))
        reset_step(diagram, params)
        diagram.step(Block(
            "drive", first, "gate", swept=("seq_idx", "beta"),
            note="left of the slash is sequence 0, right of it sequence 1"))
        diagram.step(Block(
            "drive", "y90 / x90", "gate", swept=("seq_idx", "beta"),
            note="every pulse is played with the swept DRAG coefficient"))
        diagram.step(Block("readout", "readout", "acquire"))
        return diagram

    description: ClassVar[str] = (
        "Sweep the DRAG beta coefficient under two sequences that both end on the "
        "equator: x180 then y90, and y180 then x90 (two x90 / two y90 in place of the "
        "pi pulse for target_gate='x90'). A wrong beta tilts the two final states in "
        "opposite directions, so the two lines cross at the optimal beta, which is "
        "proposed as the drive channel's drag_beta (drag_beta_x90 for "
        "target_gate='x90')."
    )
    Parameters: ClassVar[type] = QubitDragEquatorParameters
    Result: ClassVar[type] = QubitDragEquatorResult
    Contract: ClassVar[DatasetContract] = DatasetContract(
        sweeps=("seq_idx", "beta"),
        sweep_units=("", ""),
        variables=("I", "Q"),
    )

    params: QubitDragEquatorParameters

    required_operations: ClassVar[tuple[str, ...]] = ("rx", "readout")

    def define_sweep(self) -> dict[str, np.ndarray]:
        beta = np.linspace(
            self.params.min_beta,
            self.params.max_beta,
            self.params.num_beta_points,
        )
        return {
            "seq_idx": np.array([0, 1]),
            "beta": beta,
        }

    def simulate(self, coords: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        seq_idx = coords["seq_idx"]
        beta = coords["beta"]
        qubits = self.params.targets

        n_qubits = len(qubits)
        n_seq = len(seq_idx)
        n_beta = len(beta)

        i_data = np.zeros((n_qubits, n_seq, n_beta))
        q_data = np.zeros((n_qubits, n_seq, n_beta))

        rng = np.random.default_rng(stable_seed("qubit_drag_equator", *qubits))
        for k, qubit in enumerate(qubits):
            opt_beta = rng.uniform(-0.5, 0.5)
            noise = 0.015

            # Seq 0: Rx(pi) - Ry(pi/2)
            i_data[k, 0] = 0.5 + 0.3 * np.tanh(beta - opt_beta) + rng.normal(0, noise, n_beta)
            # Seq 1: Ry(pi) - Rx(pi/2)
            i_data[k, 1] = 0.5 - 0.3 * np.tanh(beta - opt_beta) + rng.normal(0, noise, n_beta)

            q_data[k, :] = rng.normal(0, noise, (n_seq, n_beta))

        return {"I": i_data, "Q": q_data}

    def estimate(self) -> QubitDragEquatorResult:
        assert self.dataset is not None
        from scqat.estimators.qubit_drag_equator import QubitDragEquatorEstimator
        from .._scqat import per_qubit_results

        # Map variable I as signal to scqat
        prepared = self.dataset.rename({"I": "signal"})

        results = per_qubit_results(
            prepared, QubitDragEquatorEstimator(), artifact_dir=self.artifact_dir
        )

        result = QubitDragEquatorResult()
        for qubit in self.params.targets:
            r = results[qubit]
            result.fit[qubit] = {
                "opt_beta": float(r["opt_beta"]) if r.get("opt_beta") is not None else None,
                "beta": [float(x) for x in r["beta"]],
                "seq0": [float(x) for x in r["seq0"]],
                "seq1": [float(x) for x in r["seq1"]],
            }
            result.outcomes[qubit] = Outcome.SUCCESSFUL if r.get("success", False) else Outcome.FAILED
        return result

    def update(self) -> None:
        if self.result is None:
            return
        knob = drag_knob(self.params.target_gate)
        for qubit, fit in self.result.fit.items():
            if self.result.outcomes[qubit] is Outcome.SUCCESSFUL and fit.get("opt_beta") is not None:
                setattr(self.device.channel(qubit, "drive"), knob, fit["opt_beta"])








    def probe(self):  # pragma: no cover - driver half
        raise NotImplementedError("a driver backend supplies probe()")
