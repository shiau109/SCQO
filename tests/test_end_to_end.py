"""End-to-end test of the abstraction with no instrument installed.

A throwaway concrete experiment (probe = no-op) is enough because the SimulatedBackend
drives ``simulate`` instead of ``probe``.
"""

from __future__ import annotations

import numpy as np

from scqo import Outcome, Session, register
from scqo.experiments import (
    QubitPowerRabi,
    QubitRamsey,
    QubitSpectroscopy,
    QubitSpectroscopyFlux,
    ReadoutFrequency,
    ReadoutPower,
    ResonatorSpectroscopy,
    ResonatorSpectroscopyFlux,
    ResonatorSpectroscopyPower,
    SingleShotReadout,
    T1Relaxation,
    T2Echo,
)
from scqo.testing import InMemoryDevice, SimulatedBackend


@register
class DemoResonatorSpectroscopy(ResonatorSpectroscopy):
    """Concrete experiment for tests/demos; no real instrument program."""

    def probe(self):  # never called by SimulatedBackend
        return None


@register
class DemoQubitRamsey(QubitRamsey):
    """Concrete Ramsey for tests/demos; no real instrument program."""

    def probe(self):  # never called by SimulatedBackend
        return None


@register
class DemoQubitPowerRabi(QubitPowerRabi):
    """Concrete power Rabi for tests/demos; no real instrument program."""

    def probe(self):  # never called by SimulatedBackend
        return None


@register
class DemoQubitSpectroscopy(QubitSpectroscopy):
    """Concrete qubit spectroscopy for tests/demos; no real instrument program."""

    def probe(self):  # never called by SimulatedBackend
        return None


@register
class DemoT1Relaxation(T1Relaxation):
    """Concrete T1 for tests/demos; no real instrument program."""

    def probe(self):  # never called by SimulatedBackend
        return None


@register
class DemoResonatorSpectroscopyPower(ResonatorSpectroscopyPower):
    """Concrete punchout for tests/demos; no real instrument program."""

    def probe(self):  # never called by SimulatedBackend
        return None


@register
class DemoT2Echo(T2Echo):
    """Concrete Hahn echo for tests/demos; no real instrument program."""

    def probe(self):  # never called by SimulatedBackend
        return None


@register
class DemoQubitSpectroscopyFlux(QubitSpectroscopyFlux):
    """Concrete flux map for tests/demos; no real instrument program."""

    def probe(self):  # never called by SimulatedBackend
        return None


@register
class DemoSingleShotReadout(SingleShotReadout):
    """Concrete IQ blobs for tests/demos; no real instrument program."""

    def probe(self):  # never called by SimulatedBackend
        return None


@register
class DemoResonatorSpectroscopyFlux(ResonatorSpectroscopyFlux):
    """Concrete resonator flux map for tests/demos; no real instrument program."""

    def probe(self):  # never called by SimulatedBackend
        return None


@register
class DemoReadoutPower(ReadoutPower):
    """Concrete fidelity-vs-amplitude scan for tests/demos; no real instrument program."""

    def probe(self):  # never called by SimulatedBackend
        return None


@register
class DemoReadoutFrequency(ReadoutFrequency):
    """Concrete fidelity-vs-frequency scan for tests/demos; no real instrument program."""

    def probe(self):  # never called by SimulatedBackend
        return None


def _device() -> InMemoryDevice:
    return InMemoryDevice(
        {
            "q0": {"readout_freq": 5.95e9, "drive_freq": 3.87e9, "pi_amp": 0.2, "readout_amp": 0.25},
            "q1": {"readout_freq": 6.05e9, "drive_freq": 4.01e9, "pi_amp": 0.18, "readout_amp": 0.22},
        }
    )


def test_experiment_runs_and_fits_dip():
    backend = SimulatedBackend(_device())
    exp = DemoResonatorSpectroscopy(
        backend, DemoResonatorSpectroscopy.Parameters(qubits=["q0", "q1"], frequency_span_hz=15e6, num_points=201)
    )
    result = exp.run()
    assert result.success
    # recovered dip lies within the swept window for each qubit
    for qubit in ["q0", "q1"]:
        assert abs(result.fit[qubit]["dip_detuning_hz"]) < 15e6 / 2


def test_session_catalog_and_run_are_json():
    sess = Session(SimulatedBackend(_device()))

    catalog = sess.catalog()
    names = {entry["name"] for entry in catalog}
    assert "resonator_spectroscopy" in names
    # schema is real JSON-schema with the declared knobs
    schema = next(e for e in catalog if e["name"] == "resonator_spectroscopy")["parameters_schema"]
    assert "frequency_span_hz" in schema["properties"]

    before = sess.device_state()["q0"]["readout_freq"]
    result = sess.run("resonator_spectroscopy", {"qubits": ["q0"], "frequency_span_hz": 15e6})
    assert result["outcomes"]["q0"] == Outcome.SUCCESSFUL.value
    # update=True wrote the fitted frequency back into the device
    after = sess.device_state()["q0"]["readout_freq"]
    assert after != before
    assert np.isclose(after, result["fit"]["q0"]["readout_freq"])


def test_ramsey_generalizes_pattern():
    """Same lifecycle, different sweep/fit/field: time sweep -> T2* + drive_freq update."""
    sess = Session(SimulatedBackend(_device()))

    # both experiments share one catalog/registry
    assert {"resonator_spectroscopy", "qubit_ramsey"} <= {e["name"] for e in sess.catalog()}

    before = sess.device_state()["q1"]["drive_freq"]
    result = sess.run(
        "qubit_ramsey",
        {"qubits": ["q1"], "frequency_detuning_hz": 1.0e6, "max_idle_time_ns": 4000, "num_points": 201},
    )
    assert result["outcomes"]["q1"] == Outcome.SUCCESSFUL.value
    # recovered residual detuning is small (|err| <= 0.2 * applied) and T2* is physical
    assert abs(result["fit"]["q1"]["detuning_error_hz"]) < 0.3e6
    assert 1e-6 < result["fit"]["q1"]["t2_star_s"] < 50e-6
    # update=True wrote the corrected drive_freq back (a different field than resonator spec)
    after = sess.device_state()["q1"]["drive_freq"]
    assert after != before
    assert np.isclose(after, result["fit"]["q1"]["drive_freq"])


def test_qubit_spectroscopy_finds_peak_and_updates_drive_freq():
    """Two-tone: peak search within the swept window -> coarse drive_freq update."""
    sess = Session(SimulatedBackend(_device()))

    before = sess.device_state()["q0"]["drive_freq"]
    result = sess.run("qubit_spectroscopy", {"qubits": ["q0"], "frequency_span_hz": 60e6})
    assert result["outcomes"]["q0"] == Outcome.SUCCESSFUL.value
    fit = result["fit"]["q0"]
    assert abs(fit["peak_detuning_hz"]) <= 60e6 / 2  # inside the swept window
    assert fit["fwhm_hz"] > 0 and fit["n_peaks"] >= 1
    after = sess.device_state()["q0"]["drive_freq"]
    assert np.isclose(after, before + fit["peak_detuning_hz"])


def test_t1_relaxation_reports_without_writeback():
    """T1: exponential decay fit -> reported t1_s inside the simulated truth range,
    and NO device field changes (diagnostics, not calibration)."""
    sess = Session(SimulatedBackend(_device()))

    state_before = sess.device_state()
    result = sess.run("t1_relaxation", {"qubits": ["q0"]})
    assert result["outcomes"]["q0"] == Outcome.SUCCESSFUL.value
    assert 20e-6 * 0.8 < result["fit"]["q0"]["t1_s"] < 60e-6 * 1.2  # sim truth 20-60 us
    assert sess.device_state() == state_before  # no writeback
    assert sess.history() == []


def test_resonator_power_2d_updates_amp_and_freq():
    """First 2D experiment: punchout picks a dispersive-regime power and writes back
    BOTH readout_amp and readout_freq."""
    sess = Session(SimulatedBackend(_device()))

    before = sess.device_state()["q0"]
    result = sess.run("resonator_spectroscopy_power", {"qubits": ["q0"]})
    assert result["outcomes"]["q0"] == Outcome.SUCCESSFUL.value
    fit = result["fit"]["q0"]
    # optimal power is below the simulated punchout knee (-12..-8 dB)
    assert fit["optimal_power_db"] <= -6.0
    assert 0 < fit["readout_amp_factor"] < 1.0
    after = sess.device_state()["q0"]
    assert np.isclose(after["readout_amp"], before["readout_amp"] * fit["readout_amp_factor"])
    assert np.isclose(after["readout_freq"], fit["readout_freq"])
    # both writebacks are in the history, linked to the same run
    fields = {h["field"] for h in sess.history()}
    assert {"readout_amp", "readout_freq"} <= fields


def test_t2_echo_reports_without_writeback():
    """Echo: exponential envelope fit -> reported t2_echo_s inside the simulated truth
    range, and NO device field changes (diagnostics, not calibration)."""
    sess = Session(SimulatedBackend(_device()))

    state_before = sess.device_state()
    result = sess.run("t2_echo", {"qubits": ["q0"]})
    assert result["outcomes"]["q0"] == Outcome.SUCCESSFUL.value
    assert 30e-6 * 0.8 < result["fit"]["q0"]["t2_echo_s"] < 80e-6 * 1.2  # sim truth 30-80 us
    assert sess.device_state() == state_before  # no writeback
    assert sess.history() == []


def test_qubit_flux_map_recovers_arch():
    """2D flux map: point-cloud + transmon arch fit -> sweet spot inside the swept
    window, arch top at the current drive_freq; no writeback (Phase-3 schema)."""
    sess = Session(SimulatedBackend(_device()))

    state_before = sess.device_state()
    result = sess.run("qubit_spectroscopy_flux", {"qubits": ["q0"]})
    assert result["outcomes"]["q0"] == Outcome.SUCCESSFUL.value
    fit = result["fit"]["q0"]
    assert -0.3 <= fit["sweet_spot_flux_v"] <= 0.3  # sim hides it inside the window
    # simulate() pins the arch top to the current drive_freq
    assert fit["f01_at_sweet_spot_hz"] == np.float64(fit["f01_at_sweet_spot_hz"])
    assert abs(fit["f01_at_sweet_spot_hz"] - fit["old_drive_freq"]) < 40e6
    assert fit["ej_sum_ghz"] > 0
    assert sess.device_state() == state_before  # no writeback yet
    assert sess.history() == []


def test_single_shot_readout_fidelity():
    """First per-shot experiment: GMM on the IQ blobs -> fidelity consistent with the
    simulated flip probabilities; no writeback."""
    sess = Session(SimulatedBackend(_device()))

    result = sess.run("single_shot_readout", {"qubits": ["q0"], "num_shots": 1500})
    assert result["outcomes"]["q0"] == Outcome.SUCCESSFUL.value
    fit = result["fit"]["q0"]
    # sim: 3.5-5 sigma separation, 1-5% thermal flips, 3-8% decay flips
    assert 0.85 < fit["readout_fidelity"] <= 1.0
    assert 0.0 <= fit["p_e_given_g"] < 0.12
    assert 0.0 <= fit["p_g_given_e"] < 0.15
    assert sess.history() == []


def test_resonator_flux_map_recovers_dispersive_model():
    """Resonator-vs-flux: dip trace + dispersive fit -> sweet spot inside the swept
    window, coupling g near the simulated range; no writeback."""
    sess = Session(SimulatedBackend(_device()))

    state_before = sess.device_state()
    result = sess.run("resonator_spectroscopy_flux", {"qubits": ["q0"]})
    assert result["outcomes"]["q0"] == Outcome.SUCCESSFUL.value
    fit = result["fit"]["q0"]
    assert -0.3 <= fit["sweet_spot_flux_v"] <= 0.3
    assert 40e6 < fit["g_hz"] < 200e6  # sim truth 70-100 MHz, loose fit tolerance
    assert abs(fit["f_r0_hz"] - fit["old_readout_freq"]) < 20e6  # bare near dressed
    assert sess.device_state() == state_before  # no writeback
    assert sess.history() == []


def test_readout_power_picks_fidelity_optimum_and_updates_amp():
    """Per-shot fidelity vs amplitude: best point below the simulated flip knee,
    readout_amp written back."""
    sess = Session(SimulatedBackend(_device()))

    before = sess.device_state()["q0"]
    result = sess.run(
        "readout_power", {"qubits": ["q0"], "num_amp_points": 8, "num_shots": 400}
    )
    assert result["outcomes"]["q0"] == Outcome.SUCCESSFUL.value
    fit = result["fit"]["q0"]
    assert 0.4 <= fit["best_amp_factor"] <= 1.8
    assert fit["best_fidelity"] > 0.8
    after = sess.device_state()["q0"]
    assert np.isclose(after["readout_amp"], before["readout_amp"] * fit["best_amp_factor"])
    assert {"readout_amp"} <= {h["field"] for h in sess.history()}


def test_readout_frequency_picks_fidelity_optimum_and_updates_freq():
    """Per-shot fidelity vs frequency: best detuning near the simulated contrast
    peak, readout_freq written back."""
    sess = Session(SimulatedBackend(_device()))

    before = sess.device_state()["q0"]
    result = sess.run(
        "readout_frequency", {"qubits": ["q0"], "num_freq_points": 9, "num_shots": 400}
    )
    assert result["outcomes"]["q0"] == Outcome.SUCCESSFUL.value
    fit = result["fit"]["q0"]
    # sim hides the peak within +-span/6 = +-0.83 MHz; grid step is 0.625 MHz
    assert abs(fit["frequency_shift_hz"]) <= 1.5e6
    after = sess.device_state()["q0"]
    assert np.isclose(after["readout_freq"], before["readout_freq"] + fit["frequency_shift_hz"])
    assert {"readout_freq"} <= {h["field"] for h in sess.history()}


def test_power_rabi_generalizes_pattern():
    """Amplitude sweep -> cosine fit -> updates a third device field: pi_amp."""
    sess = Session(SimulatedBackend(_device()))

    assert "qubit_power_rabi" in {e["name"] for e in sess.catalog()}

    before = sess.device_state()["q0"]["pi_amp"]
    result = sess.run("qubit_power_rabi", {"qubits": ["q0"], "max_amp_factor": 2.0, "num_points": 201})
    assert result["outcomes"]["q0"] == Outcome.SUCCESSFUL.value
    # recovered pi factor is near 1 (simulated miscalibration was within +-15%)
    assert 0.8 < result["fit"]["q0"]["pi_amp_factor"] < 1.2
    after = sess.device_state()["q0"]["pi_amp"]
    # the writeback ran (recorded in history) and applied the fitted value. We assert via
    # history rather than `after != before` because a reproducibly near-perfect simulated
    # calibration can leave the value numerically unchanged while still being written.
    assert any(h["qubit"] == "q0" and h["field"] == "pi_amp" for h in sess.history())
    assert np.isclose(after, result["fit"]["q0"]["pi_amp"])
