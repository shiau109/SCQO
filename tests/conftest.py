"""Suite-wide test setup."""

import os

# Headless, deterministic figure generation. Without this, matplotlib may pick the
# interactive TkAgg backend on Windows, and Tk initialization intermittently fails
# mid-suite (TclError: "Can't find a usable tk.tcl") — the artifact fallback in
# scqo/_scqat.py then drops the figure PNGs and layout tests flake.
os.environ.setdefault("MPLBACKEND", "Agg")
