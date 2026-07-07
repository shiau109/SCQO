"""Health check: venv, drivers, config chain, registries — and what to do about it.

    scqo doctor                 # the first command to run when anything misbehaves

Read-only: touches no instrument, writes nothing. Checks the whole resolution chain
a run would use — python/scqo install, the device selection (user overlay / [lab]),
the device's cooldown registry (active cycle, current setup, instrument-config folder
and its expected vendor files), backend driver entry points, data_root, registries,
and the experiment catalog. Exit 0 = healthy (warnings allowed), 1 = failures.
"""

from __future__ import annotations

import argparse
import os
import sys
from importlib.metadata import entry_points, version
from pathlib import Path

OK, WARN, FAIL = "OK", "WARN", "FAIL"

_EXPECTED_FILES = {"qblox": ("dut_config.json", "hw_config.json"),
                   "qm": ("state.json", "wiring.json")}


def _setup_checks(cfg, backends: dict) -> list[tuple[str, str, str]]:
    """Device -> cycle -> setup -> backend/folder checks (the run-time chain)."""
    from scqo.datastore import active_cooldown, current_setup, load_cooldowns

    from ._backends import SERVED_BY

    fix = f"scqo cooldown start cd1 --backend <qblox|qm|simulated> [--instrument-config <folder>]"
    try:
        cycles = load_cooldowns(cfg.data_root, cfg.device)
    except ValueError as err:
        return [(FAIL, "cooldowns", str(err))]
    if not cycles:
        return [(FAIL, "cooldowns", f"device {cfg.device!r} has no cycle registry — runs will "
                                    f"refuse; the manager runs: {fix}")]
    active = active_cooldown(cycles)
    if active is None:
        return [(FAIL, "cooldowns", f"{len(cycles)} cycle(s), none ACTIVE — runs will refuse; "
                                    f"start the next one: {fix}")]
    cid, cycle = active
    setup = current_setup(cycle)
    if setup is None:
        return [(FAIL, "cooldowns", f"cycle {cid!r} has no setup in effect (future-dated "
                                    f"'since'?) — fix its [[{cid}.setup]] blocks")]
    ports = sum(1 for k in setup if k not in ("since", "note", "backend", "instrument_config"))
    out = [(OK, "cooldowns", f"{cfg.device}: {cid} ACTIVE — setup since {setup['since']}, "
                             f"backend={setup['backend']}, {ports} port(s)")]

    backend = setup["backend"]
    if backend == "simulated":
        out.append((OK, "backend", "'simulated' — built into scqo (demo qubits, synthetic data)"))
        return out
    folder = Path(setup["instrument_config"])
    if not folder.is_dir():
        out.append((FAIL, "instr config", f"{folder} does not exist on this machine"))
    else:
        missing = [n for n in _EXPECTED_FILES[backend] if not (folder / n).is_file()]
        if missing:
            out.append((FAIL, "instr config", f"{folder}: missing {', '.join(missing)} — copy the "
                                              "vendor files there under canonical names"))
        else:
            out.append((OK, "instr config", str(folder)))
    if backend in backends:
        out.append((OK, "backend", f"{backend!r} -> {backends[backend]} (entry point)"))
    else:
        provider, venv = SERVED_BY[backend]
        out.append((FAIL, "backend", f"{backend!r} driver not registered here — wrong venv "
                                     f"(activate D:\\github\\{venv}) or {provider} needs "
                                     "`uv pip install -e` (entry points register at INSTALL time)"))
    return out


def _shared_folder_scan(data_root) -> list[tuple[str, str, str]]:
    """WARN when the ACTIVE cycles of two devices share an instrument_config folder."""
    from scqo.datastore import COOLDOWNS_FILE, active_cooldown, current_setup, load_cooldowns

    seen: dict[str, str] = {}
    warnings = []
    for reg in sorted(Path(data_root).glob(f"*/{COOLDOWNS_FILE}")):
        device = reg.parent.name
        try:
            cycles = load_cooldowns(data_root, device)
        except ValueError:
            continue  # its own doctor run reports this; don't fail the scan
        active = active_cooldown(cycles)
        setup = current_setup(active[1]) if active else None
        folder = (setup or {}).get("instrument_config")
        if not folder:
            continue
        key = os.path.normcase(folder)
        if key in seen:
            warnings.append((WARN, "shared config", f"devices {seen[key]!r} and {device!r} have "
                                                    f"ACTIVE setups on the SAME folder {folder} — "
                                                    "their writebacks will corrupt each other"))
        else:
            seen[key] = device
    return warnings


def main(argv: list[str] | None = None, prog: str | None = None) -> int:
    parser = argparse.ArgumentParser(prog=prog, description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", help="lab config path (default: $SCQO_CONFIG or ~/.scqo/config.toml)")
    args = parser.parse_args(argv)

    checks: list[tuple[str, str, str]] = []  # (status, topic, message)

    checks.append((OK, "python", sys.executable))
    checks.append((OK, "scqo", version("scqo")))

    backends = {ep.name: ep.value for ep in entry_points(group="scqo.backends")}
    checks.append((OK, "drivers", f"backends registered: {sorted(backends) or 'none (simulated only)'}"))

    from scqo import load_lab_config

    cfg = None
    try:
        cfg = load_lab_config(args.config)
    except Exception as err:  # malformed user.toml/parameters.toml, missing named files...
        checks.append((FAIL, "config", f"{type(err).__name__}: {err}"))

    if cfg is not None:
        if cfg.source is None:
            checks.append((WARN, "lab config", "none found — built-in defaults (simulated, NOTHING SAVED); see INSTALL §2"))
        else:
            checks.append((OK, "lab config", str(cfg.source)))
        checks.append((OK, "user overlay", str(cfg.user_source) if cfg.user_source else "none"))
        checks.append((OK, "parameters",
                       f"{cfg.parameters_source} ({len(cfg.parameter_defaults)} experiment table(s))"
                       if cfg.parameters_source else "none (code defaults)"))
        checks.append((OK, "device", cfg.device) if cfg.device else
                      (WARN, "device", 'none selected — built-in simulated demo, NOTHING SAVED; '
                                       'set `device = "<name>"` in ~/.scqo/user.toml'))

        if cfg.data_root is None:
            checks.append((WARN, "data_root", "not configured — runs are NOT saved"))
        elif not Path(cfg.data_root).is_dir():
            checks.append((WARN, "data_root", f"{cfg.data_root} does not exist yet (created on first run)"))
        elif not os.access(cfg.data_root, os.W_OK):
            checks.append((FAIL, "data_root", f"{cfg.data_root} is not writable by this account"))
        else:
            index = Path(cfg.data_root) / "index.sqlite"
            checks.append((OK, "data_root", f"{cfg.data_root} ({'index present' if index.is_file() else 'no index yet'})"))

        if cfg.data_root is not None and Path(cfg.data_root).is_dir():
            from scqo.datastore import load_device_registry

            checks.append((OK, "registries", f"devices.toml entries: {len(load_device_registry(cfg.data_root))}"))
            if cfg.device is not None:
                checks.extend(_setup_checks(cfg, backends))
            checks.extend(_shared_folder_scan(cfg.data_root))

        try:
            from ._backends import ensure_demo_experiments

            ensure_demo_experiments()
            from scqo import catalog

            n = len(catalog())
            checks.append((OK if n else FAIL, "catalog",
                           f"{n} experiment(s)" if n else "EMPTY — no driver entry points registered"))
        except Exception as err:
            checks.append((FAIL, "catalog", f"{type(err).__name__}: {err}"))

    failures = 0
    for status, topic, message in checks:
        if status == FAIL:
            failures += 1
        print(f"[{status:4s}] {topic:13s} {message}")
    print(f"\n{failures} problem(s) found" if failures else "\nall checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
