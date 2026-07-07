"""Add a new sample (device) — three commands, no shared-file editing at all.

    scqo sample                            # the checklist: what's manual vs automatic
    scqo sample new chipC --description "3-qubit test chip"

Since v0.5.0 a sample needs NO shared-config entry: users select it by name
(``device = "chipC"`` in their user.toml), and which instrument carries it — plus
where that instrument's vendor config lives — is recorded per era in the sample's
own cooldown registry (``scqo cooldown start``). This command creates the data
folder and prints the optional devices.toml snippet plus the exact next commands.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scqo import DataStore, load_lab_config
from scqo.datastore import load_device_registry

CHECKLIST = """\
Adding a new sample — what is manual vs automatic:

  MANUAL (manager):
    1. `scqo cooldown start cd1 --backend <qblox|qm|simulated> [--instrument-config
       <folder>]` — records the insertion + the setup (which instrument, where its
       vendor config files live). For real backends, copy the vendor files into that
       folder under canonical names (qblox: dut_config.json + hw_config.json;
       qm: state.json + wiring.json), then hand-add the port lines to the
       [[cd1.setup]] block.
    2. (optional) devices.toml: the sample's facts (description, design values).

  AUTOMATIC (no action needed):
    - <data_root>/<name>/ folders, run folders, scqo_state.json, the index row,
      viewer pages — all created on first use.
    - NO shared-config edit: users select the sample with `device = "<name>"` in
      their own ~/.scqo/user.toml; the instrument follows the cooldown registry.

`scqo sample new <name>` creates the data folder and prints all of the above
paste-ready."""


def _existing_names(cfg) -> set[str]:
    """Every device name this lab already knows: registry + index (+ the default)."""
    names: set[str] = set()
    if cfg.device:
        names.add(cfg.device)
    if cfg.data_root is not None:
        names |= set(load_device_registry(cfg.data_root))
        names |= set(DataStore(cfg.data_root, device_name=cfg.device or "device").distinct_devices())
    return names


def _new(cfg, name: str, description: str) -> int:
    if cfg.data_root is None:
        raise SystemExit(
            f"no data_root configured in {cfg.source or 'the lab config'} — "
            "a sample needs somewhere for its data to land"
        )
    device_dir = Path(cfg.data_root) / name
    if device_dir.exists() or name in _existing_names(cfg):
        print(f"note: {name!r} is already known to this lab (folder/registry/index) — "
              "steps below anyway, skip what exists\n", file=sys.stderr)
    device_dir.mkdir(parents=True, exist_ok=True)  # the command's ONLY write

    print(f"created {device_dir}\n")
    print("=" * 72)
    print(f"1. Record the first cooldown cycle + setup (manager):\n")
    print(f"   scqo cooldown start cd1 --backend qblox --instrument-config "
          f"'{(device_dir / 'qblox_cd1').as_posix()}'")
    print("   (or --backend simulated for a practice sample — no folder needed;")
    print("    for real backends copy the vendor config files into the folder under")
    print("    canonical names, then hand-add the port lines to [[cd1.setup]])")
    print("\n" + "=" * 72)
    print(f"2. PASTE into {Path(cfg.data_root) / 'devices.toml'} (optional sample facts):\n")
    print(f"[{name}]")
    print(f'description = "{description or "..."}"')
    print("\n" + "=" * 72)
    print("then:")
    print(f'  users select it with:  device = "{name}"  in ~/.scqo/user.toml')
    print("  scqo devices                        # verify the new menu row")
    print("  scqo run resonator_spectroscopy     # first stamped run")
    return 0


def main(argv: list[str] | None = None, prog: str | None = None) -> int:
    parser = argparse.ArgumentParser(prog=prog, description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", nargs="?", choices=["new"],
                        help="omit to print the add-a-sample checklist")
    parser.add_argument("name", nargs="?", help="the new sample's unique id (device name)")
    parser.add_argument("--description", default="", help="one-line sample description for devices.toml")
    parser.add_argument("--config", help="lab config path (default: $SCQO_CONFIG or ~/.scqo/config.toml)")
    args = parser.parse_args(argv)

    if args.command != "new":
        print(CHECKLIST)
        return 0
    if not args.name:
        raise SystemExit("new needs a sample name, e.g.: scqo sample new chipC")
    return _new(load_lab_config(args.config), args.name, args.description)


if __name__ == "__main__":
    sys.exit(main())
