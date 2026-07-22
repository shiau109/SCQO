"""Shared drive-power boundary for saturation-drive experiments (backend-free).

``qubit_spectroscopy`` and ``qubit_spectroscopy_flux`` both treat the saturation
power as a per-run STIMULUS: set ``drive_power_dbm`` through the RecordingDevice
before acquiring, then revert it exactly afterwards (the punchout discipline of
``resonator_spectroscopy_power_amp``). The boundary lives here so the two
experiments share ONE implementation instead of copy-pasting the try/finally.
"""

from __future__ import annotations

import math
from contextlib import contextmanager
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from ..experiment import Experiment


@contextmanager
def drive_power_boundary(experiment: "Experiment", target_dbm: float) -> Iterator[None]:
    """Recorded set -> (acquire, in the ``with`` body) -> exact revert of
    ``drive_power_dbm`` for every target.

    Each target's standing ``drive_power_dbm`` is read and validated FIRST (a
    single unknown/non-finite chain aborts before any write, so the device is
    never left half-set), then all are written to ``target_dbm``, the body runs
    (acquisition), and the ``finally`` reverts every target to its standing
    value — 2 ChangeRecords + coupled ``drive_amp`` echoes per qubit. While the
    chain is off its standing value the stored pi_amp means a different power; no
    pi pulse is played by these experiments, and the revert is exact (discrete
    chain knob, the amplitude restored verbatim).
    """
    target_dbm = float(target_dbm)
    targets = list(experiment.params.targets)
    views = {q: experiment.device.component(q) for q in targets}

    previous: dict[str, float] = {}
    for q, view in views.items():
        try:
            before = view.drive_power_dbm
        except (KeyError, ValueError):
            before = None
        if before is None or not math.isfinite(float(before)):
            raise RuntimeError(
                f"{q}: drive_power_dbm is unknown (unconfigured drive chain / zero "
                f"saturation amplitude) — the revert target would be undefined; set "
                f"drive_power_dbm (or fix drive_amp) first"
            )
        previous[q] = float(before)
    for view in views.values():
        view.drive_power_dbm = target_dbm  # recorded boundary write (+ coupled echo)

    try:
        yield
    finally:
        revert_errors = []
        for q, view in views.items():  # recorded boundary revert (+ coupled echo)
            try:
                view.drive_power_dbm = previous[q]
            except Exception as err:  # noqa: BLE001 - collected and re-raised below
                revert_errors.append(f"{q}: {type(err).__name__}: {err}")
        if revert_errors:
            raise RuntimeError(
                "drive chain revert failed for " + "; ".join(revert_errors)
            )
