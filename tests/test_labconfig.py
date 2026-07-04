"""Lab config: resolution order, loud failure on a mistyped explicit config, parsing."""

from __future__ import annotations

import pytest

from scqo import labconfig


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
