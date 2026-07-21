from __future__ import annotations

from typing import ClassVar, Dict, Any, List

import numpy as np
import xarray as xr
from pydantic import Field

from ..contract import DatasetContract
from ..experiment import Experiment
from ..result import Outcome, Result
from ..parameters import AveragingParameters, TargetSelection
from ._sim import stable_seed


class QubitRelaxationFluxParameters(TargetSelection, AveragingParameters):
    """Parameters for T1 vs flux spectroscopy."""

    min_wait_ns: float = Field(16.0, ge=0.0, description="Minimum idle delay.")
    max_wait_ns: float = Field(40000.0, gt=0.0, description="Maximum idle delay.")
    num_wait_points: int = Field(51, gt=1, description="Number of wait time points.")
    min_flux_amp_in_v: float = Field(-0.08, description="Minimum flux pulse amplitude.")
    max_flux_amp_in_v: float = Field(0.08, description="Maximum flux pulse amplitude.")
    num_flux_points: int = Field(21, gt=1, description="Number of flux bias points.")
    prepare_state: int = Field(1, description="State to prepare (0 for g, 1 for e).")
    use_state_discrimination: bool = Field(False, description="Use state classification.")


class QubitRelaxationFluxResult(Result):
    """Fitted T1 spectrum results."""


class QubitRelaxationFlux(Experiment):
    """Measure qubit relaxation time T1 vs Z flux pulse amplitude."""

    name: ClassVar[str] = "qubit_relaxation_flux"
    description: ClassVar[str] = (
        "Sweep a Z pulse amplitude and wait delay after excitation, "
        "fitting T1 decay at each flux point to map out the T1 spectrum."
    )
    Parameters: ClassVar[type] = QubitRelaxationFluxParameters
    Result: ClassVar[type] = QubitRelaxationFluxResult
    Contract: ClassVar[DatasetContract] = DatasetContract(
        sweeps=("flux_amp", "wait_time_ns"),
        sweep_units=("V", "ns"),
        variables=("I", "Q"),
    )

    params: QubitRelaxationFluxParameters

    required_operations: ClassVar[tuple[str, ...]] = ("rx", "readout", "flux_bias")

    def define_sweep(self) -> dict[str, np.ndarray]:
        flux_amp = np.linspace(
            self.params.min_flux_amp_in_v,
            self.params.max_flux_amp_in_v,
            self.params.num_flux_points,
        )
        wait_time = np.linspace(
            self.params.min_wait_ns,
            self.params.max_wait_ns,
            self.params.num_wait_points,
        )
        return {
            "flux_amp": flux_amp,
            "wait_time_ns": wait_time,
        }

    def simulate(self, coords: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        """Generate synthetic decay curves with a simulated TLS (Two-Level System) defect dip."""
        flux = coords["flux_amp"]
        wait = coords["wait_time_ns"]
        qubits = self.params.targets

        n_qubits = len(qubits)
        n_flux = len(flux)
        n_wait = len(wait)

        i_data = np.zeros((n_qubits, n_flux, n_wait))
        q_data = np.zeros((n_qubits, n_flux, n_wait))

        rng = np.random.default_rng(stable_seed("qubit_relaxation_flux", *qubits))
        for k in range(n_qubits):
            for f_idx, f_amp in enumerate(flux):
                # Qubit relaxation T1: Sweet spot is at f_amp=0 (T1 ~ 25 us)
                # Away from zero, T1 decays.
                # Introduce a TLS defect dip at f_amp = 0.03 V (where T1 drops sharply)
                t1_baseline = 25e-6 * (1.0 - 0.4 * (f_amp ** 2))
                tls_dip = 15e-6 * np.exp(-((f_amp - 0.03) / 0.008) ** 2)
                t1 = max(t1_baseline - tls_dip, 1e-6) # prevent non-positive T1

                # If prepare_state is 0, signal is ground state (stays near 1.0)
                # If prepare_state is 1, signal starts at 1.0 (excited state) and decays to 0.0
                if self.params.prepare_state == 1:
                    decay = np.exp(-(wait * 1e-9) / t1)
                else:
                    decay = np.ones_like(wait)

                noise = 0.02
                i_data[k, f_idx] = decay + rng.normal(0, noise, n_wait)
                q_data[k, f_idx] = rng.normal(0, noise, n_wait)

        return {"I": i_data, "Q": q_data}

    def estimate(self) -> QubitRelaxationFluxResult:
        assert self.dataset is not None, "run() populates self.dataset before estimate()"
        from scqat.estimators.qubit_relaxation_flux import QubitRelaxationFluxEstimator
        from .._scqat import per_qubit_results

        # Rename to scqat expected contract: variable signal + coords flux_amp & wait_time (seconds)
        prepared = self.dataset.rename({"I": "signal", "wait_time_ns": "wait_time"})
        prepared = prepared.assign_coords(wait_time=prepared["wait_time"] * 1e-9)

        results = per_qubit_results(
            prepared, QubitRelaxationFluxEstimator(), artifact_dir=self.artifact_dir
        )

        result = QubitRelaxationFluxResult()
        for qubit in self.params.targets:
            r = results[qubit]
            result.fit[qubit] = {
                "flux_amp": [float(x) for x in r["flux_amp"]],
                "t1": [float(x) for x in r["t1"]],
                "t1_stderr": [float(x) for x in r["t1_stderr"]],
                "amplitude": [float(x) for x in r["amplitude"]],
                "offset": [float(x) for x in r["offset"]],
            }
            result.outcomes[qubit] = Outcome.SUCCESSFUL if r.get("success", False) else Outcome.FAILED
        return result
