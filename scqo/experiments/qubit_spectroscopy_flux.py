"""Qubit spectroscopy vs flux — the f01(flux) arch (backend-free half).

2D map: sweep the flux bias on the qubit's own line x the drive detuning around
the current ``drive_freq``, find the 0-1 peak at every flux and fit the transmon
arch ``f = sqrt(8*Ec*Ej_eff) - Ec``. Reports the sweet spot, flux period and
``Ej_sum`` — the f01(flux) inputs that Phase-3 device-level EJ/EC inference
consumes. ``update()`` is a no-op for now: a flux offset is not yet a tracked
device field (that is the Phase-3 schema-widening step), so the arch parameters
live in the run index (``fit_trend`` on ``ej_sum_ghz`` / ``sweet_spot_flux_v``).

Flux safety: the flux axis is in volts on the qubit's flux line, bounded to
|V| <= 0.5 by the parameter schema; probes must return the line to its idle
value after the sweep.
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


class QubitSpectroscopyFluxParameters(QubitSelection, AveragingParameters):
    """Inputs for the qubit-frequency-vs-flux map."""

    frequency_span_hz: float = Field(400e6, gt=0, description="Total drive-detuning span around the current drive_freq.")
    num_freq_points: int = Field(101, gt=1, description="Number of frequency points.")
    min_flux_v: float = Field(-0.3, ge=-0.5, description="Lowest flux bias (V) on the qubit's own flux line.")
    max_flux_v: float = Field(0.3, le=0.5, description="Highest flux bias (V).")
    num_flux_points: int = Field(21, gt=4, description="Number of flux points (the arch fit needs >= 5 good slices).")
    ec_ghz: float = Field(0.2, gt=0, description="Charging energy (GHz) held fixed in the arch model.")


class QubitSpectroscopyFluxResult(Result):
    """``fit[qubit]``: ``sweet_spot_flux_v``, ``f01_at_sweet_spot_hz``, ``flux_period_v``,
    ``ej_sum_ghz`` (+ stderrs). No writeback yet (Phase-3 schema)."""


class QubitSpectroscopyFlux(Experiment):
    """Backend-agnostic f01(flux) arch. ``probe()`` is supplied by a driver."""

    name: ClassVar[str] = "qubit_spectroscopy_flux"
    description: ClassVar[str] = (
        "2D qubit spectroscopy vs flux bias: finds the 0-1 peak at every flux and fits "
        "the transmon arch; reports sweet spot, flux period and Ej_sum (the Phase-3 "
        "EJ/EC inference inputs — no device writeback yet)."
    )
    Parameters: ClassVar[type] = QubitSpectroscopyFluxParameters
    Result: ClassVar[type] = QubitSpectroscopyFluxResult
    Contract: ClassVar[DatasetContract] = DatasetContract(
        sweeps=("flux_bias_v", "detuning_hz"), sweep_units=("V", "Hz"), variables=("I", "Q")
    )

    params: QubitSpectroscopyFluxParameters

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
        rng = np.random.default_rng(stable_seed("qubit_spectroscopy_flux", *qubits))
        ec = self.params.ec_ghz
        i_data = np.empty((len(qubits), flux.size, detuning.size))
        q_data = np.empty_like(i_data)
        for k, q in enumerate(qubits):
            # hidden arch: sweet spot inside the swept window, top of the arch at
            # the current drive_freq (detuning 0) so the peak stays in-window
            f01_now = float(self.device.qubit(q).drive_freq)
            sweet = rng.uniform(0.3 * flux.min(), 0.3 * flux.max())
            period = rng.uniform(1.5, 2.5) * (flux.max() - flux.min())
            ej_sum = ((f01_now * 1e-9 + ec) ** 2) / (8.0 * ec)  # arch top == f01_now
            quan = (flux - sweet) / period
            f01_ghz = np.sqrt(8.0 * ec * ej_sum * np.abs(np.cos(np.pi * quan))) - ec
            centers = f01_ghz * 1e9 - f01_now  # as detuning
            fwhm = (detuning[-1] - detuning[0]) / 40
            noise = 0.02
            for j in range(flux.size):
                peak = 1.0 / (1.0 + ((detuning - centers[j]) / (fwhm / 2)) ** 2)
                i_data[k, j] = peak + rng.normal(0, noise, detuning.size)
                q_data[k, j] = rng.normal(0, noise, detuning.size)
        return {"I": i_data, "Q": q_data}

    def estimate(self) -> QubitSpectroscopyFluxResult:
        assert self.dataset is not None, "run() populates self.dataset before estimate()"
        from scqat.estimators.qubit_flux_arch import QubitFluxArchEstimator

        # scqat's contract: coords `flux_bias` + `detuning` + absolute `full_freq`
        # (the arch model is absolute-scale), vars I/Q; dims (flux_bias, detuning).
        qubits = list(self.dataset["qubit"].values)
        old_freqs = {q: float(self.device.qubit(q).drive_freq) for q in qubits}
        prepared = self.dataset.rename({"flux_bias_v": "flux_bias", "detuning_hz": "detuning"})
        prepared = prepared.transpose("qubit", "flux_bias", "detuning")
        detuning = prepared["detuning"].values
        full_freq = np.array([detuning + old_freqs[q] for q in qubits])
        prepared = prepared.assign_coords(full_freq=(("qubit", "detuning"), full_freq))

        results = per_qubit_results(
            prepared,
            QubitFluxArchEstimator(),
            artifact_dir=self.artifact_dir,
            ec_ghz=self.params.ec_ghz,
        )

        result = QubitSpectroscopyFluxResult()
        for qubit in self.params.qubits:
            arch = results[qubit]["arch"]
            fit: dict[str, float] = {"ec_ghz_assumed": float(arch["ec_ghz"])}
            for src, dst in (
                ("sweet_spot_flux", "sweet_spot_flux_v"),
                ("flux_period", "flux_period_v"),
                ("ej_sum_ghz", "ej_sum_ghz"),
                ("f01_max_hz", "f01_at_sweet_spot_hz"),
                ("offset_stderr", "sweet_spot_stderr_v"),
                ("ej_sum_stderr_ghz", "ej_sum_stderr_ghz"),
            ):
                if src in arch:
                    fit[dst] = float(arch[src])
            fit["old_drive_freq"] = old_freqs[qubit]
            result.fit[qubit] = fit
            result.outcomes[qubit] = Outcome.SUCCESSFUL if bool(arch["success"]) else Outcome.FAILED
        return result

    def update(self) -> None:
        # Sweet spot / Ej_sum are reported, not written back: flux offset is not a
        # tracked device field yet (Phase-3 schema widening).
        return
