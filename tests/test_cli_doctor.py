"""`scqo doctor` — the health check that should be everyone's first debugging move."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _doctor(tmp_path: Path, config_body: str | None) -> subprocess.CompletedProcess:
    env = {**os.environ, "SCQO_USER_CONFIG": "none"}
    if config_body is not None:
        config = tmp_path / "config.toml"
        config.write_text(config_body, encoding="utf-8")
        env["SCQO_CONFIG"] = str(config)
    else:
        # hermetic "fresh machine": no env var AND no real ~/.scqo — Path.home()
        # follows USERPROFILE on Windows, so point it at the tmp dir
        env.pop("SCQO_CONFIG", None)
        env["USERPROFILE"] = str(tmp_path)
        env["HOME"] = str(tmp_path)
    return subprocess.run(
        [sys.executable, "-m", "scqo.cli", "doctor"],
        capture_output=True, text=True, env=env, cwd=tmp_path,
    )


def _lab_body(tmp_path: Path, device: str = "simdev") -> str:
    return f"[lab]\ndevice = \"{device}\"\ndata_root = '{(tmp_path / 'data').as_posix()}'\n"


def test_healthy_simulated_setup_passes(tmp_path):
    data_root = tmp_path / "data"
    (data_root / "simdev").mkdir(parents=True)
    (data_root / "simdev" / "cooldowns.toml").write_text(
        '[cd1]\nstart = 2026-07-01\n\n[cd1.setup.sim_main]\nbackend = "simulated"\n',
        encoding="utf-8",
    )
    proc = _doctor(tmp_path, _lab_body(tmp_path))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "all checks passed" in proc.stdout
    assert "cd1 ACTIVE" in proc.stdout and "backend=simulated" in proc.stdout
    assert "'sim_main' (auto)" in proc.stdout  # single-setup cycle auto-selects
    assert "13 experiment(s)" in proc.stdout  # simulated fills the catalog driver-less


def test_missing_registry_or_setup_fails(tmp_path):
    (tmp_path / "data").mkdir()
    proc = _doctor(tmp_path, _lab_body(tmp_path))  # device set, no cooldowns.toml
    assert proc.returncode == 1
    assert "[FAIL] cooldowns" in proc.stdout
    assert "scqo device cooldown start" in proc.stdout  # names the fix


def test_zero_setup_cycle_fails(tmp_path):
    data_root = tmp_path / "data"
    (data_root / "simdev").mkdir(parents=True)
    # An empty cycle is LEGAL at load time (v0.7.0), but runs would refuse — doctor FAILs.
    (data_root / "simdev" / "cooldowns.toml").write_text(
        "[cd1]\nstart = 2026-07-01\n", encoding="utf-8",
    )
    proc = _doctor(tmp_path, _lab_body(tmp_path))
    assert proc.returncode == 1
    assert "[FAIL] cooldowns" in proc.stdout
    assert "has NO setups" in proc.stdout
    assert "[cd1.setup.<name>]" in proc.stdout  # names the hand-edit fix


def test_ambiguous_setup_without_selection_fails(tmp_path):
    data_root = tmp_path / "data"
    (data_root / "simdev").mkdir(parents=True)
    (data_root / "simdev" / "cooldowns.toml").write_text(
        '[cd1]\nstart = 2026-07-01\n\n'
        '[cd1.setup.sim_a]\nbackend = "simulated"\n\n'
        '[cd1.setup.sim_b]\nbackend = "simulated"\n',
        encoding="utf-8",
    )
    proc = _doctor(tmp_path, _lab_body(tmp_path))  # SCQO_USER_CONFIG=none: no selection
    assert proc.returncode == 1
    assert "[FAIL] cooldowns" in proc.stdout
    assert "scqo user --setup" in proc.stdout  # names the fix command
    assert "sim_a" in proc.stdout and "sim_b" in proc.stdout  # and the choices


def test_missing_instrument_config_files_fail(tmp_path):
    data_root = tmp_path / "data"
    folder = data_root / "chipA" / "qblox_cd1"
    folder.mkdir(parents=True)  # exists but EMPTY: canonical vendor files absent
    (data_root / "chipA" / "cooldowns.toml").write_text(
        '[cd1]\nstart = 2026-07-01\n\n[cd1.setup.qblox_main]\nbackend = "qblox"\n'
        f"instrument_config = '{folder.as_posix()}'\n",
        encoding="utf-8",
    )
    proc = _doctor(tmp_path, _lab_body(tmp_path, device="chipA"))
    assert proc.returncode == 1
    assert "[FAIL] instr config" in proc.stdout
    assert "dut_config.json" in proc.stdout


def test_shared_folder_across_devices_warns(tmp_path):
    data_root = tmp_path / "data"
    shared = data_root / "sharedcfg"
    shared.mkdir(parents=True)
    for name in ("state.json", "wiring.json"):
        (shared / name).write_text("{}", encoding="utf-8")
    for dev in ("chipA", "chipB"):
        (data_root / dev).mkdir()
        (data_root / dev / "cooldowns.toml").write_text(
            '[cd1]\nstart = 2026-07-01\n\n[cd1.setup.qm_main]\nbackend = "qm"\n'
            f"instrument_config = '{shared.as_posix()}'\n",
            encoding="utf-8",
        )
    proc = _doctor(tmp_path, _lab_body(tmp_path, device="chipA"))
    assert "[WARN] shared config" in proc.stdout
    # the message names the device:setup pairs, not just the devices
    assert "chipA:qm_main" in proc.stdout and "chipB:qm_main" in proc.stdout


def test_no_config_warns_but_passes(tmp_path):
    proc = _doctor(tmp_path, None)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "[WARN] lab config" in proc.stdout
    assert "NOTHING SAVED" in proc.stdout


def test_malformed_user_overlay_is_caught_not_crashed(tmp_path):
    user = tmp_path / "user.toml"
    user.write_text("not [valid toml", encoding="utf-8")
    env = {**os.environ, "SCQO_USER_CONFIG": str(user)}
    config = tmp_path / "config.toml"
    config.write_text("[lab]\n", encoding="utf-8")
    env["SCQO_CONFIG"] = str(config)
    proc = subprocess.run(
        [sys.executable, "-m", "scqo.cli", "doctor"],
        capture_output=True, text=True, env=env, cwd=tmp_path,
    )
    assert proc.returncode == 1
    assert "[FAIL] config" in proc.stdout
    assert "user.toml" in proc.stdout  # the message names the broken file
