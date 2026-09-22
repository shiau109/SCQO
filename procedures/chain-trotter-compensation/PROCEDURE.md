---
name: chain-trotter-compensation
description: Take two calibrated pair operations into the unidirectional Trotter chain. Calibrate the chain's per-round source-sink phase compensation with qc_trotter_compensation, write it into the chain parameter file, and run qc_unidirectional_trotter. Use after pair-partial-swap has produced both pairs' operations for the target (theta1, theta2), and again after any change to the round's timing.
goal: A chain parameter file whose compensation_amps zero the source-sink phase per round, and a qc_unidirectional_trotter run on it.
inputs:
  chain: source, relay and sink qubits (5Q4C q1, q2, q3)
  operations: the two pair operations from pair-partial-swap
  operation_gap_ns: the idle between a round's operations (20 on 5Q4C)
  max_rounds: the round-count axis (20)
outputs:
  compensation_amps: "{<sink>: a}, the amplitude factor of the sink's stark tone"
  trotter_run: sink population against round count
experiments: [qc_trotter_compensation, qc_unidirectional_trotter]
backends: [qm]
depends_on: [pair-partial-swap]
validated: hardware 5Q4C q1-q2-q3, 2026-09-22 (theta = 0.30, 0.30)
---

# chain-trotter-compensation

## Physics in brief

- **One round:** swap 1 (source → relay), swap 2 (relay → sink), reset of the relay, then
  the stark tones.
  - Only the **differential** source − sink phase per round is observable, and 0 maximizes
    the sink.
  - The relay's tone is inert: it plays after the reset, onto an emptied qubit.
- **Ideal sink after M rounds** with that phase at 0, for pair angles (θ1, θ2):
  P(M) = [sin θ1 sin θ2 Σ_{j<M} cos^(M−1−j)θ2 cos^j θ1]².
  - For equal small angles it peaks at about 4/e² ≈ 0.54, at M ≈ 2/θ². For θ = 0.30 that is
    round 22.
  - Larger angles reach the same peak in fewer rounds, so decoherence costs them less.

## Prerequisites

1. `pair-partial-swap` done for both pairs, with the readout freshly calibrated on all three
   qubits.
2. One parameter file shared by both experiments, so they cannot disagree about the round.
   5Q4C uses `~/.scqo/chain.json` (`--params` also reads TOML):
   - It holds only keys **both** Parameters classes accept. Parameters is `extra="forbid"`:
     a compensation-only key in the file makes `qc_unidirectional_trotter` refuse it.
   - Compensation-only keys go on the command line: `compensation_target`,
     `min_compensation_amp`, `max_compensation_amp`, `num_amp_points`.
   - Set every key explicitly so `~/.scqo/parameters.toml` cannot leak in. The stderr line
     `# parameter defaults from ...` lists anything that did.

   ```json
   {
     "targets": ["q1", "q2", "q3"],
     "first_pair": {"pair": "q1_q2", "operation": "partial_swap_030"},
     "second_pair": {"pair": "q2_q3", "operation": "partial_swap_030"},
     "reset_qubit": "q2",
     "reset_operation": "reset",
     "idle_reference_operation": "partial_swap",
     "swap_coupler_flux": {},
     "stark_operation": "stark",
     "stark_detuning_hz": 50000000.0,
     "compensation_amps": {"q3": 0.23},
     "prep_qubit": null,
     "prep_operation": "x180",
     "operation_gap_ns": 20,
     "max_rounds": 20,
     "reset_method": "thermal",
     "thermalization_time_ns": null,
     "active_reset_rounds": 1,
     "readout_mode": "average",
     "num_averages": 400
   }
   ```

## Steps

### Step 1: operations into the file

Set `first_pair` and `second_pair` to the operations from `pair-partial-swap`.

### Step 2: coarse compensation scan

- **Run**
  `scqo run qc_trotter_compensation --params chain.json --set compensation_target=<sink> --set max_compensation_amp=1.0 --set num_amp_points=31`.
  - If `compensation_amps` already holds the sink, add `--set "compensation_amps={}"`. The
    experiment refuses a qubit that is both swept and held fixed.
  - Takes about 1.5 minutes.
- **Read** `best_compensation_amp`, `best_sink_p_max` and `best_n_at_max`, plus the sink
  population against amplitude from `dataset.nc`. The grid step (0.033) is coarse next to a
  peak only about 0.1 wide.
- **Decide**:
  - Sweep only the **sink** and leave the source untoned. Only the difference matters.
  - On 5Q4C, q1's tone at 5192.9 MHz sits 2.6 MHz from q3 and would drive it.
  - The window stops at 1.0, one full turn (`procedures/README.md`), so it holds exactly
    one optimum (5Q4C: 0.23). The same phase one turn higher (1.05 on 5Q4C) is never used:
    a tone that strong drives the qubit.

### Step 3: fine scan

- **Run** the same command with `min_compensation_amp` and `max_compensation_amp` at the
  best value ± 0.12, clipped to 0–1.0, and 25 points (step 0.01).
- **Read**: average the sink over rounds 4..`max_rounds` and fit a parabola against
  amplitude, within ±0.05 of the best point. Cross-check with the per-amplitude maximum over
  rounds. The vertex is the compensation (2026-09-22: 0.2276 and 0.2299 → 0.23). The
  estimator itself reports only the grid argmax (Open issues).

### Step 4: write it and run the chain

- Write `"compensation_amps": {"<sink>": a}` into the chain file.
- **Run** `scqo run qc_unidirectional_trotter --params chain.json` (about 15 s).
- **Read** `sink_p_max` and `n_at_max`, and each qubit's population against round count.
- **Check** against the ideal curve of Physics in brief times a decay. 5Q4C 2026-09-22:
  - sink maximum 0.2675 at round 12
  - sink ≈ 0.05 + 0.93 × ideal(0.297, 0.306) × e^(−N/19): 19 rounds is 6.9 µs at 360 ns a
    round, close to q1's and q3's combined T2*

## Predicting the compensation from the pair calibrations

This is an optional cross-check, and it explains why Step 3 cannot be skipped. In turns,
modulo 1:

    s_sink(a*) = s_sink(a_sink,pair) − s_source(a_source,pair) + (f_source − f_sink)·(T_chain − T_pair)

- **s_q(a):** qubit q's measured stark phase curve.
- **a_sink,pair and a_source,pair:** the compensations the two pairs measured in
  `pair-partial-swap`.
- **f:** the frame (drive) frequencies.
- **T:** the **actual** round lengths, which differ from the nominal ones.

On 5Q4C the gateway simulator measured:

| round | nominal | actual | where the difference comes from |
|---|---|---|---|
| chain | 340 ns | 360 ns | the reset macro's `update_frequency` / `reset_if_phase` and the aligns add 20 ns |
| pair, gap 260 | 360 ns | 368 ns | 8 ns of overhead |
| pair, gap 252 | 352 ns | 360 ns | 8 ns of overhead |

f_q1 − f_q3 = −47.4 MHz, so one 4 ns clock cycle shifts the phase by 0.19 turn.

Verified on 2026-09-22:

- **Gap 260 with the frame term:** predicted 0.248 / 0.251, measured 0.23–0.24 (0.005 turn
  apart).
- **Gap 252, equal rounds, no frame term:** predicted 0.29, measured 0.21–0.22 (0.05 turn
  apart). The q2_q3 compensation sat at the phase-wrap point.
- **Consequence:** the prediction lands in the right neighbourhood but not precisely enough.
  An amplitude error of 0.07 costs 30–40% of the sink. Step 3 gives the final value.

## Stop criteria

- Done when the fine-scan vertex is written into the chain file and the trotter run
  completes.
- Abort on any hardware or gateway error, as `procedures/README.md` defines it.

## Traps

1. **Any timing change moves the optimum:** the gap, the reset length, the stark length, or
   align overhead. Rerun Steps 2–3 after changing the round.
2. **Drift.** Three scans within 30 minutes gave 0.23–0.24, 0.21–0.22 and 0.228–0.230. Run
   Step 3 right before the trotter run.
3. **One file, two consumers.** Keep compensation-only keys out of the chain file, and add
   `--set "compensation_amps={}"` when rescanning a sink that is already compensated.
4. **Stale readout,** as in `pair-partial-swap`.

## Typical values

5Q4C cooldown cd2, 2026-09-22, both pairs `partial_swap_030`, gap 20:

| | value |
|---|---|
| sink compensation | q3 0.23 |
| round length | 360 ns |
| trotter sink maximum | 0.2675 at round 12 |
| trotter decay | about 19 rounds |

## Evidence

5Q4C runs (all `20260922-`):

- **Coarse scans:** `194717-192`, `200826-906`
- **Fine scan:** `201332-432`
- **Trotter:** `202034-457`

## Open issues

`BACKLOG.md`:

- **F14:** a refined optimum in `qc_trotter_compensation`
- **F16:** recording the actual round length
- **F17:** a shorter round, with the stark tones played during the relay reset
- **F18:** a stark amplitude-to-phase conversion, so the one-turn bound can live in code
