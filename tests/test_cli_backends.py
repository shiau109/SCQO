"""The device -> cycle -> setup -> backend resolution chain (in-process)."""

from __future__ import annotations

import pytest

from scqo import registry
from scqo.cli import _backends
from scqo.cli.__main__ import _COMMANDS, main as cli_main


def _config(tmp_path, body: str) -> str:
    path = tmp_path / "config.toml"
    path.write_text(body, encoding="utf-8")
    return str(path)


def _lab(tmp_path, device: str | None = "chipT") -> str:
    data_root = tmp_path / "data"
    data_root.mkdir(exist_ok=True)
    device_line = f'device = "{device}"\n' if device else ""
    return _config(tmp_path, f"[lab]\n{device_line}data_root = '{data_root.as_posix()}'\n")


def _registry(tmp_path, text: str) -> None:
    ddir = tmp_path / "data" / "chipT"
    ddir.mkdir(parents=True, exist_ok=True)
    (ddir / "cooldowns.toml").write_text(text, encoding="utf-8")


def test_no_device_falls_back_to_demo(tmp_path, monkeypatch):
    """No device selected anywhere = the built-in simulated demo, nothing saved."""
    sess, cfg = _backends.build_session(_lab(tmp_path, device=None))
    assert cfg.device is None
    assert sess.backend_label == "simulated"
    assert sess.datastore is None  # demo fallback persists nothing
    assert "q0" in sess.device_state()


def test_device_without_registry_names_the_fix(tmp_path):
    with pytest.raises(SystemExit) as err:
        _backends.build_session(_lab(tmp_path))
    assert "no cooldown registry" in str(err.value)
    assert "scqo cooldown start" in str(err.value)


def test_device_without_active_cycle_refuses(tmp_path):
    _registry(tmp_path, '[cd1]\nstart = 2026-01-01\nend = 2026-02-01\n'
                        '[[cd1.setup]]\nsince = 2026-01-01\nbackend = "simulated"\n')
    with pytest.raises(SystemExit) as err:
        _backends.build_session(_lab(tmp_path))
    assert "no ACTIVE cooldown cycle" in str(err.value)


def test_future_dated_setup_refuses(tmp_path):
    _registry(tmp_path, '[cd1]\nstart = 2026-01-01\n'
                        '[[cd1.setup]]\nsince = 2099-01-01\nbackend = "simulated"\n')
    with pytest.raises(SystemExit) as err:
        _backends.build_session(_lab(tmp_path))
    assert "future-dated" in str(err.value)


def test_simulated_setup_builds_and_persists(tmp_path):
    """A device on a simulated setup saves runs under <data_root>/<device>/."""
    _registry(tmp_path, '[cd1]\nstart = 2026-01-01\n'
                        '[[cd1.setup]]\nsince = 2026-01-01\nbackend = "simulated"\n')
    sess, cfg = _backends.build_session(_lab(tmp_path))
    assert cfg.device == "chipT"
    assert sess.backend_label == "simulated"
    assert sess.datastore is not None  # device + data_root = persisted


def _driver_installed(family: str) -> bool:
    from importlib.metadata import entry_points

    return any(ep.name == family for ep in entry_points(group="scqo.backends"))


@pytest.mark.skipif(_driver_installed("qblox"), reason="qblox driver installed in this env")
def test_missing_driver_names_repo_and_venv(tmp_path):
    """A wrong-venv attempt fails loudly and says exactly what to activate/install."""
    (tmp_path / "cfg").mkdir()
    _registry(tmp_path, '[cd1]\nstart = 2026-01-01\n'
                        f'[[cd1.setup]]\nsince = 2026-01-01\nbackend = "qblox"\n'
                        f"instrument_config = '{(tmp_path / 'cfg').as_posix()}'\n")
    with pytest.raises(SystemExit) as err:
        _backends.build_session(_lab(tmp_path))
    assert "LCHQBDriver" in str(err.value)
    assert ".venv-qblox" in str(err.value)
    assert "uv pip install -e" in str(err.value)


def test_ensure_demo_experiments_is_idempotent_and_never_shadows():
    _backends.ensure_demo_experiments()
    first = {e["name"]: e for e in registry.catalog()}
    assert "resonator_spectroscopy" in first

    # a pre-registered class (a "driver" registration) must survive a second ensure
    sentinel = registry.get("resonator_spectroscopy")
    _backends.ensure_demo_experiments()
    assert registry.get("resonator_spectroscopy") is sentinel
    assert {e["name"] for e in registry.catalog()} == set(first)


def test_dispatcher_usage_lists_every_subcommand(capsys):
    assert cli_main(["--help"]) == 0
    out = capsys.readouterr().out
    for name in _COMMANDS:
        assert name in out


def test_dispatcher_rejects_unknown_command(capsys):
    assert cli_main(["frobnicate"]) == 2
    assert "unknown command" in capsys.readouterr().err
