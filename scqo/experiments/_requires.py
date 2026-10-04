"""Requirement bundles several experiments share (``scqo/requirements.py``).

An experiment composes its ``requires`` from these and its own lines:
``requires = (Requirement("drive_freq_hz", "..."), *CALIBRATED_READOUT)``.

INCLUSION IS EXPLICIT, never derived from ``required_operations``. An operation
says a target CAN be read out or driven; a bundle says the experiment needs
that to be already calibrated - and the bring-up experiments are exactly the
ones for which it is not: ``resonator_spectroscopy`` requires the ``readout``
operation and exists to FIND the readout frequency. What such an experiment
needs of that field is a place to start (``seed_ok``), which is
:data:`READOUT_WINDOW_CENTRE`.
"""

from __future__ import annotations

from ..requirements import Requirement

#: a readout parked at its working point - what every experiment that reads a
#: qubit STATE (rather than the resonator itself) takes for granted
CALIBRATED_READOUT: tuple[Requirement, ...] = (
    Requirement("readout_freq_hz", "the readout tone has to sit on the resonator"),
    Requirement("readout_power_dbm", "the readout has to be at its working power"),
)

#: a resonant, full pi pulse - what it takes to prepare |e>
CALIBRATED_PI_PULSE: tuple[Requirement, ...] = (
    Requirement("drive_freq_hz", "the x180 that prepares |e> has to be on resonance"),
    Requirement("pi_amp", "the x180 that prepares |e> has to be a full pi pulse"),
)

#: what a resonator scan needs of the frequency it is about to measure: only
#: somewhere to centre its window
READOUT_WINDOW_CENTRE = Requirement(
    "readout_freq_hz", "the swept window is centred on it", seed_ok=True)
