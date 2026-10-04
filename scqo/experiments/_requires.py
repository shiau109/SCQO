"""Requirement bundles several experiments share (``scqo/requirements.py``).

An experiment composes its ``requires`` from these and its own lines:
``requires = (Requirement("drive_freq_hz", "..."), *CALIBRATED_READOUT)``.

INCLUSION IS EXPLICIT, never derived from ``required_operations``. An operation
says a target CAN be read out or driven; a bundle says the experiment needs
that to be already calibrated - and the bring-up experiments are exactly the
ones for which it is not: ``resonator_spectroscopy`` requires the ``readout``
operation and exists to FIND the readout frequency.
"""

from __future__ import annotations

from ..requirements import Requirement

#: a readout parked at its working point - what every experiment that reads a
#: qubit STATE (rather than the resonator itself) takes for granted
CALIBRATED_READOUT: tuple[Requirement, ...] = (
    Requirement("readout_freq_hz", "the readout tone has to sit on the resonator"),
    Requirement("readout_power_dbm", "the readout has to be at its working power"),
)
