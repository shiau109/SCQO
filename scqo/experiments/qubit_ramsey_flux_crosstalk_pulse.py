"""Flux crosstalk onto a qubit from another flux line - the Ramsey apex vs a source pulse.

A flux line that is not the target's own (the SOURCE line: another qubit's z line, a
coupler's) still threads a little flux through the target's SQUID. Seen from the
target, a source move of ``b`` volts acts like its own line moving by ``m * b``, so
its flux apex - located on its OWN line - slides by ``-m * b``. This experiment reads
that slide and reports the signed ``m``.

Per shot: reset -> y90 at the idle point -> buffer -> for the whole idle ``tau`` the
target's own z line plays a square pulse of relative amplitude ``a`` AND the source
line plays one of relative amplitude ``b`` -> buffer -> x90 at the idle point ->
readout at the idle point. It is ``qubit_ramsey_flux_pulse``'s sequence with one more
line pulsed. Loops: averages (outer) -> ``b`` -> ``a`` -> ``tau`` (inner), so every
(a, b) point shares the same drift. With ``source_lead_time_ns`` the source pulse
starts that long BEFORE the own-line pulse (it is then already on during the first
pi/2 pulse) and the two still end together, so the fringe reads the crosstalk that
long after the source step.

Reading: at each ``b`` the fringes over ``a`` give the local arch and its apex
position; the apex positions follow a straight line in ``b`` whose slope is ``-m``.
The ruler is the target's own line, so no arch model and no stored fact enters, and
what moves the apex HEIGHT without moving its position - a coupler's dispersive
shift on its neighbour - is reported separately (``apex_height_span_hz``) and never
mistaken for crosstalk.

FRAMES (``_pulse`` in the name): both windows are excursions from the line's own
``idle_flux`` - the target's (``FluxPulseSweepParameters``) and the source's
(``FluxSourcePulseSweepParameters``). ``m`` is a ratio of two PULSE amplitudes of
the idle's length (16 ns to ``max_idle_time_ns``), read ``source_lead_time_ns`` after
the source step. It is NOT the DC coefficient: on 5Q4C a DC move of a coupler line
reads 6-9 percentage points above the 1.6 us pulse value on every target
(2026-10-04), which is why the lead time is a parameter.

LEAD TIME AND DUTY CYCLE: a lead lengthens every shot by itself, and the source is
then on for ``lead / (lead + reset wait)`` of the time. A response slower than the
shot period follows that duty cycle and not the step, so a long lead reads a mix;
lengthen the reset wait (``thermalization_time_ns``) to tell the two apart.

CHOOSING THE SOURCE WINDOW: keep the source away from anything that moves the
target without flux. A source QUBIT pulsed far enough reaches the target's frequency
(5Q4C: z3 at +-53 mV puts q3 on q1) and a COUPLER pulsed toward its neighbours
switches their exchange on (5Q4C: the swaps use +64..+111 mV). The default window
is small on purpose.

FOLDING: as in ``qubit_ramsey_flux_pulse`` the fringe sits at
``|D + (f_q - f_drive)|`` and ``define_sweep`` picks the sign of ``D`` from the arch
facts, here over the own window WIDENED by ``SOURCE_REACH`` times the largest source
amplitude (the apex may slide that far); a window that would still fold, or that the
idle grid cannot sample, is refused before any instrument time.

RECORD-ONLY: nothing is proposed. A crosstalk coefficient has no catalog home yet.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np
from pydantic import Field, model_validator

from ..contract import DatasetContract
from ..estimate_inputs import acquisition_note, note_acquisition
from ..experiment import Experiment
from ..parameters import AveragingParameters, TargetSelection
from ..requirements import Requirement
from ..result import Outcome, Result
from ..sequence_diagram import Block, SequenceDiagram, held
from . import register
from ._capabilities.flux import (
    END_FLUX_PULSE_DESC,
    FLUX_AXIS,
    NUM_FLUX_DESC,
    START_FLUX_PULSE_DESC,
    FluxPulseSweepParameters,
    flux_anchor_v,
    flux_sweep,
)
from ._capabilities.flux_source import (
    NUM_SOURCE_FLUX_DESC,
    SOURCE_FLUX_AXIS,
    FluxSourcePulseSweepParameters,
    source_anchor_v,
    source_flux_sweep,
    source_line_problems,
)
from ._capabilities.qubit_reset import QubitResetParameters, reset_step
from ._capabilities.state_readout import (
    POPULATION_ALT,
    StateReadoutParameters,
    measure_step,
    population_row,
    readout_vars,
    signal_rename,
)
from ._requires import CALIBRATED_READOUT
from ._sim import iq_from_population, stable_seed
from ._time_grid import time_axis_ns

NAME = "qubit_ramsey_flux_crosstalk_pulse"

#: EC used for the fold prediction when the target carries no ``ec_hz`` fact
_DEFAULT_EC_HZ = 0.2e9
#: a detuning must exceed the smaller-side excursion by this factor
FOLD_MARGIN = 1.5
#: the largest fringe may use this fraction of the idle grid's Nyquist frequency
NYQUIST_FRACTION = 0.8
#: the crosstalk assumed when sizing the fold check: the apex may slide this fraction
#: of the largest source amplitude along the target's own line
SOURCE_REACH = 0.1

#: the estimator's scalars lifted onto result.fit when finite
_SCALARS = ("curvature_hz_per_v2", "apex_height_span_hz", "line_residual_rms_v",
            "line_max_residual_v")
_COUNTS = ("n_source_points", "n_valid_source_points", "n_apex_not_bracketed",
           "nonlinear_suspected", "fold_suspected")


class QubitRamseyFluxCrosstalkPulseParameters(
    TargetSelection, AveragingParameters, StateReadoutParameters, QubitResetParameters,
    FluxPulseSweepParameters, FluxSourcePulseSweepParameters,
):
    """Inputs for the crosstalk map: the target's own window and the source's, both
    relative to their line's idle_flux. ``targets`` is ONE qubit."""

    # capability defaults narrowed to a local-arch window (canonical text constants)
    start_flux_v: float = Field(-0.02, description=START_FLUX_PULSE_DESC)
    end_flux_v: float = Field(0.02, description=END_FLUX_PULSE_DESC)
    num_flux_points: int = Field(
        7, gt=4, description=NUM_FLUX_DESC + " (the local quadratic needs >= 5 "
        "resolved points at every source amplitude).")
    num_source_flux_points: int = Field(
        5, gt=2, description=NUM_SOURCE_FLUX_DESC + " The apex line needs >= 3.")
    num_averages: int = Field(200, gt=0, description="Number of shots to average per sweep point.")
    frequency_detuning_hz: float = Field(
        4.0e6, gt=0,
        description="MAGNITUDE of the virtual detuning; the experiment picks its sign "
        "so the qubit's excursion pushes the fringe away from zero (see ramp_sign_from "
        "in the fit). Must exceed the smaller-side excursion over the window by 1.5x.")
    min_idle_time_ns: float = Field(
        16, ge=16, description="Shortest idle = pulse length on both lines (ns); 16 ns "
        "is the shortest pulse every backend plays.")
    max_idle_time_ns: float = Field(
        1600, gt=0, description="Longest idle = pulse length on both lines (ns).")
    num_idle_points: int = Field(
        100, gt=4, description="Number of idle-time points (4 ns grid). The default is a "
        "16 ns step: +-20 mV off the apex the fringe already runs at 10-20 MHz.")
    flux_buffer_ns: int = Field(
        20, ge=0,
        description="Wait at the idle point on BOTH sides of the flux pulses, so neither "
        "pi/2 pulse overlaps their edges: 0, or a multiple of 4 ns from 16 ns up.")
    source_lead_time_ns: int = Field(
        0, ge=0,
        description="How long the SOURCE pulse is already on when the own-line pulse "
        "(the fringe's idle) starts; the two end together. 0 = they start together. The "
        "fringe then reads the crosstalk from this long after the source step, so a "
        "crosstalk that depends on the pulse length is mapped by repeating the run at "
        "several values. A multiple of 4 ns. Every shot lengthens by it, and the source "
        "is then on for lead / (lead + reset wait) of the time: a response slower than "
        "the shot period follows that duty cycle, not the step (lengthen "
        "thermalization_time_ns to tell).")

    @model_validator(mode="after")
    def _buffer_on_grid(self) -> "QubitRamseyFluxCrosstalkPulseParameters":
        b = self.flux_buffer_ns
        if b != 0 and (b < 16 or b % 4):
            raise ValueError(
                f"flux_buffer_ns={b}: use 0, or a multiple of 4 ns from 16 ns up "
                f"(a shorter nonzero wait is not playable on every backend)")
        if self.source_lead_time_ns % 4:
            raise ValueError(
                f"source_lead_time_ns={self.source_lead_time_ns}: use a multiple of 4 ns "
                f"(the grid every backend plays on)")
        return self


class QubitRamseyFluxCrosstalkPulseResult(Result):
    """``fit[target]``: the signed ``flux_crosstalk`` (``m``: one volt on the source
    line acts on the target like ``m`` volts on its own) with ``flux_crosstalk_stderr``,
    and the apex at zero source amplitude (``flux_offset_from_idle``, the target's own
    frame); ``curvature_hz_per_v2``, ``apex_height_span_hz`` (how far the apex HEIGHT
    moved over the source window - not crosstalk), the line's ``line_residual_rms_v``
    / ``line_max_residual_v``, the counts ``n_source_points`` /
    ``n_valid_source_points`` / ``n_apex_not_bracketed``, the 0/1 flags
    ``nonlinear_suspected`` / ``fold_suspected``, and provenance (``source_line``,
    ``source_lead_time_ns``, ``old_idle_flux``, ``old_source_idle_flux``,
    ``old_drive_freq_hz``, ``ramp_detuning_hz``, ``ramp_sign_from``). SUCCESSFUL = a line through >= 3
    source amplitudes with neither flag set."""


def simulated_crosstalk(target: str, params) -> dict:
    """The hidden truth the simulator plants for ``target`` under ``params``.

    The crosstalk is scaled to the windows, so the apex slides visibly (10-30 % of
    the own half-window at the largest source amplitude) yet stays bracketed at every
    source amplitude. Module-level so a test can compare the fit against the truth."""
    half = max(abs(params.start_flux_v), abs(params.end_flux_v), 1e-6)
    reach = max(abs(params.start_source_flux_v), abs(params.end_source_flux_v), 1e-6)
    amp = params.frequency_detuning_hz
    rng = np.random.default_rng(stable_seed(NAME, target, str(params.source_line)))
    sign = 1.0 if rng.uniform() < 0.5 else -1.0
    return {
        "crosstalk": sign * float(rng.uniform(0.1, 0.3)) * half / reach,
        "apex_v": float(rng.uniform(-0.15, 0.15)) * half,
        "curvature_hz_per_v2": -0.4 * amp / (1.7 * half) ** 2,
        "height_hz": float(rng.uniform(-0.05, 0.05)) * amp,
        "height_shift_hz": float(rng.uniform(0.0, 0.05)) * amp,
        "source_reach_v": reach,
        "t2_s": float(rng.uniform(8e-6, 15e-6)),
    }


@register
class QubitRamseyFluxCrosstalkPulse(Experiment):
    """Backend-agnostic flux-crosstalk map. ``probe()`` is supplied by a driver."""

    name: ClassVar[str] = NAME
    requires: ClassVar[tuple[Requirement, ...]] = (
        Requirement("idle_flux",
                    "both flux windows are excursions from a standing bias, the "
                    "target line's and the source line's; the pi/2 pulses and the "
                    "readout are played at the target's"),
        Requirement("drive_freq_hz",
                    "every fringe is measured against it; at the idle point the "
                    "qubit has to sit on it"),
        *CALIBRATED_READOUT,
    )
    extracts: ClassVar[dict[str, str]] = {
        "flux_crosstalk": "the signed coefficient m: one volt on the source line "
                          "acts on the target like m volts on its own line",
        "flux_crosstalk_stderr": "the fit's standard error on m",
        "flux_offset_from_idle": "the target's apex at zero source amplitude, as an "
                                 "excursion from its idle flux",
        "flux_offset_from_idle_stderr": "the fit's standard error on that apex",
        "curvature_hz_per_v2": "the curvature of the target's local arch",
        "apex_height_span_hz": "how far the HEIGHT of the apex moved over the source "
                               "window: a shift of the qubit that is not crosstalk",
        "line_residual_rms_v": "the rms distance of the apex positions from the "
                               "fitted straight line",
        "line_max_residual_v": "the largest such distance",
        "n_source_points": "the number of source amplitudes",
        "n_valid_source_points": "how many of them gave an apex; the line needs 3",
        "n_apex_not_bracketed": "how many had their apex outside the own-line window",
        "nonlinear_suspected": "1 when the apex positions do not follow a straight "
                               "line; the run fails",
        "fold_suspected": "1 when a fringe may have folded through zero frequency; "
                          "the run fails",
        "source_line": "the flux line that was pulsed as the source",
        "source_lead_time_ns": "how long the source pulse was already on when the "
                               "own-line pulse started",
        "old_idle_flux": "the target line's idle flux: the origin of its window",
        "old_source_idle_flux": "the source line's idle flux: the origin of its "
                                "window",
        "old_drive_freq_hz": "the drive frequency every fringe was measured against",
        "ramp_detuning_hz": "the SIGNED virtual detuning that was applied",
        "ramp_sign_from": "where that sign came from: 'facts' (predicted from the "
                          "arch facts) or 'default'",
    }
    #: the source line has no default; on the demo device the other qubit's z line
    doc_parameters: ClassVar[dict] = {"source_line": "z_q1"}

    @classmethod
    def sequence_diagram(
            cls, params: QubitRamseyFluxCrosstalkPulseParameters) -> SequenceDiagram:
        diagram = SequenceDiagram({
            "drive": "q.xy", "flux": "q.z", "source": "source.z", "readout": "q.ro"})
        lead = bool(params.source_lead_time_ns)
        source = Block(
            "source", "source pulse", "square",
            swept=(SOURCE_FLUX_AXIS, "idle_time_ns"),
            note=("starts source_lead_time_ns before the own-line pulse; the two end "
                  "together" if lead else
                  "on the source line, an excursion from its idle_flux, as long as "
                  "the idle"))
        reset_step(diagram, params)
        diagram.step(Block("drive", "y90", "gate"), *([source] if lead else []))
        if params.flux_buffer_ns:
            diagram.step(Block("drive", "buffer", "wait"),
                         *([held("source")] if lead else []))
        diagram.step(
            Block("drive", "idle", "wait", swept="idle_time_ns"),
            Block("flux", "flux pulse", "square", swept=(FLUX_AXIS, "idle_time_ns"),
                  note="an excursion from idle_flux, as long as the idle"),
            held("source") if lead else source)
        if params.flux_buffer_ns:
            diagram.step(Block("drive", "buffer", "wait"))
        diagram.step(Block(
            "drive", "x90", "gate",
            note="its phase is ramped with the idle: a virtual detuning of signed "
                 "size frequency_detuning_hz"))
        measure_step(diagram, params)
        return diagram

    description: ClassVar[str] = (
        "Signed flux crosstalk onto ONE qubit from another flux line (source_line: "
        "another qubit's z line or a coupler's). A Ramsey fringe is taken with the "
        "target's own z line pulsed to a AND the source line pulsed to b during the "
        "idle (both relative to their idle_flux; the pi/2 pulses and the readout "
        "stay at the idle point). At each b the fringes over a locate the target's "
        "flux apex; the apex position moves by -m*b, and the slope gives m (one volt "
        "on the source acts like m volts on the target's own line). The apex HEIGHT, "
        "which a coupler moves without any crosstalk, is reported separately. "
        "Record-only: nothing is proposed. m is a ratio of two pulses of the idle's "
        "length and is NOT the DC coefficient (5Q4C: DC reads 6-9 points higher); "
        "source_lead_time_ns starts the source pulse earlier, so the same reading is "
        "taken that long after the source step. Choose the source window so the source stays "
        "away from the target's frequency (a qubit source) and from the exchange "
        "point (a coupler source). The existing flux_component on "
        "qubit_ramsey_flux_pulse sweeps the source INSTEAD of the own line and sees "
        "only |m|. QM only."
    )
    Parameters: ClassVar[type] = QubitRamseyFluxCrosstalkPulseParameters
    Result: ClassVar[type] = QubitRamseyFluxCrosstalkPulseResult
    Contract: ClassVar[DatasetContract] = DatasetContract(
        sweeps=(FLUX_AXIS, SOURCE_FLUX_AXIS, "idle_time_ns"),
        sweep_units=("V", "V", "ns"),
        variables=("I", "Q"), alt_variables=POPULATION_ALT,
    )
    required_operations: ClassVar[tuple[str, ...]] = ("rx", "readout", "flux_bias")
    #: stored blob centers ride the dataset -> the axial axis is the measured g->e vector
    attach_readout_positions: ClassVar[bool] = True

    params: QubitRamseyFluxCrosstalkPulseParameters

    # ------------------------------------------------------------------ sweep
    def define_sweep(self) -> dict[str, np.ndarray]:
        p = self.params
        roster = getattr(self.device, "roster", None)
        if roster is not None:
            problems = source_line_problems(roster, p.source_line, p.targets)
        elif p.source_line is None:
            problems = ["source_line is required: the flux line pulsed alongside the "
                        "target's own"]
        else:
            problems = []
        if problems:
            raise ValueError("; ".join(problems))
        axes = {
            **flux_sweep(p),
            **source_flux_sweep(p),
            "idle_time_ns": time_axis_ns(p.min_idle_time_ns, p.max_idle_time_ns,
                                         p.num_idle_points, grid_ns=4),
        }
        self._ramps = self._resolve_ramps(axes)
        return axes

    def _resolve_ramps(self, axes: dict[str, np.ndarray]) -> dict[str, dict]:
        """Per target: the SIGNED detuning and where its sign came from. The ONE
        place the direction is decided; the probe spends the number via
        :meth:`ramp_detuning_hz`."""
        p = self.params
        amp = p.frequency_detuning_hz
        idle = axes["idle_time_ns"]
        step_s = float(np.min(np.diff(np.sort(idle)))) * 1e-9 if idle.size > 1 else np.nan
        nyquist = 0.5 / step_s if step_s > 0 else np.inf
        # the apex may slide along the own line by the crosstalk times the source move
        reach = SOURCE_REACH * float(np.max(np.abs(axes[SOURCE_FLUX_AXIS])))
        window = np.linspace(float(np.min(axes[FLUX_AXIS])) - reach,
                             float(np.max(axes[FLUX_AXIS])) + reach, 101)
        ramps: dict[str, dict] = {}
        for q in p.targets:
            excursion = self._predicted_excursion(q, window)
            if excursion is None:
                # the apex case: the qubit can only drop below its drive
                ramps[q] = {"ramp_detuning_hz": -amp, "ramp_sign_from": "default"}
                continue
            e_min, e_max = excursion
            # the side the qubit swings further to pushes the fringe; the other one limits A
            sign = -1.0 if -e_min >= e_max else 1.0
            limit = max(0.0, e_max) if sign < 0 else max(0.0, -e_min)
            if amp < FOLD_MARGIN * limit:
                raise ValueError(
                    f"{q}: folding_risk - the window moves the qubit {limit / 1e6:.3f} MHz "
                    f"to the side the detuning cannot cover; raise frequency_detuning_hz "
                    f"to >= {FOLD_MARGIN * limit / 1e6:.3f} MHz or narrow the window")
            top = amp + max(abs(e_min), abs(e_max))
            if top > NYQUIST_FRACTION * nyquist:
                raise ValueError(
                    f"{q}: undersampled - the fringe reaches {top / 1e6:.3f} MHz but the "
                    f"idle grid resolves {NYQUIST_FRACTION * nyquist / 1e6:.3f} MHz; shorten "
                    f"the idle step (more num_idle_points or a smaller max_idle_time_ns) "
                    f"or narrow the windows")
            ramps[q] = {"ramp_detuning_hz": sign * amp, "ramp_sign_from": "facts"}
        return ramps

    def _predicted_excursion(self, q: str, window: np.ndarray) -> tuple[float, float] | None:
        """(min, max) of f_q - f_drive over the (widened) own window, from the arch
        facts; None when a fact is missing (the default sign is used instead)."""
        try:
            f_max = self.fact(q, "f_q_max_hz", None)
            offset = self.fact(q, "flux_offset", None)
            period = self.fact(q, "flux_per_phi0", None)
            if f_max is None or offset is None or not period:
                return None
            ec = self.fact(q, "ec_hz", _DEFAULT_EC_HZ)
            idle = self.anchor(q, "idle_flux")
            drive = self.anchor(q, "drive_freq_hz")
        except (AttributeError, KeyError, ValueError):
            # no device model to read facts from (a bare backend): same as missing
            return None
        x = idle + window
        f = (f_max + ec) * np.sqrt(np.abs(np.cos(np.pi * (x - offset) / period))) - ec
        err = f - drive
        return float(np.min(err)), float(np.max(err))

    def ramp_detuning_hz(self, target: str) -> float:
        """The signed virtual detuning a probe applies for ``target`` (the
        ``qubit_ramsey`` convention: the fringe sits at ``|D + (f_q - f_drive)|``)."""
        ramps = getattr(self, "_ramps", None)
        if ramps is None:  # a caller that skipped define_sweep (define_sweep caches it)
            ramps = self._resolve_ramps(self.sweep_axes or self.define_sweep())
        return float(ramps[target]["ramp_detuning_hz"])

    # ------------------------------------------------------------------ run
    def run(self) -> Result:
        """define_sweep -> acquire -> the resolved ramps ride the dataset -> estimate."""
        self.sweep_axes = self.define_sweep()
        self.dataset = self.backend.acquire(self)
        self.Contract.validate(self.dataset)
        self._attach_reference_positions()
        self.attach_acquisition_coords()
        note_acquisition(self.dataset, "ramps", self._ramps)
        return self.run_estimate()

    def simulate(self, coords: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        """The planted truth (:func:`simulated_crosstalk`) seen through the fringe the
        probe records: ``delta_f(a, b) = h(b) - k (a - a0 + m b)^2``. The planted
        crosstalk has no time dependence, so ``source_lead_time_ns`` changes nothing
        here."""
        flux = coords[FLUX_AXIS]
        source = coords[SOURCE_FLUX_AXIS]
        t = coords["idle_time_ns"] * 1e-9
        targets = self.params.targets
        use_state = self.params.use_state_discrimination
        shape = (len(targets), flux.size, source.size, t.size)
        i_data, q_data, state = np.empty(shape), np.empty(shape), np.empty(shape)
        for k, q in enumerate(targets):
            truth = simulated_crosstalk(q, self.params)
            ramp = self.ramp_detuning_hz(q)
            rng = np.random.default_rng(stable_seed(NAME, q, "noise"))
            apex = truth["apex_v"] - truth["crosstalk"] * source
            height = (truth["height_hz"]
                      + truth["height_shift_hz"] * (source / truth["source_reach_v"]) ** 2)
            delta = (height[None, :]
                     + truth["curvature_hz_per_v2"] * (flux[:, None] - apex[None, :]) ** 2)
            fringe = np.abs(ramp + delta)
            pop = 0.5 - 0.45 * np.exp(-t / truth["t2_s"]) * np.cos(
                2 * np.pi * fringe[..., None] * t)
            # ONE readout geometry per target: every fringe shares the reduction axis
            if use_state:
                state[k] = population_row(pop.ravel(), rng).reshape(pop.shape)
            else:
                i_row, q_row = iq_from_population(pop.ravel(), rng)
                i_data[k], q_data[k] = i_row.reshape(pop.shape), q_row.reshape(pop.shape)
        return readout_vars(use_state, state, i_data, q_data)

    # ------------------------------------------------------------------ estimate
    def estimate(self) -> QubitRamseyFluxCrosstalkPulseResult:
        assert self.dataset is not None, "run() populates self.dataset before estimate()"
        from scqat.estimators.qubit_ramsey_flux_crosstalk import (
            QubitRamseyFluxCrosstalkEstimator,
        )
        from .._scqat import per_qubit_results

        p = self.params
        ramps = (acquisition_note(self.dataset, "ramps", None)
                 or getattr(self, "_ramps", None) or {})
        rename = signal_rename(self.dataset, {FLUX_AXIS: "flux_bias",
                                              SOURCE_FLUX_AXIS: "source_flux",
                                              "idle_time_ns": "idle_time"})
        prepared = self.dataset.rename(rename)
        prepared = prepared.assign_coords(idle_time=prepared["idle_time"] * 1e-9)
        drives = {q: float(self.anchor(q, "drive_freq_hz")) for q in p.targets}
        per_target = {q: {"ramp_detuning_hz": float(ramps[q]["ramp_detuning_hz"]),
                          "drive_freq_hz": drives[q]} for q in p.targets}
        results = per_qubit_results(prepared, QubitRamseyFluxCrosstalkEstimator(),
                                    artifact_dir=self.artifact_dir,
                                    per_target_kwargs=per_target)

        old_source = source_anchor_v(self)
        result = QubitRamseyFluxCrosstalkPulseResult()
        for q in p.targets:
            r = results[q]
            fit: dict = {
                "source_line": p.source_line,
                "source_lead_time_ns": float(p.source_lead_time_ns),
                "old_idle_flux": flux_anchor_v(self, q),
                "old_source_idle_flux": old_source,
                "old_drive_freq_hz": drives[q],
                "ramp_detuning_hz": float(ramps[q]["ramp_detuning_hz"]),
                "ramp_sign_from": str(ramps[q]["ramp_sign_from"]),
            }
            fit.update({key: int(r[key]) for key in _COUNTS})
            fit.update({key: float(r[key]) for key in _SCALARS if np.isfinite(r[key])})
            if r["success"]:
                fit.update(
                    flux_crosstalk=float(r["flux_crosstalk"]),
                    flux_crosstalk_stderr=float(r["flux_crosstalk_stderr"]),
                    flux_offset_from_idle=float(r["apex_flux_at_zero_source"]),
                    flux_offset_from_idle_stderr=float(r["apex_flux_at_zero_source_stderr"]),
                )
            result.fit[q] = fit
            ok = (bool(r["success"]) and not r["nonlinear_suspected"]
                  and not r["fold_suspected"])
            result.outcomes[q] = Outcome.SUCCESSFUL if ok else Outcome.FAILED
        return result

    def update(self) -> None:
        """Record-only. The coefficient is a property of (source line, target) and
        the catalog has no field for one yet; the apex at zero source amplitude is
        ``qubit_ramsey_flux_pulse``'s to propose, on a window made for parking."""

    def probe(self):  # pragma: no cover - driver half
        raise NotImplementedError("a driver backend supplies probe()")
