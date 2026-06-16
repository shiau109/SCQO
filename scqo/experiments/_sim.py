"""Shared helpers for the offline experiment simulators."""

from __future__ import annotations

import hashlib


def stable_seed(*parts: str) -> int:
    """A process-stable RNG seed derived from string parts.

    Unlike :func:`hash`, this does not depend on ``PYTHONHASHSEED``, so a simulator
    seeded with the same experiment + qubit names reproduces the same synthetic data
    across processes — which offline tests and AI dry-runs rely on.
    """
    digest = hashlib.sha256("\x00".join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")
