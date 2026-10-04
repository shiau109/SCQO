"""Sequence-diagram fragments several experiments share.

The pieces of ``Experiment.sequence_diagram`` that are not one capability's
business (a capability's own fragment lives in its module: ``reset_step`` in
``_capabilities/qubit_reset.py``, ``measure_step`` in ``state_readout.py``).
Kept here so that two experiments drawing the same thing draw it the same way.
"""

from __future__ import annotations

from typing import Callable

from ..parameters import Parameters
from ..sequence_diagram import Block, SequenceDiagram
from ._capabilities.flux import FLUX_AXIS
from ._capabilities.qubit_reset import reset_step

#: lane sets, by role. Copy before mutating: ``SequenceDiagram(dict(READOUT_ONLY))``.
READOUT_ONLY = {"readout": "q.ro"}
DRIVE_READOUT = {"drive": "q.xy", "readout": "q.ro"}


def flux_lane(params: Parameters) -> str:
    """The label of the flux lane: the target's own line, or the SOURCE line
    when ``flux_component`` names another entity's (the crosstalk vocabulary:
    the measured qubit is the target, the other line the source)."""
    foreign = getattr(params, "flux_component", None) is not None
    return "source.z" if foreign else "q.z"


def drive_flux_readout(params: Parameters) -> dict[str, str]:
    """Drive, flux and readout lanes of a flux experiment on a driven qubit."""
    return {"drive": "q.xy", "flux": flux_lane(params), "readout": "q.ro"}


def echo_steps(diagram: SequenceDiagram, arm: Callable[[], None], *,
               drive: str = "drive") -> None:
    """The Hahn echo's three pulses. ``arm()`` adds each of the two idle arms
    between them: a plain wait, or a wait under a flux pulse."""
    diagram.step(Block(drive, "x90", "gate"))
    arm()
    diagram.step(Block(drive, "x180", "gate"))
    arm()
    diagram.step(Block(drive, "x90", "gate"))


def flux_pulse_idle_step(diagram: SequenceDiagram, label: str, time_axis: str, *,
                         note: str | None = None, drive: str = "drive",
                         flux: str = "flux") -> None:
    """An idle with a flux pulse held for all of it. The pulse's amplitude is
    the flux axis and its length is the idle, so it carries both axes."""
    diagram.step(
        Block(drive, label, "wait", swept=time_axis),
        Block(flux, "flux pulse", "square", swept=(FLUX_AXIS, time_axis), note=note))


#: the readout lane of a pair experiment: both members, read together
PAIR_READOUT_LANE = "pair.ro"

#: what the closing readout of a joint-population experiment returns
JOINT_READOUT_NOTE = ("both members, discriminated in every shot: the dataset "
                      "holds the joint populations")


def pair_measure_step(diagram: SequenceDiagram, *, readout: str = "readout",
                      note: str = JOINT_READOUT_NOTE) -> None:
    """The closing readout of a pair experiment: both members at once."""
    diagram.step(Block(readout, "readout", "acquire", note=note))


def swap_chain_lanes(params: Parameters, **extra: str) -> dict[str, str]:
    """The lanes of a repeated-swap experiment: the excited member's drive line,
    the flux line that carries the swap, any ``extra`` lanes, the joint readout.
    The members are named by ROLE, from ``drive_side`` / ``flux_side``."""
    return {"drive": f"{params.drive_side}.xy", "flux": f"{params.flux_side}.z",
            **extra, "readout": PAIR_READOUT_LANE}


#: footnotes of the repeated round's blocks
SWAP_STORED_NOTE = "the swap_operation's pulses, at their stored amplitudes"
SWAP_SWEPT_NOTE = ("the swap_operation: its member pulse at the swept amplitude, "
                   "its coupler pulse as stored")
STARK_NOTE = "off-resonant by stark_detuning_hz; its stored amplitude times stark_amp"


def swap_rounds(diagram: SequenceDiagram, params: Parameters, label: str, *,
                count_axis: str | None = None, flux_axis: str | None = None,
                stark_axis: str | None = None, stark: bool = True) -> None:
    """The repeated round of the swap-chain experiments, in a repeat bracket:
    the swap, the gap when ``operation_gap_ns`` asks for one, and the stark
    tone on the excited member. An axis argument names the sweep axis that
    block (or the count itself) varies with."""
    with diagram.repeat(label, swept=count_axis):
        diagram.step(Block("flux", "swap", "flattop", swept=flux_axis,
                           note=SWAP_SWEPT_NOTE if flux_axis else SWAP_STORED_NOTE))
        if getattr(params, "operation_gap_ns", 0):
            diagram.step(Block("flux", "gap", "wait"))
        if stark:
            diagram.step(Block("drive", "stark", "tone", swept=stark_axis,
                               note=STARK_NOTE))


def joint_measure_step(diagram: SequenceDiagram, params: Parameters) -> None:
    """``pair_measure_step`` for an experiment with a ``readout_mode``: the
    footnote says which of the two forms the dataset holds."""
    if getattr(params, "readout_mode", "average") == "shot":
        pair_measure_step(diagram, note="both members, discriminated: every "
                                        "shot's two levels are kept")
    else:
        pair_measure_step(diagram)


def depletion_step(diagram: SequenceDiagram, *, readout: str = "readout") -> None:
    """The wait after a readout for its photons to leave the resonator - the
    readout channel's ``readout_depletion_s`` (``_depletion.depletion_wait_ns``)."""
    diagram.step(Block(readout, "depletion", "wait"))


def prepared_state_steps(diagram: SequenceDiagram, params: Parameters, *,
                         drive: str = "drive", readout: str = "readout") -> None:
    """How the readout calibrations prepare the state they then read: the
    reset, and an x180 played only when the prepared state is |e>. The
    ``prepared_state`` axis is marked on that pulse."""
    reset_step(diagram, params, drive=drive, readout=readout)
    diagram.step(Block(drive, "x180", "gate", swept="prepared_state",
                       note="played only when the prepared state is e"))
