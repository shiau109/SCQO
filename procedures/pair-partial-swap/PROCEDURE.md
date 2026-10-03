---
name: pair-partial-swap
description: Develop or re-tune a square partial-swap operation of a target angle theta on one qubit pair, played at the swap resonance, and measure its per-round stark compensation. Use when a Trotter chain or any repeated-swap experiment needs a new swap angle, or when an existing angle has drifted.
goal: A stored operation partial_swap_<t> on the pair whose per-swap angle, read from N repeated swaps (tomography, or the N-oscillation period), is within 0.01 rad of theta (within 2 % of it below 0.5 rad), with its control z pulse at the fitted resonance.
inputs:
  pair: roster pair name, e.g. q1_q2
  theta_rad: target per-swap angle, e.g. 0.30
  swap_time_ns: square pulse length, 40 on 5Q4C
outputs:
  operation: macro partial_swap_<t> playing partial_swap_square_<t> (t = theta x 100, three digits; 0.30 -> 030)
  z_amp_v: control-qubit z pulse amplitude (the resonance)
  coupler_amp_v: coupler pulse amplitude (sets the angle)
  theta_rad: the angle actually reached (Step 4), stored as the <pair>.partial_swap_<t>.theta_rad monitor
  compensating_stark_amp: per-round compensation at the round length used, with that round length
experiments: [pair_coupler_spectroscopy_swap, single_shot_readout, pair_swap_flux_map, qc_swap_flux_stark, qc_n_swap_tomography, qc_n_stark_amp]
backends: [qm]
depends_on: [qubit-frequency-park]
validated: hardware 5Q4C q1_q2 + q2_q3, 2026-09-22 (theta = 0.30, 0.60; Step 4 by qc_n_stark_amp); 2026-10-01..03 (theta = 0.12-1.28; Step 4 by qc_n_swap_tomography)
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
- One swap rotates the {|10>, |01>} subspace by 2θ, and the round's leftover relative
  phase φ tilts the rotation axis. Populations see only the combined angle,
  cos θ_eff = cos(φ/2)·cos θ, so they read θ at the compensation alone. Two-qubit
  tomography of the same N-swap sequence separates θ from φ at any stark amplitude
  (Step 4).

## Prerequisites

1. **Couplers and qubits at their working frequencies,** checked in that order at the start
   of the session and again before every use of an operation.
   - **Couplers:** `pair_coupler_spectroscopy_swap` on each pair. Re-park a coupler whose
     idle frequency is more than about 2 MHz from the value its operations were calibrated
     at (5Q4C: 7.0570 and 7.1555 GHz; local slope −9 to −16 MHz/mV; single-run scatter
     about 1 MHz).
   - **Qubits:** `qubit-frequency-park`. A qubit's drift does not show at its idle point,
     the sweet spot, but it moves the swap resonance and the angle (Trap 5).
   - **The lines pull each other.** On 5Q4C a +10 mV correction of the qubit lines moved
     the couplers by −35 and −20 MHz (2026-10-03), and a coupler line moves the qubit
     apexes by 5–7 % of its own shift. After a large correction, check the couplers again.
2. **Fresh readout on both members.** Run `single_shot_readout` on both qubits at the start
   of the session, and again after hours. The pair experiments discriminate with the
   *stored* threshold and rotation, and a stale one zeroes a member silently (see Traps).
   Accept its suggestions when the stored rotation has moved or the stored threshold no
   longer sits between the two blobs.
3. The moving qubit carries the `stark` xy operation (`scqo-qm/quam_config/register_stark.py`)
   and a chosen `stark_detuning_hz` (5Q4C: 50 MHz). Its amplitude is scaled so that factor
   1.0 is one full turn of stark phase (5Q4C q1 and q3). Every stark window below stops
   there, as `procedures/README.md` requires. Step 4's tomography plays `stark_detuned`
   instead (`scqo-qm/quam_config/register_stark_detuned.py`; 5Q4C q1 and q3 carry it): the
   same envelope with the detuning baked into the waveform, because that round does not
   switch the drive frequency.
4. Converting a compensation amplitude into a phase also needs that qubit's measured phase(a)
   curve from `qubit_stark_phase_echo` plotdata. Never use the fitted k for this: the Stark
   shift saturates.

## Steps

### Step 1: starting point from the flux map

- **Run** `pair_swap_flux_map --targets <pair>` with `swap_time_ns` equal to the operation's
  length. Use a coupler window from the off point up to θ ≈ 1 rad (5Q4C: q1_q2 0.07–0.11 V,
  q2_q3 0.06–0.09 V) and a qubit window of ±5 mV around the known resonance. An existing
  map of the pair can be reused. Extend the coupler window for angles above 1 rad: on
  2026-10-02 q1_q2 reached θ 1.32 at 0.111 V and folded past π/2 at 0.113 V (map
  `20261002-010443-580`, 0.075–0.125 V).
- **Read** the per-column `theta_rad` and `resonance_qubit_flux_v` from
  `analysis/<pair>/pair_swap_flux_map_plotdata.nc`. `result.fit` holds only the summary.
- **Decide**:
  - **Coupler start:** where the per-column θ crosses the target, interpolated between
    successfully fitted columns.
  - **Flux-map bias:** the flux map's θ differs from Step 4's θ by up to 10 %, in either
    direction. The ratio changes with the pair, with the angle and from one session to the
    next, so take it from the nearest angle measured on the same pair in the same session.
    On 5Q4C (Step 4 θ / flux-map θ):
    - 2026-09-22, period θ: q1_q2 0.98 at θ 0.30 and 1.00 at 0.60, q2_q3 1.10 and 1.09.
      Corrected this way, the 0.60 starts landed 0.013 and 0.0015 rad from the target.
    - 2026-10-02, tomography θ, q1_q2: 0.915 at 0.40, 0.97 at 0.60, about 0.95 at 0.90.
  - **Coupler start without a new map:** when the pair already carries calibrated
    operations, interpolate the coupler amplitude from their (coupler, θ) points (Typical
    values). After a drift, re-measure one of them and shift the curve by the offset it
    shows. On 5Q4C 2026-10-03 six q1_q2 angles then took one to three Step 4 runs each.
  - **z start:** the pair's last `qc_swap_flux_stark` resonance, shifted by the change of the
    map's `resonance_poly_curve` between the two coupler amplitudes. From θ 0.30 to 0.60 the
    resonance moved by +0.17 mV on q1_q2 and −0.35 mV on q2_q3.

### Step 2: register the operation

- **Run**, in `.venv-qm`:
  `scqo-qm register-partial-swap --pair <pair> --name partial_swap_<t> --z-amp <z start> --coupler-amp <coupler start>`.
  `--length` defaults to 40 ns.
- It writes three entries into the active setup's QUAM tree
  (`<data_root>/<device>/<cycle>/<setup>/backend_config/state.json`):
  - `qubit_control.z.operations["partial_swap_square_<t>"]`: `SquarePulse(amplitude=z start, length)`
  - `coupler.operations["partial_swap_square_<t>"]`: `SquarePulse(amplitude=coupler start, length)`
  - `macros["partial_swap_<t>"]`: `ISwapImplementation(flux_pulse="partial_swap_square_<t>")`
- Later steps retune with `--update --z-amp <v>` or `--update --coupler-amp <v>`, which
  change the two amplitudes only. `--list` shows what every pair carries.
- The tool replaces the live `state.json` only after a staged save shows that nothing else
  changes. It refuses an amplitude the port would clip. Run it between measurements: an edit
  made during a run shows up as setup-snapshot drift in that run's record.
- Declare a NEW operation in the device roster too (`components.toml`,
  `[composites.<pair>] operations = [..., "partial_swap_<t>"]`). Only a declared operation
  holds the angle Step 4 proposes; without it the run says so on stderr and keeps the angle
  in its fit alone.

### Step 3: the resonance, and the compensation at this round length

- **Run** `qc_swap_flux_stark --targets <pair>` with:
  - `swap_operation=partial_swap_<t>`
  - `swap_count` N = round(1.2/θ): 4 at θ = 0.30, 2 at 0.60, 1 for θ ≥ 0.8. N·θ must stay
    below π/2, or the arch folds.
  - `swap_angle_rad=θ`
  - a flux window of ±3.5 mV around the z start (31 points)
  - stark 0–1.0 (31 points), never wider. A compensation near 1.0 is the same phase as one
    near 0 (Trap 4).
  - the chosen `operation_gap_ns` (see Traps: round length)
  - `num_averages=200`
  - **at N = 1:** a flux window of ±8 mV and `min_row_contrast=0.15` (default 0.3). With
    the settings above the fit returned `resonance_unresolved` = 1 (5Q4C q1_q2, θ 0.89,
    `20261003-194932-894`); with these two changes it resolved the resonance to ±0.07 mV
    (`195119-674`). They were changed together, so which of the two is needed is not known.
- **Read**:
  - `resonance_flux_amp_v` ± `resonance_flux_err_v`
  - the flags `resonance_at_edge`, `resonance_unresolved` and `compensation_in_gap`
  - `compensating_stark_amp` ± `compensating_stark_err`. At N = 1 there is none: the stark
    tone follows the only swap, so the populations do not depend on it.
- **Decide**: if the resonance is at the edge or unresolved, move the window onto the fitted
  centre and rerun once. Otherwise set the operation's z amplitude to
  `resonance_flux_amp_v` (`scqo-qm register-partial-swap --update --z-amp`). Do not use
  `swap_angle_rad_refined`, the arch-fit angle, as the stop criterion (Trap 3).
- This step is also the drift check of an existing operation: rerun it right before the
  operation is used (Trap 5).

### Step 4: the angle from N repeated swaps

Two experiments read the angle from the same N-swap sequence. Each proposes the operation's
`theta_rad` on its own evidence, and neither is the authority over the other.

- **`qc_n_swap_tomography`, the default.** Two-qubit tomography after every count gives θ
  with an error bar, and the per-round phase, at each stark amplitude. About 2 minutes. It
  needs `stark_detuned` (Prerequisite 3).
- **`qc_n_stark_amp`, the alternative.** The stark × N population map reads θ from the
  oscillation period at the compensation. Under a minute, no error bar (F15), and it plays
  the plain `stark` operation. Use it on a qubit without `stark_detuned`, or as a
  cross-check.
- On 5Q4C 2026-10-01 the two, 46 minutes apart, read q1_q2 0.4367 (tomography) against
  0.4371, and q2_q3 0.4212 against 0.4336: a 3 % gap, the size of that evening's drift
  (Trap 5).

**With the tomography**

- **Run** `qc_n_swap_tomography --targets <pair>` with:
  - `swap_operation=partial_swap_<t>` and `stark_operation=stark_detuned`
  - `stark_amps`: three values 0.03–0.05 apart, centred on Step 3's
    `compensating_stark_amp`, all below 1.0. At N = 1, where Step 3 returns none, centre
    them on the compensation of the pair's other operations: it hardly depends on the
    angle (Typical values).
  - `swap_counts` 0..N_max, with N_max = 8 for θ ≥ 0.35, 12 for 0.2–0.35 and 16 below
    0.2. That is one transfer period (π/θ counts) down to θ ≈ 0.2 and less below it: 0.6
    of a period at θ 0.12.
  - the gap of Step 3, and the round's real length as `round_duration_ns` (368 at gap
    260, Trap 2)
  - `num_averages=1000` and `readout_calibration_shots=1000`
- **Read**:
  - `theta_rad` ± `theta_rad_err`
  - `theta_consistency_sigma`: how far the angle at any one stark amplitude sits from the
    reported one, in combined standard errors
  - `fit_rms`
  - `compensating_stark_amp`, and `compensation_extrapolated` (1 = it lies outside the
    sampled amplitudes)
  - `frame_step_rad` against `predicted_frame_step_rad`: with the real round length they
    agreed within about 2° on 5Q4C
- **Decide**:
  - The run proposes `theta_rad` only when `fit_rms` ≤ 0.08 and
    `theta_consistency_sigma` ≤ 3.
  - If `theta_consistency_sigma` > 3, centre `stark_amps` on this run's
    `compensating_stark_amp` and rerun once (Trap 7).
  - If `compensation_extrapolated` = 1, the reported compensation is an extrapolation:
    recentre before relying on that value. The angle's proposal stands when the two
    conditions above hold.
  - Then apply the common rule below.

**With the population map**

- **Run** `qc_n_stark_amp --targets <pair>` with `swap_operation=partial_swap_<t>`,
  `swap_counts` 0..20, stark 0–1.0 (21 points), the gap of Step 3 and `num_averages=200`.
  - The counts should span at least two periods, i.e. 2π/θ counts: 21 at θ = 0.30. 0..20
    spans about four periods at 0.60. Lengthen them for smaller angles (5Q4C: 0..40 at
    θ 0.18, 0..56 at 0.12).
  - Below θ ≈ 0.2 the compensation peak along the stark axis is narrow. After the 0–1.0
    scan, repeat with a 0.25-wide window around it in 0.01 steps: on 5Q4C q2_q3
    (2026-09-30, 0.35–0.60 × 26) that moved θ from 0.1831 to 0.1780 and from 0.1200 to
    0.1223.
- **Read**:
  - `compensating_theta_rad`, which is π / `compensating_osc_period`
  - `compensating_stark_amp_refined`
  - `osc_criteria_agree`
  - `min_osc_period`, which must stay ≥ 2: no stark row may swap by more than π/2 per count
- **Decide**: the run proposes `theta_rad` only when `osc_criteria_agree` = 1 and
  `min_osc_period` ≥ 2. Then apply the common rule below.

**Common rule**

- **Done** if |θ − target| ≤ 0.01 rad, or ≤ 2 % of the target when the target is below
  0.5 rad (0.01 rad is 8 % of θ 0.12). Accept the run's `theta_rad` suggestion
  (`scqo accept <run>`): the chain analysis draws its ideal curves from it.
- **Otherwise** change the coupler amplitude by (target − θ)/slope
  (`scqo-qm register-partial-swap --update --coupler-amp`) and repeat Steps 3–4. The
  resonance moves by about 0.1–0.2 mV when the coupler changes.
- **Slope** on 5Q4C, in rad/mV:
  - 2026-09-22: q1_q2 0.043 at θ 0.30 and 0.039 at 0.60; q2_q3 0.031 at 0.30 and about
    0.066 at 0.60 (from the flux map; that pair needed no second point).
  - 2026-10-01..03: q1_q2 0.03 at θ 0.28–0.40, 0.04 at 0.56, 0.04–0.08 at 0.9 and
    0.08–0.11 at 1.2–1.3; q2_q3 0.017 at 0.12–0.18, 0.023 at 0.18–0.28, 0.028 at
    0.28–0.40 and 0.038 at 0.40–0.56.
  - Once two points are measured, interpolate between them instead.
- **Expect** one to three iterations.
  - Tomography: `theta_rad_err` is 0.001–0.003 rad (0.1–0.5 % on q1_q2, 0.4–1.4 % on
    q2_q3), and repeats at fixed amplitudes scattered by about ±1 % within half an hour.
    Iterating below that chases noise and drift.
  - Population map: a single run's θ scatters by about ±0.007 rad.
  - At θ ≈ 0.12 the tomography error stays at 0.0013–0.0018 rad, and doubling
    `num_averages` to 2000 barely moved it. The trajectory there covers 0.6 of a transfer
    period, so longer `swap_counts` is the lever to try (not yet tested).

## Stop criteria

- Success: Step 4's θ is within 0.01 rad of the target (within 2 % of it below 0.5 rad),
  the resonance is resolved (not at the edge, not unresolved), and the run met its own
  proposal conditions: `fit_rms` and `theta_consistency_sigma` for the tomography,
  `osc_criteria_agree` and `min_osc_period` for the population map.
- Abort on any hardware or gateway error, as `procedures/README.md` defines it.

## Traps

1. **Stale readout thresholds.**
   - *Symptom:* one member's joint states are exactly 0.000 over the whole map. Only
     `resonance_unresolved` flags it.
   - *Case:* 5Q4C, 2026-09-22 18:13, `20260922-181347-904`. q1's "10"/"11" were 0.000 across
     961 pixels after the IQ phase drifted during the day. q2's too-close threshold also
     inflated "01" to about 0.4 far from resonance.
   - *Cure:* Prerequisite 2.
2. **Round length.**
   - Program overhead makes rounds longer than their nominal length. For `qc_n_stark_amp`,
     `qc_n_swap_tomography` and `qc_swap_flux_stark` a round is swap + gap + stark + 8 ns:
     368 ns at gap 260 and 360 ns at gap 252, measured on the QM gateway simulator on
     2026-09-22.
   - Always store the gap with a compensation value.
   - Comparing compensations across different round lengths needs the frame term; see
     `chain-trotter-compensation`.
3. **Four estimates of θ, two of them biased.**
   - *Flux map (Step 1):* a starting point only, off by up to 10 % in either direction.
   - *Arch (Step 3, `swap_angle_rad_refined`):* never the stop criterion. Against the
     period angle it read 2–9 % low on 2026-09-22. Against the tomography on
     2026-10-01..03 it read between 5 % low and 1 % high for θ 0.27–0.69, 11 % low at
     0.18, 16–18 % low at 0.12, and about 10 % HIGH at N = 1 (1.023 against 0.925).
   - *Tomography and period (Step 4):* the references.
4. **A compensation at the phase-wrap point.** When the compensating phase is about one full
   turn, the pick can land near stark 0 in one experiment and near the top of the window in
   the other, as q2_q3 did at gap 252 (1.000 and 0.018). Both are the same phase.
5. **Drift.** The resonance moved about 0.7 mV overnight. Rerun Step 3 before relying on an
   old z amplitude.
   - *Within an evening:* 5Q4C 2026-10-01, with fixed amplitudes and the couplers on
     target. In 73 minutes q1_q2's θ fell from 0.396 to 0.381, and its tomography
     compensation moved from 0.487 to 0.576; q2_q3's θ fell from 0.399 to 0.388 in 57
     minutes. The three qubit lines had drifted by −0.5 to −0.65 mV: invisible at idle (the
     apex heights were unchanged), about 2.5 MHz at the swap point. Re-parking the qubits
     brought θ back to 0.390 and the compensation to 0.486.
   - *What shows it:* Step 3's resonance and the tomography's `compensating_stark_amp`. An
     idle Ramsey does not.
   - *Consequence:* calibrate an operation right before the experiment that uses it. A
     ratio of two angles holds better than either angle, since both drift together.
   - *Large jump:* 5Q4C 2026-09-29, between 11:03 and 23:31, with the vendor config
     unchanged (same setup snapshot) and no run in between. The q1_q2 resonance moved from
     −0.149 to −0.165 V and q2_q3's from −0.154 to −0.164 V, and the same coupler
     amplitude gave about twice the angle (q1_q2 at 0.0959 V: θ 0.40 → 0.86). Readout and
     x180 were unaffected.
   - *Large jump again:* between 2026-10-02 and 10-03 every flux line moved by +8 to
     +11 mV (couplers +92 and +109 MHz).
   - *Symptom in the chain:* the source decays at about its T1 rate and the sink stays flat.
     Step 3 is flat across its ±3.5 mV window (`resonance_unresolved` = 1).
   - *Cure, first:* re-park the couplers and the qubits (Prerequisite 1), iterating until
     both hold. On 2026-10-03 the operations then carried over with untouched amplitudes:
     q2_q3 040 read 0.3997 (0.3976 before the jump), q1_q2 040 0.3889 (0.4011 before).
   - *Cure, when the frequencies cannot be restored:* a wide Step 1 survey (qubit flux from
     0 to beyond the old point, coupler from 0 to the working amplitude, about 40 s) finds
     the new resonance. Then run Steps 1–4 again from scratch; old coupler amplitudes do
     not carry over. This is what 2026-09-29 took. Evidence: survey `20260929-234245-691`,
     maps `234615-004` / `234735-222`, final angles `20260930-001012-833`, `001057-903`,
     `000545-538`, `000622-011`.
6. **A stark window wider than one turn.**
   - *Symptom:* two compensations one turn apart inside the window, and
     `osc_criteria_agree` = 0 because the contrast and period criteria each pick a different
     one. The two can also read different angles.
   - *Case:* 5Q4C q1_q2, θ 0.60, window 0–1.3, `20260922-213409-297`: branches at 0.47 and
     1.19. The upper one read θ 0.598 and would have ended the iteration. The rerun with
     0–1.0, `20260922-213557-000`, read 0.6135 at 0.45, which needed a second iteration.
   - *Cure:* windows stop at one turn (`procedures/README.md`). The upper branch also means a
     tone strong enough to drive the qubit.
7. **The tomography withholds its proposal at `theta_consistency_sigma` > 3.**
   - *Symptom:* a normal `fit_rms` and a plausible `theta_rad`, but no suggestion.
   - *Cases:* 5Q4C q1_q2, 2 of 26 runs. 069, `20261002-011750-244`: amplitudes
     0.399–0.499, compensation 0.486, 3.6σ. 126, `20261003-201122-412`: amplitudes
     0.43–0.53, compensation 0.511, 3.2σ. q1_q2 runs often read 2–3σ (q2_q3 mostly below
     2), so the gate is close on that pair.
   - *Cure:* centre the three amplitudes on the run's own `compensating_stark_amp` and
     rerun once. The next runs of both operations read 0.8σ and 1.0σ. Whether the
     centring or the repeat did it is not established: other runs as far off-centre
     passed.

## Typical values

5Q4C cooldown cd2, 2026-10-01..03, 40 ns square pulses, gap 260 (368 ns round), Step 4 by
`qc_n_swap_tomography`. Each row is the run whose `theta_rad` was accepted when the
operation was calibrated:

| operation | pair | coupler (V) | z (V) | θ ± err (rad) | Step 3 N | `swap_counts` | compensating stark |
|---|---|---|---|---|---|---|---|
| 013 | q2_q3 | 0.07113 | −0.153675 | 0.1236 ± 0.0016 | 10 | 0..16 | 0.954 |
| 018 | q2_q3 | 0.07414 | −0.154055 | 0.1754 ± 0.0010 | 7 | 0..16 | 0.921 |
| 023 | q2_q3 | 0.07670 | −0.154072 | 0.2324 ± 0.0014 | 5 | 0..12 | 0.921 |
| 028 | q2_q3 | 0.07872 | −0.154096 | 0.2815 ± 0.0011 | 4 | 0..12 | 0.922 |
| 040 | q2_q3 | 0.08290 | −0.154348 | 0.3986 ± 0.0020 | 3 | 0..8 | 0.908 |
| 056 | q2_q3 | 0.08717 | −0.154484 | 0.5615 ± 0.0029 | 2 | 0..8 | 0.908 |
| 028 | q1_q2 | 0.09106 | −0.149276 | 0.2828 ± 0.0010 | 4 | 0..12 | 0.507 |
| 040 | q1_q2 | 0.09543 | −0.149030 | 0.3982 ± 0.0017 | 3 | 0..8 | 0.486 |
| 057 | q1_q2 | 0.09963 | −0.149502 | 0.5521 ± 0.0021 | 2 | 0..8 | 0.489 |
| 069 | q1_q2 | 0.10260 | −0.149499 | 0.6867 ± 0.0016 | 2 | 0..8 | 0.481 |
| 089 | q1_q2 | 0.10624 | −0.149540 | 0.8775 ± 0.0013 | 1 | 0..8 | 0.480 |
| 126 | q1_q2 | 0.11153 | −0.149519 | 1.2833 ± 0.0013 | 1 | 0..8 | 0.475 |

- The q2_q3 rows are from 2026-10-01 21:39–22:05, the q1_q2 rows from 2026-10-03
  18:50–20:15 (after that day's re-park; the q1_q2 z values follow it). 1000 averages,
  except q2_q3 013 at 2000.
- The compensation hardly depends on the angle: 0.475–0.507 on q1_q2, 0.908–0.954 on
  q2_q3. It moves with qubit drift instead (Trap 5).

Iterations of that calibration:

| operation | pair | coupler (V) | θ (rad) |
|---|---|---|---|
| 040 | q1_q2 | 0.09590 → 0.09554 → 0.09513 | 0.4146 → 0.4082 → 0.3964 |
| 018 | q2_q3 | 0.07436 → 0.07414 | 0.1822 → 0.1754 |
| 013 | q2_q3 | 0.07120 → 0.07105 → 0.07113 | 0.1285 → 0.1221 → 0.1236 |
| 057 | q1_q2 | 0.10053 → 0.09963 | 0.5949 → 0.5605 |
| 028 | q1_q2 | 0.09061 → 0.09106 | 0.2676 → 0.2828 |
| 089 | q1_q2 | 0.10703 → 0.10664 → 0.10624 | 0.9250 → 0.9091 → 0.8775 |
| 126 | q1_q2 | 0.11080 → 0.11180 → 0.11153 | 1.1972 → 1.3041 → 1.2833 |

Each iteration (Step 3, then the tomography) costs about 3.5 minutes of instrument time;
a tomography alone, after a coupler change only, about 2.

5Q4C cooldown cd2, 2026-09-22, 40 ns square pulses, `stark_detuning_hz` 50 MHz, Step 4 by
`qc_n_stark_amp`:

| θ target | pair | control | coupler (V) | z (V) | θ period | θ arch | compensating stark, gap 260 | gap 252 |
|---|---|---|---|---|---|---|---|---|
| 0.30 | q1_q2 | q1 | 0.08692 | −0.15004 | 0.292 / 0.302 | 0.285 | 0.475–0.490 | 0.93 |
| 0.30 | q2_q3 | q3 | 0.0714 | −0.15425 | 0.306 / 0.305 | 0.285 | 0.849–0.856 | 1.00 ≡ 0 (one turn) |
| 0.60 | q1_q2 | q1 | 0.0958 | −0.14987 | 0.602 | 0.577 | 0.484–0.487 | — |
| 0.60 | q2_q3 | q3 | 0.0797 | −0.15460 | 0.5985 | 0.589 | 0.892–0.904 | — |

Iterations:

| θ target | pair | coupler (V) | θ period (rad) |
|---|---|---|---|
| 0.30 | q1_q2 | 0.0875 → 0.08692 | 0.317 → 0.292 |
| 0.30 | q2_q3 | 0.0725 → 0.0714 | 0.340 → 0.306 |
| 0.60 | q1_q2 | 0.0961 → 0.0958 | 0.6135 → 0.602 |
| 0.60 | q2_q3 | 0.0797 | 0.5985 |

Each iteration costs about 2.5 minutes of instrument time.

## Evidence

5Q4C runs, 2026-10-01..03 (Step 4 by tomography):

- **Tomography against the period, 2026-10-01:** `qc_n_stark_amp` `20261001-193311-704`
  (q1_q2), `193357-316` (q2_q3); tomography `202059-791`, `201942-810`.
- **q2_q3, 2026-10-01 (Step 3, tomography):** 040 `213758-364`, `213912-168`; 056
  `214052-574`, `214204-989`; 028 `214345-955`, `214458-489`; 023 `214705-406`,
  `214817-767`; 018 `215405-086`, `215517-570`; 013 `220141-709`, `220534-639`.
- **q1_q2, 2026-10-03 (Step 3, tomography):** 040 `184848-435`, `185009-884`; 028
  `190234-900`, `190631-782`; 057 `191918-885`, `192039-749`; 069 `193454-901`,
  `193615-733`; 089 `195119-674`, `195632-926`; 126 `200944-967`, `201505-200`.
- **Step 3 at N = 1:** `20261003-194932-894` (defaults, unresolved), `195119-674`,
  `200944-967`.
- **Flux map for the angles above 0.6:** `20261002-010443-580`.
- **Drift within an evening (Trap 5):** q1_q2 040 at one coupler amplitude,
  `20261001-213408-508`, `224718-007`, then after the qubit re-park `231945-638`.
- **After the 10 mV jump (Trap 5):** `20261003-184503-921`, `184626-096`.
- **Proposal withheld (Trap 7):** `20261002-011750-244`, `20261003-201122-412`.
- **Small-angle population map, 2026-09-30:** 018 `224502-977`, `224918-207`; 013
  `224559-009`, `224750-761`.

5Q4C runs, 2026-09-22 (all `20260922-` unless dated otherwise; Step 4 by `qc_n_stark_amp`):

- **Flux maps:** q1_q2 `094311-796`; q2_q3 `20260921-215258-520`, `20260921-202125-547`.
- **θ 0.30, q1_q2:** round 1 `190651-183`, `190952-035`; round 2 `191202-726`, `191430-328`.
- **θ 0.30, q2_q3:** round 1 `192421-043`, `192643-893`; round 2 `192844-092`, `193104-093`.
- **θ 0.30, gap-252 re-measurements:** `200343-879`, `200454-326`, `200547-676`, `200707-291`.
- **θ 0.60, q1_q2:** round 1 `213123-952`, `213557-000` (and `213409-297`, Trap 6); round 2
  `213742-598`, `213932-285`.
- **θ 0.60, q2_q3:** `220355-949`, `220541-535`.
- **Invalid (stale readout):** `181347-904`.

## Open issues

`BACKLOG.md`:

- **F15:** an error bar on `compensating_theta_rad`
- **F16:** recording the actual round length
- **F18:** a stark amplitude-to-phase conversion, so the one-turn bound can live in code
- **F31:** what the tomography's first version left out (a detuning check, a monitor for
  the incoherent error per step)
- **I21:** a flag for a member whose readout collapsed
- **I36:** a stark tone near one turn adds population loss per round on q3, where q2_q3's
  compensation sits (0.91–0.95)

Not yet in `BACKLOG.md`:

- a procedure for re-parking the couplers together with the qubits (Prerequisite 1 names
  the experiments only)
- Step 3 at N = 1: which of the two changed settings resolves the resonance
- the tomography at θ ≈ 0.12 with longer `swap_counts`
