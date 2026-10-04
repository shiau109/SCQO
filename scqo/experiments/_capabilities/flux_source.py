"""Flux-source capability: a SECOND flux line pulsed alongside the target's own.

An experiment HAS this capability exactly when its Parameters subclass
:class:`FluxSourcePulseSweepParameters`; the catalog derives ``"flux_source"`` from
that subclass relation (never from a declared string). The capability owns the
source line's name, its swept window (canonical names and texts), the swept-axis
name (``SOURCE_FLUX_AXIS``), the window's origin (:func:`source_anchor_v`) and the
roster gate (:func:`source_line_problems`).

WHAT IT IS FOR: flux crosstalk. A flux line that is not the target's own - another
qubit's z line, a coupler's - still threads a little flux through the target's
SQUID. The carrier plays a pulse on that SOURCE line while the target is probed on
its own line, and reads how far the target's flux apex slides. Vocabulary: the
measured qubit is the TARGET and the other line is the SOURCE line; a matrix cell is
``m(target <- source line)``.

NOT ``flux_component``: that field sweeps another entity's line INSTEAD of the
target's own, which leaves a target parked at its apex with a response that is
quadratic in the source amplitude and blind to its sign. Here both lines play in
the same shot, so the target's own line stays the ruler.

THE SOURCE IS NAMED BY ITS LINE (``z2``, ``zc12``), the way ``drive_line`` names a
drive line: the bias a pulse rides on belongs to the wire, and the cell being
measured is (source line, target).

ONE FRAME ONLY: RELATIVE. The probe PLAYS the source pulse on top of that line's
standing bias, so 0 is "the source line stays at its ``idle_flux``". Every carrier
therefore ends its registered name in ``_pulse`` (pinned by
``tests/test_capabilities.py``) and records the origin as ``old_source_idle_flux``.

THE WINDOW IS A TRAVERSAL ORDER, as on every capability window: the probe walks
``start_source_flux_v`` -> ``end_source_flux_v`` either way and the dataset keeps
that order; scqat is direction-blind. Only a zero-width window is refused
(``.._window``). No rail bound here - the source port's rail, and the sum of its
standing bias and the excursion, are the backend's to refuse by name.

No safe default window exists across chips: a source qubit pulsed far enough
crosses the target's frequency, and a coupler pulsed toward its neighbours switches
their coupling on. The default is deliberately small; the carrier's description
says how to choose a wider one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field, model_validator

from ...parameters import Parameters
from .._window import refuse_zero_width

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ...experiment import Experiment

#: the swept-axis name: volts of the source-line pulse, relative to that line's idle.
SOURCE_FLUX_AXIS = "source_flux_v"

#: canonical field texts - a carrier overriding a DEFAULT re-declares the Field with
#: these constants, so the catalog text can never drift (test-enforced).
SOURCE_LINE_DESC = (
    "Roster flux LINE pulsed alongside the target's own (the crosstalk SOURCE), "
    "e.g. 'z2' (another qubit's z line) or 'zc12' (a coupler's). Not the target's "
    "own flux line. Required. One target per run."
)
START_SOURCE_FLUX_DESC = (
    "First source-line pulse amplitude (V) of the sweep, RELATIVE to that line's "
    "idle_flux (0 = the source line stays at its standing bias). The probe walks "
    "start_source_flux_v -> end_source_flux_v IN THAT ORDER, either direction, and "
    "the data keeps it; the fitted result does not depend on it."
)
END_SOURCE_FLUX_DESC = (
    "Last source-line pulse amplitude (V) of the sweep, relative to that line's "
    "idle_flux. May be above or below start_source_flux_v; only a zero-width window "
    "is refused. The backend refuses a window the source port cannot emit on top of "
    "its standing bias, naming the reachable range."
)
NUM_SOURCE_FLUX_DESC = "Number of source-line amplitudes."


class FluxSourcePulseSweepParameters(Parameters):
    """Mixin: the SOURCE flux line and its swept pulse window, RELATIVE to that
    line's ``idle_flux`` (canonical names). A traversal order; see the module
    docstring."""

    source_line: str | None = Field(None, description=SOURCE_LINE_DESC)
    start_source_flux_v: float = Field(-0.05, description=START_SOURCE_FLUX_DESC)
    end_source_flux_v: float = Field(0.05, description=END_SOURCE_FLUX_DESC)
    num_source_flux_points: int = Field(5, gt=1, description=NUM_SOURCE_FLUX_DESC)

    @model_validator(mode="after")
    def _source_window_spans(self) -> "FluxSourcePulseSweepParameters":
        refuse_zero_width(
            self.start_source_flux_v, self.end_source_flux_v,
            start_name="start_source_flux_v", end_name="end_source_flux_v",
            points_name="num_source_flux_points", quantity="source flux")
        line = self.source_line
        if line is not None and (not line or "." in line):
            raise ValueError(
                f"source_line={line!r}: name the flux LINE only (e.g. 'z2' or "
                f"'zc12'); the target comes from targets")
        return self


def source_flux_sweep(params: FluxSourcePulseSweepParameters) -> dict[str, np.ndarray]:
    """The define_sweep fragment: ``{SOURCE_FLUX_AXIS: linspace(start, end, n)}``
    - in THAT order, descending when ``start_source_flux_v > end_source_flux_v``."""
    return {
        SOURCE_FLUX_AXIS: np.linspace(
            params.start_source_flux_v, params.end_source_flux_v,
            params.num_source_flux_points)
    }


def source_line_problems(roster, source_line: str | None, targets) -> list[str]:
    """The roster gate of a flux-source carrier, as problem strings ([] when clear):
    a source line is named, it is a line of this roster that carries a flux channel,
    there is ONE target, and the source is not that target's own flux line."""
    flux_lines = sorted({c.line for c in roster.channels().values() if "flux" in c.kinds})
    if source_line is None:
        return [f"source_line is required: the flux line pulsed alongside the "
                f"target's own (flux lines of this roster: {', '.join(flux_lines)})"]
    problems = []
    if len(targets) != 1:
        problems.append(
            f"{list(targets)}: one target per run - two targets in superposition "
            f"shift each other's fringes, and the source moves that shift")
    if source_line not in roster.lines():
        problems.append(
            f"source_line={source_line!r} is not a line of this roster (flux lines: "
            f"{', '.join(flux_lines)})")
        return problems
    if source_line not in flux_lines:
        problems.append(
            f"source_line={source_line!r} carries no flux channel (flux lines: "
            f"{', '.join(flux_lines)})")
        return problems
    for target in targets:
        own = roster.defaults.get((target, "flux"))
        if own is not None and roster.entities[own].line == source_line:
            problems.append(
                f"source_line={source_line!r} is {target}'s OWN flux line - its "
                f"response to that line is the arch itself (flux_per_phi0), not a "
                f"crosstalk; name another flux line")
    return problems


def source_anchor_v(experiment: "Experiment") -> float:
    """The origin the source window is measured from: the source line's
    ``idle_flux``.

    Read through ``Experiment.anchor``, which falls back to ``design.toml``
    (tagging the run ``seeded:``) and otherwise raises a bring-up instruction
    rather than fitting around garbage.
    """
    return experiment.anchor(experiment.params.source_line, "idle_flux")
