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

#: the amplitude of the gate a ``target_gate`` experiment plays: the pi pair
#: or the x90 pair, as ``_gate_target.amp_knob`` decides. For the two-valued
#: ``target_gate`` of the DRAG calibrations; an experiment with more gate names
#: states its own pair.
GATE_AMPLITUDE: tuple[Requirement, ...] = (
    Requirement("pi_amp", "the rotation angle of the gate whose DRAG term is tuned",
                when=("target_gate", "x180")),
    Requirement("pi_amp_x90", "the rotation angle of the gate whose DRAG term is tuned",
                when=("target_gate", "x90")),
)

#: what a pair experiment that reads the JOINT state takes for granted of BOTH
#: members: each readout parked at its working point and each discriminator
#: calibrated - the joint populations are counted from every shot's two
#: discriminated outcomes, so there is no I/Q form to fall back on
PAIR_JOINT_READOUT: tuple[Requirement, ...] = (
    Requirement("readout_freq_hz",
                "each member's readout tone has to sit on its resonator"),
    Requirement("readout_power_dbm",
                "each member's readout has to be at its working power"),
    Requirement("readout_rotation_rad",
                "both members are discriminated in every shot: the axis each is "
                "projected on"),
    Requirement("readout_threshold",
                "both members are discriminated in every shot: what splits |0> "
                "from |1> on that axis"),
)

#: the pi pulse that puts ONE excitation into a pair - on the member the
#: experiment's ``drive_side`` names
PAIR_MEMBER_PI: tuple[Requirement, ...] = (
    Requirement("drive_freq_hz",
                "the x180 on the excited member has to be on resonance"),
    Requirement("pi_amp",
                "the x180 on the excited member has to be a full pi pulse"),
)

#: what a pair's flux pulses stand on: every flux amplitude a pair experiment
#: plays - on a member's line or on the coupler's - is a pulse on top of that
#: line's standing bias
PAIR_FLUX_PULSE_ORIGIN = Requirement(
    "idle_flux", "the standing bias of the member's flux line and of the "
                 "coupler's: every flux amplitude here is a pulse on top of it")

#: the origin of a ``coupler_flux`` window (``_capabilities/coupler_flux.py``)
COUPLER_PULSE_ORIGIN = Requirement(
    "idle_flux", "the coupler window is an excursion from the coupler's standing "
                 "bias, and every position found is re-referenced to it")

#: a discriminator that is ALWAYS used - for an experiment whose instrument-side
#: arithmetic consumes the discriminated state of every shot. (The optional
#: case is the state_readout capability's own conditional pair.)
CALIBRATED_DISCRIMINATOR: tuple[Requirement, ...] = (
    Requirement("readout_rotation_rad",
                "every shot is discriminated: the axis it is projected on"),
    Requirement("readout_threshold",
                "every shot is discriminated: what splits |0> from |1> on that axis"),
)
