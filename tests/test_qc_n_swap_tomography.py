"""qc_n_swap_tomography on the simulated backend: the channel the simulator plants
comes back out, the compensation it finds really zeroes the phase, the readout
correction falls back as documented, and update() proposes only what it should."""

import math

import numpy as np
import pytest
from pydantic import ValidationError

from scqo import Session
from scqo import experiments as registry
from scqo.testing import (
    InMemoryDevice,
    SimulatedBackend,
    demo_components,
    demo_design,
    demo_vendor_state,
)

QUBITS = ("q0", "q1")
PAIR = "q0_q1"
COUNTS = list(range(0, 13))


def _session(tmp_path):
    roster = demo_components(QUBITS, tunable=True)
    design = demo_design(roster, QUBITS)
    vendor = InMemoryDevice(roster, demo_vendor_state(roster, design))
    return Session(SimulatedBackend(vendor), roster, design=design,
                   scqo_dir=tmp_path / "scqo", data_root=tmp_path / "data",
                   device_name="chipT", setup_name="sim", cooldown_id="cd1")


@pytest.fixture
def session(tmp_path):
    return _session(tmp_path)


def _run(session, update="none", **params):
    out = session.run("qc_n_swap_tomography",
                      {"targets": [PAIR], "swap_counts": COUNTS, "num_averages": 600,
                       **params}, update=update)
    assert out.get("error") is None, out.get("error")
    return out


def test_runs_in_both_readout_modes(session):
    for mode in ("average", "shot"):
        out = _run(session, readout_mode=mode, num_averages=300)
        assert out["outcomes"][PAIR] == "successful", mode
        fit = out["fit"][PAIR]
        assert fit["readout_calibrated"] == 1.0
        assert 0.0 < fit["theta_rad"] < math.pi / 2


def test_the_planted_angle_comes_back_and_is_proposed(session):
    session.set_values({f"{PAIR}.iswap.theta_rad": 0.3})
    out = _run(session, update="suggest", stark_amps=[0.0, 0.5])
    fit = out["fit"][PAIR]
    assert abs(fit["theta_rad"] - 0.3) < max(4 * fit["theta_rad_err"], 0.006)
    rows = [s for s in out["suggestions"] if s["entity"] == f"{PAIR}.iswap"]
    assert [(s["field"], s["role"]) for s in rows] == [("theta_rad", "monitor")]
    assert rows[0]["after"] == pytest.approx(fit["theta_rad"])


def test_the_compensation_it_finds_zeroes_the_phase(session):
    """Self-consistency without peeking at the hidden phase: the root found over
    a wide list, run on its own, must leave (almost) no phase per step."""
    out = _run(session, stark_amps=[0.05, 0.35, 0.65, 0.95])
    root = out["fit"][PAIR]["compensating_stark_amp"]
    assert math.isfinite(root) and 0.0 <= root < 1.0
    check = _run(session, stark_amps=[round(root, 4)])
    assert abs(check["fit"][PAIR]["phase_at_theta_amp_rad"]) < 0.05


def test_readout_correction_falls_back_to_stored_fidelities(session):
    bare = _run(session, readout_calibration_shots=0, num_averages=200)["fit"][PAIR]
    assert (bare["readout_calibrated"], bare["readout_corrected"]) == (0.0, 0.0)
    session.set_values({f"fl.{q}.{field}": value for q in QUBITS
                        for field, value in (("fidelity_g", 0.95), ("fidelity_e", 0.92))})
    stored = _run(session, readout_calibration_shots=0, num_averages=200)["fit"][PAIR]
    assert (stored["readout_calibrated"], stored["readout_corrected"]) == (0.0, 1.0)


def test_t1_t2_predictions_need_the_round_and_measured_facts(session):
    out = _run(session, num_averages=200)
    assert math.isnan(out["fit"][PAIR]["predicted_dephasing"])
    session.set_values({f"{q}.{field}": value for q in QUBITS
                        for field, value in (("t1_s", 20e-6), ("t2_star_s", 10e-6))})
    fit = _run(session, num_averages=200, round_duration_ns=368.0)["fit"][PAIR]
    assert fit["predicted_t1_loss_high"] == pytest.approx(1 - math.exp(-0.368 / 20))
    assert math.isfinite(fit["excess_dephasing_per_step"])
    # the measurement frames' turn per round: fitted always, predicted from the
    # members' drive frequencies once the round length is known
    assert math.isfinite(fit["frame_step_rad"])
    assert -math.pi <= fit["predicted_frame_step_rad"] <= math.pi


def test_an_undeclared_operation_proposes_nothing(session, capsys):
    out = _run(session, update="suggest", swap_operation="partial_swap", num_averages=200)
    assert math.isfinite(out["fit"][PAIR]["theta_rad"])
    assert out["suggestions"] == []
    assert f"{PAIR}.partial_swap is not declared" in capsys.readouterr().err


@pytest.mark.parametrize("bad", [
    {"swap_counts": [1, 2, 3, 4]},          # no 0
    {"swap_counts": [0, 1, 2]},             # too few
    {"swap_counts": [0, 1, 1, 2, 3]},       # repeated
    {"swap_counts": [0, -1, 2, 3]},         # negative
    {"stark_amps": []},
    {"stark_amps": [0.3, 0.3]},
    {"stark_amps": [2.0]},
    {"readout_calibration_shots": -1},
    {"round_duration_ns": 0.0},
])
def test_parameters_refuse(bad):
    cls = registry.get("qc_n_swap_tomography")
    with pytest.raises(ValidationError):
        cls.Parameters(targets=[PAIR], **bad)


def test_the_dataset_carries_the_calibration_block(session):
    from scqo.contract import ContractError
    from scqo.experiments.qc_n_swap_tomography import BASIS_LABELS

    cls = registry.get("qc_n_swap_tomography")
    experiment = cls(session.backend,
                     cls.Parameters(targets=[PAIR], swap_counts=COUNTS, num_averages=50))
    experiment.sweep_axes = experiment.define_sweep()
    ds = session.backend.acquire(experiment)
    cls.Contract.validate(ds)
    assert ds["calibration_population"].dims == ("target", "prepared_state", "joint_state")
    assert list(ds["basis"].values) == list(BASIS_LABELS)
    np.testing.assert_allclose(ds["calibration_population"].sum("joint_state"), 1.0)
    bad = ds.assign(calibration_population=ds["calibration_population"]
                    .isel(prepared_state=0, drop=True))
    with pytest.raises(ContractError, match="calibration_population"):
        cls.Contract.validate(bad)
