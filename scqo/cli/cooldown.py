"""Manage the device's cooldown-cycle registry — cycles + setup eras.

    scqo cooldown                                  # validate + list cycles, show the current setup
    scqo cooldown start cd9 --backend qblox --instrument-config D:\\qpu_data\\chipA\\qblox_cd9
    scqo cooldown start cd1 --backend simulated    # practice cycle, no config folder
    scqo cooldown end                              # close the open cycle (today's date)

A cycle records the insertion (start/end, fridge, packaging — fixed while cold) and
holds ``[[<id>.setup]]`` era records: each carries the WHOLE setup — ``backend``,
``instrument_config`` (the folder with the vendor config files under canonical
names), and the device-port -> "instrument.port" map. ANY change (a broken channel
moving, or the whole instrument swapping) = HAND-ADD a new ``[[<id>.setup]]`` block
with a new ``since`` date and a DIFFERENT folder. Every run is auto-stamped with the
active cycle and the setup era (query: ``scqo find --cooldown``). The no-args form
is the validator. Manager-run by convention.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import date
from pathlib import Path

from scqo import load_lab_config
from scqo.datastore import (
    COOLDOWNS_FILE,
    SETUP_BACKENDS,
    active_cooldown,
    current_setup,
    load_cooldowns,
)

_START_TEMPLATE = """
[{cid}]
start = {today}
fridge = "{fridge}"
packaging = "{packaging}"
note = "{note}"

[[{cid}.setup]]
since = {today}
backend = "{backend}"
{config_line}# Ports: hand-add device-port -> "instrument.port" lines to THIS block, e.g.
# "q1.drive"   = "cluster0.module2.out0"
# Any later change (port OR instrument) = hand-add a NEW [[{cid}.setup]] block with a
# new `since` and a DIFFERENT instrument_config folder.
"""


def _device(cfg) -> str:
    if cfg.device is None:
        raise SystemExit('no device selected — set `device = "<name>"` in ~/.scqo/user.toml '
                         "(or [lab] device in the shared config); `scqo devices` shows the menu")
    if cfg.data_root is None:
        raise SystemExit("no data_root configured — cooldown registries live under <data_root>/<device>/")
    return cfg.device


def _registry_path(cfg) -> Path:
    return Path(cfg.data_root) / _device(cfg) / COOLDOWNS_FILE


def _show(cfg) -> int:
    device = _device(cfg)
    cycles = load_cooldowns(cfg.data_root, device)  # raises loudly on a broken file
    if not cycles:
        print(f"no cooldown cycles declared for {device} ({_registry_path(cfg)})")
        return 0
    active = active_cooldown(cycles)
    for cid, cycle in cycles.items():
        marker = "ACTIVE" if active and cid == active[0] else f"ended {cycle.get('end', '?')}"
        extras = "  ".join(f"{k}={cycle[k]}" for k in ("fridge", "packaging") if cycle.get(k))
        print(f"{cid:12s} start={cycle.get('start', '?')}  {marker:18s} "
              f"setups={len(cycle.get('setup', []))}  {extras}")
    if active:
        setup = current_setup(active[1])
        if setup:
            folder = setup.get("instrument_config", "(built-in)")
            print(f"\ncurrent setup of {active[0]} (since {setup['since']}): "
                  f"backend={setup['backend']}  config={folder}")
            for port, target in setup.items():
                if port not in ("since", "note", "backend", "instrument_config"):
                    print(f"  {port:16s} -> {target}")
        else:
            print(f"\n{active[0]} has no setup in effect yet (future-dated?) — check its 'since' dates")
    return 0


def _start(cfg, cid: str, backend: str, instrument_config: str | None,
           fridge: str, packaging: str, note: str) -> int:
    device = _device(cfg)
    path = _registry_path(cfg)
    cycles = load_cooldowns(cfg.data_root, device)
    active = active_cooldown(cycles)
    if active:
        raise SystemExit(f"cycle {active[0]!r} is still open — run `scqo cooldown end` first")
    if cid in cycles:
        raise SystemExit(f"cycle {cid!r} already exists in {path}")
    if backend == "simulated":
        if instrument_config:
            raise SystemExit("--instrument-config makes no sense for 'simulated' (built-in demo device)")
        config_line = ""
    else:
        if not instrument_config:
            raise SystemExit(f"backend {backend!r} needs --instrument-config <folder> "
                             "(the folder holding the vendor config files under canonical names)")
        folder = Path(instrument_config).expanduser()
        config_line = f"instrument_config = '{folder}'\n"
        expected = {"qblox": ("dut_config.json", "hw_config.json"),
                    "qm": ("state.json", "wiring.json")}[backend]
        missing = [n for n in expected if not (folder / n).is_file()]
        if missing:
            print(f"WARNING: {', '.join(missing)} not (yet) in {folder} — copy the vendor "
                  "files there under those canonical names before the first run", file=sys.stderr)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Append-only: hand-written content and comments above stay untouched.
    with open(path, "a", encoding="utf-8") as f:
        f.write(_START_TEMPLATE.format(cid=cid, today=date.today().isoformat(), backend=backend,
                                       config_line=config_line, fridge=fridge,
                                       packaging=packaging, note=note))
    load_cooldowns(cfg.data_root, device)  # re-parse: the write must be valid
    print(f"started {cid} on backend {backend!r} in {path} — hand-add the port lines to its [[{cid}.setup]]")
    return 0


def _end(cfg) -> int:
    device = _device(cfg)
    path = _registry_path(cfg)
    cycles = load_cooldowns(cfg.data_root, device)
    active = active_cooldown(cycles)
    if active is None:
        raise SystemExit(f"no open cycle in {path}")
    cid = active[0]
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    # Targeted line edit (comments preserved): insert `end = <today>` right after the
    # open cycle's `start = ...` line inside its [cid] block (which always precedes
    # its [[cid.setup]] blocks).
    in_block, inserted = False, False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == f"[{cid}]":
            in_block = True
        elif in_block and stripped.startswith("start"):
            lines.insert(i + 1, f"end = {date.today().isoformat()}\n")
            inserted = True
            break
    if not inserted:
        raise SystemExit(f"could not locate the start line of [{cid}] in {path} — add `end = ...` by hand")
    backup = path.with_suffix(".toml.bak")
    shutil.copy2(path, backup)
    path.write_text("".join(lines), encoding="utf-8")
    try:
        load_cooldowns(cfg.data_root, device)  # re-parse: never leave a broken registry
    except ValueError as err:
        shutil.copy2(backup, path)
        raise SystemExit(f"edit produced an invalid file — restored from {backup}: {err}")
    print(f"ended {cid} ({date.today().isoformat()}) in {path} — runs refuse until the next "
          f"`scqo cooldown start`")
    return 0


def main(argv: list[str] | None = None, prog: str | None = None) -> int:
    parser = argparse.ArgumentParser(prog=prog, description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", nargs="?", choices=["start", "end"],
                        help="omit to validate + list cycles and the current setup")
    parser.add_argument("cycle", nargs="?", help="cycle id for `start`, e.g. cd9")
    parser.add_argument("--backend", choices=list(SETUP_BACKENDS),
                        help="which backend carries the device this cycle (required for start)")
    parser.add_argument("--instrument-config", metavar="FOLDER",
                        help="folder with the vendor config files (required unless --backend simulated)")
    parser.add_argument("--fridge", default="", help="which fridge this insertion is in")
    parser.add_argument("--packaging", default="", help="packaging description (fixed for the cycle)")
    parser.add_argument("--note", default="", help="free-text note stored with the cycle")
    parser.add_argument("--config", help="lab config path (default: $SCQO_CONFIG or ~/.scqo/config.toml)")
    args = parser.parse_args(argv)

    cfg = load_lab_config(args.config)
    if args.command == "start":
        if not args.cycle:
            raise SystemExit("start needs a cycle id, e.g.: scqo cooldown start cd9 --backend qblox ...")
        if not args.backend:
            raise SystemExit("start needs --backend (qblox | qm | simulated)")
        return _start(cfg, args.cycle, args.backend, args.instrument_config,
                      args.fridge, args.packaging, args.note)
    if args.command == "end":
        return _end(cfg)
    return _show(cfg)


if __name__ == "__main__":
    sys.exit(main())
