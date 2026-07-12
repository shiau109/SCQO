"""SCQO-native config + change history: runs are recorded, device_state() is the
authoritative SCQO config, and the state round-trips through JSON (load is authoritative
— it pushes the SCQO values back into the vendor device)."""

from __future__ import annotations

import json

import numpy as np

from scqo import Outcome, Session, register
from scqo.experiments import QubitPowerRabi, QubitRamsey, QubitRelaxation, ResonatorSpectroscopy
from scqo.testing import InMemoryDevice, SimulatedBackend


# Concrete demo experiments (probe is a no-op under SimulatedBackend). Registering under
# the canonical names is idempotent across test modules (last registration wins; all are
# equivalent no-op-probe subclasses).
@register
class _DemoRes(ResonatorSpectroscopy):
    def probe(self):
        return None


@register
class _DemoRabi(QubitPowerRabi):
    def probe(self):
        return None


@register
class _DemoRamsey(QubitRamsey):
    def probe(self):
        return None


@register
class _DemoT1(QubitRelaxation):
    def probe(self):
        return None


def _device() -> InMemoryDevice:
    return InMemoryDevice(
        {
            "q0": {"readout_freq": 5.95e9, "drive_freq": 3.87e9, "pi_amp": 0.2, "readout_amp": 0.25},
            "q1": {"readout_freq": 6.05e9, "drive_freq": 4.01e9, "pi_amp": 0.18, "readout_amp": 0.22},
        }
    )


def test_run_records_history_and_updates_config():
    sess = Session(SimulatedBackend(_device()))
    before = sess.device_state()["q0"]["readout_freq"]

    result = sess.run("resonator_spectroscopy", {"qubits": ["q0"]}, update="apply")
    assert result["outcomes"]["q0"] == Outcome.SUCCESSFUL.value

    # device_state() is the authoritative SCQO config and reflects the update
    after = sess.device_state()["q0"]["readout_freq"]
    assert after != before
    assert np.isclose(after, result["fit"]["q0"]["readout_freq"])

    # the change is recorded with provenance (which experiment, old -> new)
    hist = sess.history()
    assert len(hist) == 1
    rec = hist[0]
    assert (rec["qubit"], rec["field"], rec["experiment"]) == ("q0", "readout_freq", "resonator_spectroscopy")
    assert rec["old"] == before
    assert np.isclose(rec["new"], after)
    assert rec["timestamp"]  # non-empty ISO timestamp


def test_state_round_trips(tmp_path):
    path = str(tmp_path / "scqo_state.json")

    sess = Session(SimulatedBackend(_device()), state_path=path, state_sync="push")
    sess.run("qubit_power_rabi", {"qubits": ["q0"]}, update="apply")
    saved_pi = sess.device_state()["q0"]["pi_amp"]
    saved_history = sess.history()
    assert saved_history  # recorded and (since state_path is set) persisted

    # A fresh push-mode session loads the SCQO state instead of re-seeding from the vendor.
    sess2 = Session(SimulatedBackend(_device()), state_path=path, state_sync="push")
    assert np.isclose(sess2.device_state()["q0"]["pi_amp"], saved_pi)
    assert len(sess2.history()) == len(saved_history)


def _stale_state(tmp_path):
    path = tmp_path / "scqo_state.json"
    path.write_text(
        json.dumps(
            {
                "config": {"q0": {"readout_freq": 7.0e9, "drive_freq": 4.0e9, "pi_amp": 0.5, "readout_amp": 0.25}},
                "history": [
                    {
                        "timestamp": "2026-01-01T00:00:00+00:00", "qubit": "q0",
                        "field": "readout_freq", "old": 5.9e9, "new": 7.0e9,
                        "experiment": "resonator_spectroscopy",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return str(path)


def test_push_load_is_authoritative(tmp_path):
    """state_sync="push" (a device SCQO fully owns): the saved SCQO config wins on load —
    its values are pushed into the vendor device, even where the vendor differs."""
    backend = SimulatedBackend(_device())  # vendor q0.readout_freq starts at 5.95e9
    sess = Session(backend, state_path=_stale_state(tmp_path), state_sync="push")

    # SCQO config reports the loaded value...
    assert sess.device_state()["q0"]["readout_freq"] == 7.0e9
    # ...and it was pushed into the vendor device (authoritative on load).
    assert backend.device.snapshot()["q0"]["readout_freq"] == 7.0e9


def test_pull_load_does_not_clobber_vendor(tmp_path):
    """Default state_sync="pull" (another tool may also calibrate the vendor, e.g.
    qualibrate on QM): a stale SCQO state file must NOT overwrite vendor values at
    startup — but the saved history is kept, so provenance is continuous."""
    backend = SimulatedBackend(_device())
    sess = Session(backend, state_path=_stale_state(tmp_path))  # default pull

    # vendor wins at startup: nothing was pushed, SCQO config mirrors the vendor
    assert backend.device.snapshot()["q0"]["readout_freq"] == 5.95e9
    assert sess.device_state()["q0"]["readout_freq"] == 5.95e9
    # provenance survives the pull
    assert len(sess.history()) == 1
    assert sess.history()[0]["experiment"] == "resonator_spectroscopy"

    # an APPLIED measurement still writes back + pushes (writes are always legitimate)
    sess.run("resonator_spectroscopy", {"qubits": ["q0"]}, update="apply")
    assert backend.device.snapshot()["q0"]["readout_freq"] == sess.device_state()["q0"]["readout_freq"]
    assert len(sess.history()) == 2


def test_change_records_carry_operator(monkeypatch):
    """Every property change is attributed: run -> author (P3)."""
    monkeypatch.setattr("scqo.config._current_operator", lambda: "alice")
    sess = Session(SimulatedBackend(_device()))
    sess.run("resonator_spectroscopy", {"qubits": ["q0"]}, update="apply")
    assert sess.history()[0]["operator"] == "alice"


def test_manual_write_is_attributed(monkeypatch):
    """Writes outside any run (a notebook tweaking pi_amp) are attributed too —
    stamping lives in RecordingDevice, not in the Session's run context."""
    monkeypatch.setattr("scqo.config._current_operator", lambda: "bob")
    from scqo import RecordingDevice

    device = RecordingDevice(_device())
    device.qubit("q0").pi_amp = 0.31
    rec = device.history()[0].as_dict()
    assert rec["operator"] == "bob"
    assert rec["experiment"] is None and rec["run_id"] is None


def test_vendor_rejection_leaves_no_phantom_history():
    """If the instrument rejects a value, neither the SCQO config nor the history may
    claim a change that never reached the hardware (vendor push happens first)."""
    import pytest

    from scqo import RecordingDevice

    inner = _device()

    class _RejectingQubit:
        def __init__(self, view):
            object.__setattr__(self, "_view", view)

        def __getattr__(self, name):
            return getattr(object.__getattribute__(self, "_view"), name)

        def __setattr__(self, name, value):
            raise ValueError("vendor rejected value")

    class _RejectingDevice:
        def qubit(self, name):
            return _RejectingQubit(inner.qubit(name))

        def snapshot(self):
            return inner.snapshot()

        def save(self):
            pass

    device = RecordingDevice(_RejectingDevice())
    before = device.snapshot()["q0"]["pi_amp"]
    with pytest.raises(ValueError):
        device.qubit("q0").pi_amp = 0.5
    assert device.history() == []  # no phantom record
    assert device.snapshot()["q0"]["pi_amp"] == before  # config untouched


# ---------------------------------------------------------------- record-only fields


class _SpyDevice:
    """Vendor device that records every setattr it receives (push detector)."""

    def __init__(self):
        self._inner = _device()
        self.pushed: list[tuple[str, str, float]] = []

    def qubit(self, name):
        spy = self

        class _SpyQubit:
            def __init__(self, view):
                object.__setattr__(self, "_view", view)

            def __getattr__(self, attr):
                return getattr(object.__getattribute__(self, "_view"), attr)

            def __setattr__(self, attr, value):
                spy.pushed.append((name, attr, value))
                setattr(object.__getattribute__(self, "_view"), attr, value)

        return _SpyQubit(self._inner.qubit(name))

    def snapshot(self):
        return self._inner.snapshot()

    def save(self):
        pass


def test_record_only_write_skips_vendor():
    """A record-only measured value is recorded (history + config) but NEVER pushed —
    the instrument has no readout_fidelity knob; a calibration knob still pushes."""
    from scqo import RecordingDevice

    vendor = _SpyDevice()
    device = RecordingDevice(vendor)

    device.qubit("q0").readout_fidelity = 0.97
    assert vendor.pushed == []  # no vendor setattr for a record-only field
    assert device.snapshot()["q0"]["readout_fidelity"] == 0.97
    assert device.history()[-1].field == "readout_fidelity"

    device.qubit("q0").pi_amp = 0.3
    assert ("q0", "pi_amp", 0.3) in vendor.pushed  # pushed fields still push


def test_record_only_getter_none_when_absent():
    from scqo import RecordingDevice

    device = RecordingDevice(_device())
    assert device.qubit("q0").readout_fidelity is None  # not measured yet — no KeyError


def test_record_only_rejects_non_finite():
    import pytest

    from scqo import RecordingDevice

    device = RecordingDevice(_device())
    with pytest.raises(ValueError, match="non-finite"):
        device.qubit("q0").readout_fidelity = float("nan")
    assert device.history() == []


def test_untracked_field_write_fails_loudly():
    """Physics moved to scqo.physical: writing t1_s straight to the device config
    (a notebook habit, or stale contrib code) must raise, not vanish silently."""
    import pytest

    from scqo import RecordingDevice

    device = RecordingDevice(_device())
    with pytest.raises(AttributeError, match="scqo.physical"):
        device.qubit("q0").t1_s = 25e-6
    assert device.history() == []
    assert "t1_s" not in device.snapshot()["q0"]


def test_pull_seed_merges_recorded_values_and_drops_legacy_fields(tmp_path):
    """Pull mode: vendor wins every PUSHED field and the qubit set; saved RECORD-ONLY
    values still in FIELDS are retained; retired fields (pre-v0.6 t1_s — its home is
    physical.json now) are simply not read; vendor-dropped qubits disappear."""
    path = tmp_path / "scqo_state.json"
    path.write_text(
        json.dumps(
            {
                "config": {
                    "q0": {"readout_freq": 7.0e9, "readout_fidelity": 0.97, "t1_s": 25e-6},
                    "gone": {"readout_fidelity": 0.9},
                },
                "history": [],
            }
        ),
        encoding="utf-8",
    )
    sess = Session(SimulatedBackend(_device()), state_path=str(path))  # default pull
    state = sess.device_state()
    assert state["q0"]["readout_freq"] == 5.95e9  # vendor wins the pushed field
    assert state["q0"]["readout_fidelity"] == 0.97  # recorded value retained
    assert "t1_s" not in state["q0"]  # legacy physics key not read (fresh start)
    assert "gone" not in state  # vendor-dropped qubit not resurrected
    assert "readout_fidelity" not in state["q1"]  # never measured on q1


def test_push_load_never_pushes_record_only(tmp_path):
    """Push mode pushes the calibration fields into the vendor — record-only fields
    stay out of the vendor entirely but remain in the SCQO state; retired fields
    (legacy t1_s) are dropped on load."""
    from scqo import RecordingDevice

    path = tmp_path / "scqo_state.json"
    path.write_text(
        json.dumps({"config": {"q0": {"pi_amp": 0.5, "readout_fidelity": 0.97, "t1_s": 25e-6}},
                    "history": []}),
        encoding="utf-8",
    )
    vendor = _SpyDevice()
    device = RecordingDevice(vendor, state_path=str(path), on_load="push")
    pushed_fields = {f for _, f, _ in vendor.pushed}
    assert "pi_amp" in pushed_fields
    assert "readout_fidelity" not in pushed_fields
    assert device.snapshot()["q0"]["readout_fidelity"] == 0.97
    assert "t1_s" not in device.snapshot()["q0"]  # fresh-start drop


def test_recorded_physics_survives_session_restart(tmp_path):
    """THE regression test, v0.6 form: measure T1 in session 1 (applied); a FRESH
    session over a fresh vendor still shows it — physical.json persists next to the
    state file, so restarts never erase measured physics."""
    path = str(tmp_path / "scqo_state.json")

    sess1 = Session(SimulatedBackend(_device()), state_path=path)  # pull is the default
    result = sess1.run("qubit_relaxation", {"qubits": ["q0"]}, update="apply")
    t1 = result["fit"]["q0"]["t1_s"]
    assert sess1.physical_state()["q0"]["t1_s"] == t1

    sess2 = Session(SimulatedBackend(_device()), state_path=path)  # restart, fresh vendor
    assert sess2.physical_state()["q0"]["t1_s"] == t1  # retained across the restart
    assert sess2.device_state()["q0"]["readout_freq"] == 5.95e9  # vendor wins pushed
    hist = sess2.history(store="physical")
    assert [h["field"] for h in hist] == ["t1_s"]  # provenance continuous


def test_ramsey_pushes_drive_freq_and_records_t2_star():
    sess = Session(SimulatedBackend(_device()))
    result = sess.run(
        "qubit_ramsey",
        {"qubits": ["q1"], "frequency_detuning_hz": 1.0e6, "max_idle_time_ns": 4000, "num_points": 201},
        update="apply",
    )
    assert result["outcomes"]["q1"] == Outcome.SUCCESSFUL.value
    state = sess.device_state()["q1"]
    assert state["drive_freq"] == result["fit"]["q1"]["drive_freq"]  # pushed calibration
    assert sess.physical_state()["q1"]["t2_star_s"] == result["fit"]["q1"]["t2_star_s"]
    assert [h["field"] for h in sess.history()] == ["drive_freq"]  # instrument history
    assert [h["field"] for h in sess.history(store="physical")] == ["t2_star_s"]


def test_record_only_run_counts_as_device_update(tmp_path):
    """An APPLIED T1-only run sets updated_device: 'the device record changed'
    includes recorded physics — filter history by field to mean 'calibration pushed'."""
    sess = Session(SimulatedBackend(_device()), data_root=tmp_path / "data", device_name="devA")
    result = sess.run("qubit_relaxation", {"qubits": ["q0"]}, update="apply")
    record = sess.find_runs(experiment="qubit_relaxation")[0]
    assert record["updated_device"] is True
    assert result["run_id"] == record["run_id"]


def test_suggestions_skipped_for_failed_qubit():
    from scqo import Outcome as _O
    from scqo import PhysicalStore, RecordingDevice
    from scqo.experiments import QubitRelaxation
    from scqo.suggestions import SuggestionCapture

    class _Demo(QubitRelaxation):
        def probe(self):
            return None

    backend = SimulatedBackend(_device())
    exp = _Demo(backend, _Demo.Parameters(qubits=["q0"]))
    capture = SuggestionCapture(RecordingDevice(backend.device), PhysicalStore())
    exp.device = capture
    exp.result = _Demo.Result(outcomes={"q0": _O.FAILED}, fit={"q0": {"t1_s": 1e-6}})
    exp.update()
    assert capture.suggestions == []  # failed fits propose nothing
