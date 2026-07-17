from __future__ import annotations

from typing import ClassVar, Dict, Any, List

import numpy as np
import xarray as xr
from pydantic import Field

from scqo.contract import DatasetContract
from scqo.experiment import Experiment
from scqo.result import Outcome, Result
from scqo.parameters import AveragingParameters, QubitSelection
from scqo.experiments._sim import stable_seed


class QubitEchoFluxParameters(QubitSelection, AveragingParameters):
    """Parameters for T2 echo vs flux spectroscopy."""

    min_wait_ns: float = Field(32.0, ge=0.0, description="Minimum idle delay (total tau).")
    max_wait_ns: float = Field(40000.0, gt=0.0, description="Maximum idle delay (total tau).")
    num_wait_points: int = Field(51, gt=1, description="Number of wait time points.")
    min_flux_amp_in_v: float = Field(-0.08, description="Minimum flux pulse amplitude.")
    max_flux_amp_in_v: float = Field(0.08, description="Maximum flux pulse amplitude.")
    num_flux_points: int = Field(21, gt=1, description="Number of flux bias points.")
    use_state_discrimination: bool = Field(False, description="Use state classification.")


class QubitEchoFluxResult(Result):
    """Fitted T2 echo spectrum results."""


class QubitEchoFlux(Experiment):
    """Measure qubit Hahn echo coherence time T2_echo vs Z flux pulse amplitude."""

    name: ClassVar[str] = "qubit_echo_flux"
    description: ClassVar[str] = (
        "Sweep a Z pulse amplitude and total wait delay in a Hahn echo sequence, "
        "fitting T2_echo decay at each flux point to map out the T2_echo spectrum."
    )
    Parameters: ClassVar[type] = QubitEchoFluxParameters
    Result: ClassVar[type] = QubitEchoFluxResult
    Contract: ClassVar[DatasetContract] = DatasetContract(
        sweeps=("flux_amp", "wait_time_ns"),
        sweep_units=("V", "ns"),
        variables=("I", "Q"),
    )

    params: QubitEchoFluxParameters

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
        """Generate synthetic Hahn echo decay curves with a simulated TLS defect dip."""
        flux = coords["flux_amp"]
        wait = coords["wait_time_ns"]
        qubits = self.params.qubits

        n_qubits = len(qubits)
        n_flux = len(flux)
        n_wait = len(wait)

        i_data = np.zeros((n_qubits, n_flux, n_wait))
        q_data = np.zeros((n_qubits, n_flux, n_wait))

        rng = np.random.default_rng(stable_seed("qubit_echo_flux", *qubits))
        for k in range(n_qubits):
            for f_idx, f_amp in enumerate(flux):
                # T2_echo: Sweet spot is at f_amp=0 (T2_echo ~ 50 us)
                # Introduce a TLS defect dip at f_amp = 0.03 V
                t2e_baseline = 50e-6 * (1.0 - 0.4 * (f_amp ** 2))
                tls_dip = 30e-6 * np.exp(-((f_amp - 0.03) / 0.008) ** 2)
                t2e = max(t2e_baseline - tls_dip, 1e-6)

                decay = np.exp(-(wait * 1e-9) / t2e)
                noise = 0.02
                i_data[k, f_idx] = decay + rng.normal(0, noise, n_wait)
                q_data[k, f_idx] = rng.normal(0, noise, n_wait)

        return {"I": i_data, "Q": q_data}

    def estimate(self) -> QubitEchoFluxResult:
        assert self.dataset is not None, "run() populates self.dataset before estimate()"
        from scqat.estimators.qubit_echo_flux import QubitEchoFluxEstimator
        from scqo._scqat import per_qubit_results

        # Rename to scqat expected contract: variable signal + coords flux_amp & wait_time (seconds)
        prepared = self.dataset.rename({"I": "signal", "wait_time_ns": "wait_time"})
        prepared = prepared.assign_coords(wait_time=prepared["wait_time"] * 1e-9)

        results = per_qubit_results(
            prepared, QubitEchoFluxEstimator(), artifact_dir=self.artifact_dir
        )

        result = QubitEchoFluxResult()
        for qubit in self.params.qubits:
            r = results[qubit]
            result.fit[qubit] = {
                "flux_amp": [float(x) for x in r["flux_amp"]],
                "t2_echo": [float(x) for x in r["t2_echo"]],
                "t2_echo_stderr": [float(x) for x in r["t2_echo_stderr"]],
                "amplitude": [float(x) for x in r["amplitude"]],
                "offset": [float(x) for x in r["offset"]],
            }
            result.outcomes[qubit] = Outcome.SUCCESSFUL if r.get("success", False) else Outcome.FAILED
        return result
