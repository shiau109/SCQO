"""``python -m scqo <data_root>`` — rebuild the datastore index from the run folders."""

from __future__ import annotations

import sys

from .datastore import reindex

if len(sys.argv) != 2:
    print("usage: python -m scqo <data_root>   (rebuilds <data_root>/index.sqlite)", file=sys.stderr)
    raise SystemExit(2)
print(f"indexed {reindex(sys.argv[1])} runs")
