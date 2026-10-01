"""N repeated partial swaps read by two-qubit state tomography.

Excite ONE member of a pair, repeat the pair's swap ``N`` times with a FIXED
AC-Stark tone between swaps — the round of ``qc_n_stark_amp``, unchanged — and
then measure both members in the nine two-qubit Pauli bases (each member rotated
so the measured axis lands on Z: ``z`` nothing, ``x`` -Y90, ``y`` +X90). The
sweep is ``stark_amp`` (a short explicit list) x ``swap_count`` x ``basis``.

WHAT THE TOMOGRAPHY BUYS. In the single-excitation subspace one round is a
rotation ``Rz(phi) Rx(2 theta)``. Populations alone see only the composite
angle, ``cos(theta_eff) = cos(phi/2) cos(theta)`` — which is why
``qc_n_stark_amp`` has to scan the stark amplitude for the slowest oscillation.
The tomographic trajectory separates the two at ANY stark amplitude, so one
N-sweep gives:

* ``theta_rad`` — the exchange angle per step (proposed as the operation's
  ``theta_rad`` monitor, like ``qc_n_stark_amp``);
* ``phase_at_theta_amp_rad`` and, across two or more stark amplitudes,
  ``compensating_stark_amp`` — where the per-step phase crosses zero;
* the incoherent error per step: each member's T1 loss, the dephasing of the
  single-excitation coherence, the prep error, the growth of ``|11>`` — and,
  with ``round_duration_ns`` and both members' measured T1/T2*, what T1/T2*
  alone predict and the excess over it.

WHAT IT DOES NOT MEASURE: the detuning. A detuned exchange is exactly an
equatorial one of a slightly smaller angle between two equal Z rotations, so the
detuning costs the angle only at second order (1 MHz over 40 ns: -0.26 %) and
otherwise hides in the per-step phase together with the frame, stark and
pulse-edge phases. The resonance stays with ``qc_swap_flux_stark``.

READOUT. Digital, both modes (``readout_mode``), member order (high, low). A
readout CALIBRATION block is measured in the same run
(``readout_calibration_shots`` per prepared basis state ``00 .. 11``) and stored,
always averaged, as ``calibration_population @ (target, prepared_state,
joint_state)``: the analysis inverts that 4x4 confusion, crosstalk between the
two multiplexed readouts included. With 0 shots it falls back to the members'
stored ``fidelity_g`` / ``fidelity_e`` (a product, no crosstalk).

The phase belongs to the ROUND, so a compensation from here is valid only at the
round length it was measured at — exactly as ``qc_n_stark_amp``'s.
"""

from __future__ import annotations

import sys
from typing import ClassVar, Literal

import numpy as np
import xarray as xr
from pydantic import Field, field_validator

from ..contract import ContractError, DatasetContract
from ..experiment import FACT_MEASURED, Experiment
from ..parameters import AveragingParameters, TargetSelection
from ..result import Outcome, Result
from . import register
from ._capabilities.qubit_reset import QubitResetParameters
from ._capabilities.state_readout import (
    ReadoutModeParameters,
    joint_state_labels,
    states_to_joint_population,
)
from ._sim import stable_seed
from .pair_swap_chevron import DRIVE_SIDE_DESC, FLUX_SIDE_DESC, _flux_member_problems, _role_names

#: the nine measurement bases, first character = the HIGH member. Mirrors
#: ``scqat.tools.two_qubit_tomography.BASIS_LABELS`` (simulate() must not import
#: scqat); the drivers read the pre-rotations off these labels.
BASIS_LABELS: tuple[str, ...] = tuple(a + b for a in "zxy" for b in "zxy")
#: the calibration block's prepared basis states (digit order high, low).
PREPARED_STATES: tuple[str, ...] = ("00", "01", "10", "11")

#: scalar fit keys lifted from the scqat metadata into ``result.fit``.
FIT_KEYS = (
    "theta_rad", "theta_rad_err", "theta_spread_rad", "theta_consistency_sigma",
    "theta_stark_amp",
    "phase_at_theta_amp_rad", "compensating_stark_amp", "compensation_extrapolated",
    "t1_loss_per_step_high", "t1_loss_per_step_low", "dephasing_per_step",
    "prep_error", "leak_to_11_per_step", "predicted_t1_loss_high",
    "predicted_t1_loss_low", "predicted_dephasing", "excess_dephasing_per_step",
    "fit_rms", "n_fit_ok",
)

#: the theta_rad proposal needs residuals under this (features are populations
#: and Bloch components, so 0.08 is a broken model, not shot noise).
MAX_FIT_RMS = 0.08
#: ...and an angle that agrees across stark amplitudes: every amplitude's fit
#: within this many combined standard errors of the reported one. In SIGMA, not
#: radians: far from compensation the angle is several times less certain.
MAX_THETA_DEVIATION_SIGMA = 3.0


class QcNSwapTomographyParameters(TargetSelection, AveragingParameters,
                                  QubitResetParameters, ReadoutModeParameters):
    """Inputs for the repeated-swap tomography. ``targets`` are PAIR components."""

    swap_operation: str = Field(
        "iswap",
        description="The named pair operation repeated each round, played at its FIXED "
                    "baked amplitudes (the driver resolves it on the vendor pair). Meant "
                    "for a PARTIAL swap; the tomography reads any angle up to pi/2.")
    swap_counts: list[int] = Field(
        default_factory=lambda: list(range(11)),
        description="The swap counts N (rounds) to apply. Must include 0 (the prepared "
                    "state, which also fixes the prep error) and hold at least four "
                    "distinct non-negative counts. About half an oscillation (pi/(2 "
                    "theta) counts) is enough: the 3D trajectory fixes the angle.")
    stark_amps: list[float] = Field(
        default_factory=lambda: [0.0],
        description="The stark tone amplitudes (factors of the stark operation's baked "
                    "amplitude) - a short explicit list. One value measures theta and the "
                    "phase there; two or more also locate the compensating amplitude, "
                    "where the per-step phase crosses zero (best bracketing it, e.g. the "
                    "expected value +-0.05).")
    stark_operation: str = Field(
        "stark",
        description="The off-resonant XY operation played on the control member in every "
                    "round (as in qc_n_stark_amp).")
    stark_detuning_hz: float = Field(
        50e6, description="FIXED detuning (Hz) of the stark tone from the control's drive "
                          "frequency.")
    operation_gap_ns: int = Field(
        0, ge=0,
        description="Idle (ns) on the pair's flux lines between each swap and its stark "
                    "tone. 0 disables; the QM backend requires a multiple of 4 ns. Part of "
                    "the round length, so of the phase.")
    drive_side: Literal["high", "low"] = Field("low", description=DRIVE_SIDE_DESC)
    flux_side: Literal["high", "low"] = Field("low", description=FLUX_SIDE_DESC)
    readout_calibration_shots: int = Field(
        1000, ge=0,
        description="Shots per prepared basis state (00, 01, 10, 11) of the in-run readout "
                    "calibration the analysis inverts. 0 skips it; the analysis then uses "
                    "the members' stored fidelity_g/fidelity_e (no readout crosstalk).")
    round_duration_ns: float | None = Field(
        None, gt=0,
        description="ANALYSIS ONLY: the real length of one round (swap + gap + stark + "
                    "program overhead; 368 ns on 5Q4C at gap 260). With it and both "
                    "members' measured T1/T2*, the fit reports what T1/T2* alone predict "
                    "per step and the excess. Changes nothing that plays.")

    @field_validator("swap_counts")
    @classmethod
    def _counts(cls, v: list[int]) -> list[int]:
        if len(set(v)) != len(v):
            raise ValueError("swap_counts must not repeat a count")
        if any(n < 0 for n in v):
            raise ValueError("swap_counts must be non-negative")
        if 0 not in v:
            raise ValueError("swap_counts must include 0 (the prepared state)")
        if len(v) < 4:
            raise ValueError("swap_counts needs at least four counts to fit a rotation")
        return v

    @field_validator("stark_amps")
    @classmethod
    def _amps(cls, v: list[float]) -> list[float]:
        if not v:
            raise ValueError("stark_amps needs at least one amplitude")
        if len(set(v)) != len(v):
            raise ValueError("stark_amps must not repeat an amplitude")
        if any(not (0.0 <= a < 2.0) for a in v):
            raise ValueError("each stark amplitude factor must lie in [0, 2)")
        return v


class QcNSwapTomographyResult(Result):
    """``fit[pair]``: the channel read off the tomography — ``theta_rad`` (+ its
    error, its spread across stark amplitudes in radians and in combined standard
    errors, ``theta_consistency_sigma``; ``theta_stark_amp`` = the amplitude it was
    taken at), the per-step phase there, the
    ``compensating_stark_amp`` (NaN with one amplitude;
    ``compensation_extrapolated`` = 1 when outside the swept list), the
    incoherent error per step (``t1_loss_per_step_high/low``,
    ``dephasing_per_step``, ``prep_error``, ``leak_to_11_per_step``), the T1/T2*
    predictions and the excess dephasing (NaN without ``round_duration_ns`` and
    measured T1/T2*), ``fit_rms``, ``n_fit_ok``, and ``readout_calibrated`` /
    ``readout_corrected`` (1/0: in-run calibration used / any correction used).
    The per-amplitude columns stay in the scqat metadata."""


class _TomographyContract(DatasetContract):
    """The swept tomography plus, when present, the calibration block's shape."""

    def validate(self, ds: xr.Dataset) -> None:
        super().validate(ds)
        if "calibration_population" in ds.data_vars:
            dims = set(ds["calibration_population"].dims)
            want = {self.target_dim, "prepared_state", "joint_state"}
            if dims != want:
                raise ContractError(
                    f"calibration_population has dims {tuple(dims)}, expected "
                    f"{tuple(sorted(want))}")


@register
class QcNSwapTomography(Experiment):
    """Backend-agnostic repeated-swap tomography. ``probe()`` is supplied by a driver."""

    name: ClassVar[str] = "qc_n_swap_tomography"
    description: ClassVar[str] = (
        "Repeated partial swaps read by two-qubit state tomography: excite ONE member of a "
        "pair, repeat its swap N times with a fixed AC-Stark tone between swaps (the "
        "qc_n_stark_amp round), then measure both members in the nine Pauli bases. Fitting "
        "the swap as a channel gives, from one N sweep, the exchange angle per step (proposed "
        "as the operation's theta_rad monitor), the relative Z phase per step - with two or "
        "more stark amplitudes, the compensating amplitude where it crosses zero - and the "
        "incoherent error per step (each member's T1 loss, dephasing, prep error, |11> "
        "growth; with round_duration_ns and measured T1/T2*, the excess over T1/T2*). Replaces "
        "qc_n_stark_amp's stark x N scan for the angle; the resonance stays with "
        "qc_swap_flux_stark (a detuning is invisible here beyond second order). The readout "
        "is calibrated in the same run (4x4 confusion incl. crosstalk). QM only."
    )
    Parameters: ClassVar[type] = QcNSwapTomographyParameters
    Result: ClassVar[type] = QcNSwapTomographyResult
    Contract: ClassVar[DatasetContract] = _TomographyContract(
        sweeps=("stark_amp", "swap_count", "basis"), sweep_units=("", "", ""),
        variables=("joint_population",), readout_dims=("joint_state",),
        alt_variables=(("state",),),
        alt_readout_dims=(("member", "shot_idx"),),
    )
    target_kinds: ClassVar[tuple[str, ...]] = ("qubit_pair",)
    #: none, as qc_n_stark_amp: the operations are what this experiment tunes.
    required_operations: ClassVar[tuple[str, ...]] = ()

    params: QcNSwapTomographyParameters

    def define_sweep(self) -> dict[str, np.ndarray]:
        return {
            "stark_amp": np.array(self.params.stark_amps, dtype=float),
            "swap_count": np.array(self.params.swap_counts, dtype=int),
            "basis": np.array(BASIS_LABELS),
        }

    def readout_coords(self) -> dict:
        coords = {"joint_state": joint_state_labels(2),
                  "prepared_state": list(PREPARED_STATES)}
        if self.params.readout_mode == "shot":
            coords.update({"member": ["high", "low"],
                           "shot_idx": np.arange(self.params.num_averages)})
        return coords

    # ------------------------------------------------------------ the model
    def _readout_fidelities(self, member: str) -> tuple[float, float] | None:
        try:
            view = self.device.channel(member, "readout")
            fg, fe = getattr(view, "fidelity_g"), getattr(view, "fidelity_e")
        except Exception:
            return None
        if fg is None or fe is None:
            return None
        return float(fg), float(fe)

    def _members(self, pair: str) -> tuple[str, str]:
        names = _role_names(self.device, [pair])[pair]
        return names["high_name"], names["low_name"]

    def simulate(self, coords: dict[str, np.ndarray]) -> dict[str, tuple]:
        """The channel the analysis fits, run forward and measured shot by shot.

        Hidden truth per pair (seeded): the angle is the operation's theta_rad
        monitor when the roster declares the operation and it is set, else drawn
        in [0.15, 0.5]; the per-step phase is ``phi0 + 2 pi a^2`` (one full turn
        at a = 1); T1 loss ~0.017, dephasing ~0.05 and a 3 % prep error per
        step; the readout confusion is the product of the members' stored
        fidelities (0.95 / 0.92 when unset)."""
        amps = coords["stark_amp"].astype(float)
        counts = coords["swap_count"].astype(int)
        shots = int(self.params.num_averages)
        shot_mode = self.params.readout_mode == "shot"
        excite_high = self.params.drive_side == "high"
        n_cal = int(self.params.readout_calibration_shots)
        per_pair, per_cal = [], []
        for pair in self.params.targets:
            rng = np.random.default_rng(stable_seed("qc_n_swap_tomography", pair))
            theta = self._planted_theta(pair, rng)
            phi0 = float(rng.uniform(-np.pi, np.pi))
            a_off = float(rng.uniform(-np.pi, np.pi))
            decay = (float(rng.uniform(0.012, 0.022)), float(rng.uniform(0.012, 0.022)),
                     float(rng.uniform(0.03, 0.07)), float(rng.uniform(0.01, 0.04)))
            high, low = self._members(pair)
            m = _confusion(self._readout_fidelities(high) or (0.95, 0.92),
                           self._readout_fidelities(low) or (0.95, 0.92))
            probs = np.zeros((amps.size, counts.size, len(BASIS_LABELS), 4))
            for i, a in enumerate(amps):
                states = _channel_states(theta, phi0 + 2 * np.pi * a ** 2, a_off,
                                         *decay, int(counts.max()), excite_high)
                for k, label in enumerate(BASIS_LABELS):
                    u = np.kron(_PRE[label[0]], _PRE[label[1]])
                    for j, n in enumerate(counts):
                        p = np.clip(np.real(np.diag(u @ states[n] @ u.conj().T)), 0.0, None)
                        probs[i, j, k] = m @ (p / p.sum())
            if shot_mode:
                cum = np.cumsum(probs, axis=-1)
                u = rng.random((*probs.shape[:-1], shots))
                code = (u[..., None, :] > cum[..., :, None]).sum(axis=-2)  # (a, n, b, shot)
                per_pair.append(np.stack([code // 2, code % 2]).astype(np.int64))
            else:
                flat = probs.reshape(-1, 4)
                drawn = np.array([rng.multinomial(shots, p / p.sum()) for p in flat]) / shots
                per_pair.append(np.moveaxis(drawn.reshape(probs.shape), -1, 0))
            if n_cal > 0:
                per_cal.append(np.array([rng.multinomial(n_cal, m[:, k]) / n_cal
                                         for k in range(4)]))
        out: dict[str, tuple] = {}
        if shot_mode:
            out["state"] = (("target", "member", "stark_amp", "swap_count", "basis",
                             "shot_idx"), np.stack(per_pair))
        else:
            out["joint_population"] = (("target", "joint_state", "stark_amp", "swap_count",
                                        "basis"), np.stack(per_pair))
        if per_cal:
            out["calibration_population"] = (("target", "prepared_state", "joint_state"),
                                             np.stack(per_cal))
        return out

    def _planted_theta(self, pair: str, rng) -> float:
        entity = f"{pair}.{self.params.swap_operation}"
        drawn = float(rng.uniform(0.15, 0.5))
        roster = getattr(self.device, "roster", None)
        if roster is None or entity not in roster:
            return drawn
        try:
            value = self.device.operation(pair, self.params.swap_operation).read_knob("theta_rad")
        except Exception:
            value = None
        return float(value) if value is not None and 0.0 < float(value) < np.pi / 2 else drawn

    # ------------------------------------------------------------ analysis
    def _decay_kwargs(self, pair: str) -> dict:
        high, low = self._members(pair)
        out = {"high_name": high, "low_name": low}
        fid_high, fid_low = self._readout_fidelities(high), self._readout_fidelities(low)
        if fid_high is not None and fid_low is not None:
            out.update(fid_high=fid_high, fid_low=fid_low)
        for key, (member, field) in {"t1_high_s": (high, "t1_s"), "t1_low_s": (low, "t1_s"),
                                     "t2_star_high_s": (high, "t2_star_s"),
                                     "t2_star_low_s": (low, "t2_star_s")}.items():
            value, tier = self.fact_sourced(member, field)
            if value is not None and tier == FACT_MEASURED:
                out[key] = float(value)
        return out

    def estimate(self) -> QcNSwapTomographyResult:
        assert self.dataset is not None, "run() populates self.dataset before estimate()"
        if "state" in self.dataset.data_vars:
            jp = states_to_joint_population(self.dataset["state"],
                                            member_dim="member", shot_dim="shot_idx")
            ds = jp.to_dataset()
        else:
            ds = self.dataset[["joint_population"]]
        ds = ds.transpose("target", "joint_state", "stark_amp", "swap_count", "basis")
        if "calibration_population" in self.dataset.data_vars:
            ds["calibration_population"] = self.dataset["calibration_population"]

        from scqat.estimators.qc_n_swap_tomography import QcNSwapTomographyEstimator
        from .._scqat import per_qubit_results

        analysis = per_qubit_results(
            ds, QcNSwapTomographyEstimator(), artifact_dir=self.artifact_dir,
            drive_side=self.params.drive_side,
            round_duration_ns=self.params.round_duration_ns,
            per_target_kwargs={pair: self._decay_kwargs(pair) for pair in self.params.targets})

        result = QcNSwapTomographyResult()
        for pair in self.params.targets:
            fit_in = analysis.get(pair, {})
            fit = {key: float(fit_in.get(key, float("nan"))) for key in FIT_KEYS}
            how = fit_in.get("readout_correction", "none")
            fit["readout_calibrated"] = float(how == "calibration")
            fit["readout_corrected"] = float(how in ("calibration", "stored_product"))
            result.fit[pair] = fit
            ok = int(fit_in.get("success", 0)) == 1 and np.isfinite(fit["theta_rad"])
            result.outcomes[pair] = Outcome.SUCCESSFUL if ok else Outcome.FAILED
        return result

    def update(self) -> None:
        """Propose the exchange angle as the swap operation's ``theta_rad``
        monitor — gated on the fit (residuals, and an angle that does not move
        with the stark amplitude), and only for a DECLARED operation."""
        if self.result is None:
            return
        op = self.params.swap_operation
        for pair, fit in self.result.fit.items():
            if self.result.outcomes[pair] is not Outcome.SUCCESSFUL:
                continue
            theta = fit["theta_rad"]
            consistent = (not np.isfinite(fit["theta_consistency_sigma"])
                          or fit["theta_consistency_sigma"] <= MAX_THETA_DEVIATION_SIGMA)
            if not (np.isfinite(theta) and fit["fit_rms"] <= MAX_FIT_RMS and consistent):
                continue
            entity = f"{pair}.{op}"
            if entity not in self.device.roster:
                print(f"scqo: {entity} is not declared in the roster, so its "
                      f"theta_rad ({theta:.4f} rad) has nowhere to go - add "
                      f"{op!r} to [composites.{pair}].operations to keep it",
                      file=sys.stderr)
                continue
            self.device.operation(pair, op).write_knob("theta_rad", float(theta))

    @classmethod
    def validate_targets(cls, roster, targets):
        """The swap rides a member's flux line, as in ``qc_n_stark_amp``."""
        return _flux_member_problems(roster, targets, "nothing to play the swap pulse on")

    def probe(self):  # pragma: no cover - driver half
        raise NotImplementedError("a driver backend supplies probe()")


# ---------------------------------------------------------------- forward model
# A compact numpy twin of scqat.tools.swap_channel (simulate() must not import
# scqat): basis |high low> = |00>,|01>,|10>,|11>.
_I2 = np.eye(2)
_X = np.array([[0, 1], [1, 0]], dtype=complex)
_Y = np.array([[0, -1j], [1j, 0]], dtype=complex)
_PRE = {"z": _I2,
        "x": np.cos(-np.pi / 4) * _I2 - 1j * np.sin(-np.pi / 4) * _Y,   # -Y90
        "y": np.cos(np.pi / 4) * _I2 - 1j * np.sin(np.pi / 4) * _X}     # +X90


def _confusion(fid_high: tuple[float, float], fid_low: tuple[float, float]) -> np.ndarray:
    def one(fg, fe):
        return np.array([[fg, 1.0 - fe], [1.0 - fg, fe]])
    return np.kron(one(*fid_high), one(*fid_low))


def _channel_states(theta, phi, a_off, p_high, p_low, lam, eps, n_max, excite_high):
    sm = np.array([[0.0, 1.0], [0.0, 0.0]])
    swap = np.eye(4, dtype=complex)
    swap[1, 1] = swap[2, 2] = np.cos(theta)
    swap[1, 2] = swap[2, 1] = -1j * np.sin(theta)

    def zhigh(angle):
        return np.diag([1.0, 1.0, np.exp(-1j * angle), np.exp(-1j * angle)])

    step = zhigh(phi) @ swap
    kraus = [
        [np.kron(np.diag([1.0, np.sqrt(1 - p_high)]), _I2), np.kron(np.sqrt(p_high) * sm, _I2)],
        [np.kron(_I2, np.diag([1.0, np.sqrt(1 - p_low)])), np.kron(_I2, np.sqrt(p_low) * sm)],
        [np.sqrt(1 - lam / 2) * np.eye(4), np.sqrt(lam / 2) * np.kron(np.diag([1.0, -1.0]), _I2)],
    ]
    rho = np.zeros((4, 4), dtype=complex)
    rho[2 if excite_high else 1, 2 if excite_high else 1] = 1.0 - eps
    rho[0, 0] = eps
    record = zhigh(a_off)
    out = []
    for _ in range(n_max + 1):
        out.append(record @ rho @ record.conj().T)
        rho = step @ rho @ step.conj().T
        for ks in kraus:
            rho = sum(k @ rho @ k.conj().T for k in ks)
    return out
