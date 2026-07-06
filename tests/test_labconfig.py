"""Lab config: resolution order, loud failure on a mistyped explicit config, parsing."""

from __future__ import annotations

import pytest

from scqo import labconfig


@pytest.fixture(autouse=True)
def _isolate_user_files(monkeypatch, tmp_path):
    """Hermeticity: never read the developer's real ~/.scqo/parameters.toml or user.toml.

    Individual tests re-point the paths at their own files when they need one.
    """
    monkeypatch.setattr(labconfig, "PARAMS_DEFAULT_PATH", tmp_path / "no-parameters.toml")
    monkeypatch.setattr(labconfig, "USER_DEFAULT_PATH", tmp_path / "no-user.toml")
    monkeypatch.delenv(labconfig.USER_ENV_VAR, raising=False)


def test_defaults_when_no_config(monkeypatch, tmp_path):
    monkeypatch.delenv(labconfig.ENV_VAR, raising=False)
    monkeypatch.setattr(labconfig, "DEFAULT_PATH", tmp_path / "absent.toml")
    cfg = labconfig.load()
    assert cfg.backend == "simulated"
    assert cfg.data_root is None and cfg.state_path is None
    assert cfg.source is None  # built-in defaults, nothing loaded


def test_explicit_missing_path_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        labconfig.load(tmp_path / "nope.toml")


def test_env_var_missing_file_raises(monkeypatch, tmp_path):
    """A typo'd $SCQO_CONFIG must fail loudly, not silently run simulated + unsaved."""
    monkeypatch.setenv(labconfig.ENV_VAR, str(tmp_path / "gone.toml"))
    with pytest.raises(FileNotFoundError):
        labconfig.load()


def test_tilde_paths_are_expanded(tmp_path):
    """macOS/Linux configs say data_root = '~/qpu_data'; that must not create a
    literal './~' folder."""
    path = tmp_path / "config.toml"
    path.write_text(
        '[lab]\ndata_root = "~/qpu_data"\nstate_path = "~/qpu_data/scqo_state.json"\n',
        encoding="utf-8",
    )
    cfg = labconfig.load(path)
    assert "~" not in str(cfg.data_root)
    assert cfg.data_root.is_absolute()
    assert "~" not in str(cfg.state_path)


_TWO_SAMPLE_CONFIG = """
[lab]
data_root = "D:/qpu_data"
device_name = "fallback"
state_path = "D:/qpu_data/fallback/scqo_state.json"
backend = "%s"

[qblox]
config_dir = "./qblox_state"
device_name = "chipA"
state_path = "D:/qpu_data/chipA/scqo_state.json"

[qm]
device_name = "chipB"
"""


def test_backend_table_overrides_device(tmp_path):
    """Two instruments carrying two samples: the ACTIVE backend's vendor table names
    the mounted sample, so switching backend switches device (device = the sample)."""
    path = tmp_path / "config.toml"

    path.write_text(_TWO_SAMPLE_CONFIG % "qblox_sim", encoding="utf-8")
    cfg = labconfig.load(path)
    assert cfg.device_name == "chipA"  # qblox_sim reads the [qblox] table
    assert "chipA" in str(cfg.state_path)

    path.write_text(_TWO_SAMPLE_CONFIG % "qm", encoding="utf-8")
    cfg = labconfig.load(path)
    assert cfg.device_name == "chipB"
    assert "fallback" in str(cfg.state_path)  # [qm] has no state_path -> [lab] wins

    path.write_text(_TWO_SAMPLE_CONFIG % "simulated", encoding="utf-8")
    cfg = labconfig.load(path)
    assert cfg.device_name == "fallback"  # no vendor family -> [lab] values
    assert cfg.extras["qblox"]["config_dir"] == "./qblox_state"  # passthrough intact


def test_parse_full_file(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        """
[lab]
data_root = "D:/qpu_data"
device_name = "SQ4B_v3"
state_path = "D:/qpu_data/SQ4B_v3/scqo_state.json"
backend = "qblox"
state_sync = "push"
default_tags = ["cooldown7", "run-b"]

[qblox]
config_dir = "./qblox_state"
""",
        encoding="utf-8",
    )
    cfg = labconfig.load(path)
    assert cfg.device_name == "SQ4B_v3"
    assert cfg.backend == "qblox"
    assert cfg.state_sync == "push"
    assert cfg.default_tags == ["cooldown7", "run-b"]
    assert cfg.data_root is not None and cfg.state_path is not None
    assert cfg.extras["qblox"]["config_dir"] == "./qblox_state"
    assert cfg.source == path


# ---------------------------------------------------------------- parameters.toml


def test_parameter_defaults_absent_is_empty(monkeypatch, tmp_path):
    monkeypatch.delenv(labconfig.ENV_VAR, raising=False)
    monkeypatch.setattr(labconfig, "DEFAULT_PATH", tmp_path / "absent.toml")
    cfg = labconfig.load()
    assert cfg.parameter_defaults == {}
    assert cfg.parameters_source is None


def test_parameter_defaults_loaded_from_default_path(monkeypatch, tmp_path):
    params = tmp_path / "parameters.toml"
    params.write_text(
        "[resonator_spectroscopy]\nfrequency_span_hz = 15e6\nnum_points = 201\n\n"
        '[single_shot_readout]\nqubits = ["q1"]\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(labconfig, "PARAMS_DEFAULT_PATH", params)
    config = tmp_path / "config.toml"
    config.write_text('[lab]\nbackend = "simulated"\n', encoding="utf-8")
    cfg = labconfig.load(config)
    # TOML-native types survive: float via exponent, int, list of strings
    assert cfg.parameter_defaults["resonator_spectroscopy"] == {"frequency_span_hz": 15e6, "num_points": 201}
    assert isinstance(cfg.parameter_defaults["resonator_spectroscopy"]["frequency_span_hz"], float)
    assert isinstance(cfg.parameter_defaults["resonator_spectroscopy"]["num_points"], int)
    assert cfg.parameter_defaults["single_shot_readout"] == {"qubits": ["q1"]}
    assert cfg.parameters_source == params


def test_parameter_defaults_without_config_file(monkeypatch, tmp_path):
    """Standing experiment preferences are independent of the backend wiring."""
    monkeypatch.delenv(labconfig.ENV_VAR, raising=False)
    monkeypatch.setattr(labconfig, "DEFAULT_PATH", tmp_path / "absent.toml")
    params = tmp_path / "parameters.toml"
    params.write_text("[qubit_ramsey]\nnum_points = 201\n", encoding="utf-8")
    monkeypatch.setattr(labconfig, "PARAMS_DEFAULT_PATH", params)
    cfg = labconfig.load()
    assert cfg.source is None  # still built-in lab defaults
    assert cfg.parameter_defaults == {"qubit_ramsey": {"num_points": 201}}
    assert cfg.parameters_source == params


def test_parameters_file_key_overrides_default_path(monkeypatch, tmp_path):
    default_file = tmp_path / "parameters.toml"
    default_file.write_text("[qubit_ramsey]\nnum_points = 101\n", encoding="utf-8")
    monkeypatch.setattr(labconfig, "PARAMS_DEFAULT_PATH", default_file)
    project_file = tmp_path / "projectB.toml"
    project_file.write_text("[qubit_ramsey]\nnum_points = 999\n", encoding="utf-8")
    config = tmp_path / "config.toml"
    config.write_text(f'[lab]\nparameters_file = "{project_file.as_posix()}"\n', encoding="utf-8")
    cfg = labconfig.load(config)
    assert cfg.parameter_defaults["qubit_ramsey"]["num_points"] == 999
    assert cfg.parameters_source == project_file


def test_explicit_parameters_file_missing_raises(tmp_path):
    """A typo'd parameters_file must fail loudly, not silently run on code defaults."""
    config = tmp_path / "config.toml"
    config.write_text(
        f'[lab]\nparameters_file = "{(tmp_path / "gone.toml").as_posix()}"\n', encoding="utf-8"
    )
    with pytest.raises(FileNotFoundError):
        labconfig.load(config)


def test_vendor_table_overrides_parameters_file(tmp_path):
    """Two samples on two instruments: the ACTIVE backend's vendor table may name its
    own parameter set, exactly like it names its own device_name/state_path."""
    lab_file = tmp_path / "lab.toml"
    lab_file.write_text("[qubit_ramsey]\nnum_points = 1\n", encoding="utf-8")
    chip_file = tmp_path / "chipA.toml"
    chip_file.write_text("[qubit_ramsey]\nnum_points = 2\n", encoding="utf-8")
    template = (
        '[lab]\nbackend = "%s"\nparameters_file = "' + lab_file.as_posix() + '"\n\n'
        '[qblox]\nparameters_file = "' + chip_file.as_posix() + '"\n'
    )
    config = tmp_path / "config.toml"
    config.write_text(template % "qblox_sim", encoding="utf-8")
    assert labconfig.load(config).parameter_defaults["qubit_ramsey"]["num_points"] == 2
    config.write_text(template % "simulated", encoding="utf-8")
    assert labconfig.load(config).parameter_defaults["qubit_ramsey"]["num_points"] == 1


def test_invalid_parameters_toml_raises(monkeypatch, tmp_path):
    """Measurement-affecting config never fails silently — and the error must say
    WHICH toml file broke (two TOMLs load per call now)."""
    params = tmp_path / "parameters.toml"
    params.write_text("[resonator_spectroscopy\nnum_points = 201\n", encoding="utf-8")  # missing ]
    monkeypatch.setattr(labconfig, "PARAMS_DEFAULT_PATH", params)
    config = tmp_path / "config.toml"
    config.write_text("[lab]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="parameters.toml"):
        labconfig.load(config)


def test_non_table_top_level_key_raises(monkeypatch, tmp_path):
    """The likely mistake: a bare knob at file root instead of inside a table."""
    params = tmp_path / "parameters.toml"
    params.write_text("num_points = 201\n", encoding="utf-8")
    monkeypatch.setattr(labconfig, "PARAMS_DEFAULT_PATH", params)
    config = tmp_path / "config.toml"
    config.write_text("[lab]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="experiment tables"):
        labconfig.load(config)


def test_unknown_experiment_table_loads_silently(monkeypatch, tmp_path):
    """Contrib experiments may not be installed in this env; their tables must survive.
    A typo'd table name only surfaces if that experiment is actually run."""
    params = tmp_path / "parameters.toml"
    params.write_text("[not_installed_experiment]\nfoo = 1\n", encoding="utf-8")
    monkeypatch.setattr(labconfig, "PARAMS_DEFAULT_PATH", params)
    config = tmp_path / "config.toml"
    config.write_text("[lab]\n", encoding="utf-8")
    cfg = labconfig.load(config)
    assert cfg.parameter_defaults["not_installed_experiment"] == {"foo": 1}


# ---------------------------------------------------------------- user overlay


def _write_user(tmp_path, text):
    user = tmp_path / "user.toml"
    user.write_text(text, encoding="utf-8")
    return user


def _base_config(tmp_path, body='[lab]\nbackend = "simulated"\n'):
    config = tmp_path / "config.toml"
    config.write_text(body, encoding="utf-8")
    return config


def test_user_overlay_backend_switches_vendor_table(monkeypatch, tmp_path):
    """The overlay picks the instrument; the vendor table — and the SAMPLE — follow."""
    config = _base_config(tmp_path, _TWO_SAMPLE_CONFIG % "qblox_sim")
    user = _write_user(tmp_path, 'backend = "qm"\n')
    monkeypatch.setattr(labconfig, "USER_DEFAULT_PATH", user)
    cfg = labconfig.load(config)
    assert cfg.backend == "qm"
    assert cfg.device_name == "chipB"  # [qm] table selected by the overlaid backend
    assert cfg.user_source == user


def test_user_overlay_default_tags_merge_dedup(monkeypatch, tmp_path):
    config = _base_config(tmp_path, '[lab]\ndefault_tags = ["cooldown7", "shared"]\n')
    user = _write_user(tmp_path, 'default_tags = ["projA", "cooldown7"]\n')
    monkeypatch.setattr(labconfig, "USER_DEFAULT_PATH", user)
    cfg = labconfig.load(config)
    assert cfg.default_tags == ["cooldown7", "shared", "projA"]


def test_user_overlay_parameters_file_beats_vendor_and_lab(monkeypatch, tmp_path):
    for name, points in (("lab.toml", 1), ("chip.toml", 2), ("mine.toml", 3)):
        (tmp_path / name).write_text(f"[qubit_ramsey]\nnum_points = {points}\n", encoding="utf-8")
    body = (
        '[lab]\nbackend = "%s"\nparameters_file = "' + (tmp_path / "lab.toml").as_posix() + '"\n\n'
        '[qblox]\nparameters_file = "' + (tmp_path / "chip.toml").as_posix() + '"\n'
    )
    config = tmp_path / "config.toml"
    user = _write_user(tmp_path, f'parameters_file = "{(tmp_path / "mine.toml").as_posix()}"\n')
    monkeypatch.setattr(labconfig, "USER_DEFAULT_PATH", user)
    config.write_text(body % "qblox_sim", encoding="utf-8")  # vendor table active
    assert labconfig.load(config).parameter_defaults["qubit_ramsey"]["num_points"] == 3
    config.write_text(body % "simulated", encoding="utf-8")  # only [lab] in play
    assert labconfig.load(config).parameter_defaults["qubit_ramsey"]["num_points"] == 3


def test_user_overlay_disallowed_key_raises(monkeypatch, tmp_path):
    """Machine wiring is not a personal choice — reject loudly, naming the key."""
    config = _base_config(tmp_path)
    user = _write_user(tmp_path, 'data_root = "D:/elsewhere"\n')
    monkeypatch.setattr(labconfig, "USER_DEFAULT_PATH", user)
    with pytest.raises(ValueError, match="data_root") as err:
        labconfig.load(config)
    assert "backend" in str(err.value)  # message names the allowed keys


def test_user_overlay_ignored_without_base_config(monkeypatch, tmp_path):
    """No base config = built-in defaults; a backend switch could run unsaved."""
    monkeypatch.delenv(labconfig.ENV_VAR, raising=False)
    monkeypatch.setattr(labconfig, "DEFAULT_PATH", tmp_path / "absent.toml")
    user = _write_user(tmp_path, 'backend = "qblox"\n')
    monkeypatch.setattr(labconfig, "USER_DEFAULT_PATH", user)
    cfg = labconfig.load()
    assert cfg.backend == "simulated"
    assert cfg.user_source is None


@pytest.mark.parametrize("value", ["none", "NONE", "None", ""])
def test_user_env_none_disables_overlay(monkeypatch, tmp_path, value):
    config = _base_config(tmp_path)
    user = _write_user(tmp_path, 'default_tags = ["projA"]\n')
    monkeypatch.setattr(labconfig, "USER_DEFAULT_PATH", user)
    monkeypatch.setenv(labconfig.USER_ENV_VAR, value)
    cfg = labconfig.load(config)
    assert cfg.default_tags == []
    assert cfg.user_source is None


def test_user_env_path_missing_raises(monkeypatch, tmp_path):
    config = _base_config(tmp_path)
    monkeypatch.setenv(labconfig.USER_ENV_VAR, str(tmp_path / "gone.toml"))
    with pytest.raises(FileNotFoundError):
        labconfig.load(config)


def test_user_env_path_selects_file(monkeypatch, tmp_path):
    config = _base_config(tmp_path)
    _write_user(tmp_path, 'default_tags = ["default-file"]\n')  # at USER_DEFAULT_PATH's dir
    monkeypatch.setattr(labconfig, "USER_DEFAULT_PATH", tmp_path / "user.toml")
    other = tmp_path / "other.toml"
    other.write_text('default_tags = ["env-file"]\n', encoding="utf-8")
    monkeypatch.setenv(labconfig.USER_ENV_VAR, str(other))
    cfg = labconfig.load(config)
    assert cfg.default_tags == ["env-file"]
    assert cfg.user_source == other


def test_user_overlay_malformed_toml_raises(monkeypatch, tmp_path):
    config = _base_config(tmp_path)
    user = _write_user(tmp_path, 'backend = "unclosed\n')
    monkeypatch.setattr(labconfig, "USER_DEFAULT_PATH", user)
    with pytest.raises(ValueError, match="user.toml"):
        labconfig.load(config)


def test_user_overlay_wrong_type_raises(monkeypatch, tmp_path):
    config = _base_config(tmp_path)
    user = _write_user(tmp_path, 'default_tags = "oops"\n')
    monkeypatch.setattr(labconfig, "USER_DEFAULT_PATH", user)
    with pytest.raises(ValueError, match="default_tags"):
        labconfig.load(config)


def test_user_overlay_applies_to_explicit_config_path(monkeypatch, tmp_path):
    """--config / $SCQO_CONFIG select the BASE; the overlay still layers on top —
    that IS the shared-server pattern (machine-wide SCQO_CONFIG + per-account user.toml)."""
    config = _base_config(tmp_path, '[lab]\ndefault_tags = ["shared"]\n')
    user = _write_user(tmp_path, 'default_tags = ["mine"]\n')
    monkeypatch.setattr(labconfig, "USER_DEFAULT_PATH", user)
    cfg = labconfig.load(config)  # explicit path argument
    assert cfg.default_tags == ["shared", "mine"]
    assert cfg.user_source == user


def test_make_session_wires_parameter_defaults(monkeypatch, tmp_path):
    from scqo.testing import InMemoryDevice, SimulatedBackend

    params = tmp_path / "parameters.toml"
    params.write_text("[qubit_ramsey]\nnum_points = 201\n", encoding="utf-8")
    monkeypatch.setattr(labconfig, "PARAMS_DEFAULT_PATH", params)
    config = tmp_path / "config.toml"
    config.write_text("[lab]\n", encoding="utf-8")
    cfg = labconfig.load(config)
    sess = labconfig.make_session(SimulatedBackend(InMemoryDevice({"q0": {"readout_freq": 5.9e9}})), cfg)
    assert sess.parameter_defaults == {"qubit_ramsey": {"num_points": 201}}
    assert sess.parameter_defaults_source == str(params)
