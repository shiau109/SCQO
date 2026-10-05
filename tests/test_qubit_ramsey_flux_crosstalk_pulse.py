"""qubit_ramsey_flux_crosstalk_pulse: signed flux crosstalk from the apex position.

Offline, on the tunable demo device. Pins that the fit recovers the SIGNED
coefficient the simulator planted (through a qubit's line and a coupler's), that the
run is record-only, the frames it records (both windows are idle-relative), the
pre-probe refusals, and where the virtual detuning's sign comes from.
"""

from __future__ import annotations

import warnings

import numpy as np
import pytest

from scqo import experiments as registry
from scqo.experiments.qubit_ramsey_flux_crosstalk_pulse import simulated_crosstalk
from scqo.session import Session
from scqo.testing import (
    InMemoryDevice,
    SimulatedBackend,
    demo_components,
    demo_design,
    demo_vendor_state,
)

NAME = "qubit_ramsey_flux_crosstalk_pulse"


@pytest.fixture()
def session(tmp_path):
    roster = demo_components(tunable=True)
    design = demo_design(roster)
    vendor = InMemoryDevice(roster, demo_vendor_state(roster, design))
    s = Session(SimulatedBackend(vendor), roster, design=design,
                scqo_dir=tmp_path / "scqo", data_root=tmp_path / "data",
                device_name="chipT", setup_name="sim", cooldown_id="cd1")
    s.set_values({"z_q0.idle_flux": 0.05, "z_q1.idle_flux": -0.02,
                  "zc_q0_q1.idle_flux": 0.11})
    return s


def _run(session, **params):
    params.setdefault("targets", ["q0"])
    params.setdefault("source_line", "z_q1")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return session.run(NAME, params)


def _truth(**params):
    params.setdefault("targets", ["q0"])
    params.setdefault("source_line", "z_q1")
    return simulated_crosstalk("q0", registry.get(NAME).Parameters(**params))


@pytest.mark.parametrize("extra", [
    {},                                                   # a qubit's z line
    {"source_line": "zc_q0_q1"},                          # a coupler's line
    {"use_state_discrimination": True},
    {"start_source_flux_v": 0.08, "end_source_flux_v": -0.08, "num_source_flux_points": 7},
])
def test_the_planted_crosstalk_is_recovered_with_its_sign(session, extra):
    out = _run(session, **extra)
    assert out["error"] is None, out["error"]
    assert out["outcomes"] == {"q0": "successful"}
    fit, truth = out["fit"]["q0"], _truth(**extra)
    tolerance = max(5 * fit["flux_crosstalk_stderr"], 2e-3)
    assert fit["flux_crosstalk"] == pytest.approx(truth["crosstalk"], abs=tolerance)
    assert np.sign(fit["flux_crosstalk"]) == np.sign(truth["crosstalk"])
    assert fit["flux_offset_from_idle"] == pytest.approx(truth["apex_v"], abs=0.3e-3)
    assert fit["n_valid_source_points"] == fit["n_source_points"]
    assert fit["nonlinear_suspected"] == 0 and fit["fold_suspected"] == 0
    # the apex HEIGHT moved with the source (planted) and did not leak into m
    assert fit["apex_height_span_hz"] > 0


def test_the_run_is_record_only_and_says_where_both_lines_stood(session):
    out = _run(session, source_line="zc_q0_q1")
    assert out["error"] is None
    assert out["suggestions"] == []
    fit = out["fit"]["q0"]
    assert fit["source_line"] == "zc_q0_q1"
    assert fit["old_idle_flux"] == pytest.approx(0.05)          # the target's own line
    assert fit["old_source_idle_flux"] == pytest.approx(0.11)   # the source line
    # no arch facts on the demo device -> the apex default sign, said so
    assert fit["ramp_sign_from"] == "default"
    assert fit["ramp_detuning_hz"] == pytest.approx(-4.0e6)
    assert fit["source_lead_time_ns"] == 0.0                   # the pulses start together


def test_the_dataset_keeps_all_three_axes(session):
    out = _run(session, num_flux_points=5, num_source_flux_points=3, num_idle_points=40)
    ds = session.datastore.open_dataset(out["run_id"])
    assert set(ds["I"].dims) == {"target", "flux_bias_v", "source_flux_v", "idle_time_ns"}
    assert ds.sizes["flux_bias_v"] == 5 and ds.sizes["source_flux_v"] == 3
    assert ds.sizes["idle_time_ns"] == 40
    assert float(ds["idle_time_ns"].min()) >= 16.0


@pytest.mark.parametrize("extra,match", [
    ({"source_line": None}, "source_line is required"),
    ({"source_line": "z_q0"}, "OWN flux line"),
    ({"source_line": "xy_q1"}, "carries no flux channel"),
    ({"source_line": "nope"}, "not a line of this roster"),
    ({"targets": ["q0", "q1"], "source_line": "zc_q0_q1"}, "one target per run"),
])
def test_what_cannot_be_measured_is_refused_before_the_probe(session, extra, match):
    out = _run(session, **extra)
    assert out["error"] is not None and match in out["error"]


def _with_arch(session, apex_above_drive_hz=0.0):
    """Arch facts with the apex AT the standing idle, apex_above_drive_hz over the drive."""
    session.set_values({"z_q0.q0.flux_offset": 0.05,
                        "z_q0.q0.flux_per_phi0": 0.9,
                        "q0.f_q_max_hz": session.device_state()["xy_q0.q0"]["drive_freq_hz"]
                        + apex_above_drive_hz})


def test_arch_facts_orient_the_detuning(session):
    _with_arch(session)
    out = _run(session)
    assert out["error"] is None, out["error"]
    fit = out["fit"]["q0"]
    assert fit["ramp_sign_from"] == "facts"
    assert fit["ramp_detuning_hz"] == pytest.approx(-4.0e6)  # the qubit only drops


def test_a_folding_window_is_refused_before_the_probe(session):
    # apex 1 MHz above the drive: the window swings the qubit to BOTH sides of the
    # drive, so a 0.3 MHz detuning folds whichever sign it takes
    _with_arch(session, apex_above_drive_hz=1e6)
    out = _run(session, frequency_detuning_hz=0.3e6)
    assert out["error"] is not None and "folding_risk" in out["error"]


def test_the_fold_check_counts_how_far_the_source_can_push_the_apex(session):
    """The own window alone would pass; widened by SOURCE_REACH x the source
    amplitude it cannot be sampled."""
    _with_arch(session)
    narrow = _run(session, start_source_flux_v=-0.01, end_source_flux_v=0.01)
    assert narrow["error"] is None, narrow["error"]
    wide = _run(session, start_source_flux_v=-0.45, end_source_flux_v=0.45)
    assert wide["error"] is not None and "undersampled" in wide["error"]


@pytest.mark.parametrize("bad", [4, 12, 18])
def test_flux_buffer_must_be_playable(bad):
    with pytest.raises(ValueError, match="flux_buffer_ns"):
        registry.get(NAME).Parameters(targets=["q0"], flux_buffer_ns=bad)
    registry.get(NAME).Parameters(targets=["q0"], flux_buffer_ns=0)
    registry.get(NAME).Parameters(targets=["q0"], flux_buffer_ns=24)


def test_a_source_lead_is_recorded_and_changes_no_axis(session):
    """The lead is a property of the run, not a swept axis: the dataset has the same
    shape, and the fit says how long the source was already on."""
    out = _run(session, source_lead_time_ns=1000)
    assert out["error"] is None, out["error"]
    assert out["outcomes"] == {"q0": "successful"}
    assert out["fit"]["q0"]["source_lead_time_ns"] == 1000.0
    ds = session.datastore.open_dataset(out["run_id"])
    assert set(ds["I"].dims) == {"target", "flux_bias_v", "source_flux_v", "idle_time_ns"}


@pytest.mark.parametrize("bad", [-4, 2, 1001])
def test_the_source_lead_must_be_on_the_4_ns_grid(bad):
    with pytest.raises(ValueError, match="source_lead_time_ns"):
        registry.get(NAME).Parameters(targets=["q0"], source_lead_time_ns=bad)
    assert registry.get(NAME).Parameters(targets=["q0"]).source_lead_time_ns == 0
    registry.get(NAME).Parameters(targets=["q0"], source_lead_time_ns=10_000_000)
