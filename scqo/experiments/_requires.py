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

#: the same for a drive-frequency scan (the ``drive_detuning`` capability's
#: window is measured from this knob)
DRIVE_WINDOW_CENTRE = Requirement(
    "drive_freq_hz", "the swept window is centred on it", seed_ok=True)

#: what a ``_pulse`` flux experiment needs of the flux line: its window is an
#: excursion from the standing bias (``_capabilities/flux.py``), so every
#: number it reports is read from there
FLUX_PULSE_ORIGIN = Requirement(
    "idle_flux", "the flux window is an excursion from this standing bias, where "
                 "the pulses and the readout are played")

#: a saturation drive's power is set through the drive chain for the run and
#: put back afterwards (``_drive_power.drive_power_boundary``), which refuses a
#: chain with no standing value to return to
DRIVE_CHAIN = Requirement(
    "drive_power_dbm", "the run moves the drive chain to its own saturation power "
                       "and restores this value afterwards, so one has to be set")

#: a discriminator that is ALWAYS used - for an experiment whose instrument-side
#: arithmetic consumes the discriminated state of every shot. (The optional
#: case is the state_readout capability's own conditional pair.)
CALIBRATED_DISCRIMINATOR: tuple[Requirement, ...] = (
    Requirement("readout_rotation_rad",
                "every shot is discriminated: the axis it is projected on"),
    Requirement("readout_threshold",
                "every shot is discriminated: what splits |0> from |1> on that axis"),
)
