"""``python -m scqo.viewer`` — serve the run-viewer (lab convention: port 8080).

Zero-config: reads data_root/device/state_path from the lab config. Ports:
8001 qualibrate · 8080 THIS viewer · 8081 datasette (``python -m scqo.browse``).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..labconfig import load


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--data-root", help="override the lab config's data_root")
    parser.add_argument("--config", help="lab config path (default: $SCQO_CONFIG or ~/.scqo/config.toml)")
    args = parser.parse_args(argv)

    cfg = load(args.config)
    root = Path(args.data_root) if args.data_root else cfg.data_root
    if root is None or not (root / "index.sqlite").is_file():
        raise SystemExit(
            f"no index.sqlite under {root or '(no data_root configured)'} — "
            "run a measurement first, or check ~/.scqo/config.toml"
        )

    try:
        import uvicorn

        from .app import create_app
    except ModuleNotFoundError as err:
        raise SystemExit(
            f"missing package: {err.name}\n"
            "The viewer needs its extras:  uv pip install fastapi uvicorn jinja2\n"
            "(or install scqo with them:   uv pip install -e D:/github/SCQO[viewer])"
        )

    app = create_app(root, device_name=cfg.device_name, state_path=cfg.state_path)
    print(f"SCQO run viewer: http://127.0.0.1:{args.port}  (Ctrl+C to stop)")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
