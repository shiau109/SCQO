"""Sequence-diagram fragments several experiments share.

The pieces of ``Experiment.sequence_diagram`` that are not one capability's
business (a capability's own fragment lives in its module: ``reset_step`` in
``_capabilities/qubit_reset.py``, ``measure_step`` in ``state_readout.py``).
Kept here so that two experiments drawing the same thing draw it the same way.
"""

from __future__ import annotations

from ..parameters import Parameters
from ..sequence_diagram import Block, SequenceDiagram
from ._capabilities.qubit_reset import reset_step

#: lane sets, by role. Copy before mutating: ``SequenceDiagram(dict(READOUT_ONLY))``.
READOUT_ONLY = {"readout": "q.ro"}
DRIVE_READOUT = {"drive": "q.xy", "readout": "q.ro"}


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
