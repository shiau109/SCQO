---
name: pair-partial-swap
description: Develop or re-tune a square partial-swap operation of a target angle theta on one qubit pair, played at the swap resonance, and measure its per-round stark compensation. Use when a Trotter chain or any repeated-swap experiment needs a new swap angle, or when an existing angle has drifted.
goal: A stored operation partial_swap_<t> on the pair whose per-swap angle, read from the N-oscillation period, is theta +- 0.01 rad, with its control z pulse at the fitted resonance.
inputs:
  pair: roster pair name, e.g. q1_q2
  theta_rad: target per-swap angle, e.g. 0.30
  swap_time_ns: square pulse length, 40 on 5Q4C
outputs:
  operation: macro partial_swap_<t> playing partial_swap_square_<t> (t = theta x 100, three digits; 0.30 -> 030)
  z_amp_v: control-qubit z pulse amplitude (the resonance)
  coupler_amp_v: coupler pulse amplitude (sets the angle)
  theta_rad: period-based angle actually reached
  compensating_stark_amp: per-round compensation at the round length used, with that round length
experiments: [single_shot_readout, pair_swap_flux_map, qc_swap_flux_stark, qc_n_stark_amp]
backends: [qm]
validated: hardware 5Q4C q1_q2 + q2_q3, 2026-09-22 (theta = 0.30)
---

# pair-partial-swap

## Physics in brief

- The swap angle is θ = J(Φc)·t. J is set by the coupler pulse amplitude, which rides on
  the coupler's `decouple_offset` (a pulse, never the line voltage). t is the pulse length.
  The control qubit's z pulse brings it into resonance with its partner.
- Repeated swaps add up (transfer sin²(Nθ)) only when the relative phase the pair picks up
  per round is compensated. The compensating element is a stark tone on the moving qubit.
  That phase depends on the **round length** modulo 1/Δ, where Δ is the pair's frequency
  difference. q1_q2 on 5Q4C: Δ = 301 MHz, so one 4 ns clock cycle is 0.2 turn. A
  compensation amplitude means nothing without the round length it was measured at.

## Prerequisites

1. **Fresh readout on both members.** Run `single_shot_readout` on both qubits and accept its
   suggestions at the start of the session, and again after hours. The pair experiments
   discriminate with the *stored* threshold and rotation. A stale one zeroes a member
   silently (see Traps).
2. The moving qubit carries the `stark` xy operation (`scqo-qm/quam_config/register_stark.py`)
   and a chosen `stark_detuning_hz` (5Q4C: 50 MHz).
3. Converting a compensation amplitude into a phase also needs that qubit's measured phase(a)
   curve from `qubit_stark_phase_echo` plotdata. Never use the fitted k for this: the Stark
   shift saturates.

## Steps

### Step 1: starting point from the flux map

- **Run** `pair_swap_flux_map --targets <pair>` with `swap_time_ns` equal to the operation's
  length. Use a coupler window from the off point up to θ ≈ 1 rad (5Q4C: q1_q2 0.07–0.11 V,
  q2_q3 0.06–0.09 V) and a qubit window of ±5 mV around the known resonance.
- **Read** the per-column `theta_rad` and `resonance_qubit_flux_v` from
  `analysis/<pair>/pair_swap_flux_map_plotdata.nc`. `result.fit` holds only the summary.
- **Decide**:
  - **Coupler start:** where the per-column θ crosses the target, interpolated between
    successfully fitted columns.
  - **Flux-map bias:** the flux map's θ differs from the period-based θ of Step 4 by 0–10% at
    small angles. If an earlier operation on the pair has a known period θ, scale by that
    ratio.
  - **z start:** the column's resonance, or the pair's last `qc_swap_flux_stark` resonance.

### Step 2: register the operation

The operation is three entries in the setup's QUAM tree
(`<data_root>/<device>/<cycle>/<setup>/backend_config/state.json`):

- `qubit_control.z.operations["partial_swap_square_<t>"]`: `SquarePulse(amplitude=z start, length)`
- `coupler.operations["partial_swap_square_<t>"]`: `SquarePulse(amplitude=coupler start, length)`
- `macros["partial_swap_<t>"]`: `ISwapImplementation(flux_pulse="partial_swap_square_<t>")`

Load and save through the QM backend of `build_session()`, so it is the setup's own folder,
with `machine.save(path=state_dir)`. Copy `state.json` and `wiring.json` aside first, save to
a staging folder, and write the live folder only after checking that the saved tree differs
by these three entries alone. Re-tuning later changes the two amplitudes only.

Tool: pending, see Open issues. The 2026-09-22 session used a scratch script with exactly
this contract.

### Step 3: the resonance, and the compensation at this round length

- **Run** `qc_swap_flux_stark --targets <pair>` with:
  - `swap_operation=partial_swap_<t>`
  - `swap_count` N with N·θ ≲ 1.2. For θ = 0.30 use N = 4. N·θ must stay below π/2, or the
    arch folds.
  - `swap_angle_rad=θ`
  - a flux window of ±3.5 mV around the z start (31 points)
  - stark 0–1.0 (31 points); widen to 1.3 when the compensation sits near an edge
  - the chosen `operation_gap_ns` (see Traps: round length)
  - `num_averages=200`
- **Read**:
  - `resonance_flux_amp_v` ± `resonance_flux_err_v`
  - the flags `resonance_at_edge`, `resonance_unresolved` and `compensation_in_gap`
  - `compensating_stark_amp` ± `compensating_stark_err`
- **Decide**: if the resonance is at the edge or unresolved, move the window onto the fitted
  centre and rerun once. Otherwise set the operation's z amplitude to
  `resonance_flux_amp_v`. Do not use `swap_angle_rad_refined`, the arch-fit angle, as the
  stop criterion: decoherence biases it low, by 2–9% on 5Q4C.

### Step 4: the angle from the N-oscillation

- **Run** `qc_n_stark_amp --targets <pair>` with `swap_operation=partial_swap_<t>`,
  `swap_counts` 0..20, the same stark window and gap as Step 3 (21–27 points) and
  `num_averages=200`. The counts should span at least two periods, i.e. 2π/θ counts: 21 at
  θ = 0.30. Lengthen them for smaller angles.
- **Read**:
  - `compensating_theta_rad`, which is π / `compensating_osc_period`
  - `compensating_stark_amp_refined`
  - `osc_criteria_agree`
  - `min_osc_period`, which must stay ≥ 2: no stark row may swap by more than π/2 per count
- **Decide**:
  - **Done** if |θ − target| ≤ 0.01.
  - **Otherwise** change the coupler amplitude by (target − θ)/slope and repeat Steps 3–4. The
    resonance moves by about 0.1–0.2 mV when the coupler changes.
  - **Slope** near the off point on 5Q4C was 0.03–0.043 rad/mV (q1_q2 0.043, q2_q3 0.031).
    Once two points are measured, interpolate between them instead.
  - **Expect** two iterations. A single run's θ scatters by about ±0.007 rad, so iterating
    below that chases noise.

## Stop criteria

- Success: the period-based θ is within 0.01 rad of the target, the resonance is resolved
  (not at the edge, not unresolved), and `osc_criteria_agree` holds.
- Abort on any hardware or gateway error, as `procedures/README.md` defines it.

## Traps

1. **Stale readout thresholds.**
   - *Symptom:* one member's joint states are exactly 0.000 over the whole map. Only
     `resonance_unresolved` flags it.
   - *Case:* 5Q4C, 2026-09-22 18:13, `20260922-181347-904`. q1's "10"/"11" were 0.000 across
     961 pixels after the IQ phase drifted during the day. q2's too-close threshold also
     inflated "01" to about 0.4 far from resonance.
   - *Cure:* Prerequisite 1.
2. **Round length.**
   - Program overhead makes rounds longer than their nominal length. For `qc_n_stark_amp` and
     `qc_swap_flux_stark` a round is swap + gap + stark + 8 ns: 368 ns at gap 260 and 360 ns
     at gap 252, measured on the QM gateway simulator on 2026-09-22.
   - Always store the gap with a compensation value.
   - Comparing compensations across different round lengths needs the frame term; see
     `chain-trotter-compensation`.
3. **Two estimates of θ.** The flux-map θ is a starting point only (0–10% bias at small
   angles). The arch θ from Step 3 is biased low. The period θ from Step 4 is the reference.
4. **A compensation at the phase-wrap point.** When the compensating phase is about one full
   turn, the pick can land near stark 0 in one experiment and near the top of the window in
   the other, as q2_q3 did at gap 252 (1.000 and 0.018). Both are the same phase.
5. **Drift.** The resonance moved about 0.7 mV overnight. Rerun Step 3 before relying on an
   old z amplitude.

## Typical values

5Q4C cooldown cd2, 2026-09-22, θ target 0.30, 40 ns square pulses, `stark_detuning_hz` 50 MHz:

| pair | control | coupler (V) | z (V) | θ period | θ arch | compensating stark, gap 260 | gap 252 |
|---|---|---|---|---|---|---|---|
| q1_q2 | q1 | 0.08692 | −0.15004 | 0.292 / 0.302 | 0.285 | 0.475–0.490 | 0.93 |
| q2_q3 | q3 | 0.0714 | −0.15425 | 0.306 / 0.305 | 0.285 | 0.849–0.856 | 1.00 ≡ 0 (one turn) |

Iterations:

| pair | coupler (V) | θ period (rad) |
|---|---|---|
| q1_q2 | 0.0875 → 0.08692 | 0.317 → 0.292 |
| q2_q3 | 0.0725 → 0.0714 | 0.340 → 0.306 |

Each iteration costs about 2.5 minutes of instrument time.

## Evidence

5Q4C runs (all `20260922-` unless dated otherwise):

- **Flux maps:** q1_q2 `094311-796`; q2_q3 `20260921-215258-520`.
- **q1_q2:** round 1 `190651-183`, `190952-035`; round 2 `191202-726`, `191430-328`.
- **q2_q3:** round 1 `192421-043`, `192643-893`; round 2 `192844-092`, `193104-093`.
- **Gap-252 re-measurements:** `200343-879`, `200454-326`, `200547-676`, `200707-291`.
- **Invalid (stale readout):** `181347-904`.

## Open issues

`BACKLOG.md`:

- **F13:** a registration tool for Step 2
- **F15:** an error bar on `compensating_theta_rad`
- **F16:** recording the actual round length
- **I21:** a flag for a member whose readout collapsed
