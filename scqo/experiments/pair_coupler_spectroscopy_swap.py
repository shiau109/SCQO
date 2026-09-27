"""The coupler's 0-1 frequency at its idle point, by swapping its excitation into a neighbour.

Per shot: reset both members -> a tone of frequency ``f`` on the PROBE member's drive
line (its ``saturation`` operation, ``tone_len_ns`` long, at ``tone_power_dbm``) ->
``flux_buffer_ns`` -> in the RAMP arm, a flux waveform on the ramped line: with
``ramp_v = (first, last)`` it jumps to ``first`` at once, runs linearly to ``last`` at
``ramp_rate_v_per_us``, and drops back to idle at once; in the REFERENCE arm, a wait
of the same length ->
``flux_buffer_ns`` -> both members read out 2-level. Loops: averages (outer) -> ``f``
(start -> end) -> the two arms back to back (inner), so drift cancels between them.

The coupler has no drive line; the tone reaches it through its hybridization with
the probe (a coupler Rabi of about ``g / delta`` of the probe's). At ``f = f_c`` the
coupler is excited. The slow ramp then carries the coupler across the probe
ADIABATICALLY - the excitation moves into the probe - and the sudden return is
diabatic, so it stays there; the probe's excited population peaks at ``f_c``. The
reference arm keeps the excitation in the coupler, so it shows only what the tone
does to the probe directly (its own transitions, the readout, a TLS). The scqat
estimator (``pair_coupler_spectroscopy_swap``) fits the ramp-minus-reference
difference and refuses a line the reference arm shares.

THE RAMP is ``ramp_v = (first, last)`` in PLAY order, and only its slow segment
(first -> last) is adiabatic: every crossing inside a jump (idle -> first, last ->
idle) is passed diabatically, and the member the slow segment crosses FIRST receives
the excitation. So ``(0, 0.14)`` swaps on the way out (slow out, fast back) and
``(0.14, 0)`` jumps out and swaps on the way BACK. On 5Q4C the second is the one that
works: the coupler (7.06 GHz) sits above the readout resonators (5.87-6.08 GHz),
which sit above the qubits, and swapping on the way back means the coupler crosses
the resonators again only after its excitation has gone to a qubit (2026-09-27; with
the coupler above both members the way back meets the OUTER one, the low member,
first). The slope sets the adiabaticity - Landau-Zener depends only on the rate at
which the crossing is passed: on 5Q4C q1_q2 the coupler slope at q1's crossing
(b = +0.109 V) is 22 MHz/mV, so 0.15 V/us is 99 % adiabatic at g = 50 MHz.

Every ramp voltage is a pulse amplitude relative to the ramped line's ``idle_flux``
(recorded as ``old_ramp_idle_flux``); ``ramp_v`` has no default - its far end comes
from ``pair_coupler_crossing_pulse``'s crossing plus about 30 mV.

ONE LO PER RUN: the tone window is ABSOLUTE and at most 500 MHz wide, played as
+-250 MHz of IF around one LO at its center. Proposes the coupler's ``f_01_hz`` (its
frequency at the CURRENT idle); no knob is written. One pair per run, as for
``pair_coupler_crossing_pulse``.
"""

from __future__ import annotations

import math
from typing import ClassVar, Literal

import numpy as np
from pydantic import Field, model_validator

from ..contract import DatasetContract
from ..experiment import Experiment
from ..parameters import AveragingParameters, TargetSelection
from ..result import Outcome, Result
from . import register
from ._capabilities.coupler_flux import pair_coupler
from ._capabilities.qubit_reset import QubitResetParameters
from ._capabilities.state_readout import joint_state_labels
from ._drive_power import drive_power_boundary
from ._sim import stable_seed
from ._window import refuse_zero_width, window_bounds
from .pair_coupler_crossing_pulse import one_coupled_pair_problems
from .pair_swap_chevron import _role_names

TONE_AXIS = "tone_freq_hz"
ARM_AXIS = "ramp_played"

#: the widest tone window one LO plays (+-250 MHz of IF around its center)
MAX_TONE_SPAN_HZ = 500e6
#: the ramp waveform is played on the 4 ns clock, 16 ns at least
_CLOCK_NS = 4
_MIN_RAMP_NS = 16

_FLAG_KEYS = ("no_peak", "multiple_peaks", "reference_feature", "peak_at_edge")


class PairCouplerSpectroscopySwapParameters(
    TargetSelection, AveragingParameters, QubitResetParameters,
):
    """Inputs for coupler spectroscopy by swap. ``targets`` is ONE pair component."""

    start_tone_freq_hz: float = Field(
        6.55e9, gt=0,
        description="First tone frequency (Hz, ABSOLUTE) on the probe's drive line. "
        "The probe walks start -> end in that order, either direction. Center the "
        "window on pair_coupler_crossing_pulse's f_c_at_idle_hz.")
    end_tone_freq_hz: float = Field(
        7.05e9, gt=0,
        description="Last tone frequency (Hz, absolute). The window is at most 500 MHz "
        "wide: one LO at its center plays it as +-250 MHz of IF.")
    num_tone_freq_points: int = Field(251, gt=4, description="Number of tone frequencies.")
    num_averages: int = Field(300, gt=0, description="Number of shots to average per sweep point.")
    tone_power_dbm: float = Field(
        -20.0, le=10.0,
        description="Tone power in dBm at the instrument's drive port, set for the run "
        "and restored exactly afterwards. The coupler is driven at about g/delta (a "
        "few %) of the probe's Rabi rate, so this is ~30 dB above a qubit "
        "saturation power.")
    tone_len_ns: float = Field(
        10000.0, ge=16, multiple_of=4,
        description="Tone length (ns, multiple of 4). Longer than the coupler's T1 "
        "saturates it; the swapped peak is then at most ~0.5.")
    probe: Literal["high", "low"] = Field(
        "high",
        description="The member that gets the tone and receives the coupler excitation "
        "(roster role). The SLOW segment of ramp_v must cross it first: with the "
        "coupler above both members that is 'high' for (0, far) and 'low' for "
        "(far, 0) with 'far' past both crossings.")
    ramp_on: Literal["coupler", "probe"] = Field(
        "coupler",
        description="Which flux line plays the ramp: the coupler's, or the probe's own "
        "(for a coupler designed below the qubit, or a qubit that can move toward it).")
    ramp_v: tuple[float, float] | None = Field(
        None,
        description="(first, last) pulse amplitudes (V, relative to the ramped line's "
        "idle_flux) in PLAY order: the output jumps to first at once, runs linearly to "
        "last at ramp_rate_v_per_us, and drops to idle at once. Only that slow segment "
        "is adiabatic - the member it crosses first receives the excitation, and every "
        "crossing inside a jump is passed diabatically. (0, 0.14) swaps on the way out; "
        "(0.14, 0) jumps out and swaps on the way back (the one that works on 5Q4C, "
        "where the readout resonators sit between the coupler and the qubits). The far "
        "end is pair_coupler_crossing_pulse's crossing plus ~30 mV. Required: None is "
        "refused before any instrument time.")
    ramp_rate_v_per_us: float = Field(
        0.15, gt=0,
        description="Slope of the slow segment (V/us). Landau-Zener depends only on it.")
    flux_buffer_ns: int = Field(
        100, ge=0,
        description="Wait after the tone before the ramp, and after the ramp before the "
        "readout: 0, or a multiple of 4 ns from 16 ns up.")

    @model_validator(mode="after")
    def _window_and_grid(self) -> "PairCouplerSpectroscopySwapParameters":
        refuse_zero_width(self.start_tone_freq_hz, self.end_tone_freq_hz,
                          start_name="start_tone_freq_hz", end_name="end_tone_freq_hz",
                          points_name="num_tone_freq_points")
        span = abs(self.end_tone_freq_hz - self.start_tone_freq_hz)
        if span > MAX_TONE_SPAN_HZ:
            raise ValueError(
                f"the tone window spans {span / 1e6:.0f} MHz; one run plays at most "
                f"{MAX_TONE_SPAN_HZ / 1e6:.0f} MHz (one LO, +-250 MHz of IF). Split it "
                f"into runs.")
        b = self.flux_buffer_ns
        if b != 0 and (b < 16 or b % 4):
            raise ValueError(f"flux_buffer_ns={b}: use 0, or a multiple of 4 ns from 16 ns up")
        if self.ramp_v is not None and self.ramp_v[0] == self.ramp_v[1]:
            raise ValueError(f"ramp_v={list(self.ramp_v)}: both ends are equal - the ramp "
                             f"would not move")
        return self


class PairCouplerSpectroscopySwapResult(Result):
    """``fit[pair]``: ``f_c_hz`` (with ``f_c_stderr_hz``), ``fwhm_hz``, ``peak_height``
    and ``snr`` of the strongest ramp-only line, ``n_peaks``, the flags ``no_peak``,
    ``multiple_peaks``, ``reference_feature``, ``peak_at_edge``, and the provenance
    ``lo_hz``, ``ramp_duration_ns``, ``old_ramp_idle_flux``. SUCCESSFUL = a line
    that is neither shared with the reference arm nor at the window edge. The other
    lines (a two-photon 0-2 transition, reference-arm features) are in the
    estimator's metadata JSON."""


def simulated_line(pair: str, start_hz: float, end_hz: float) -> dict:
    """The hidden coupler line (and a decoy both arms share) the simulator plants
    for ``pair`` over a tone window. Module-level so a test can compare."""
    lo, hi = window_bounds(start_hz, end_hz)
    span = hi - lo
    rng = np.random.default_rng(stable_seed("pair_coupler_spectroscopy_swap", pair))
    f_c = lo + float(rng.uniform(0.55, 0.75)) * span
    return {"f_c_hz": f_c, "fwhm_hz": span / 80, "height": 0.35,
            "decoy_hz": lo + float(rng.uniform(0.2, 0.35)) * span, "decoy_height": 0.25}


def _line(f: np.ndarray, center: float, height: float, fwhm: float) -> np.ndarray:
    return height / (1 + ((f - center) / (fwhm / 2)) ** 2)


@register
class PairCouplerSpectroscopySwap(Experiment):
    """Backend-agnostic coupler swap spectroscopy. ``probe()`` is supplied by a driver."""

    name: ClassVar[str] = "pair_coupler_spectroscopy_swap"
    description: ClassVar[str] = (
        "Coupler frequency at its idle point: a tone on one pair member's drive line "
        "excites the coupler when it hits f_c, then a slow flux ramp carries the "
        "coupler across that member so the excitation swaps into it (a sudden return "
        "leaves it there), and the member's population peaks at f_c. Every frequency "
        "also runs a reference shot without the ramp, which rejects lines that excite "
        "the member directly. The window is absolute, at most 500 MHz (one LO); the "
        "ramp end comes from pair_coupler_crossing_pulse. Proposes the coupler's "
        "f_01_hz. One pair per run; needs state discrimination."
    )
    Parameters: ClassVar[type] = PairCouplerSpectroscopySwapParameters
    Result: ClassVar[type] = PairCouplerSpectroscopySwapResult
    Contract: ClassVar[DatasetContract] = DatasetContract(
        # raw nesting order: frequency outer, the two arms inner
        sweeps=(TONE_AXIS, ARM_AXIS), sweep_units=("Hz", ""),
        variables=("joint_population",), readout_dims=("joint_state",),
    )
    target_kinds: ClassVar[tuple[str, ...]] = ("qubit_pair",)
    required_operations: ClassVar[tuple[str, ...]] = ()

    params: PairCouplerSpectroscopySwapParameters

    # ------------------------------------------------------------------ helpers
    def probe_member(self, pair: str) -> str:
        return self.device.roster.entities[pair].roles[self.params.probe][0]

    def ramp_line(self, pair: str) -> str:
        """The entity whose flux channel plays the ramp."""
        if self.params.ramp_on == "coupler":
            return pair_coupler(self.device.roster, pair)
        return self.probe_member(pair)

    def ramp_duration_ns(self) -> int:
        """The played slow segment: |last - first| at the requested slope, rounded UP
        to the 4 ns clock (so the realized slope is never steeper), 16 ns at least."""
        first, last = self.ramp_play_order()
        ns = abs(last - first) / self.params.ramp_rate_v_per_us * 1e3
        return max(_MIN_RAMP_NS, int(math.ceil(ns / _CLOCK_NS - 1e-9)) * _CLOCK_NS)

    def ramp_play_order(self) -> tuple[float, float]:
        """``ramp_v`` as floats: (first, last) AS PLAYED - the output jumps to ``first``
        at once, runs linearly to ``last``, and drops to idle at once."""
        first, last = self.params.ramp_v
        return float(first), float(last)

    def lo_hz(self) -> float:
        """The one LO the window is played around: its center."""
        return 0.5 * (self.params.start_tone_freq_hz + self.params.end_tone_freq_hz)

    # ------------------------------------------------------------------ physics
    def define_sweep(self) -> dict[str, np.ndarray]:
        p = self.params
        if p.ramp_v is None:
            raise ValueError(
                "ramp_v is required: (first, last) in play order, e.g. [0.14, 0] to jump "
                "past the crossings and swap on the slow way back. Take the far end from "
                "pair_coupler_crossing_pulse's crossings (crossing_<role>_upper_v or "
                "_lower_v, on the side the ramp goes) plus ~30 mV - 5Q4C q1_q2: 0.14 V.")
        if p.ramp_on == "probe":
            roster = self.device.roster
            for pair in p.targets:
                member = self.probe_member(pair)
                if (member, "flux") not in roster.defaults:
                    raise ValueError(f"{pair}: ramp_on='probe' but the probe {member!r} "
                                     f"has no flux channel to ramp")
        return {
            TONE_AXIS: np.linspace(p.start_tone_freq_hz, p.end_tone_freq_hz,
                                   p.num_tone_freq_points),
            ARM_AXIS: np.array([1, 0]),
        }

    def readout_coords(self) -> dict:
        return {"joint_state": joint_state_labels(2)}

    def run(self) -> Result:
        """define_sweep -> acquire inside the recorded tone-power boundary on the
        PROBE member's drive channel -> estimate."""
        self.sweep_axes = self.define_sweep()
        members = [self.probe_member(pair) for pair in self.params.targets]
        with drive_power_boundary(self, self.params.tone_power_dbm, targets=members):
            self.dataset = self.backend.acquire(self)
        self.Contract.validate(self.dataset)
        return self.run_estimate()

    def simulate(self, coords: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        """The planted line on the probe in the ramp arm only, a decoy on the probe in
        BOTH arms, members independent, sampled with ``num_averages`` shots."""
        f = coords[TONE_AXIS]
        arms = coords[ARM_AXIS]
        p = self.params
        joint = np.empty((len(p.targets), 4, f.size, arms.size))
        for k, pair in enumerate(p.targets):
            truth = simulated_line(pair, p.start_tone_freq_hz, p.end_tone_freq_hz)
            rng = np.random.default_rng(stable_seed("pair_coupler_spectroscopy_swap", pair,
                                                    "noise"))
            decoy = _line(f, truth["decoy_hz"], truth["decoy_height"], truth["fwhm_hz"])
            for a, arm in enumerate(arms):
                probe = 0.02 + decoy + (_line(f, truth["f_c_hz"], truth["height"],
                                              truth["fwhm_hz"]) if arm else 0.0)
                other = np.full(f.size, 0.02)
                ph, pl = (probe, other) if p.probe == "high" else (other, probe)
                probs = np.stack([(1 - ph) * (1 - pl), (1 - ph) * pl, ph * (1 - pl), ph * pl])
                for j in range(f.size):
                    joint[k, :, j, a] = (rng.multinomial(p.num_averages, probs[:, j])
                                         / p.num_averages)
        return {"joint_population": (("target", "joint_state", TONE_AXIS, ARM_AXIS), joint)}

    def estimate(self) -> PairCouplerSpectroscopySwapResult:
        assert self.dataset is not None, "run() populates self.dataset before estimate()"
        from scqat.estimators.pair_coupler_spectroscopy_swap import (
            PairCouplerSpectroscopySwapEstimator,
        )
        from .._scqat import per_qubit_results

        p = self.params
        names = _role_names(self.device, p.targets)
        played = getattr(self, "_ramp_duration_ns", None) or self.ramp_duration_ns()
        idle = {pair: self.anchor(self.ramp_line(pair), "idle_flux") for pair in p.targets}
        ds = self.dataset.transpose("target", "joint_state", TONE_AXIS, ARM_AXIS)
        results = per_qubit_results(
            ds, PairCouplerSpectroscopySwapEstimator(), artifact_dir=self.artifact_dir,
            per_target_kwargs=names, probe=p.probe, lo_hz=self.lo_hz(),
            ramp_duration_ns=float(played))

        result = PairCouplerSpectroscopySwapResult()
        for pair in p.targets:
            r = results[pair]
            fit: dict = {
                "f_c_hz": r["f_c_hz"], "f_c_stderr_hz": r["f_c_stderr_hz"],
                "fwhm_hz": r["fwhm_hz"], "peak_height": r["peak_height"], "snr": r["snr"],
                "n_peaks": int(r["n_peaks"]),
                "lo_hz": self.lo_hz(), "ramp_duration_ns": float(played),
                "old_ramp_idle_flux": idle[pair],
            }
            fit.update({flag: int(r[flag]) for flag in _FLAG_KEYS})
            result.fit[pair] = fit
            result.outcomes[pair] = Outcome.SUCCESSFUL if r["success"] else Outcome.FAILED
        return result

    def update(self) -> None:
        """One SUCCESSFUL pair: the coupler's ``f_01_hz`` (its frequency at the current
        idle). No knob moves."""
        if self.result is None or len(self.result.fit) != 1:
            return
        for pair, fit in self.result.fit.items():
            if self.result.outcomes[pair] is not Outcome.SUCCESSFUL:
                continue
            self.device.component(pair_coupler(self.device.roster, pair)).f_01_hz = fit["f_c_hz"]

    @classmethod
    def validate_targets(cls, roster, targets):
        """One pair with a coupler flux line and two drivable, readable members (the
        same gate as ``pair_coupler_crossing_pulse``)."""
        return one_coupled_pair_problems(roster, targets)

    def probe(self):  # pragma: no cover - driver half
        raise NotImplementedError("a driver backend supplies probe()")
