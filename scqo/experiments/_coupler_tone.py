"""The coupler tone both coupler spectroscopies play (``pair_coupler_spectroscopy_swap``
and ``pair_coupler_spectroscopy_zz``).

The coupler has no drive line: a tone on one pair member's drive line reaches it
through the member-coupler hybridization, at about ``g / delta`` of the member's Rabi
rate, so it is played ~30 dB above a qubit saturation tone. The window is ABSOLUTE
Hz (the coupler is far from any drive frequency a detuning could hang on) and at most
500 MHz wide: one LO at its center plays it as +-250 MHz of IF. The tone rides on the
member's ``saturation`` operation at ``tone_power_dbm``, which ``run()`` sets for the
run and restores exactly (``_drive_power.drive_power_boundary``).

A plain Parameters mixin, not a capability: it is the shared window of two
experiments of one family, with no mode of its own to classify by.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from ..parameters import Parameters
from ..requirements import Requirement
from ._window import refuse_zero_width

TONE_AXIS = "tone_freq_hz"

#: the widest tone window one LO plays (+-250 MHz of IF around its center)
MAX_TONE_SPAN_HZ = 500e6

#: the tone's power is set through the tone member's drive chain for the run and
#: put back afterwards (``_drive_power.drive_power_boundary``), which refuses a
#: chain with no standing value to return to
TONE_DRIVE_CHAIN = Requirement(
    "drive_power_dbm", "the run moves the tone member's drive chain to "
                       "tone_power_dbm and restores this value afterwards, so one "
                       "has to be set")

#: the footnote of the tone block in both experiments' sequence diagrams
TONE_NOTE = "tone_len_ns long at tone_power_dbm, on a member's drive line"

#: the ``extracts`` entries both experiments share: the f01 line, the ladder
#: and the flags (each adds its own height / depth and provenance keys)
COUPLER_LINE_EXTRACTS: dict[str, str] = {
    "f_c_hz": "the coupler's 0-1 frequency: the highest of its lines. Proposed as "
              "f_01_hz",
    "f_c_stderr_hz": "the standard error of that frequency",
    "fwhm_hz": "the width of that line",
    "snr": "the height of that line over the noise of the trace",
    "alpha_hz": "the coupler's anharmonicity, from the f02/2 line; NaN when that "
                "line was not found. Proposed as anharmonicity_hz",
    "alpha_stderr_hz": "the standard error of the anharmonicity",
    "n_ladder_lines": "how many of the coupler's lines sit on the multi-photon "
                      "ladder of f01, f01 included",
    "lo_hz": "the local oscillator the window was played around: its centre",
    "no_line": "1 when no coupler line was found",
    "unexplained_lines": "1 when a coupler line sits off the ladder; the run fails",
    "peak_at_edge": "1 when f01 is at the edge of the window; the run fails",
}


class CouplerToneParameters(Parameters):
    """The coupler tone's window, points, power and length."""

    start_tone_freq_hz: float = Field(
        6.55e9, gt=0,
        description="First tone frequency (Hz, ABSOLUTE) on the drive line that carries "
        "the tone. The probe walks start -> end in that order, either direction. Center "
        "the window on pair_coupler_crossing_pulse's f_c_at_idle_hz, or on a coupler "
        "f01 already measured.")
    end_tone_freq_hz: float = Field(
        7.05e9, gt=0,
        description="Last tone frequency (Hz, absolute). The window is at most 500 MHz "
        "wide: one LO at its center plays it as +-250 MHz of IF.")
    num_tone_freq_points: int = Field(
        501, gt=4,
        description="Number of tone frequencies. The default steps 1 MHz over 500 MHz: "
        "f01 is 4-7 MHz wide at -20 dBm, and a line under two steps wide is ignored. "
        "Measure a narrower line (f02/2) with a narrower window or more points.")
    tone_power_dbm: float = Field(
        -20.0, le=10.0,
        description="Tone power in dBm at the instrument's drive port, set for the run "
        "and restored exactly afterwards. The coupler is driven at about g/delta (a "
        "few %) of the member's Rabi rate, so this is ~30 dB above a qubit "
        "saturation power.")
    tone_len_ns: float = Field(
        10000.0, ge=16, multiple_of=4,
        description="Tone length (ns, multiple of 4). Longer than the coupler's T1 "
        "saturates it (5Q4C q1_q2_c: T1 ~5 us).")

    @model_validator(mode="after")
    def _tone_window(self) -> "CouplerToneParameters":
        refuse_zero_width(self.start_tone_freq_hz, self.end_tone_freq_hz,
                          start_name="start_tone_freq_hz", end_name="end_tone_freq_hz",
                          points_name="num_tone_freq_points")
        span = abs(self.end_tone_freq_hz - self.start_tone_freq_hz)
        if span > MAX_TONE_SPAN_HZ:
            raise ValueError(
                f"the tone window spans {span / 1e6:.0f} MHz; one run plays at most "
                f"{MAX_TONE_SPAN_HZ / 1e6:.0f} MHz (one LO, +-250 MHz of IF). Split it "
                f"into runs.")
        return self


def tone_lo_hz(params: CouplerToneParameters) -> float:
    """The one LO the window is played around: its center."""
    return 0.5 * (params.start_tone_freq_hz + params.end_tone_freq_hz)
