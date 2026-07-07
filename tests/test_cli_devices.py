"""`scqo devices` — the Tier-1 DEVICE menu (registries only, no instrument)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _run(tmp_path: Path, config: Path, user: str | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "SCQO_CONFIG": str(config), "SCQO_USER_CONFIG": "none"}
    if user is not None:
        user_file = config.parent / "user.toml"
        user_file.write_text(user, encoding="utf-8")
        env["SCQO_USER_CONFIG"] = str(user_file)
    return subprocess.run(
        [sys.executable, "-m", "scqo.cli", "devices"],
        capture_output=True, text=True, env=env, cwd=tmp_path,
    )


def test_menu_lists_devices_and_selection_hint(tmp_path):
    data_root = tmp_path / "data"
    (data_root / "chipA").mkdir(parents=True)
    cfg_folder = data_root / "chipA" / "qblox_cd3"
    cfg_folder.mkdir()
    (data_root / "chipA" / "cooldowns.toml").write_text(
        '[cd3]\nstart = 2026-07-01\npackaging = "PCB v3"\n\n'
        f'[[cd3.setup]]\nsince = 2026-07-01\nbackend = "qblox"\n'
        f"instrument_config = '{cfg_folder.as_posix()}'\n"
        '"q1.drive" = "cluster0.module2.out0"\n',
        encoding="utf-8",
    )
    (data_root / "simdev").mkdir()
    (data_root / "simdev" / "cooldowns.toml").write_text(
        '[cd1]\nstart = 2026-07-01\n[[cd1.setup]]\nsince = 2026-07-01\nbackend = "simulated"\n',
        encoding="utf-8",
    )
    config = tmp_path / "config.toml"
    config.write_text(
        f"[lab]\ndevice = \"simdev\"\ndata_root = '{data_root.as_posix()}'\n", encoding="utf-8"
    )

    out = _run(tmp_path, config).stdout
    assert "chipA" in out and "cd3 [PCB v3]" in out  # device row with cycle + packaging
    assert "qblox" in out and "qblox_cd3" in out  # setup backend + config folder
    assert "LCHQBDriver" in out and ".venv-qblox" in out  # where that backend runs
    assert "simdev" in out and "simulated" in out
    assert 'device = "<name>"' in out  # the how-to-select hint
    assert out.count("<- selected") == 1  # exactly one current device marked
    selected_line = next(line for line in out.splitlines() if "<- selected" in line)
    assert selected_line.startswith("simdev")

    # the overlay moves the selection marker (the user picks the SAMPLE)
    out = _run(tmp_path, config, user='device = "chipA"\n').stdout
    selected_line = next(line for line in out.splitlines() if "<- selected" in line)
    assert selected_line.startswith("chipA")


def test_menu_shows_registry_errors_and_degrades(tmp_path):
    data_root = tmp_path / "data"
    (data_root / "broken").mkdir(parents=True)
    (data_root / "broken" / "cooldowns.toml").write_text("not [valid toml", encoding="utf-8")
    config = tmp_path / "config.toml"
    config.write_text(f"[lab]\ndata_root = '{data_root.as_posix()}'\n", encoding="utf-8")
    proc = _run(tmp_path, config)
    assert proc.returncode == 0, proc.stderr
    assert "REGISTRY ERROR" in proc.stdout  # broken device shown, menu still renders

    config2 = tmp_path / "config2.toml"
    config2.write_text("[lab]\n", encoding="utf-8")
    proc = _run(tmp_path, config2)
    assert proc.returncode == 0
    assert "no data_root" in proc.stdout  # no registries at all — still explains itself
