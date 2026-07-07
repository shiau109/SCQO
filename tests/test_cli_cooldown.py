"""Cooldown-cycle lifecycle through `scqo cooldown` / `scqo run` / `scqo find`.

device -> cycle -> wiring era -> runs: start a cycle, measure (stamped), hand-add a
mapping snapshot (era moves), end the cycle (runs stamp "" again). Absorbs
LCHQBDriver/tests/test_cooldown_lifecycle.py.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path


def _env(tmp_path: Path) -> dict:
    config = tmp_path / "config.toml"
    config.write_text(
        "\n".join(
            [
                "[lab]",
                'device = "simdev"',
                f"data_root = '{(tmp_path / 'data').as_posix()}'",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return {**os.environ, "SCQO_CONFIG": str(config), "SCQO_USER_CONFIG": "none"}


def _cli(env: dict, tmp_path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "scqo.cli", *args],
        capture_output=True, text=True, env=env, cwd=tmp_path,
    )


def test_cooldown_lifecycle(tmp_path):
    env = _env(tmp_path)
    today = date.today().isoformat()

    # start needs --backend; a real backend needs --instrument-config
    assert _cli(env, tmp_path, "cooldown", "start", "cd1").returncode != 0
    assert _cli(env, tmp_path, "cooldown", "start", "cd1", "--backend", "qblox").returncode != 0

    # start a simulated cycle (writes a REAL [[setup]] block); second start refuses
    proc = _cli(env, tmp_path, "cooldown", "start", "cd1", "--backend", "simulated",
                "--fridge", "TestFridge", "--packaging", "PCB v1")
    assert proc.returncode == 0, proc.stderr
    assert _cli(env, tmp_path, "cooldown", "start", "cd2", "--backend", "simulated").returncode != 0

    # a run is stamped with the cycle AND the setup era from day one
    proc = _cli(env, tmp_path, "run", "resonator_spectroscopy", "--qubits", "q0")
    assert proc.returncode == 0, proc.stderr
    r1 = json.loads(proc.stdout.split("\nsaved:")[0])
    rec1 = json.loads((Path(r1["data_path"]) / "record.json").read_text(encoding="utf-8"))
    assert rec1["cooldown"] == "cd1" and rec1["setup_since"] == today
    assert rec1["backend"] == "simulated"  # provenance = the resolved setup's backend

    # hand-add a later setup (the documented workflow for ANY change) — the era moves.
    # (Same-day here, so give it a port to see it win as the later block.)
    reg = tmp_path / "data" / "simdev" / "cooldowns.toml"
    reg.write_text(
        reg.read_text(encoding="utf-8")
        + f'\n[[cd1.setup]]\nsince = {today}\nbackend = "simulated"\n'
        '"q0.drive" = "cluster0.module2.out0"\n',
        encoding="utf-8",
    )
    show = _cli(env, tmp_path, "cooldown")
    assert show.returncode == 0, show.stderr
    assert "cluster0.module2.out0" in show.stdout  # validator shows the current setup

    # find by cycle through the query command
    listed = _cli(env, tmp_path, "find", "--cooldown", "cd1")
    assert r1["run_id"] in listed.stdout

    # end the cycle: file stays parseable (validated even with setup blocks after the
    # cycle header — the end-surgery regression case; .bak written)…
    proc = _cli(env, tmp_path, "cooldown", "end")
    assert proc.returncode == 0, proc.stderr
    assert reg.with_suffix(".toml.bak").is_file()
    # …and later runs REFUSE loudly instead of stamping "" (behavior since v0.5.0)
    proc = _cli(env, tmp_path, "run", "resonator_spectroscopy", "--qubits", "q0")
    assert proc.returncode != 0
    assert "no ACTIVE cooldown cycle" in proc.stderr
