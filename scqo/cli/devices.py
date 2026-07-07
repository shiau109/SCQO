"""What can I measure here? — the device menu for Tier-1 users.

    scqo devices                      # every known device + how to select it

For each device under the lab's data_root (plus devices.toml entries), shows: its
active cooldown cycle + packaging, the CURRENT setup's backend and instrument-config
folder, the mapped-port count, which venv serves that backend — and the exact
``~/.scqo/user.toml`` line that selects it. Touches NO instrument: this only reads
the registries, so it is safe from any account at any time. Pick your device once in
your own user.toml; the instrument follows the device's cooldown registry.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scqo import load_lab_config
from scqo.datastore import (
    COOLDOWNS_FILE,
    active_cooldown,
    current_setup,
    load_cooldowns,
    load_device_registry,
)

from ._backends import SERVED_BY


def _device_row(data_root, device: str) -> tuple[str, str, str, str]:
    """(cycle text, backend, config folder, ports) for the device's current state."""
    try:
        cycles = load_cooldowns(data_root, device)
    except ValueError as err:
        return f"REGISTRY ERROR: {err}", "-", "-", "-"
    active = active_cooldown(cycles)
    if active is None:
        ended = len(cycles)
        return (f"none ACTIVE ({ended} past)" if ended else "no cycles yet"), "-", "-", "-"
    cid, cycle = active
    cycle_text = cid + (f" [{cycle['packaging']}]" if cycle.get("packaging") else "")
    setup = current_setup(cycle)
    if setup is None:
        return cycle_text, "(no setup in effect)", "-", "-"
    ports = sum(1 for k in setup if k not in ("since", "note", "backend", "instrument_config"))
    return cycle_text, setup["backend"], setup.get("instrument_config", "built-in"), str(ports)


def main(argv: list[str] | None = None, prog: str | None = None) -> int:
    parser = argparse.ArgumentParser(prog=prog, description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", help="lab config path (default: $SCQO_CONFIG or ~/.scqo/config.toml)")
    args = parser.parse_args(argv)

    cfg = load_lab_config(args.config)
    print(f"# lab config: {cfg.source or 'built-in defaults (simulated, nothing saved)'}")
    print(f"# user overlay: {cfg.user_source or 'none'}")

    if cfg.data_root is None:
        print("\nno data_root configured — no device registries to list; runs use the "
              "built-in simulated demo and are NOT saved (see INSTALL §2)")
        return 0

    root = Path(cfg.data_root)
    known: set[str] = set(load_device_registry(root))
    if root.is_dir():
        known |= {p.parent.name for p in root.glob(f"*/{COOLDOWNS_FILE}")}
        known |= {p.name for p in root.iterdir() if p.is_dir()}
    if cfg.device:
        known.add(cfg.device)

    if not known:
        print("\nno devices known yet — create one:  scqo sample new <name>")
        return 0

    print(f"\n{'device':12s} {'cooldown':22s} {'backend':11s} {'ports':5s} "
          f"{'instrument config':36s} run from")
    for device in sorted(known):
        cycle_text, backend, folder, ports = _device_row(root, device)
        provider, venv = SERVED_BY.get(backend, ("-", "-"))
        served = f"{provider} ({venv})" if provider != "-" else "-"
        marker = "  <- selected" if device == cfg.device else ""
        print(f"{device:12s} {cycle_text:22s} {backend:11s} {ports:5s} {str(folder):36s} {served}{marker}")

    print('\nselect a device once per project:  device = "<name>"  in ~/.scqo/user.toml')
    print("(the instrument follows the device's cooldown registry; your tags/parameters_file "
          "can live there too)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
