---
name: qubit-frequency-park
description: Park a flux-tunable qubit at its flux apex, or at a chosen f01, and keep it there as the line's DC offset drifts. Use at bring-up, after a cooldown, when T1/T2* drop or the drive no longer matches the qubit, and after ANY change of a coupler's standing bias.
goal: The qubit's idle_flux within 0.2 mV of its apex (or of the root for the chosen f01), confirmed against the same run's reading, with drive_freq_hz / f_01_hz at the parked frequency to ~10 kHz.
inputs:
  qubit: the flux-tunable qubit to park, e.g. q1
  park_frequency_hz: the f01 to park at; omit for the apex
  flux_side: lower | upper | nearest, only when a window holds a root on each side of the apex
outputs:
  idle_flux: the parked DC bias, absolute volts
  drive_freq_hz: the drive at the parked frequency, with its f_01_hz fact
  flux_offset: the DC apex (absolute), when the last window held it
  f_q_max_hz: the apex frequency at the current coupler biases, when the window held it
experiments: [resonator_spectroscopy_flux, qubit_spectroscopy_flux_pulse, qubit_ramsey_flux_pulse, qubit_ramsey, qubit_ramsey_flux_crosstalk_pulse]
backends: [qm]
validated: hardware 5Q4C q1, 2026-09-26 (apex; from a deliberate +8 mV DC offset); q1, q2, q3 re-parked by Steps 3-5 on 2026-10-04
---

# qubit-frequency-park

## Physics in brief

- **The offset walks, the arch does not.** On 5Q4C every z line's DC offset moved +6 to
  +10 mV in four days (at times ~0.2 mV/h) while each qubit's apex frequency moved by
  0.02–0.46 MHz. Parking is performance, not bookkeeping: re-parking q3 onto its apex took
  T1 from 16.8 to 24.8 µs.
- **The tolerance is ±1 mV** of a sweet spot (5Q4C curvature 0.015–0.018 MHz/mV², so 1 mV
  costs ~15 kHz). The fine step reaches 0.02 mV, so the procedure's working goal is 0.2 mV:
  the run-to-run scatter.
- **Three complementary readings of the same arch.** No one of them is the authority; each
  proposes `idle_flux`, and the step list below uses each where it is strongest.

  | experiment | frame | sees | gives | still works when | 5Q4C q1, from +8 mV |
  |---|---|---|---|---|---|
  | `resonator_spectroscopy_flux` | DC, absolute window | the resonator dip | offset, **period**, coarse apex | the qubit is not visible yet | ~2 mV off, 16 s |
  | `qubit_spectroscopy_flux_pulse` | pulse, relative | the qubit line | the whole arch (offset, period, `ej_sum_hz`, `f_q_max_hz`) | T2* is short | 0.26 mV off, 53 s |
  | `qubit_ramsey_flux_pulse` | pulse, relative | a Ramsey fringe per flux | the local arch to kHz: apex or the root for an f01 | the fringe survives several cycles | 0.39 mV off after one run, 0.016 mV after two; 97 s per run |

- **How the fine step works.** The π/2 pulses and the readout stay at the idle point. A
  square z pulse detunes the qubit only during the idle τ, so the fringe frequency gives f01
  at each amplitude. A pulse moves the qubit by g times the same DC step, with no constant
  offset, and g differs from line to line (5Q4C: q1 0.956–0.958, q2 0.921). A park found
  from far away therefore lands within 4–8 % of the move, and a re-run converges.
- **Every flux line moves every apex, and a DC move more than a pulse.** At DC a coupler
  line shifts qubit apex LOCATIONS by 6–13 % of its own change (5Q4C zc12: q1 5.6 %, q2
  12.8 %, q3 7.4 %, q3 is not even its neighbour), and another QUBIT's line by about 8 %
  (z2: q1 8.4 %, q3 7.7 %). A pulse of a few microseconds reads far less (z2: −0.3 % and
  +1.3 %): a slow part of 6–9 points arrives over about a millisecond
  (`scq-reports/reports/flux_crosstalk_time_dependence_20261004`, BACKLOG F32). A park is a
  DC move, so the DC values are the ones that count here. A coupler also shifts a
  neighbour's apex HEIGHT through its own frequency. So `flux_offset` and `f_q_max_hz` hold
  only at the current biases of the other lines, and couplers are parked first.

## Prerequisites

1. **The couplers' standing biases are final.** A coupler `idle_flux` that moved by more than
   ~15 mV since the last park invalidates the parks of the qubits around it, neighbours or
   not. (The coupler side is BACKLOG F24.)
2. **A working π/2 at the idle point.** The fine step's Ramsey needs it (`pi_amp_x90`, or the
   x90 the backend derives). A qubit that moved far since its last calibration gets Step 2
   first.
3. **Readout.** With `use_state_discrimination=true`, a fresh `single_shot_readout`, as in
   `pair-partial-swap` Prerequisite 1. I/Q works without it (the axis comes from the stored
   blob centers).
4. **Arch facts, if possible.** `flux_offset`, `flux_per_phi0` and `f_q_max_hz` let the fine
   step predict its swing, pick the direction of its virtual detuning and refuse a window
   that would fold. Without them it runs with the apex default and says so
   (`ramp_sign_from = "default"`).

## Steps

### Step 1: coarse position and period (only when they are unknown)

- **Run** `resonator_spectroscopy_flux --targets <q>` with an absolute window around the
  expected apex that spans a good part of a period (5Q4C q1: `start_flux_v=0.0`,
  `end_flux_v=0.49`, 50 points), inside the port's rail.
- **Read** `flux_offset`, `flux_per_phi0`.
- **Decide:** accept to seed `idle_flux` and the arch facts, then go to Step 2 or Step 3.
  **Never run it after Step 3**: its DC sweep over hundreds of mV most likely moves the apex
  by itself (Trap 3).

### Step 2: the arch (when the facts are missing or stale, or the target is far away)

- **Run** `qubit_spectroscopy_flux_pulse --targets <q>` with a window of ±40 mV relative to
  idle, 21 points, a drive window that covers the swing (5Q4C: `start_drive_detuning_hz=5e6`,
  `end_drive_detuning_hz=-35e6`, 51 points), 100 averages.
- **Read** `flux_offset`, `flux_per_phi0`, `f01_at_sweet_spot_hz`, `ej_sum_hz`.
- **Decide:** accept. It re-parks at its apex and refreshes the arch facts Step 3 predicts
  with. It reads a pulsed excursion a few percent large, so from far away it lands within a
  fraction of a millivolt, not better. **If the qubit's T2* is too short for Ramsey fringes
  (they die before a few cycles, e.g. T2* < ~1 µs at 4 MHz), stop here**: this is the
  park.

### Step 3: the fine park

- **Run** `qubit_ramsey_flux_pulse --targets <q>` on ONE qubit, with the defaults: ∓12 mV
  relative, 7 points, `frequency_detuning_hz=4e6`, idle 16–4000 ns in 201 points, 200
  averages. Add `use_state_discrimination=true` when the readout supports it. For a target
  frequency, add `park_frequency_hz=<f>` and narrow the window to ∓3–5 mV around the
  predicted root. Add `flux_side` only when both roots fall inside it.
- **Read** from `result.fit[<q>]`: `flux_offset_from_idle` (apex) or `park_excursion_v`
  (target), `idle_flux`, `ramp_detuning_hz` / `ramp_sign_from`, `fold_suspected`,
  `apex_not_bracketed` / `park_out_of_window`, `n_valid_points`, and the outcome.
- **Decide:**
  - SUCCESSFUL, |excursion| ≤ 0.2 mV: accept; this is within the run-to-run scatter.
    Go to Step 4.
  - SUCCESSFUL, larger: accept and run Step 3 again. Each run misses by 4–8 % of its move
    (1 − g): from +8 mV, q1's run 1 stopped 0.39 mV short and run 2 landed 0.016 mV from the
    DC reference; q2 moved by 0.73 mV came out 0.06 mV past its apex. A move of more than
    ~20 mV may take a third run.
  - `apex_not_bracketed` or `park_out_of_window`: the window missed. Shift it toward the side
    where the curve rises (apex) or toward the target, or do Step 2 first.
  - Refused before the probe with `folding_risk` or `undersampled`, or `fold_suspected`: the
    message names the detuning or time grid that works. Raise `frequency_detuning_hz`, or
    narrow the window.

### Step 4: verify

- **Run** `qubit_ramsey --targets <q>` with `frequency_detuning_hz=3e5` and
  `max_idle_time_ns=30000`.
- **Read** `detuning_error_hz`, `t2_star_s`.
- **Decide:** |detuning error| below ~10 kHz means the park and its drive agree; accept its
  `drive_freq_hz`. A T2* that fell relative to the previous park is worth a second look (a
  TLS near the new frequency, or a missed apex).

### Step 5: several qubits

- Park them one at a time with Steps 3–4. A park is a DC move, and at DC a qubit line
  moves the other qubits' apexes by about 8 % of its own change (see *Physics in brief*;
  the ~1 % once quoted here is the short-pulse value). A re-park of 1 mV therefore moves
  the others by ~0.08 mV and one pass is enough. After a move of more than ~2 mV on any
  line, read the qubits parked BEFORE it again (Step 3) and re-park those above 0.2 mV.
- End with a record-only reading of each qubit (`qubit_ramsey_flux_pulse --no-update`, one
  target per run), or with one multi-target run as an inspection. The multi-target run is
  record-only by design (`multi_target_context`): every line moves at once, and simultaneous
  neighbours pick up ZZ/2 in their fringes.

### Step 6: once per cooldown

- The crosstalk matrix, coupler columns included. It has two readings per cell, and a park
  needs the DC one:
  - **DC:** move the source line's `idle_flux` by ±20 mV with `scqo set`, read the
    target's apex with Step 3 (`--no-update`) at each stop, return to the start in between
    and at the end. The apex moves by −m times the DC move.
  - **Short pulses:** `qubit_ramsey_flux_crosstalk_pulse --set source_line=<line>`, about a
    minute per cell, no device write. Its `source_lead_time_ns` reads how the value grows
    toward the DC one.
  - A `flux_component` scan of a qubit sitting at its apex gives only |m|, and not even that
    reliably next to a coupler (the apex HEIGHT moves too).
  Open decisions (where the coefficients are stored): BACKLOG F28, F32.

## Stop criteria

- Success: the last Step 3 run is SUCCESSFUL with |excursion| ≤ 0.2 mV and the Step 4
  detuning error is below ~10 kHz.
- Abort on any hardware or gateway error, as `procedures/README.md` defines it.

## Traps

1. **Folding.**
   - *Symptom:* a hand-run Ramsey scan over flux gives an "arch" that jumps up and down by
     the detuning.
   - *Case:* 5Q4C 2026-09-26, 1 MHz detuning over a 1.4 MHz swing; the earlier "q2 re-park
     that did not move" was the same fold.
   - *Cure:* the fine step picks the ramp's sign from the arch facts and refuses a window that
     would fold. Do not reproduce it by hand with a small detuning.
2. **Reading a large-detuning Ramsey with the `qubit_ramsey` estimator.** At 4 MHz it
   reported frequencies >1 MHz off (BACKLOG I24). The fine step reads fringes with
   `tools.fringe_frequency` instead. A hand scan must do the same.
3. **A wide DC sweep moves the apex.**
   - *Case:* 5Q4C q1 2026-09-26: the DC apex read 0.260756 V at 21:32 and 0.260448 V at
     21:40, with `resonator_spectroscopy_flux` sweeping q1 over 0–0.49 V at 21:33 in between.
     Over the previous 1.5 h it had drifted only +0.06 mV. Most likely hysteresis; not yet
     isolated.
   - *Cure:* Step 1 only before Step 3, never after it.
4. **An old truth.** The DC apex drifts (5Q4C q1: −0.33 mV between 16:00 and 20:00). Judge a
   result only against a reference from the same hour.
5. **`apex_flux_stderr` is optimistic.** It reads 0.001–0.004 mV while repeated runs scatter
   by ~0.1 mV. Use 0.2 mV as the repeatability.
6. **Coupler changes.** See Prerequisite 1. After a coupler moves, `f_q_max_hz` and
   `flux_offset` of the qubits around it are stale too.
7. **The fine step starts off its drive.** At +8 mV the 5Q4C q1 idle sits ~1 MHz below its
   drive, and the 16 ns π/2 tolerates it. A qubit with a long, weak π/2 that has moved far
   loses fringe contrast. Park coarsely first (Step 2), or retune the drive (Step 4) before
   the fine step.
8. **Long flux pulses at a high duty cycle move the apexes.**
   - *Case:* 5Q4C 2026-10-04: crosstalk runs that held a source line up to 100 mV off its
     bias for 0.3–3 ms of every shot. Over that evening the apexes of q1, q2 and q3 went
     from +0.19 / +0.06 / +0.38 mV to −0.83 / −0.73 / −0.36 mV from their biases, most of it
     while those runs were taken. Not separated from the ordinary drift.
   - *Cure:* re-park after such runs, or keep their duty cycle low (a longer
     `thermalization_time_ns`).

## Typical values

5Q4C cooldown cd2, 2026-09-26, coupler biases q1_q2_c 0.16 V and q2_q3_c 0.06 V:

| qubit | DC curvature (MHz/mV²) | parked `idle_flux` (V) | f01 (MHz) |
|---|---|---|---|
| q1 | −0.0152 / −0.0153 | 0.260448 (21:40) | 5144.605 |
| q2 | −0.0183 | −0.017872 (16:00) | 4842.148 |
| q3 | −0.0172 | 0.007432 (16:00) | 5191.926 |

- Pulse frame on q1: curvature −0.0141 MHz/mV², g = 0.956–0.958, no constant offset.
- Repeatability: 2–3 kHz for a frequency repeat at the apex; ~0.1 mV for the apex between
  runs minutes apart.
- Instrument time: `resonator_spectroscopy_flux` 16 s, `qubit_spectroscopy_flux_pulse` 53 s,
  `qubit_ramsey_flux_pulse` 97 s, a manual DC reference scan (six Ramseys) ~3.5 min.

## Evidence

5Q4C runs, all `20260926-`:

- **Four-method comparison** (tag `f23-compare`): DC reference 1 `212946-898` …
  `213219-138`; `resonator_spectroscopy_flux` `213255-994`; `qubit_spectroscopy_flux_pulse`
  `213312-180`; `qubit_ramsey_flux_pulse` run 1 (accepted) `213405-254`, run 2
  `213542-674`; DC reference 2 `213726-502` … `213958-117`.
- **Pulse-frame pre-test** with a scratch builder (not in the datastore; data in
  `scqat/temp/ramsey_flux_pulse_pretest/`) and its DC reference (tag `flux-park-dc-ref`):
  `195648-159` … `195933-386`.
- **First manual DC park** (tag `flux-park`): q1 `154741-747` … `155024-392`, q2
  `155314-209` … `155531-551`, q3 `155630-420` … `155855-936`.
- **Coupler crosstalk** (tag `coupler-scan`): see `docs/coupler-readout-plan.md`.

5Q4C runs of 2026-10-04:

- **DC crosstalk** (tag `crosstalk-dc`): zc12 walked ±20 mV, `20261004-193018-577` …
  `194637-322`; z2 walked ±20 mV, `215825-075` … `221522-451`.
- **Re-park of q1, q2, q3** (tag `re-park`, Steps 3–5 as written): `223509-604` …
  `224703-886`. Two fine passes per qubit; the closing readings sat +0.02 / −0.03 /
  −0.01 mV from the new biases and the Step 4 detuning errors were +4.8 / −0.8 / +0.4 kHz.

## Open issues

`BACKLOG.md`:

- **F24:** coupler state readout and the crosstalk matrix (Step 6, Prerequisite 1)
- **I24:** the `ramsey` estimator at large virtual detuning (Trap 2)
- **I25:** the pulse arch's excursion ratio (Step 2)
- **F28, F32:** where the crosstalk coefficients are stored, and the slow part of the
  crosstalk (Steps 5 and 6)
- Qblox: `qubit_ramsey_flux_pulse` has a probe, but no hardware run yet.
