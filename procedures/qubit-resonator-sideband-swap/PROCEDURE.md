---
name: qubit-resonator-sideband-swap
description: Find the flux-modulation tone (frequency, amplitude) that swaps a flux-tunable qubit's excitation into its own readout resonator in a GIVEN time T, through the red sideband |e,0> <-> |g,1>. Use it to build a parametric reset of a chosen length, or whenever a qubit's population has to be handed to its resonator in a fixed window.
goal: A square tone on the qubit's z line, at parametric_freq_hz f* and parametric_amp_v A*, whose first exact zero of the qubit population falls at T (on the 4 ns grid), with P(e) at T within ~1-2 % of the readout floor.
inputs:
  qubit: the flux-tunable qubit, idling at its apex, e.g. q3
  swap_time_ns: the target time T (QM: a multiple of 4 ns, >= 16)
outputs:
  parametric_freq_hz: f*, the modulation frequency at A*
  parametric_amp_v: A*, the tone amplitude at the DAC
  sideband_order: k, the harmonic of f_m that bridges the qubit-resonator detuning
  chevron_fit: g_k, kappa, f0 and t* from the Step 2 / Step 4 chevrons
  ringdown_ns: how long the photon left in the resonator needs to fall below 1 %
experiments: [qubit_parametric_drive_amp, qubit_parametric_drive_time]
backends: [qm]
depends_on: [qubit-frequency-park]
validated: hardware 5Q4C q3, 2026-10-01 (k=2, T=100 ns; Steps 1-4 walked as written, ~8 min of instrument time). Also 5Q4C q2, 2026-08-26..09-21 (k=4, first zero 131-133 ns; reconstructed from the saved runs).
---

# qubit-resonator-sideband-swap

## Physics in brief

- **The sideband.** An RF tone at f_m on the qubit's own z line modulates f01. When a
  harmonic of the modulation bridges the qubit-resonator detuning, the excitation is
  exchanged: `k * f_m = f_r - f_q_mean`, with f_r the resonator's `f_dress0_hz` and
  `f_q_mean = f_q_apex - D(A)`. D is the mean frequency DROP the modulation causes; it grows as
  A^2 at small amplitude. So the line in the (A, f_m) map starts at `Delta0 / k` as A -> 0
  (Delta0 = f_r - f_q_apex) and bends UP as `D(A) / k`.
- **Only even k at the apex.** At the sweet spot f01 responds to flux quadratically, so a tone
  at f_m moves f01 at 2 f_m: k = 2, 4, 6, ... The k = 2 line is the strongest.
- **The exchange rate.** g_k = g * |c_k|, with |c_k| the Fourier weight of e^{-i theta(t)} (the
  modulation's accumulated phase), NOT of the f01(t) spectrum. For a nearly pure 2 f_m tone,
  |c_k| = J_{k/2}(beta), beta = D / (2 f_m). So g_2 ~ g * beta / 2 grows as ~A^2. The k = 4 rate,
  g * J_2(beta) ~ g * beta^2 / 8, needs a much larger tone (and a larger D) for the same g_k.
- **Pick the lowest k whose line is reachable**: its start `Delta0 / k` must lie inside the z
  output's band, and the needed A inside the rail. A lower k means a smaller A and a smaller
  D, so the line moves less per percent of amplitude (see Trap 6).
- **The given time fixes g_k.** With the resonator losing energy at kappa, the qubit
  amplitude is `c_e(t) = e^{-kappa t / 4} [cos(W t) + kappa / (4 W) sin(W t)]`,
  `W = sqrt(g_k^2 - kappa^2 / 16)`, and its first exact zero is
  `t* = (pi - arctan(4 W / kappa)) / W` (all angular). Setting t* = T gives the g_k to aim for:

  | T (ns) | g_k/2pi (MHz) at kappa/2pi = 1 / 2 / 4 MHz | photon left at T | ring-down to 1 % (ns) |
  |---|---|---|---|
  | 60 | 4.33 / 4.49 / 4.83 | 0.83 / 0.69 / 0.47 | 703 / 336 / 153 |
  | 80 | 3.29 / 3.45 / 3.79 | 0.78 / 0.60 / 0.37 | 693 / 326 / 143 |
  | 100 | 2.66 / 2.83 / 3.17 | 0.73 / 0.53 / 0.28 | 683 / 316 / 133 |
  | 140 | 1.95 / 2.12 / 2.47 | 0.64 / 0.41 / 0.17 | 663 / 296 / 113 |
  | 200 | 1.41 / 1.59 / 1.95 | 0.53 / 0.28 / 0.08 | 633 / 266 / 83 |

  g_k must exceed kappa / 4, otherwise there is no zero at all. That is the exceptional
  point: on a small-kappa chip it would need hundreds of ns, so swap-and-release wins.
- **A swap, not yet a reset.** At T the qubit is empty, but the energy sits in the resonator
  as a photon. It leaves at kappa (table above). Anything that sees the resonator's photon
  number, such as a readout or a gate on that qubit (it carries the dispersive shift), must
  wait for the ring-down.

## Prerequisites

1. **The qubit sits at its apex** (`procedures/qubit-frequency-park`, same day). The
   condition is frequency-matched: an f01 error delta moves the line by delta / k in f_m, and
   an off-apex bias adds odd harmonics and changes D.
2. **Discriminated readout.** A fresh `single_shot_readout`, then run every step with
   `use_state_discrimination=true` (Trap 2). The contrast sets the floor the final P(e) is
   judged against.
3. **Facts for the prediction:** the qubit's `f_01_hz` (= `f_q_max_hz` at the apex),
   `ej_sum_hz` / `ec_hz`, `flux_per_phi0`; the resonator's `f_dress0_hz`, `g_hz`,
   `kappa_tot_hz`.
4. **Nothing on the z line config.** Both experiments patch a z oscillator into the generated
   config themselves (`ensure_flux_oscillators`). The stored macro does not (Step 5).

## Steps

### Step 0: predict (offline)

- **Compute** Delta0 = `f_dress0_hz` - `f_01_hz`, choose k (Physics), and read the needed g_k
  off the table for T, with the resonator's `kappa_tot_hz` (Trap 7: the chevron's kappa can
  be half of it).
- **Model** the line and the amplitude with the Floquet sideband model in
  `scq-reports/reports/parametric_qubit_reset_20260929/sideband_model.py` (swap in the
  qubit's constants). It returns the flux amplitude phi_ac in Phi0. In volts at the DAC, that
  is phi_ac * `flux_per_phi0` / r, where r is the z line's RF/DC transfer at f_m. On 5Q4C
  q2's line, r = 0.57-0.64 at 350-372 MHz. Another line can differ by tens of percent, so
  the prediction only places the Step 1 window. The model also under-predicts g_k (Trap 8).
- **Decide:** if `Delta0 / k` is outside the z band, or the needed A is beyond the rail, go to
  the next even k, or ask for a longer T.

### Step 1: find the line at the fixed time T

- **Run** `qubit_parametric_drive_amp --targets <q>` with `drive_time_ns=T`,
  `start_parametric_amp_v=0`, `end_parametric_amp_v` ~ 2x the predicted A (21 points), and a
  frequency window from just below `Delta0 / k` to above the predicted f_m at the top
  amplitude (1 MHz steps; 5Q4C q3: 330-430 MHz, 101 points), 200 averages.
- **Read** the `population` map (`parametric_amp_v` x `parametric_freq_hz`). Not `best_*`
  (Trap 1).
- **Decide:**
  - A dip line that starts near `Delta0 / k` and bends up confirms the sideband. Follow it to
    the amplitude where P(e) at T first reaches its minimum: that is A1, at f1.
  - The line's depth still growing at the top amplitude: extend `end_parametric_amp_v`.
  - A line that does not start at `Delta0 / k`: another partner (a coupler, a TLS, another
    harmonic). Step 2's kappa and k tell which.

### Step 2: characterize the coupling at A1

- **Run** `qubit_parametric_drive_time --targets <q>` with `parametric_amp_v=A1`, frequency
  f1 +- ~(3 g_k / k) (k = 2 at ~3 MHz: +-4 MHz, 21 points; k = 4: +-2 MHz), and
  `start_drive_time_ns=20`, `end_drive_time_ns` ~ 4 T on the 4 ns grid (101 points).
- **Read** the `population` map (`parametric_freq_hz` x `drive_time_ns`), and fit it
  GLOBALLY: `P = B + C |c_e(t + t0)|^2`, with the detuning tied across rows as
  `2 pi k (f - f0)` and g, kappa, k, f0, B, C, t0 free. The reference implementation is
  `scq-reports/reports/parametric_qubit_reset_20260929/chevfit.py`. The estimator's
  per-frequency fits do not give f0 or t* (Trap 1, BACKLOG I32).
- **Decide:**
  - kappa in the resonator's range and k near the chosen order: it is the readout-resonator
    sideband. Go on.
  - t* off T: rescale A2 = A1 * (t* / T)^(1/p), with g_k ~ A^p. Measured on 5Q4C q2 at
    k = 4: p ~ 1.65 (0.26 -> 0.34 V). On q3 (k = 2) Step 1's A1 already gave t* = 99.1 ns,
    a 0.5 % rescale, so A2 = A1. Step 3 removes the error left by this rule.

### Step 3: the fine map at the fixed time T

- **Run** `qubit_parametric_drive_amp --targets <q>` with `drive_time_ns=T`, the amplitude
  A2 +- 5 % (~0.5 % steps) and the frequency f(A2) +- (5 % x A2 x slope + 1 MHz) in 0.1 MHz
  steps, the slope being Step 1's line. 5Q4C q3: 0.0995-0.1105 V (23 points) x 352-358 MHz
  (61 points), the line tilting 324 MHz/V.
- **Read** the `population` map, and fit it at the fixed T with the chevron model: g_k =
  g1 (A / A2)^p, a line f0(A) = f1 + s (A - A2) + q (A - A2)^2, and kappa, k, t0 fixed from
  Step 2. The fitted surface's minimum is (f*, A*). Do not take the raw minimum (Trap 10).
- **Decide:** the minimum is within ~1-2 % of the readout floor (B of Step 2) and not on a
  window edge: go to Step 4. On an edge: re-centre and repeat. This map, not the chevron, sets
  the final values: it measures the pulse that is actually played, including the few-ns
  offset t0 that the chevron fit carries (Trap 5).

### Step 4: verify

- **Run** `qubit_parametric_drive_time --targets <q>` at `parametric_amp_v=A*`, f* +- 1 MHz
  (11 points), 20 ns to ~3 T.
- **Read** the global fit's t* (Step 2), and P(e) at T on the f* row.
- **Decide:** the first zero at T +- 4 ns and P(e)(T) within ~1-2 % of the floor: done.
  5Q4C q3: first zero 98.8 ns, P(e)(100 ns) 0.022 against a floor of 0.023, at 400 averages.
  Repeat it later in the day for drift (5Q4C q2's line held to ~0.5 MHz over four weeks).

### Step 5 (optional): store it as the qubit's reset

- The family is record-only. Storing the tone is a hand edit of the vendor config, with q2's
  `reset` macro as the template: `<q>.z.operations.parametric_reset` (a square pulse, T x A*)
  and `<q>.macros["reset"]` (`ParametricReset`, `drive_frequency=f*`).
- The z line needs `intermediate_frequency` 0, not None. With None the macro fails at compile
  (5Q4C: q2 had 0; q3 had None and was set to 0 with its macro).
- Write the three entries (IF, pulse, macro) by proof, as `scqo-qm register-partial-swap`
  does: save the edited tree to a temporary folder and replace the live `state.json` only if
  it differs by exactly those entries and `wiring.json` is unchanged. Then confirm offline
  that `generate_config()` gives the z element an IF and that a QUA program calling
  `<q>.macros["reset"].apply()` builds. The tree before the edit is the last run's setup
  snapshot (`scqo restore`).
- 5Q4C q3, stored 2026-10-01 after Step 4: `q3.z.operations.parametric_reset` = square
  100 ns x 0.105 V, `q3.macros["reset"]` = `ParametricReset(drive_frequency=355000000)`.
- The macro leaves the z oscillator at f* (BACKLOG I33): a later pulse on the same z line in
  the same program plays modulated.
- The macro does not wait for the ring-down (BACKLOG I37): the caller waits `ringdown_ns`.

## Stop criteria

- Success: Step 4 passes.
- Stop and choose another k or a longer T: the needed g_k needs an A beyond the rail, or the
  line beyond the z band.
- Abort on any hardware or gateway error, as `procedures/README.md` defines it.

## Traps

1. **`best_*` is not the calibration (BACKLOG I32).**
   - `qubit_parametric_drive_amp`'s `best_peak_amplitude` is polarity-normalized. Runs before
     scqat 956a30b carry mis-seeded `best_*`.
   - `qubit_parametric_drive_time`'s `best_parametric_freq_hz` is the argmax of the EP metric
     `best_ep_metric`, not the resonance: 372.1 MHz against the global fit's 372.59 MHz on
     5Q4C q2, with 12.8 % P(e) left there at 140 ns.
   - `best_gamma_hz` / `best_lambda_hz` / `best_delta_hz` are angular rates in 1/s, not Hz.
2. **Raw I/Q.** The `_time` estimator falls back to I and reports rates in volts per ns that
   look like numbers. Run discriminated.
3. **Coupled windows.** The chevron's half-width in f_m is ~2 g_k / k. A frequency step larger
   than that steps over it, and every per-row fit converges on nothing.
4. **Readout quality.** 5Q4C 2026-09-02: the readout fidelity fell to 0.66-0.85 that night, the
   chevrons' contrast to ~0.6, and the global fit ran to its bounds. Check the floor (B) and
   the contrast (C) before trusting g, kappa or t*.
5. **The played time is not the nominal time.** The global fit's t0 was -5 to +8 ns on the
   good 5Q4C q2 chevrons: the z line's rise and filtering
   shift the effective swap time. Calibrate at the fixed T (Step 3) instead of computing T from a chevron.
6. **Amplitude moves the line.** In the model it moves by 2 D / k per unit of relative
   amplitude; take the real slope from the Step 1 line:
   - 5Q4C q2 (k = 4): the measured slope is 207 MHz/V at 0.34 V, so 1 % of A is 0.70 MHz in
     f_m against a 2 % window of +-0.15 MHz.
   - 5Q4C q3 (k = 2): 324 MHz/V at 0.105 V, the model's 2 D / (k A) exactly. 1 % of A is
     0.34 MHz. At a fixed A the window is f* +-0.31 MHz for 1 % P(e) above the floor
     (+-0.44 MHz for 2 %); at a fixed f it is A* +-0.9 % (+-1.3 %).
   So the final search is two-dimensional (Step 3), never a frequency scan at a fixed A.
7. **Two kappas.** Chevron against resonator spectroscopy on 5Q4C: q2_res 3.79 +- 0.23 against
   7.76 MHz (13 chevrons); q3_res 1.62-1.66 against 1.94 MHz (2 chevrons). Not investigated.
   The chevron's kappa is the one that sets t* and the ring-down.
8. **The model is a window, not a value.**
   - 5Q4C q2: the Floquet model under-predicts g_4 by ~1.4x, the fit gives k = 4.5 +- 0.4
     instead of 4, and the measured f_m*(A) is concave where the model predicts convex.
   - 5Q4C q3: the needed g_2 came at D = 34.2 MHz (line at 355.0 MHz), not at the model's
     D = 42 MHz (358.8 MHz), so the model is ~1.2x low in g per unit D. The fit gives
     k = 1.86-1.91. The amplitude still landed inside the predicted window (0.105 V, against
     0.105-0.118 V).
9. **Flux drift detunes it.** A qubit 10 mV off its apex (q3: 0.0172 MHz/mV^2, so 1.7 MHz)
   moves a k = 2 line by ~0.9 MHz in f_m, which leaves ~9 % P(e) at 100 ns. Add the qubit to the
   re-park order once it carries such a reset.
10. **The fixed-T valley is long and flat along the line.** In the (f, A) map at a fixed T,
    P(e) stays near the floor along the tilted line over several percent of A, and rises
    steeply across it. A noisy map's raw minimum therefore wanders along the valley.
    5Q4C q3: the smoothed raw minimum sat at 0.101 V / 353.70 MHz, while the fitted exact zero
    is at 0.1051 V / 355.005 MHz. Fit the surface (Step 3), and expect only the cross-line
    direction to be tight.

## Typical values

5Q4C, cooldown cd2:

| | q2 (2026-08-26..09-21) | q3 (2026-10-01, T = 100 ns) |
|---|---|---|
| f_q apex / f_dress0 | 4842.12 / 6021.48 MHz | 5191.92 / 5867.77 MHz |
| Delta0, g | 1179.3 MHz, 79.1 MHz | 675.9 MHz, 97.0 MHz |
| k | 4 (k = 2 would need 590 MHz) | 2 (fit 1.86-1.91) |
| line f_m*(A) | 223.2 + 672.1 A - 683.6 A^2 MHz (0.22-0.38 V) | visible from ~341 MHz at 0.04 V; 355.0 MHz at 0.105 V, 324 MHz/V there |
| kappa/2pi | 3.79 +- 0.23 MHz (chevrons) | 1.62-1.66 MHz (chevrons) |
| at the chosen tone | 0.34 V: g_4 2.4-2.5 MHz, f0 372.53-372.59 MHz | 0.105 V: g_2 2.766-2.778 MHz, f0 354.90-355.04 MHz, t0 0.6-1.1 ns |
| first zero / result | 131-133 ns; stored 372.5 MHz, 0.34 V x 140 ns, 1-2 % P(e) | 98.8-99.1 ns; f* 355.0 MHz, A* 0.105 V: P(e)(100 ns) = floor (0.022 vs 0.023) |
| photon left at t*, ring-down | ~20 %, 1/kappa = 42 ns | 59 %, ~400 ns to 1 % (1/kappa = 97 ns) |

- q3's three f0 readings (Steps 2-4, 20:46-20:50) spread over 0.14 MHz, from different
  windows and experiments. That is inside the +-0.31 MHz window. A same-day repeat for
  drift is still owed.
- q3's Step 1 map at 100 ns also shows the next minima along the line: P(e) 0.025-0.03 at
  0.16-0.18 V (386-394 MHz), past a revival at 0.13-0.14 V.

- q2's 0.34 V tone modulates f01 almost as a pure 2 f_m tone of 313 MHz amplitude
  (beta = 0.42). The k = 4
  weight is J_2 of that single tone, which is why it couples at all.
- Instrument time on q3 (its 229 us thermal wait dominates): Step 1 (21 x 101, 200 averages)
  ~2 min, Step 2 (21 x 101) ~2 min, Step 3 (23 x 61) ~1.5 min, Step 4 (11 x 71, 400 averages)
  ~1.5 min.

## Evidence

5Q4C q3, 2026-10-01, discriminated, tag `q3-sideband-swap`, all `20261001-`:

- Prerequisites: `qubit_ramsey` `192733-854` (q3 detuning error 8.8 kHz), `single_shot_readout`
  `192858-889` (q3 fidelity 0.926).
- Step 1 `204331-847`; Step 2 `204556-446`; Step 3 `204835-611`; Step 4 `205026-414`
  (400 averages).

5Q4C q2, discriminated, 200 averages unless noted. The analysis is the report
`scq-reports/reports/parametric_qubit_reset_20260929/` (fits in its `data/`):

- Step 1 (`qubit_parametric_drive_amp`): `20260826-014139-942`, `20260921-205706-872`,
  `20260921-210333-928`. The line track is `data/ampline.json`.
- Steps 2-4 (`qubit_parametric_drive_time`, 0.26-0.34 V): 13 usable chevrons, from
  `20260826-014448-540` to `20260921-211249-852`. The final tone is `20260908-144252-583`,
  `20260908-144347-474` and `20260921-211249-852`. The 09-02 runs are the Trap 4 night.

## Open issues

`BACKLOG.md`:

- **I32:** the family's outputs mislead a calibration; `_time` should report f0 and t* from a
  fit that ties the detuning across rows (Step 2, Trap 1).
- **I33:** `ParametricReset.apply()` leaves the z oscillator at f* (Step 5).
- **I37:** `ParametricReset` has no ring-down wait (Step 5).
