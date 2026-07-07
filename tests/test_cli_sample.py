"""`scqo sample` — the add-a-sample scaffold (v0.5.0: no shared-config edit at all)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _run(tmp_path: Path, config: Path | None, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "SCQO_USER_CONFIG": "none"}
    if config is not None:
        env["SCQO_CONFIG"] = str(config)
    return subprocess.run(
        [sys.executable, "-m", "scqo.cli", "sample", *args],
        capture_output=True, text=True, env=env, cwd=tmp_path,
    )


def _config(tmp_path: Path) -> Path:
    (tmp_path / "data").mkdir()
    config = tmp_path / "config.toml"
    config.write_text(f"[lab]\ndata_root = '{(tmp_path / 'data').as_posix()}'\n", encoding="utf-8")
    return config


def test_scaffold_prints_steps_and_creates_folder(tmp_path):
    config = _config(tmp_path)
    proc = _run(tmp_path, config, "new", "chipC", "--description", "3-qubit test chip")
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "scqo cooldown start cd1 --backend" in out  # the ONE manual manager step
    assert "[chipC]" in out and "3-qubit test chip" in out  # devices.toml block
    assert 'device = "chipC"' in out  # the user.toml selection line
    assert "config.toml" not in out.split("created")[1]  # NO shared-config paste anymore
    assert (tmp_path / "data" / "chipC").is_dir()  # the one write
    # shared config untouched (governance)
    assert "chipC" not in config.read_text(encoding="utf-8")


def test_existing_name_warns(tmp_path):
    config = _config(tmp_path)
    assert _run(tmp_path, config, "new", "chipC").returncode == 0
    proc = _run(tmp_path, config, "new", "chipC")  # folder now exists from the first call
    assert proc.returncode == 0
    assert "already known" in proc.stderr


def test_requires_data_root_and_checklist_works(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text("[lab]\n", encoding="utf-8")
    proc = _run(tmp_path, config, "new", "chipC")
    assert proc.returncode != 0
    assert "data_root" in proc.stderr

    checklist = _run(tmp_path, config)  # no command -> the self-documenting checklist
    assert checklist.returncode == 0
    assert "MANUAL" in checklist.stdout and "AUTOMATIC" in checklist.stdout
    assert "cooldown start" in checklist.stdout
