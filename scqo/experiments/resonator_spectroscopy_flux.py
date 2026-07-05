"""Resonator spectroscopy vs flux — the dispersive flux map (backend-free half).

2D map: sweep the flux bias x readout detuning, track the resonator dip at every
flux and fit the full dispersive model f_r(flux) = f_r0 + g^2 / (f_r0 - f_q(flux))
(transmon arch f_q). Reports the flux sweet spot, flux period (dv_phi0), the bare
resonator f_r0 and the coupling g — the resonator-side flux picture that pairs
with qubit_spectroscopy_flux for Phase-3 inference. ``update()`` is a no-op:
flux offsets are not tracked fields yet, and readout_freq updates remain
resonator_spectroscopy's job at the chosen operating flux.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np
from pydantic import Field

from .._scqat import per_qubit_results
from ._sim import stable_seed
from ..contract import DatasetContract
from ..experiment import Experiment
from ..parameters import AveragingParameters, QubitSelection
from ..result import Outcome, Result


class ResonatorSpectroscopyFluxParameters(QubitSelection, AveragingParameters):
    """Inputs for the resonator-vs-flux map."""

    frequency_span_hz: float = Field(20e6, gt=0, description="Total readout-detuning span around the current readout_freq.")
    num_freq_points: int = Field(101, gt=1, description="Number of frequency points.")
    min_flux_v: float = Field(-0.3, ge=-0.5, description="Lowest flux bias (V) on the qubit's own flux line.")
    max_flux_v: float = Field(0.3, le=0.5, description="Highest flux bias (V).")
    num_flux_points: int = Field(21, gt=4, description="Number of flux points (the dispersive fit needs >= 5 good slices).")
    f_q_max_hz: float | None = Field(
        None, description="Qubit sweet-spot frequency (Hz) to hold fixed in the dispersive fit; None = estimator heuristic."
    )


class ResonatorSpectroscopyFluxResult(Result):
    """``fit[qubit]``: ``sweet_spot_flux_v``, ``sweet_spot_freq_hz``, ``dv_phi0_v``,
    ``f_r0_hz``, ``g_hz``. No writeback."""


class ResonatorSpectroscopyFlux(Experiment):
    """Backend-agnostic resonator flux map. ``probe()`` is supplied by a driver."""

    name: ClassVar[str] = "resonator_spectroscopy_flux"
    description: ClassVar[str] = (
        "2D resonator spectroscopy vs flux bias: tracks the dip at every flux and fits "
        "the dispersive model; reports flux sweet spot, flux period, bare f_r0 and "
        "coupling g (no device writeback)."
    )
    Parameters: ClassVar[type] = ResonatorSpectroscopyFluxParameters
    Result: ClassVar[type] = ResonatorSpectroscopyFluxResult
    Contract: ClassVar[DatasetContract] = DatasetContract(
        sweeps=("flux_bias_v", "detuning_hz"), sweep_units=("V", "Hz"), variables=("I", "Q")
    )

    params: ResonatorSpectroscopyFluxParameters

    def define_sweep(self) -> dict[str, np.ndarray]:
        span = self.params.frequency_span_hz
        return {
            "flux_bias_v": np.linspace(self.params.min_flux_v, self.params.max_flux_v, self.params.num_flux_points),
            "detuning_hz": np.linspace(-span / 2, span / 2, self.params.num_freq_points),
        }

    def simulate(self, coords: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        flux = coords["flux_bias_v"]
        detuning = coords["detuning_hz"]
        qubits = self.params.qubits
        rng = np.random.default_rng(stable_seed("resonator_spectroscopy_flux", *qubits))
        kappa = (detuning[-1] - detuning[0]) / 40
        ec = 0.2  # GHz
        i_data = np.empty((len(qubits), flux.size, detuning.size))
        q_data = np.empty_like(i_data)
        for k, q in enumerate(qubits):
            # centers generated FROM the dispersive model the estimator fits
            readout_now = float(self.device.qubit(q).readout_freq)
            f_q_max = float(self.device.qubit(q).drive_freq)
            sweet = rng.uniform(0.3 * flux.min(), 0.3 * flux.max())
            period = rng.uniform(1.8, 2.6) * (flux.max() - flux.min())
            g = rng.uniform(70e6, 100e6)
            f_r0 = readout_now - 2e6  # bare resonator (dressed sits above for f_q < f_r0)
            ej_sum = ((f_q_max * 1e-9 + ec) ** 2) / (8.0 * ec)
            quan = (flux - sweet) / period
            f_q = (np.sqrt(8.0 * ec * ej_sum * np.abs(np.cos(np.pi * quan))) - ec) * 1e9
            centers = (f_r0 + g**2 / (f_r0 - f_q)) - readout_now  # as detuning
            noise = 0.01
            for j in range(flux.size):
                magnitude = 1.0 - 0.75 / (1.0 + ((detuning - centers[j]) / kappa) ** 2)
                i_data[k, j] = magnitude + rng.normal(0, noise, detuning.size)
                q_data[k, j] = rng.normal(0, noise, detuning.size)
        return {"I": i_data, "Q": q_data}

    def estimate(self) -> ResonatorSpectroscopyFluxResult:
        assert self.dataset is not None, "run() populates self.dataset before estimate()"
        from scqat.estimators.resonator_spectroscopy_flux import ResonatorSpectroscopyFluxEstimator

        qubits = list(self.dataset["qubit"].values)
        old_freqs = {q: float(self.device.qubit(q).readout_freq) for q in qubits}
        prepared = self.dataset.rename({"flux_bias_v": "flux_bias", "detuning_hz": "detuning"})
        prepared = prepared.transpose("qubit", "flux_bias", "detuning")
        detuning = prepared["detuning"].values
        full_freq = np.array([detuning + old_freqs[q] for q in qubits])
        prepared = prepared.assign_coords(full_freq=(("qubit", "detuning"), full_freq))

        kwargs = {}
        if self.params.f_q_max_hz is not None:
            kwargs["f_q_max"] = float(self.params.f_q_max_hz)
        results = per_qubit_results(
            prepared, ResonatorSpectroscopyFluxEstimator(), artifact_dir=self.artifact_dir, **kwargs
        )

        result = ResonatorSpectroscopyFluxResult()
        for qubit in self.params.qubits:
            disp = results[qubit]["dispersion"]
            vs = results[qubit]["vs_flux"]
            result.fit[qubit] = {
                "sweet_spot_flux_v": float(disp["sweet_spot_flux"]),
                "sweet_spot_freq_hz": float(disp["sweet_spot_freq"]),
                "dv_phi0_v": float(disp["dv_phi0"]),
                "f_r0_hz": float(disp["f_r0"]),
                "g_hz": float(disp["g"]),
                "f_q_max_hz": float(disp["f_q_max"]),
                "n_good_flux": int(vs["n_good"]),
                "old_readout_freq": old_freqs[qubit],
            }
            result.outcomes[qubit] = Outcome.SUCCESSFUL if bool(disp["success"]) else Outcome.FAILED
        return result

    def update(self) -> None:
        # Sweet spot / f_r0 / g are reported, not written back (flux offset is not a
        # tracked field yet; readout_freq stays resonator_spectroscopy's job).
        return
