# BACKLOG — deferred features and known issues

The memory that CLAUDE.md is not allowed to be. Append an entry whenever you DEFER a feature
or DISCOVER a non-urgent problem while working on something else; give it the date, what you
were working on when you found it, the pointer (file / function), and what "done" looks like.
Delete the entry when it lands and name the commit or `RELEASES.d/` fragment in its place for
one release, then drop it. Priorities: **high** = blocks or corrupts data, **medium** = wrong
provenance or a trap a user can walk into, **low** = hygiene.

## Planned features (deferred by decision)

### F1 Pull-seed drift rows — record hand edits of the vendor config as history (medium)
- Added 2026-09-03 while doing the drive-frequency audit + setup snapshots.
- Problem: `RecordingDevice._seed_pull` writes no history rows by design (seeding is not a
  change), so a hand edit of the vendor config leaves a hole; `Store.record` takes `old` from
  scqo_state.json, not the vendor, so the NEXT row records a wrong `old` (even a first-ever
  write records `old=None` while `scqo set`'s confirmation shows the vendor value); and CLI
  `scqo state --sources` (live values) and the viewer (file values) disagree after a hand edit.
- Where: `scqo/device.py` `_seed_pull` / `_set_knob`, `scqo/stores.py::Store.record`,
  `scqo/provenance.py`, `scqo/viewer/app.py::_context_sources`, `scqo/changes.py` (a new
  column, e.g. `origin`).
- Done when: at pull-seed a vendor value that differs (exact compare) from the last recorded
  one appends a ChangeRecord marked as vendor-originated (observer login, discovery time);
  provenance gains that status; CLI and viewer agree.

### F2 Read the written field back after the push (medium)
- Added 2026-09-03 while explaining push-first.
- Problem: `_set_knob` records the REQUESTED value and `_sync_coupled` skips the written
  field, so grid-rounding setters (QM `thermalization_time_s` 4 ns, `readout_depletion_s`
  4 ns, `flux_delay_s` 1 ns) leave history `new` != vendor value; the next session's
  provenance shows `(externally changed)` with no hand edit (measured: requested
  2.34567e-4 s, vendor 2.34564e-4 s).
- Where: `scqo/device.py` L440-453; `scqo-qm/scqo_qm/quam_fields.py`
  `set_thermalization_time` / `set_readout_depletion` / `set_flux_delay`.
- Done when: the recorded `new` is the vendor readback (or both are stored) and a rounded
  write no longer flips provenance to external.

### F3 Experiment-reported run-scoped amendments in the run record (medium)
- Added 2026-09-03 with the setup-snapshot feature (deliberately left out).
- Problem: the setup snapshot is the STANDING config at run start; the broadband probes'
  per-segment LO/band/RF tables and the cryoscope's run-scoped drive op never appear in any
  record (they are restored before the run ends).
- Where: `scqo/experiment.py` (a `note_vendor_amendment(**fields)` accumulator persisted as
  record.json `vendor_amendments`), `scqo-qm/scqo_qm/experiments/broadband_*.py`,
  `qubit_spectroscopy_cryoscope.py::install_drive_op`,
  `scqo-qblox/scqo_qblox/experiments/broadband_*.py`.
- Done when: a broadband run's record lists every segment's LO/band/RF and the cryoscope
  run its drive op parameters; additive only, no sequence change.

### F4 Snapshots listing + index column (low)
- Added 2026-09-03 with the setup-snapshot feature.
- A device-level viewer page listing the distinct setup snapshots (hash, first/last run,
  source setup), and `scqo find --snapshot <hash>` — the latter needs a `runs` column, so a
  `SCHEMA_VERSION` bump and a full reindex on every lab.

### F5 `drive_freq_hz` read side: `f_01` or `xy.RF_frequency`? (decision)
- Added 2026-09-03 with the drive-frequency audit.
- Today `get_drive_freq` reads `f_01` (bookkeeping) while the line plays `xy.RF_frequency`;
  the startup audit keeps them equal. Reading the RF instead would change the "uncalibrated
  qubit reads None" contract (`anchor()` falls back to design.toml today).
- Where: `scqo-qm/scqo_qm/quam_fields.py::get_drive_freq`, `qm_backend.py::_read_or_none`.

### F6 Run the whole-tree audits from `scripts/check_real_config.py` (low)
- Added 2026-09-03. The QM self-test loads the state directly and runs none of
  `flux_point_problems` / `flux_headroom_problems` / `drive_frequency_problems`.

### F7 Lift the TEMPORARY push refusal
- Added 2026-09-03 (fragment `hardware-push-refusal`). Retitled 2026-09-25: the qualibrate GUI
  is gone (F21), so the remaining reason is the one that was always the real one — a push seeds
  the vendor config from `scqo_state.json` with no history rows and would clobber hand edits.
- Delete the guard in `scqo/labconfig.py::make_session` + its tests
  (`test_make_session_refuses_push_on_hardware_backends`,
  `test_hardware_setup_with_push_config_refuses_without_traceback`); keep the `state_sync`
  parse validation. The QM driver's second guard is ALREADY GONE (scqo-qm `cdb6e79`), so this
  is now a one-place change.

### F8 PR #29 viewer dashboard — held pending a CHARTER decision
- Carried over; the reviewed defects live only in the session memory `pr29-viewer-dashboard-held`.
  Decide the charter, then either land with the fixes or close.

### F9 Lab report: value from physical/state, the +/- from the campaign that produced it (medium)
- Added 2026-09-05 while fixing the lab report's dressed-frequency source.
- Problem: the authority for a reported value should be `physical.json` / `scqo_state.json`,
  which is accept-gated by construction - a campaign's aggregate suggestion is `role="fact"`
  (`t1_s` / `t2_star_s` / `t2_echo_s` / `n_th`) and reaches the store only once a human
  accepts it. But `extract_chip_metrics` takes t1 / t2_ramsey / t2_echo / readout_fidelity /
  n_th CAMPAIGN-FIRST with the physical value as the fallback, and
  `query_campaign_statistics` never looks at suggestion status - it takes the newest
  qualifying campaign, reviewed or not. So one sheet carries two rules: the `#1` columns are
  reviewed, the `#100` columns are not. It was a fair workaround while campaigns did not
  offer their accept step (that landed 2026-09-04, `06ef197`); it is not one now.
- Where: `scqo/viewer/lab_report/metrics.py::extract_chip_metrics` - the `state`/`phys`
  dicts drop each row's `"source"` key, and the statistics are fetched independently by
  device/cooldown. Both inputs already exist: `scqo/viewer/app.py::_param_rows` puts the
  full `scqo.provenance.live_sources` info dict on every row, and that dict carries
  `campaign_id` whenever the current value traces to a campaign accept.
- Design already decided (do not re-litigate):
  - VALUE from physical/state; the +/- and `n` from the ONE campaign named by
    `source["campaign_id"]`, never `query_campaign_statistics`' newest-first pick.
  - That route also dissolves the "statistics are keyed by FIT key, suggestions by CATALOG
    field" join problem - the change history already made the link - and `live_sources` is
    strict-match, so a drifted value reports "external" instead of crediting a campaign.
  - NO CORRESPONDING VALUE MEANS AN EMPTY CELL (operator's call, 2026-09-05): the export
    shape is someone else's template and must not grow rows. So when the physical value's
    provenance is not a campaign (status run / manual / external / unrecorded), `T1 #100`
    is blank - and since `DATA_ROWS` has no `T1 #1` row, that chip's T1 leaves the Data
    sheet entirely until a campaign is run AND accepted.
  - Flip the `n_th` precedence in the same change (it feeds `temperature_mk`). Deliberately
    NOT a separate entry: it cannot land alone without leaving two rules in one sheet.
  - Trap: `suggestions_pending == 0` is NOT "reviewed". A campaign whose quantities all fell
    below `[writeback] min_n` proposes nothing, so its pending count is zero too
    (`scqo/datastore.py::_upsert_campaign`). The check must read the manifest's suggestion rows.
  - The unified (whole-cooldown) context merges rows by `source["timestamp"]` and keeps each
    winning row dict whole, so `value` and `source` stay same-sourced - but a row whose
    status is "external" still competes on timestamp.
- Done when: a `#100` cell carries a number only while that physical value's provenance is a
  campaign, its +/- comes from that same campaign, and `tests/test_lab_report.py` pins that
  an un-accepted campaign does not reach the sheet.

### F10 OPX+ flux predistortion: the FIR/IIR writeback (medium)
- Deferred 2026-09-11 when the OPX+/Octave support landed (scqo-qm, phases 0-5 + 7;
  phase 6 was skipped by decision because the lab's OPX+ wiring is not settled).
- Problem: `apply_distortion` writes an LF-FEM `opx_output.exponential_filter`, a list
  of (A, tau) pairs. An `OPXPlusAnalogOutputPort` has no such field - it predistorts
  through `feedforward_filter` (FIR) + `feedback_filter` (IIR), both on the shared
  `LFAnalogOutputPort` base. That is a DIFFERENT decomposition, not a renamed field, so
  the conversion is real arithmetic and not a mapping.
- Today it refuses BY NAME rather than doing the wrong thing, and
  `operator_commands()` hides the CLI on a tree whose flux lines are all OPX+, so an
  operator is never sent at a door that is walled up. That refusal is the correct
  interim behaviour, not a stopgap to rush past: before it, quam ACCEPTED the
  assignment on a port class with no such field and then dropped it on `to_dict()` -
  printed success, saved state.json with no filter in it, flux line still distorted.
- Both cryoscopes still MEASURE the distortion on an OPX+ and their facts land in
  physical.json as usual; only the vendor writeback is missing.
- Where: `scqo-qm/scqo_qm/backend/_distortion.py::_exponential_filter_port` is the one
  door both entry points resolve through, so the FIR/IIR path has exactly one place to
  attach. `scqo_qm/_family.py::flux_port_family` already answers which family a channel
  is on.
- Only worth doing once an OPX+ with z lines actually exists - see the hardware
  validation row below, which has to come first.
- Done when: an accepted cryoscope's facts reach `feedforward_filter` / `feedback_filter`
  on an OPX+ port, the round trip is pinned offline against a real built tree
  (`scripts/make_opxp_fixture.py`), and the CLI stops being hidden on those trees.

### F11 Offline re-estimate: the `scqo estimate` verb (P2) and its surroundings (P3)
- Added 2026-09-20, when P1 of `docs/reestimate-plan.md` landed (the self-contained
  `dataset.nc`: `Experiment.run_estimate`, `scqo/estimate_inputs.py`, the embedded
  acquisition-time snapshot). The plan itself was not in this file at all, so the
  remaining two thirds were invisible to "consult BACKLOG.md before planning".
- P2 is the verb: `Session.reestimate()` + `scqo estimate <run_id> [--set k=v]`, the
  estimate-stage field marking (`estimate_field` in `parameters.py`; only a field no
  probe reads may be overridden), the derived-run shape (`reestimate_of`, era inherited
  from the root, no campaign stamp), index `SCHEMA_VERSION` 10 -> 11, and the
  whole-registry round-trip test. Old runs (no embedded attrs) take their inputs from
  `device_before.json` + the setup snapshot — with an UNAVAILABLE physical store when
  the run predates 2026-09-03, because an empty one would silently downgrade
  `fact_sourced()` from measured to design.
- Still to decide before P2 starts (plan §1): D1 verb name, D2 derived-run dataset is a
  COPY, D4 `update="apply"` refused at re-estimate, D5 the first batch of
  estimate-stage fields. D3 (embed the whole snapshot) was decided and is implemented.
- P3 is the surroundings: viewer links between a root and its re-fits, TUTORIAL/AGENTS
  sections, the two drivers' AST tests (no `self.estimate()`), release fragment.
- Also deferred with the plan (§8): campaign statistics recomputed after a child is
  re-fitted; BATCH re-estimation (refresh a window of old runs after a fit fix — needs a
  folder-multiplication policy first); rebuilding pre-2026-09-03 facts from
  `history.sqlite` by `started_at` instead of `--facts live`; `design.toml` in the setup
  snapshot; folding the 5 `run()` overriders into base `run()` + an `acquire()` hook
  (they are all "boundary write around acquire", and none calls
  `attach_acquisition_coords()`).
- Done when: `scqo estimate <run_id> --set analysis_method=circle` produces a derived run
  on a REAL old 5Q4C `resonator_spectroscopy` run, with the figure and the absolute
  frequency checked by eye; and `docs/reestimate-plan.md` is deleted, its content moved
  into TUTORIAL/CLAUDE.md.

### F12 Finish and review the `peak_inverted` polarity carrier (medium)
- Added 2026-09-20, when the WIP branch `claude/vigilant-nobel-92e114` was merged into
  scqat main (merge `0b14f0a`, one commit `193b3f0`). That commit calls ITSELF
  "UNFINISHED AND UNREVIEWED": it was last edited 2026-08-26 and committed only to
  preserve worktree state across the `D:\github` -> `D:\project\scqo_system` move, so it
  has never had a review pass. It merged clean (main had touched none of its 9 files) and
  the three touched test files pass, which is why it is a backlog entry and not a revert.
- What landed: `peak_fit.fit_peaks` picks the stronger polarity per row and, when the dip
  wins, fits POSITIVE Lorentzians on the negated trace — so `peak_amplitude` is
  polarity-NORMALIZED and cannot by itself tell an absorption dip from an emission peak
  (since 2026-09-27 `fit_peaks` never reports a negative amplitude). `peak_inverted` (per
  peak) and `n_inverted` (per map) now carry that distinction through `track_peaks`'
  pooling and out through both estimators' plot_data/attrs; `reduced_map` is never negated.
- What is NOT finished: the flag has NO consumer. Both visualizations only state that it
  "rides along in plot_data for consumers that need dip-vs-peak" — nothing plots it,
  nothing branches on it, and nobody takes the signed
  `np.where(peak_inverted, -peak_amplitude, peak_amplitude)` the docstrings advertise. A
  dip-heavy map still reads as if every peak were an emission peak, which is the trap the
  commit set out to close.
- Second trap, for whoever writes that consumer: this CHANGED the result contract of
  `track_peaks` and of both estimators' plot_data. A consumer must tolerate
  `peak_inverted` being ABSENT, or replotting any `plotdata.nc` written before
  2026-09-20 breaks — the same way the readout average-mode change already stopped old
  readout plotdata from replotting.
- Where: `scqat/tools/peak_map.py` (`track_peaks`);
  `scqat/estimators/parametric_drive_resonance/{estimator,visualization}.py`;
  `scqat/estimators/qubit_spectroscopy_flux/{estimator,peaks,visualization}.py`. Tests:
  `tests/test_peak_map.py`, `tests/test_parametric_drive_resonance_estimator.py`,
  `tests/test_qubit_spectroscopy_flux_estimator.py` (23 passed, 0 skipped at the merge).
- Done when: the polarity work is reviewed and actually CONSUMED — at minimum the two
  visualizations render dip-fitted peaks distinguishably and the docstrings stop promising
  a consumer that does not exist. The release fragment is already written
  (`RELEASES.d/peak-inverted-polarity.toml`, kind `additive`) and says in as many words
  that the flag has no consumer, so the next combo ANNOUNCES the gap instead of shipping
  it silently — do not treat that fragment as evidence the feature is finished.

### F15 `qc_n_stark_amp`: an error bar on `compensating_theta_rad` (low)
- Added 2026-09-22 (`procedures/pair-partial-swap`, Step 4).
- Problem: the procedure stops at |theta - target| <= 0.01 rad, but the period-based angle
  scatters ~+-0.007 rad run to run and the estimator reports no uncertainty, so the stop
  rule cannot tell a real miss from noise.
- Where: scqat `estimators/qc_n_stark_amp/` (the period fit's covariance at the compensating
  row).
- Done when: `compensating_theta_err_rad` is reported.

### F16 Record the actual round length of repeated-round experiments (medium)
- Added 2026-09-22 while comparing the pair and chain compensations.
- Problem: a stark compensation only means something at the round length it was measured
  at (frequency difference x round length: 0.19-0.2 turn per 4 ns clock cycle on 5Q4C),
  and the programs run longer than their nominal rounds — `qc_n_stark_amp` /
  `qc_swap_flux_stark` = swap + gap + stark + 8 ns, the Trotter chain = nominal + 20 ns
  (the reset macro's `update_frequency`/`reset_if_phase` and the aligns). Found only by
  measuring pulse spacings on the QM gateway simulator with a scratch script.
- Method of that script, so it can be rebuilt: `Session.preview(name, params, out_dir,
  options={"simulate_ns": N})` builds the program exactly as a run would; keep
  `job.get_simulated_samples()`; on the moving qubit's z output (`"<fem>-<port>"` key) the
  round is the spacing between consecutive swap pulses, detected against the trace's
  baseline (the output carries the idle DC offset). Preview does not hand the samples out,
  so the script had to replace the private `QMBackend._simulated_waveforms`; a real tool
  needs preview to keep the raw samples first. The chain simulation needed a 16 us window
  and `max_rounds=2`. Deliberately left out of the `register_partial_swap` landing
  (2026-09-22): it had been used on one day only, and not by the second partial-swap
  calibration (θ 0.60), whose rounds matched the first.
- Where: the four QM probes (`qc_n_stark_amp`, `qc_swap_flux_stark`,
  `qc_trotter_compensation`, `qc_unidirectional_trotter`), the run record, and
  `QMBackend.preview` (raw samples).
- Done when: each run records its round period (measured once per program build, or derived
  from the compiled program) — or the probes pad a round to a declared length — and the
  simulator measurement is a script in `scqo-qm/scripts/`.

### F17 A shorter Trotter round: the stark tones during the relay reset — CODE LANDED 2026-10-08, HARDWARE OWED (medium)
- Added 2026-09-22 after the `partial_swap_030` chain run `20260922-202034-457`.
- Problem: 80 ns of the 360 ns round swaps; the rest is three gaps (60), the relay reset
  (140 + overhead) and the stark tones (60). The sink decays with ~19 rounds (6.9 us),
  close to the q1-q3 combined dephasing, so round length is the lever. The tones act on the
  source and sink, the reset on the relay, so they can play concurrently.
- Landed (`RELEASES.d/chain-stark-with-reset.toml`): `stark_timing="with_reset"` on
  `qc_unidirectional_trotter` and, inherited, `qc_trotter_compensation`; the default
  `after_reset` is the round as it was. QM only — neither chain experiment has a Qblox
  probe. The round body now lives once, in `scqo-qm` `_chain_round.play_chain_round`.
  Offline only: the default programs are the earlier ones statement for statement, and a
  `with_reset` program differs from them by the one `align()` before the tones.
- Done on 5Q4C 2026-10-08 (tag `stark-with-reset-1008`; every line sat ~2 mV off its park
  that day, which this test does not depend on): **the tones do not disturb the relay's
  reset.** q2 prepared in |1>, both swap steps `idle`, 8 rounds, 4000 averages; q2 after
  1-8 resets, mean:

  | tone on q3 | `after_reset` | `with_reset` |
  |---|---|---|
  | none (the same program) | 0.0176 (`122345-811`) | 0.0159 (`122218-446`) |
  | 0.40 | 0.0184 (`122259-598`) | 0.0169 (`122238-867`) |
  | 0.90 | 0.0185 (`122455-283`) | 0.0179 (`122322-654`) |

  The two no-tone runs are one program and differ by 0.0017, so that is the scatter. q3
  itself read 0.062-0.065 in the first two rows; at 0.90 the tone drives it in both
  timings (I36), more with the reset (mean 0.093, highest 0.116 at round 4-5) than after
  it (0.075, 0.084).
- Still owed, all on 5Q4C:
  1. the `with_reset` round length on the gateway simulator (F16's method), and how far the
     reset pulse starts behind the tones (the reset macro sets its z frequency first). By
     the pulse budget at gap 20 the round is ~300 ns (40 + 20 + 40 + 20 + 140 + 20 + ~20
     of overhead), not the ~280 this entry first said. Tried 2026-10-08 and blocked by I43;
  2. the compensation rescanned at `with_reset`, and the sink curve against the 360 ns
     round. Not run 2026-10-08: the lines had to be re-parked first;
  3. `procedures/chain-trotter-compensation/PROCEDURE.md` does not name `stark_timing` yet
     (the file carried another session's uncommitted edits on 2026-10-08).
- Done when: those three are done.

### F18 A stark amplitude-to-phase conversion, and the one-turn bound in code (medium)
- Added 2026-09-22 with the operator's rule that a stark compensation tone stays below one
  full turn (a stronger tone drives the qubit), met while calibrating `partial_swap_060`
  on 5Q4C (`procedures/pair-partial-swap`, Trap 6).
- Problem: only the procedures enforce the bound (`procedures/README.md` rules): windows
  stop at amplitude factor 1.0 because 5Q4C's `stark` operations are scaled so that 1.0 is
  2π on q1 and q3. No code knows that scale. `qc_n_stark_amp`, `qc_swap_flux_stark` (whose
  `stark_amp_2pi` is only a Parameters prior) and `qc_trotter_compensation` accept any
  window the QM driver can play (its QUA `amplitude_scale` bound is 2.0,
  `scqo-qm/scqo_qm/experiments/_amp_limits.py`), and converting an amplitude into a phase
  means reading the `qubit_stark_phase_echo` plotdata curve by hand.
- Where: `qubit_stark_phase_echo` (the measurement) and the three experiments that sweep a
  stark amplitude; where the measured curve is stored is open (placement rule).
- Done when: those experiments refuse a stark window beyond one turn by name, and a
  compensation can be reported as a phase as well as an amplitude.

### F19 `scqo-qm`: the remaining read-only queries (low)
- Added 2026-09-24 when `scqo-qm cluster` landed as the first query (the user chose to start
  with it).
- Problem: three lookups still hide behind flags of WRITE commands, where one missing flag
  turns a look into a write: the pairs' partial swaps (`register-partial-swap --list`), the
  Octave calibration file's location and cached entries (`calibrate-octave --dry-run`), and
  the exponential filter currently on each z line (no read path at all; only
  `apply-distortion --dry-run` shows it, as a preview of a write).
- Where: `scqo-qm/scqo_qm/cli.py` (dispatches from `fieldmap.OPERATOR_COMMANDS`); one module
  per query under `scqo_qm/backend/`, shaped like `backend/cluster.py`.
- Done when: `scqo-qm swaps`, `scqo-qm octave` and `scqo-qm filters` exist, read-only, and
  each write command's listing flag either goes or points at its query.

### F20 `scqo-qblox`: the same operator CLI on the Qblox side (low)
- Added 2026-09-24 with the `scqo-qm` console script.
- Problem: Qblox's operator commands are still invoked as `python -m
  scqo_qblox.backend.apply_distortion` and `python scripts/calibrate_mixers.py <config_dir>`,
  and the second is a PATH-invoked script that ends its own process with `os._exit`, so it
  cannot be dispatched as it stands.
- Where: `scqo-qblox/scqo_qblox/backend/fieldmap.py` `OPERATOR_COMMANDS`,
  `scqo-qblox/scripts/calibrate_mixers.py`; the QM shape to copy is `scqo-qm/scqo_qm/cli.py`.
- Done when: `scqo-qblox -h` lists both commands from its `OPERATOR_COMMANDS`, and
  `calibrate_mixers` lives in the package with the `os._exit` confined to its own entry.

### F21 Retire qualibrate — LANDED 2026-09-25
- Every done-when is met. Neither `qualibrate` nor `qualibration-libs` is in
  `scqo-qm/pyproject.toml` or `requirements-qm.lock.txt`; the full scqo-qm suite (716, zero
  skips) passes in a venv built from that lock, where `qualibrate`, `qualibration_libs`,
  `qiskit` and `qutip` are absent and only `qualibrate-config`, `quam` and `qm` are present;
  no doc describes a GUI path; and both fragments name **v3.13.0** as the tag the vendored
  nodes and the frozen archive live in now.
- Phase 1 (v3.13.0, fragment `qualibrate-free-driver`): vendored the two `qualibration-libs`
  pieces, made `scqo_qm.quam_io` the load+save door, took the T1-Bayesian SPAM terms off
  QUAM's confusion matrix. Made the driver RUN without the packages; deleted nothing.
- Phase 2, unreleased, fragments `qualibrate-removed` + `three-state-readout-removed`:
  scqo-qm `69e16df` (gef probe), `24edf03` (the four GUI-only knobs), `cdb6e79` (the
  deletion: 345 files, ~43k lines, all 742 qualibrate imports, the deps and the lock);
  SCQO `cea0669` (gef shell + the `fidelity_f`/`pos_f_*` monitors), `dde085a` (docs + the
  8001 port line).
- Worth keeping from the execution, since each contradicted the plan: scqat was NEVER
  involved (the gef experiment had no estimator of its own — `state_discrimination` is shared
  with two survivors); `calibration_db.json` was the Octave mixer-cal CWD artifact, not GUI
  residue, and is now gitignored; `quam_config/instrument_limits.py` had a live test importer
  besides the deleted tree, so `_power.MAX_IF_AMP_V` became the one home for the 0.5 V rail;
  and removing `amp_mode` made three pair-swap guards unreachable, which went with it (I17's
  rule). The lock was regenerated CONSTRAINED to the old pins because a plain `uv pip compile`
  moved 73 packages including the whole `qm-qua`/`quam` stack.
- **DECIDED (user, 2026-09-26): `qutip` does NOT become a dependency.** It left the lock with
  `qiskit-experiments`, its only source. Nothing in these repos imports it, so it has no claim
  on `scqo-qm/pyproject.toml`. CONSEQUENCE, so nobody rediscovers it as a bug: rebuilding
  `.venv-qm` from the new lock leaves that environment WITHOUT qutip, and it is where the
  notebooks open run data (`notebook-kernels-qutip-vs-data`) — whoever needs it there installs
  it into the venv by hand, alongside the three editables. The existing `.venv-qm` still has it.
- Follow-on: **F7** (lift the core push refusal) lost its QM-side half — that driver guard is
  already gone, so only `scqo/labconfig.py::make_session` remains.

### F22 `readout_time_of_flight` — QM VALIDATED ON HARDWARE 2026-09-26; QBLOX OWED
- Built as decision (1) of F21: the retired qualibrate nodes 01a/01b were the only path
  that measured time of flight, and the Qblox side never had one. ONE experiment for both
  backends, as the operator asked - not a QM-only stopgap.
- **QM DONE-WHEN MET, 5Q4C q1 (cd2/qm_5q), 2026-09-26.** `scqo run readout_time_of_flight
  --target q1 --set readout_amp_factor=2.8` reports **392 ns against the stored 384** - 8 ns,
  two grid steps - reproducibly across independent runs (arrival 364.7 / 365.1 ns), plateau
  SNR 22-27, a 4 ns edge, no refusal flags, and the writeback hint renders
  `q1: q.resonator.time_of_flight = 392 ns`. The stored 384 is the retired node's number on
  this wiring, so the two agree. NOTHING on the instrument was mutated: all five qubits
  unchanged afterwards and `setup_snapshot.drift` empty.
- What it does: emits a readout pulse, opens the acquisition window at a DECLARED EARLY
  ORIGIN, records the RAW digitizer trace averaged over shots. The pulse edge is the delay.
  Absolute answer = `window_start_ns + arrival`, on the 4 ns grid the vendor fields take.
- THE DESIGN POINT: the window does NOT open at the channel's current setting. If that
  setting is already right the pulse sits at sample 0, there is no pre-arrival baseline, and
  the threshold has nothing to sit between - the measurement would work only while it was not
  needed. The frame travels with the dataset, so a re-fit cannot silently use a different
  origin than the one the data was taken in.
- Proposes NOTHING - the field is VendorOnly on both backends. `_tof_hint` prints it; the
  backend names WHICH VendorOnly entry (`readout_delay_context`) and the path/unit/edit come
  from that inventory, so the neutral layer learns neither vendor's spelling.
- **THREE DEFECTS THE HARDWARE FOUND, all now fixed and regression-tested. Worth keeping,
  because none of them was reachable offline:**
  (a) The borrow never reached the instrument. `generate_config()` runs AFTER `probe()`
  returns, so writing the QUAM tree in `probe()` and restoring in a `finally` released it
  before it was ever read - the program would have opened its window at the very setting
  under test, and the QUA assembles cleanly either way. Caught by `--preview` against the
  real tree BEFORE any qubit was touched (the embedded config still read 384). Fixed by
  amending the GENERATED CONFIG instead (`patch_preview_config` + a probe-supplied acquire
  callable, the parametric-drive pattern), which also removes the risk class entirely: no
  vendor state is written, so none can be left wrong by a crash.
  (b) A raw trace needs its own readout amplitude. At the stored 0.313 the trace was flat
  noise end to end (SNR 0.37) and the fit correctly refused. Integration over an 800 ns
  readout buys ~28x SNR that a per-sample trace does not get - which is why the retired node
  hard-set -12 dBm. Hence `readout_amp_factor`, applied in the same amendment, refused by
  name past the DAC rail. 2.8 reproduces the node's amplitude on 5Q4C.
  (c) `rise_time_ns` was measured from the wrong end: it reported 339 ns for an edge whose
  true 10-90 % is 4 ns, because the 10 % level sits inside the noise band and the search
  started at the trace head. Now anchored outward from the midpoint.
  Also: the default `num_averages` is 4000 here, not the mixin's 100 - at 100 the SNR was 1.2
  and the edge finder tripped on noise; the run costs seconds either way.
- **STILL OWED: one `scqo run readout_time_of_flight` on QBLOX.** The schedule compiles, but
  the SHAPE the cluster returns for a `Trace` acquisition has never been seen here; the
  canonicalization assumes one complex array per `acq_channel` over the trace samples, which
  is what every other protocol returns over its swept axis. If that is wrong, `_to_canonical`
  is where it lands. Two more things to check there: the per-repetition `ResetClockPhase`
  actually took (a flat |IQ| with noise-like quadratures means it did not, and the fit says
  `arrival_unresolved` rather than guessing), and what `readout_amp_factor` needs to be -
  Qblox declares no `full_scale_v`, so its saturation flag reports NaN until the QRM's real
  input range with its attenuation is known.
- Open, low: the hint prints the fieldmap's generic path (`q.resonator.time_of_flight`)
  rather than `qubits.q1.resonator.time_of_flight`. The target is named on the same line, and
  the path is shared verbatim with `scqo state --fields`, so this is cosmetic - but a
  per-target path would be nicer if VENDOR_ONLY ever grows a formatter.

### F26 Sweep windows that are not yet a traversal ORDER (low)
- Found 2026-09-26 landing F25 (flux, detuning and amplitude windows are now start -> end in
  the order given; scqat `sweep_order.ascending` + an `order_free` test per estimator; SCQO
  `tests/test_sweep_order.py` checks every carrier). The rule in memory is that a NEW window
  uses start/end; these older ones still do not:
  - the parametric-drive pair (`qubit_parametric_drive_amp` / `_time`) already says
    start/end but NORMALISES ascending through `_window.window_bounds` (its docstrings say
    so); `time_axis_ns` would first have to accept a descending time window, and
    scqo-qm's `test_a_reversed_window_still_plays_ascending_and_seeds_the_low_edge` pins
    the current behaviour;
  - min/max windows on non-capability axes: `pair_swap_angle` + `pair_swap_flux_map`
    (`min/max_coupler_flux_v`, `min/max_qubit_flux_v`), `pair_swap_chevron` + `qc_n_swap_amp`
    + `qc_swap_flux_stark` (`min/max_flux_amp_v`), `qc_n_stark_amp` + `qc_swap_flux_stark`
    + `qubit_stark_phase_echo` (`min/max_stark_amp`), `qc_trotter_compensation` (`min/max_compensation_amp`), both DRAG
    experiments (`min/max_beta`), both punchouts (`min/max_power_dbm`, validator min < max);
    `pair_zz_coupler`'s `min/max_coupler_v` is I26's.
  - Their estimators are not yet under `order_free` tests; F23's new scqat
    `qubit_ramsey_flux_pulse` estimator (sorted internally) should get one too.
- Time windows (`min/max_wait_ns`, `min/max_idle_time_ns`) are deliberately out: their grids
  are built ascending on the 4 ns clock and are not a traversal choice.
- 2026-09-27: restored. Commit `062bcbe` ("F23 landed and goes") deleted this entry along with
  F23 although none of it had landed. F24's planned `coupler_flux` capability
  (`docs/coupler-readout-plan.md` §3) gives the pair maps' `coupler_flux_v` a start/end home
  to move onto.
- Done when: each window above is start/end with a zero-width refusal only, its estimator
  carries an `order_free` test, and both drivers' sweep-order tests cover it.

### F24 Coupler state readout: three tool experiments, then the crosstalk matrix (medium)
- Found 2026-09-26 (hardware 5Q4C, `--tag coupler-scan`; scripts/raw results in
  `scqat/temp/coupler_scan/`). Design of the three experiments: `docs/coupler-readout-plan.md`
  (§3 = experiment 1's spec; §6 = verification methods and the 2026-09-26 evidence; §7 =
  analogous existing experiments).
- 2026-09-27: experiment 1 `pair_coupler_crossing_pulse` LANDED, QM only (scqat estimator
  `pair_coupler_crossing`, SCQO capability `coupler_flux`). HARDWARE 5Q4C q1_q2 the same day
  (run 20260927-162801-951, `--no-update`): SUCCESSFUL, center = apex at b -0.0929 V
  (flux_offset 0.0671 V in the pulse frame), period 0.620 pulse-V, f_c_max 7.21 GHz, f_c at
  idle 6.80 GHz. q2_q3 (run 20260927-163758-216): SUCCESSFUL, apex at b -0.0949 V
  (-0.0349 V), period 0.582 pulse-V, f_c_max 7.70 GHz, f_c at idle 7.17 GHz. Still owed: the
  same-hour DC reference for the coupler line's
  pulse/DC ratio g_c (plan doc §6.2) - the 0.074 V DC reconstruction implies g_c ~0.93.
- 2026-09-27: experiment 3 `pair_coupler_spectroscopy_swap` LANDED, QM only (scqat estimator
  `pair_coupler_spectroscopy_swap`; spec plan doc §4), and ran on 5Q4C q1_q2 the same day (all
  `--no-update`): **q1_q2_c f01 = 7.058 GHz at idle 0.16 V, alpha ~ -135 MHz** (6.991 = f02/2,
  6.921 = f03/3; the whole ladder moves +88..+96 MHz for idle 0.15 V). The swap works only with
  `ramp_shape=fast_then_slow` (the readout resonators sit between the coupler and the qubits);
  the neighbour's readout also sees the coupler state directly (reference arm, ~5 us decay).
  Experiment 1's arch predicted 6.80 GHz, 0.26 GHz low. The ramp is now ONE `ramp_v = (first,
  last)` in play order (user's proposal). q2_q3 the same day: **q2_q3_c f01 = 7.156 GHz at idle
  0.06 V, alpha ~ -148 MHz** (7.082 = f02/2, 7.014 = f03/3); arch predicted 7.17 (14 MHz off);
  reference arm flat; the swap lands mostly on q2 (outer) here but on q1 (inner) for q1_q2.
  Estimator v2 LANDED the same day (plan doc §4 "estimator v2"): total excitation 1 - P00;
  lines under two sweep steps IGNORED (a measurement problem - re-measure finer; user); coupler
  lines = the ones the ramp changes (a reference-arm line no longer vetoes); f01 = the TOP of the
  multi-photon ladder, alpha from f02/2; writeback f_01_hz + anharmonicity_hz; default 501
  points. Re-analysis of the 16 runs: q2_q3 through q3's line now reads 7.1558 (v1 took f02/2).
  v2 on HARDWARE the same evening (run 20260927-203446-486, q1_q2, 1 MHz steps, tone on q2's
  line, -20 dBm): SUCCESSFUL, f01 = 7.0575 GHz +- 0.35 MHz, one coupler line only (f_01_hz
  proposal left pending on the run). OPTIONAL, not pursued (user 2026-09-27: alpha is not
  the focus): (a) alpha from the fit - through q2's line at -20 dBm f02/2 (6.991) does not show
  at 1 MHz steps (one-point spike, dropped); it needs more power through q2's line or q1's line
  (which Stark-shifts f01). STILL OWED: (b) a known blind spot - when f01 is not a line in the
  ramp arm at all, the highest remaining coupler line is taken for f01: run 20260927-183300-636
  (slow-then-fast ramp, tone through q1's line, -10 dBm) reads f03/3 = 6.921 GHz as a SUCCESSFUL
  f01. That setting is known not to work; decide whether the estimator should catch it (e.g. a
  significant ramp-minus-reference change left unexplained by the coupler lines) or the
  procedure should just forbid it.
- The three BASIC TOOL experiments (user, 2026-09-27: "one step at a time"), in the order
  1 -> 3 -> 2: (1) the coupler flux period from where a fixed x180 stops exciting BOTH
  neighbours as the coupler crosses them (`pair_coupler_crossing_pulse`; brings the
  `coupler_flux` capability); (3) the coupler frequency by an adiabatic SAWTOOTH swap into the
  neighbour (`ramp_on: coupler | probe` - a coupler may be designed below the qubit);
  (2) the coupler frequency by the qubit-coupler ZZ spoiling a selective pi - spec written
  2026-09-27 as `pair_coupler_spectroscopy_zz` (plan doc §5) and approved, the pi FIRST as the
  calibrated x180 (user: try the x gate, reshape the pulse only if there is no signal) - with
  ZZ ~0.3-0.9 MHz on 5Q4C a 16 ns x180 is expected to show NO dip; the fallback is a 2 us square
  selective pi. Tone on one member's line, pi on the other, no-pi reference arm. LANDED the same
  day (scqat 9611e82, SCQO 0415bfe, scqo-qm 1a7a96c) and run on 5Q4C q1_q2 (20260927-211451-900):
  no ZZ dip, as expected (pi_contrast 0.89 - the x180 on q1 survives the band switch). FOUND:
  the no-pi reference arm shows q1's readout seeing the coupler (0.1 bumps at f01 7.057 and
  f02/2 6.991) while the pi arm (q1 in |1>) does not - state-dependent, so pi-minus-reference
  makes FALSE dips at the coupler's lines (1-2 points here, dropped). The same day (user):
  the pi became a 2 us SQUARE selective pi with the x180's rotation area (square beats cosine
  and Gaussian because the coupler decays during the pulse, T1 ~5 us - plan doc §5 table) and
  the dips are read from the PI ARM alone, the reference arm's lines only reported. HARDWARE
  (run 20260927-213623-198, q1_q2, tone on q2, 2 us pi on q1): SUCCESSFUL, q1_q2_c f01 =
  7.05695 GHz +- 0.13 MHz, dip 0.40 deep, 6.9 MHz wide - 0.5 MHz from experiment 3's 7.0575
  the same day; f02/2 a one-point dip (no alpha); pi_contrast 0.80. ACCEPTED (user: the two
  experiments agree closely enough, either will do): q1_q2_c.f_01_hz = 7.05695 GHz. q2_q3 (run
  20260927-214341-704, tone on q2, pi on q3): SUCCESSFUL, q2_q3_c f01 = 7.15550 GHz +- 0.23 MHz
  (experiment 3: 7.1555-7.1560), dip 0.31; reference arm flat (q3's readout does not see
  q2_q3_c); its f_01_hz ACCEPTED (q2_q3_c.f_01_hz = 7.15550 GHz). Experiment 3's pending
  q1_q2 proposal (run 20260927-203446-486) was REJECTED as superseded. Experiment 3's `probe`
  field is now `tone_on` (and `ramp_on="tone_member"`), one name with experiment 2.
- DEFERRED by the user (2026-09-27, after experiment 2 landed): (1) the same-hour DC reference
  for the coupler line's g_c (above); (2) why experiment 1's arch predicted q1_q2_c 0.26 GHz low
  (q2_q3_c only 14 MHz); (3) the swap estimator's blind spot (b) above - with experiment 2 in
  hand a procedure could simply cross-check; (4) q3_q4_c and q4_q5_c - all three experiments
  ran on q1_q2 and q2_q3 only. The crosstalk-matrix fact home (the "Done when" below, with the
  catalog note and `coupler-park`) was handed to a separate session.
- Reading the coupler THROUGH A NEIGHBOUR - the raw neighbour frequency vs coupler DC, or the
  neighbour's `qubit_ramsey_flux_pulse` apex at several coupler biases - is LOW PRIORITY and for
  VERIFICATION only (user, 2026-09-27). It mixes the coupler line's crosstalk into the probe's
  own SQUID (apex LOCATION: q1 5.45 %, q3 7.16 % of the coupler move) with the coupler's Lamb
  shift (apex HEIGHT: q1 +524 kHz for -80 mV); q1_q2_c's DC apex reconstructs to ~0.074 V.
- 2026-09-28 (user): the `qubit_*` experiments take a COUPLER target through two Parameters
  mixins - `drive_line` (drive through a named line's channel, e.g. the borrowed `xy2.q1_q2_c`)
  and `mapped_readout` (`readout_member`: the zz experiment's selective pi plus the member's
  x180 copy the coupler's state onto a pair member, which is then read) - instead of
  `coupler_*` copies (CLAUDE.md estimator-binding rule 4). Spec `docs/coupler-transmon-plan.md`
  (APPROVED with every section-10 recommendation). IMPLEMENTED and offline-validated the same
  day on `feature/coupler-transmon` (scqat cea9ea8: `power_rabi` takes the FIRST extremum;
  SCQO e0e3312; scqo-qm f0adf0c: `scqo-qm adopt-channel`, `MixedTransmonQuam.borrowed_channels`,
  `QMBorrowedDriveChannel`, `MappedTarget`; scqo-qblox a7a57a2 refuses both fields by name).
  First carrier: `qubit_power_rabi`. Merged to main the same day (fragment `coupler-transmon`).
- 2026-09-28, plan section-8 steps 0-1 DONE on 5Q4C (cd2/qm_5q): `xy2.q1_q2_c` is ADOPTED - con1/6/3
  upconverter 2 at 7.1 GHz, RF 7.05695 GHz (IF -43.05 MHz), x180/x90 0.25/0.125 x 200 ns; ports 6/2
  + 6/3 are now band 2 (LO 4.9 GHz kept). Nothing else in state.json moved; wiring.json
  byte-identical. Backup: `backend_config/state.json.pre-adopt-channel.bak`.
- 2026-09-28, step 2 (hardware regression on band 2, all `--no-update`, no setup drift): q2 PASSES
  (`qubit_power_rabi` pi_amp 0.2159 vs stored 0.2142, run 20260928-185021-139); the zz re-find
  PASSES on the two-upconverter port (f01 7.0590 GHz +- 0.10 MHz, FWHM 5.07 MHz, dip 0.39,
  pi_contrast 0.83 - 2.05 MHz above 09-27's 7.05695; tone LO 7.1 GHz, no band switch; run
  20260928-185316-000 with the 09-27 window 6.85-7.35 GHz - the DEFAULT window 6.55-7.05 GHz
  misses this coupler, run -185057-298 = no_line). q1 FAILS the 3 % gate: pi_amp 0.1918 vs
  0.2141 (run 20260928-184843-486; the band-1 smoke the same day read 0.2098). Its Rabi rate per
  unit amplitude is 12 % higher on band 2 (fit f 0.5594 vs 0.5001, same contrast): the band-2
  path outputs ~1 dB more at 5.14 GHz, which q2 at 4.84 GHz does not show. The 09-27 zz runs
  already had q1 on band 2 (pi_contrast 0.80-0.89).
- 2026-09-28, q1 recalibration on band 2 (user: recalibrate rather than roll back): `pi_amp`
  0.2141 -> 0.1918 ACCEPTED (run 20260928-190940-876, reproducing -184843-486). `pi_amp_x90`
  0.1055 -> 0.09255: the first benchmarking run's data put the optimum at ~0.877 of the stored
  value but its estimator proposed 0.0528 (I30; rejected), so 0.0926 was SET by hand from that
  run's V vertex (user-approved) and a second run straddling 1.0 (20260928-191745-112, window
  0.9-1.1) read a_opt 0.9995 -> 0.09255, ACCEPTED. DRAG and the x180's frame detuning need no
  recalibration: band 2 scales both quadratures alike, so the amplitude fix restores the same
  physical pulse at the qubit.
- 2026-09-28, plan steps 3-5 DONE - the coupler's power Rabi works: the preview's QUA matches
  section 4 (q1's 301 us thermal wait, x180 on `xy2.q1_q2_c`, q1's 2 us selective pi then x180,
  q1's discriminated read; nothing on q2). Coarse scan, window 0-1.9 (run
  20260928-193455-510): a clean coherent Rabi read through q1 - baseline 0.13, peaks 0.80,
  back to baseline at 2pi, 3+ periods, and the FIRST extremum taken (decision 5(b) working);
  the fit's first peak 0.0696 (grid argmax 0.0665). Seed set to 0.0696, fine scan 0-1.4 (run
  20260928-193927-094): one arch, factor 1.008 -> `xy2.q1_q2_c.pi_amp` = 0.0702 ACCEPTED. The
  map reads the coupler as 0.13 + 0.66 x P_c.
- 2026-09-28, step 6 closure PASSES (run 20260928-194531-866, `--no-update`): fit factor 0.995
  (1/(2f), f 0.5026, phi = pi), grid argmax 1.008; baseline 0.115, peak 0.79.
- 2026-09-28, step 7 DONE: `xy2.q2_q3_c` adopted (upconverter 2 shared at 7.1 GHz, IF +55.50 MHz;
  the state diff is the one new element; backup `state.json.pre-adopt-q2_q3_c.bak`). Read
  through q3 (its port 6/4 stays on band 1, no recalibration): coarse 0-1.9 (run
  20260928-200550-400) a clean coherent Rabi - baseline 0.16, peaks 0.80, ~4 periods, first
  extremum taken; fit first peak 0.0592; fine (run -201451-692) factor 1.008 ->
  `xy2.q2_q3_c.pi_amp` = 0.0597 ACCEPTED; closure (run -201536-329) factor 0.991 (fit) / 0.980
  (grid). The plan's section 8 is complete for both couplers.
- NEXT: both adopted channels' `pi_amp_x90` are still the adoption seed 0.125 - calibrate them
  (the benchmarking experiment, after I30 or around a seed as for q1) before any x90-based
  coupler experiment; then the LATER list below, one experiment at a time with its own spec.
- LATER, one experiment at a time, each with its own spec once the power Rabi works:
  `qubit_relaxation` (the coupler's T1), `qubit_ramsey` and `qubit_echo`; `qubit_xyz_delay`
  (zc12 against xy2) and the two cryoscopes (zc12's taps) - these pulse the TARGET's flux line,
  so the QM handle then needs `z` = the coupler's flux element and an `initialize_qpu` that
  settles it; the microwave-crosstalk Rabi (`drive_line` alone, e.g. `xy2.q1`, adopted on
  upconverter 1); the zz/swap tone through the adopted channel instead of moving the LO per run;
  the swap map as a second mapped-readout method; IQ (non-discriminated) mapped readout; Qblox
  adoption.
- DECIDED, for the work AFTER the three experiments (user, 2026-09-27): the idle criterion is
  not the readout's business - J=0 (F27) and ZZ=0 (`pair_zz_coupler`, `_pulse` after I26) come
  from their own experiments with their own writebacks, and a coupler-state readout parks the
  coupler at a frequency the USER names. The crosstalk matrix becomes FACTS with no automatic
  compensation (F29), shaped as `__<source>` scalars on the target's flux channel
  (`q1_z.flux_crosstalk__q1_q2_c_z`; parallel lists would break catalog's rule that `float[]`
  never aligns to entities). Writers: F28.
- Also owed after them: the catalog note that a qubit's `flux_offset` / `f_q_max_hz` hold at the
  CURRENT coupler biases; a procedure `coupler-park` (park couplers before qubits).
- Done when: the three tool experiments exist and have measured one 5Q4C coupler's apex,
  period and f_c, and the crosstalk matrix (incl. coupler columns) has its fact home.

### F27 A J=0 writer for the coupler's `idle_flux` (medium)
- Decided 2026-09-27 with F24: the coupler idle criterion belongs to the experiments that measure
  it, each keeping its own writeback. ZZ=0 has one (`pair_zz_coupler`, `_pulse` after I26); J=0
  has NONE - the 5Q4C q1_q2_c value 0.16 V was picked by hand from a swap map on 2026-09-15.
- Candidate: `pair_swap_flux_map` (or the chevron) proposes the coupler `idle_flux` at the J
  minimum, re-referenced to absolute (its `coupler_flux_v` is a pulse riding on the idle).
- Done when: some experiment proposes a J=0 coupler `idle_flux`, and its description states
  its strengths/weaknesses next to the ZZ=0 one.

### F28 Writers for the rest of the flux-crosstalk matrix (low)
- From F24: the `flux_crosstalk__<source>` facts have NO planned writer (that name predates
  v4.0.0, which removed the `<field>__<target>` grammar - re-plan the fact's owner first). The
  F24 neighbour-apex sibling (A) would have written the cell "probe <- its own coupler", but
  the user made A verification-only, low priority (2026-09-27). Every cell needs a writer:
  neighbour cells (q1 <- q1_q2_c 5.45 % by DC), non-neighbour cells (q3 <- q1_q2_c 7.16 %, both
  measured by DC on 2026-09-26) and qubit <- qubit cells (~1 %).
  The signed m needs the target's apex LOCATION at several source biases; a parked-at-apex
  `flux_component` scan gives only |m|.
- Until then they are entered by hand.
- 2026-10-04: `qubit_ramsey_flux_crosstalk_pulse` measures the signed m for any qubit
  target and any source line (pulse frame) but proposes nothing - the writeback waits
  for the fact home (F32).
- Done when: an experiment measures a signed m for any (target, source) pair and proposes it.

### F29 Virtual-flux compensation of DC moves (deferred by decision)
- The user decided 2026-09-27 (F24): the crosstalk matrix is stored as facts and NOT used to
  compensate automatically. Compensation would mean every DC move of a line (`scqo set` /
  accept of an `idle_flux`) also moves its targets by -m*dV, and pulse-frame probes add
  compensating pulses (a neighbour pulsed by -m*b alongside the coupler stays on its own
  apex, turning the nested neighbour-apex reading from 3D into 2D).
  That touches the knob write path and both drivers - its own feature, when wanted.
- Done when: decided and built, or dropped.

### F30 An operation's full definition in scqo_state: z amplitude, duration, pulse shape (medium)
- Deferred 2026-09-29 by the user's scoping of the operation-angle feature (step 1 landed:
  the `theta_rad` MONITOR on `<pair>.<op>`, proposed by `qc_n_stark_amp`, read by
  `qc_unidirectional_trotter`'s ideal curves). What an operation still cannot say in SCQO:
  - the control qubit's z-pulse amplitude (the RESONANCE) - no `OPERATION_FIELDS` entry at all;
    today it lives only in QUAM, set by `scqo-qm register-partial-swap --z-amp`;
  - `duration_s` - Unrealized on QM because two pulses (z + coupler) carry it and a
    one-sided write would desync them (`scqo-qm/scqo_qm/backend/fieldmap.py`
    OPERATION_UNREALIZED);
  - the pulse SHAPE (square / flattop cosine / DRAG cosine): the catalog has only `float` and
    `float[]` field shapes, so no shape name fits - the same gap leaves the drive channel's
    x gate described by `pi_amp` / `pi_duration_s` / `drag_beta` without its envelope.
- Traps: a new operation knob needs a real vendor home on EVERY backend (Qblox realizes no
  operation knob today); a shape field is a catalog-machinery change, not a field addition.
- Done when: the z amplitude and duration are operation knobs with a coupled QM binding, and
  a decision on how (or whether) the catalog carries a pulse shape.

### F31 `qc_n_swap_tomography`: what v1 left out (low)
- Deferred 2026-10-01 while landing the experiment (`docs/qc-n-swap-tomography-plan.md`,
  user-approved; hardware validation is in *Hardware validation owed*). Each a separate step:
  - a DETUNING check from the phase's z-amplitude dependence: the per-step phase is linear
    in the control's z amplitude with slope t_p * df/dV (~1.1-1.2 rad/mV on 5Q4C) while
    theta' is quadratic with its maximum on resonance - three runs at z0, z0 +- 0.5 mV;
  - an operation MONITOR for the incoherent error per step (decision 3: v1 keeps it in
    `result.fit` only; a monitor is a `catalog.py` OPERATION_FIELDS edit = shared core);
  - the same tomography at CHAIN level, to measure the chain's source-sink phase per round
    directly instead of scanning it (`qc_trotter_compensation`);
  - `procedures/pair-partial-swap`: replace Step 4 (`qc_n_stark_amp`) once the hardware
    comparison passes, and record the small-angle stark-window lesson (below 0.2 rad the
    compensation peak is narrow: 0.35-0.60 x 26, not 0-1.0 x 21);
  - a Qblox probe (the qc_* family is QM-only today).
- Done when: each item is landed or explicitly dropped by the user.

### F32 Flux crosstalk: what `qubit_ramsey_flux_crosstalk_pulse` v1 left out (medium)
- 2026-10-04: v1 built, offline-validated and run on 5Q4C (*Hardware validation owed*),
  committed the same night (QM only;
  scqat estimator `qubit_ramsey_flux_crosstalk` over `tools/local_arch` +
  `tools/flux_crosstalk`; SCQO capability `flux_source`). It reads the signed
  m(target <- source line) in the PULSE frame from the target's flux-apex POSITION at each
  source amplitude, and is record-only.
- Deferred, each a separate step (user 2026-10-03/04: the Ramsey version first):
  - the SPECTROSCOPY version - the same (own, source) grid with the drive detuning as the
    inner axis, reusing `flux_source` and `tools/flux_crosstalk`: three targets per run, no
    coherence needed, a 20 us pulse instead of <= 1.6 us. Fix I20 first, or its first
    comparison cannot tell crosstalk from I20/I25;
  - the FACT HOME, then a writeback (F28): 4.0.0 removed the `__<source>` grammar; a
    candidate is a borrowed flux channel `<source line>.<target>`. Decide first whether the
    pulse-frame and the DC coefficient are one fact or two - compare this experiment with
    the 2026-09-26 DC values (q1 <- zc12 +5.45 %, q3 <- zc12 +7.16 %). 2026-10-04: they are
    NOT one number - the pulse frame reads -3.24 % and +0.95 % for those two cells (the
    first with the opposite sign), stable across the 1.6 us pulse.
    SAME-HOUR DC READING 2026-10-04 19:30-19:47 (tag `crosstalk-dc`; `zc12.idle_flux` walked
    V0, +20 mV, V0, -20 mV, V0 with the own-line `qubit_ramsey_flux_pulse` apex of each
    target read twice per stop; bias restored, setup snapshot hash identical before and
    after): DC m = q1 +5.62 %, q2 +12.79 %, q3 +7.42 % (+-0.05), the same for both signs and
    at ~20 s and ~3 min after the step, no hysteresis at the V0 stops. DC minus pulse is
    +8.9 / +8.5 / +6.5 points - a slow part of ONE sign on all three targets. The coupler
    line's own action is not frame dependent: q1's apex height moves -15.5 kHz/mV (pulse)
    against -16.2 (DC), q2's -9.9 against -10.8. So TWO numbers per cell, or one with a time
    axis (the user, 2026-10-04: the difference is real, cause unknown, m may be a function
    of the pulse time).
    LEAD-TIME SCAN the same night (`source_lead_time_ns`, added 2026-10-04: the source pulse
    starts that long before the own one and ends with it; tag `crosstalk-lead`,
    21:12-21:47, 19 runs, all SUCCESSFUL). q1 <- zc12 with the normal 301 us reset wait:
    -3.30 % at 0, -3.28 at 1 us, -3.18 at 3 us, -2.82 at 10 us, -1.93 at 30 us, +0.18 at
    100 us, +2.95 at 300 us, +4.93 at 1 ms, +5.47 at 3 ms. With 3 ms between shots it reads
    LESS (-0.84 at 100 us, +1.52 at 300 us, +3.59 at 1 ms): the slow part outlives a shot,
    so a run reads the periodic steady state and not the step. One model fits both series
    to 0.04 points: m_fast -3.28 %, then the gap to DC closes as 54 % with 171 us and 46 %
    with 1.6 ms (a description, not a unique decomposition). The single-step response it
    implies: -2.98 % at 10 us, -0.90 at 100 us, +1.40 at 300 us, +3.41 at 1 ms, +4.98 at
    3 ms, DC by 10 ms. The same two constants predict q3 <- zc12 (+3.69 at 100 us and +7.11
    at 1 ms measured, 3.73 and 7.01 predicted). A QUBIT line carries the same slow part:
    q3 <- z2 goes +1.26 -> +4.16 (100 us) -> +7.41 (1 ms), so its DC value should be near
    +7.9 % (not measured) - not the ~1 % assumed for qubit <- qubit cells (F28).
    So a cell is (m_fast, m_dc, the time constants), and the pulse-frame m holds for
    pulses up to a few us only.
    DC WALK OF z2 the same night (22:00-22:15, tag `crosstalk-dc`; V0, +20 mV, V0, -20 mV,
    V0; bias restored, setup snapshot hash identical): DC m = q1 <- z2 +8.41 % (pulse
    -0.33), q3 <- z2 +7.72 % (pulse +1.26; the lead scan had predicted +7.9). q2 ITSELF, read
    on a window re-centred on -dV: its pulse-frame apex moves 1.0859 V per DC volt, i.e. a
    DC volt of its own line moves it 8.59 % more than a pulse volt - this is I25, measured.
    THE SLOW PART DEPENDS ON THE TARGET ONLY (DC minus pulse, in points): q1 +8.86 from
    zc12 and +8.74 from z2; q2 +8.54 from zc12 and +8.59 from its own line; q3 +6.47 from
    zc12 and +6.46 from z2. A coupler's line and another qubit's line reach a given SQUID
    with the same low-frequency weight, and q2's OWN line does too. That is what a return
    path shared by all lines would do (a reading of the numbers, not a verified mechanism).
    If it holds for the other lines, a chip needs one slow weight per target plus the fast
    matrix, not two matrices.
    BUT q1's own line seems to carry about half of it: the re-park's two passes give a
    DC-to-pulse ratio of 1.03 +- 0.03 on q1 (1.08 +- 0.03 on q2, 1.02 +- 0.06 on q3), and
    2026-09-26 read 1.045 on q1 (g 0.956-0.958), against the +8.8 points q1 gets from other
    lines. So "the target's own line included" is established on q2 only.
    Open: a DC walk of z1 and of z3 (the own-line ratio of q1 and q3, and whether the
    per-target weight really does not depend on the source); zc23 as a source; the cause;
    and the DC walk itself as an experiment or procedure (tonight it was a script of
    `scqo set` + own-line runs).
    SIDE EFFECT to know before repeating a long-lead run: over the evening every apex moved
    by -0.6 to -0.9 mV (own-line reading, 19:30 -> 22:00: q1 +0.07 -> -0.83, q2 +0.09 ->
    -0.76, q3 +0.28 -> -0.40 mV from idle), most of it while the leads of 0.3-3 ms ran
    (apex(0) of q1 fell 0.4 mV in those 27 min, 3x its rate before); it was flat again
    during the z2 walk. A long lead at 80-97 % duty is a quasi-DC excursion of up to
    100 mV on the source line, so either that left a persistent offset or the usual drift
    ran faster - not separated. RE-PARKED the same night (22:35-22:47, tag `re-park`,
    `procedures/qubit-frequency-park` Steps 3-5, two fine passes per qubit): the closing
    readings sit +0.02 / -0.03 / -0.01 mV from the new biases (z1 0.271281, z2 -0.006647,
    z3 0.015876 V) and the verifying Ramseys read +4.8 / -0.8 / +0.4 kHz.
    `procedures/qubit-frequency-park` was corrected the same night: its Step 5 quoted ~1 %
    for qubit-to-qubit crosstalk (the short-pulse value; a park is a DC move, ~8 %), and it
    now carries the DC values, the DC recipe in Step 6 and the long-lead trap. Still stale:
    `qubit_ramsey_flux_pulse`'s catalog description says a pulse moves the qubit "~4 % less
    than the same DC step" - that is q1's value; q2 reads 8 %.
    REPORT: `scq-reports/reports/flux_crosstalk_time_dependence_20261004/` (HTML, written
    PDF, slides; 104 runs in the NAS raw store);
  - the apex HEIGHT's own dependence on the source (`apex_height_span_hz`): q3 moves
    -0.56 kHz per mV of z2 without any crosstalk (most likely z2 pulling q2_q3_c), which is
    what makes the `flux_component` scan of a parked target unusable for the SIGN - its
    vertex is set by that slope, not by the crosstalk;
  - a FIXED-idle-time reading (asked 2026-10-04): at one idle time the phase response to a
    small own-line step and to a small source step gives m as their ratio - 28 settings
    instead of 3500. Checked offline on the three saved cubes: at ONE operating point it is
    off by 4-6 % (q3) and 45-49 % (q1 <- zc12), because the source moves the apex height
    too; reading both sides of the apex (+-20 mV) and differencing gives m to 0.001-0.009
    points of the full run. Per shot it is only 1.3-3.3x the idle sweep; the price is phase
    wrapping (0.8-2.4 turns across the source window at 500 ns) and no fringe to judge. It
    would be a second experiment with its own estimator. The idle sweep itself has 47x
    headroom on its fringe gate (snr >= 1400 against 30 at 200 averages), so fewer
    averages are the zero-code speed-up: `num_averages=50` ran the nine other cells at about
    1 min each and reproduced q3 <- z2 (20 is untried);
  - COUPLER targets (qubit lines pull the couplers ~15 %, 2026-10-03): the probe has to be
    a coupler frequency reading;
  - sources z4, z5, zc34, zc45 (q4/q5 are not brought up, and their frequencies set the
    safe source windows);
  - several targets per run (non-neighbours only: two targets in superposition shift each
    other's fringes, and a coupler source moves that shift);
  - active reset (a hardware-gated opt-in: `scqo-qm/tests/test_reset_method.py` CARRIERS);
  - retiring `flux_component` on `qubit_ramsey_flux_pulse` and
    `qubit_spectroscopy_flux_pulse`: it sweeps the source INSTEAD of the own line, so a
    target at its apex shows only |m|, and QM refuses a coupler there.
    `resonator_spectroscopy_flux` keeps its own;
  - a Qblox probe.
- Done when: each item is landed or explicitly dropped by the user.

## Known issues / potential problems (found in passing)

### I1 Qblox broadband probes swallow a failed clock restore (medium)
- Found 2026-09-03. `scqo-qblox/scqo_qblox/experiments/broadband_resonator_spectroscopy.py`
  (the `clock_freqs.readout` restore) and `broadband_qubit_spectroscopy.py` (the
  `clock_freqs.f01` restore) wrap each restore in `try/except Exception: pass`; a failed
  restore leaves the element parked at a sub-band frequency for the rest of the session.
  Since the setup-snapshot feature this shows up as `setup_snapshot.drift`; the LO restore
  next to it raises, and the clock restore should too.

### I2 A vendored node can re-create the f_01 / RF split (medium, cannot be fixed here)
- Found 2026-09-03. `scqo-qm/calibrations/17_pi_vs_flux_long_distortions.py` L144 shifts
  `xy.RF_frequency` alone; after a GUI run the next scqo session refuses with
  "drive frequencies ..." and the operator re-aligns `f_01` by hand. Vendored file — never
  edit; document in the operator notes if it bites.

### I3 scqo-qblox CLAUDE.md mixer-AMC premise no longer literal (low)
- Found 2026-09-03. The paragraph says the AMC survives a run only because hw_config has no
  `hardware_options.mixer_corrections`; the live chipA `hw_config.json` DOES carry that block
  (`auto_lo_cal` / `auto_sideband_cal` modes, no `mixer_corr_*` values). Verify the failure
  mode and reword.

### I4 Qblox LO numbers disagree between docs, fixtures and the live config (low)
- Found 2026-09-03. `tests/fixtures/hw_config_min.json` + `hw_config_2q.json` and
  `tests/test_qblox_power.py` use 5.8e9 / 4.5e9; the live chipA `hw_config.json` runs
  5.1e9 / 3.0e9; `D:\qpu_data_dev\chipA\cd1\qblox\backend_config\EDIT_ME.md` still says
  5.8 GHz. Only `power_context` / the setup snapshot record which one ran. Refresh EDIT_ME.md.

### I5 `quam_state/state.json` has case-colliding keys (low)
- Found 2026-09-03: `CZ_time` and `Cz_time`. Python is fine; PowerShell `ConvertFrom-Json`
  refuses the file, and any case-insensitive consumer of a setup snapshot would break.

### I6 `QUAM_STATE_PATH` is set process-wide and never unset (low)
- Found 2026-09-03. `QMBackend.load` exports it, and a second session or script in the same
  process inherits the folder. Half of this landed in v3.13.0: the backend's own save no
  longer depends on the variable (`QMBackend.load` passes the folder down as `state_dir`), so
  what is left is the export itself and everything else that still reads it - see I22.

### I7 `state_lib/10Q` resonator `f_01` vs `resonator.RF_frequency` disagree (low)
- Found 2026-09-03: 1.0–1.4 MHz apart on q3/q4/q5. scqo reads the RF only, so it is not a
  silent failure today; decide whether the readout pair needs an audit like the drive pair.

### I8 `tests/test_index_scale.py` hardcodes `schema_version` 9 (low)
- Found 2026-09-03. A value in the INSERT tuple, not the constant — harmless until a schema
  bump changes what the column means.

### I9 A resolved-but-NaN aggregate still explains nothing (low)
- Found 2026-09-04 while making the campaign accept step visible.
- `suggestion_notes` covers the `min_n` shortfall only. A target whose statistic
  RESOLVED (`n >= min_n`) but is NaN/Inf is dropped by the finiteness gate in
  `scqo/session.py::_campaign_suggestions` and still says nothing — deliberately, since
  it is a different cause with a different remedy (the fits are bad, not too few), and
  folding it into the min_n wording would be a lie. Pinned as silent by
  `tests/test_campaign.py::test_generation_filters_nonfinite_and_nonscalar`.
- Done when: a NaN-only target gets its own note naming the fit failure, not the floor.

### I10 Nothing machine-checks the per-repo test commands (low)
- Found 2026-09-04 writing `ENVIRONMENTS.md`.
- Each sibling's `ENVIRONMENTS.md` stub repeats its own test command verbatim (so a reader who
  does not click the URL cannot reach the wrong one), and `scripts/check_contribution.py`'s
  `TEST_COMMANDS` holds a fourth copy. Four strings that must agree, with nothing enforcing it —
  the same drift that produced the four arrangements in the first place, one level up.
- Done when: a test in `SCQO/tests/` asserts `ENVIRONMENTS.md` exists and that every command in
  its per-repo table appears verbatim in `TEST_COMMANDS`. `tests/test_docs_current.py` is the
  precedent for "a doc block that must not rot".

### I11 `scqo-qm/.venv` exists and is unusable (low)
- Found 2026-09-04. It holds no `qm`, no `quam`, no `qualibrate`, no `scqat`, `scqo` frozen at
  2.3.0 — residue of a stray `uv run`, which resolves from `pyproject.toml` instead of
  `requirements-qm.lock.txt`. The docs now say it is not a thing and `check_contribution.py`
  warns when it is present, but the directory itself is still sitting there for the next person
  to point an interpreter at.
- Done when: deleted on the lab machine (nothing references it), or `scqo-qm` grows a
  `[tool.uv]` guard that makes a stray `uv run` fail loudly instead of building it.

### I12 Stale names and version lines (hygiene)
- `scqo/cli/__main__.py::_usage()` still names LCHQBDriver / LCHQMDriver.
- `scqo-qm/scqo_qm/backend/qm_backend.py` module docstring: "shared with the qualibrate
  writebacks" (retired).
- `scqo-qm/quam_state/` holds six `*.bak*` files; QUAM merges any `*.json` under its state
  directory, so a backup must never be named `*.json`.

### I13 `RB fidelity #100` exists only through the campaign bypass (low)
- Found 2026-09-05 while planning F9.
- `qubit_sqrb` has no `update()` (only `define_sweep` / `simulate` / `estimate` / `probe`), so
  it never proposes anything, and `scqo/catalog.py` has no `rb_fidelity` field on any kind.
  `metrics.py`'s `rb_fidelity_single` is therefore ALWAYS None, and the row's only source is
  the direct campaign-statistics read - which F9 removes, blanking the row permanently.
- Same shape, second instance in the same function: `state.get((ro, "readout_fidelity"))` is
  dead too - the catalog gives the readout channel `fidelity_g` / `fidelity_e` / `fidelity_f`
  and no `readout_fidelity`. The live path is the `(fidelity_g + fidelity_e) / 2` branch
  above it.
- Where: `scqo/experiments/qubit_sqrb.py`; the transmon mode fields in `scqo/catalog.py`;
  the `ro_single` and `rb_single` fallbacks in `scqo/viewer/lab_report/metrics.py`.
- Done when: `rb_fidelity` has a catalogued home and `qubit_sqrb` an `update()` that writes
  it, or the row and both dead `_first` branches leave the report together.

### I14 The `--note` backslash value is never asserted to survive (low)
- Found 2026-09-07 while fixing the `\q` SyntaxWarning on the same line.
- `test_start_escapes_metadata_and_validates_cycle_id` promises in its docstring that quotes
  AND backslashes in `--fridge` / `--packaging` / `--note` "must never corrupt the shared
  registry", but the only survival assertion is `'PCB "rev3"' in show.stdout` - the QUOTE
  case. The backslash note (`r"D:\qpu\chipA path"`) is covered only indirectly, by exit
  code 0 and "the registry re-parses cleanly", so a TOML writer that silently ate, doubled
  or normalised a backslash would still pass this test green.
- Where: `tests/test_cli_cooldown.py::test_start_escapes_metadata_and_validates_cycle_id`,
  the `show.stdout` asserts at the end.
- Done when: the note's exact value is asserted to round-trip (`assert r"D:\qpu\chipA path"
  in show.stdout`), or it is read back out of `cooldowns.toml` and compared.

### I15 Stale cp950 comment in `test_cli_doctor.py` (low)
- Found 2026-09-07 while pinning the subprocess encodings for the 7 cp950 test failures.
- The comment above the `UV_PYTHON_INSTALL_DIR` assert says the `§` "can mangle when
  subprocess stdout round-trips through the OS locale encoding on Windows". Both ends of
  that pipe are now pinned to UTF-8 (`encoding="utf-8"` on the `subprocess.run` plus
  `PYTHONIOENCODING` in the env), so the premise is false and the ASCII-safe-token
  workaround it justifies is no longer needed - the assert could name the `§1` pointer.
- Where: `tests/test_cli_doctor.py:296`, end of `test_doctor_renders_the_profile_witness_rows`.
- Done when: the comment is dropped or rewritten and the assert reflects what is actually
  guaranteed now that both ends of the pipe are pinned.

### I16 scqo-agent: four problems to close before Phase C (medium)
- Found 2026-09-21 while surveying `D:\github\scqo-agent` for an autonomous single-qubit
  bring-up design. Read from the code, not exercised on an instrument.
- (1) Nothing gates `run_experiment` on a human. `server.py::create_agent` sets
  `interrupt_on = {}` (the approval block is commented out) and the CLI's `-n` mode sets
  `auto_approve=True`, while `tools/lab_tool.py::run_experiment`'s docstring says "Requires
  approval before running" and `02_Calibration_Workflow.md` asks for confirmation before each
  hardware step. Under `launch/run-qblox.ps1` / `run-qm.ps1` that prose is the only brake.
  Writebacks stay suggest-only, so the device state is safe; the instrument is not gated.
- (2) Stop and Delete undo the QM `detach` policy. `server.py::stop_workflow` and
  `delete_workflow` call `procutil.terminate_tree(pid)` on the whole QCA process tree,
  experiment children included — the kill that `core/runner.py` says orphans the
  instrument-side job and wedges the gateway for every later run.
- (3) Nothing refuses a second experiment while a detached QM child is still running; the
  rule exists only in `system-prompt.md`.
- (4) The chain the LLM is taught is out of order. `data/knowledge/documents/
  02_Calibration_Workflow.md` puts `readout_power` (step 2, described as "best power below
  punch-out") and `readout_frequency` (step 3) BEFORE qubit spectroscopy — but both sweep
  `prepared_state` 0/1, so they need a calibrated pi pulse and belong after power Rabi. The
  punchout it describes is `resonator_spectroscopy_power_amp`, which the chain omits.
- Done when: hardware deployments gate `run_experiment` on a human (or the Phase C notes say
  plainly that they do not); Stop/Delete under `detach` leave an in-flight experiment child
  running or refuse while one runs; a second start is refused while a detached child lives;
  the taught chain runs punchout before, and readout optimization after, the pi pulse.

### I17 A value pinned at its swept-window bound still reports SUCCESSFUL (medium)
- Found 2026-09-21 while checking whether `Outcome` could gate an unattended bring-up step.
  Read from the code, not reproduced on data. `update()` writes for every SUCCESSFUL target,
  so each case below proposes a writeback from a value the window cut off.
- `qubit_relaxation` / `qubit_echo`: `scqat/tools/fit_exp_decay.py` bounds tau at 4x the
  swept span, so the estimators' `0 < t1 < 10 * t_span` guard can never fire. A T1 longer
  than the window comes back pinned and still proposes `t1_s` AND the
  `thermalization_time_s` knob (the reset wait) from it.
- `qubit_spectroscopy`: `scqat/tools/peak_fit.py::fit_peaks` bounds x0 inside the local fit
  window and, when the fit raises, falls back to the initial guess with NaN errors and still
  returns the peak; SCQO's `low <= det <= high` check therefore cannot fail.
- `resonator_spectroscopy` (lorentzian): x0 is bounded to the sweep and `in_span` in
  `scqat/tools/dip_fit.py` is inclusive, so a centre sitting on the bound passes.
- `readout_frequency` / `readout_power`: the best point is `nanargmax` over the sweep
  (`readout_fidelity/estimator.py::_select_best_index`) and an endpoint is accepted.
- 2026-10-04, three more found while documenting them (their documents' Traps say so):
  `qubit_drag_alternating` - scqat returns `success: True` unconditionally;
  `qubit_drag_equator` - the estimator computes whether the crossing is inside the swept
  window and then discards it, so an extrapolated crossing is SUCCESSFUL;
  `qubit_pi_pulse_error` - the inline fit clips its vertex to the window with `np.clip`
  and is SUCCESSFUL unless it raises. (`qubit_deterministic_benchmarking` is I30.)
- Related: the uncertainties that would expose this (`detuning_err`, `fwhm_err`,
  `chi_square`, peak stderrs, Ramsey `var_explained`) are computed but reach only
  `analysis/<target>/*_metadata.json` — not `Result.fit`, and not at all under
  `skip_artifacts`. Only T1 and T2echo carry a stderr in `Result.fit`.
- Done when: each of these fails (or flags) a value at or within a step of its bound, the
  T1/echo guard is consistent with the tau bound, and a test per estimator pins a
  window-too-short / feature-off-window case.

### I18 chipA's dev-box data: a datasheet that is not this chip, and a second qubit named q1 (low)
- Found 2026-09-21 while choosing which measured facts could seed a simulated chip. Data on
  this dev box's scratch `data_root` (`D:\qpu_data_dev`), not repo content.
- `chipA/design.toml` (header: "Carried over from the pre-cutover roster") says
  `q1_res.f_dress0_hz = 5.94e9`, `q1.f_01_hz = 4.73e9`. Both chipA setups that measured q1
  agree with each other and not with it: `cd1/qblox` and `cd1/qm_OPX1000` physical.json give
  5.0118 GHz and 2.9413 GHz. A resonator 16 % (and a qubit 38 %) off its layout is far
  outside a normal fabrication spread, so the datasheet most likely describes another chip or
  was a placeholder — confirm with whoever wrote it. Until then every design-seeded anchor and
  the `scqo state --design` column compare against it, and its `g_hz` / `kappa_tot_hz` /
  `anharmonicity_hz` are suspect for the same reason.
- `cd1/qblox_q2` stores a DIFFERENT physical qubit as `q1` (f01 3.2774 GHz, resonator
  5.1130 GHz), while `components.toml` states q1 is the same qubit in every vendor config.
  Cross-context views (the device page's facts matrix, /trends port 2, the whole-cooldown
  lab-report context) therefore mix two qubits under one name.
- Done when: `design.toml` carries chipA's real layout values (or its q1 block is removed
  until known), and the second qubit is either a `q2` mode in `components.toml` measured
  under that name, or its setup moves to its own device.

### I19 Backend-parity gaps in the basic single-qubit bring-up (medium)
- Found 2026-09-21 while specifying the emulated backend (`docs/emulated-backend-plan.md`),
  which has to pick ONE realization per experiment. Read from the code, not exercised; each
  item cites both drivers' `experiments/<name>.py` unless noted.
- `qubit_ramsey` realizes different sequences: QM plays `y90` - idle - `x90` with the phase
  as a frame rotation, amplitude `pi_amp_x90` and a vendor-only x90 length; Qblox plays
  `X90` - idle - `Rxy(90, phi)` at `pi_amp/2` and `pi_duration_s` (`pi_amp_x90` is Unrealized
  there). `qubit_echo`'s x90s split the same way. The fitted frequency survives (free fit
  phase); the pulse area and the knob the loop must calibrate do not.
- The stored time coordinate differs: QM keeps the realized grid times (4 ns cycles, 8 ns for
  the echo's two arms; `qm_backend.py` `_to_canonical` only renames), Qblox the requested
  axis. Same Parameters, different `dataset.nc` coords for ramsey / relaxation / echo.
- Amplitude guard: Qblox refuses `factor x pi_amp > 1` (`experiments/_amp_limits.py`), QM
  only `|factor| >= 2` (QUA's `amplitude_scale` range). CLAUDE.md's `amplitude.py` paragraph
  says both refuse the former.
- `_capabilities/qubit_reset.py`'s BOUNDARY RULE ("drivers resolve the wait through
  `reset_wait_ns`") is followed by neither driver — no driver module calls it. Each wraps
  its own override around the vendor reset, and QM's thermal reset silently falls back to
  5 x T1 when `thermalization_time` is unset instead of raising.
- `resonator_spectroscopy.readout_amplitude` (and `broadband_resonator_spectroscopy`'s power
  overrides) are Parameters no driver reads — the "a backend ignores it" shape CLAUDE.md's
  parity section calls a counter-example.
- `resonator_spectroscopy` shot spacing: QM waits `readout_depletion_s`, Qblox a hard-coded
  10 us `IdlePulse`.
- Docs: `scqo_qm/experiments/qubit_echo.py`'s docstring says the final +x90 refocuses to |1>,
  but Rx(pi/2) Rx(pi) Rx(pi/2) = Rx(2 pi) refocuses to |0> (the estimator's a exp(-t/tau) + c
  fits either); `scqo-qblox/CLAUDE.md` still says `qubit_spectroscopy` refuses active reset,
  which the code allows. QM has no driver test pinning the Ramsey detuning sign (Qblox does,
  `tests/test_ramsey_detuning.py`).
- No basic bring-up step calibrates `pi_amp_x90`: only `qubit_deterministic_benchmarking`
  with an x90 `target_gate`, and only on QM.
- 2026-10-04, decided (user) while adding `Experiment.sequence_diagram`
  (`docs/experiment-docs-plan.md` §11): the declared `qubit_ramsey` sequence is `y90` - idle -
  `x90`, perpendicular axes - QM's realization, and the sine `scqat.tools.ramsey_fit` seeds.
  Qblox is the side to change (needs a hardware run); until then
  `QbloxQubitRamsey.backend_notes` states the deviation. The knob split (`pi_amp_x90` on QM,
  half of `pi_amp` on Qblox) is now DECLARED per driver in `requires`, which records it and
  resolves nothing. `qubit_echo` is not decided.
- 2026-10-04, second batch of documents (same plan, section 14) - three more of the same
  kind, each now stated in that driver's `backend_notes`:
  `qubit_relaxation_flux_pulse.prepare_state` is read by `simulate()` only - the one probe
  (QM) always plays the `x180`; `qubit_spectroscopy_flux_pulse` has no length parameter and
  the two probes realize different drives (QM a pulse of the stored saturation operation's
  length, I20; Qblox a continuous tone held for the reset wait); and the pi/2 knob split of
  `qubit_ramsey` holds for `qubit_ramsey_phasor`, `qubit_ramsey_flux_pulse`, `qubit_echo`
  and `qubit_echo_flux_pulse` too, declared per driver in `requires`.
- 2026-10-04, third batch of documents (same plan, section 15), each stated in the driver's
  `backend_notes`:
  - `qubit_drag_equator.pulse_repetitions` is read by no probe and by no `simulate()`: both
    backends play ONE pi pulse per sequence. (Its registry description still spoke of three
    sequences with `(Y180)^N`; corrected to the two sequences the probes play.)
  - The swept DRAG coefficient is realized three ways. QM `qubit_drag_alternating` scales
    the stored pulse's DRAG quadrature by `beta / stored`, with `stored` taken from the
    FIRST target for all of them, and is blind when the stored coefficient is 0. QM
    `qubit_drag_equator` bakes a reference coefficient into the benchmarked gate's family
    only, so the other family's pulses in the same sequence do not carry the swept beta.
    Qblox `qubit_drag_equator` writes `drag_beta` on the device per point; with
    `target_gate=x90` it still sweeps that one coefficient and proposes `drag_beta_x90`,
    which is Unrealized there (`qubit_deterministic_benchmarking` refuses the pi/2 gates on
    Qblox for the same reason; the equator does not).
  - `qubit_tomography`: the Qblox probe does not read the `amp` / `detuning` entries of
    `qubit_configs`.
  - `qubit_sqrb`: the identity Clifford is an idle one pi pulse long on QM and nothing at
    all on Qblox, so a Clifford averages 1.875 pulses on one and 44/24 on the other, while
    scqat divides by 1.875 for both.
- 2026-10-04, fourth batch of documents (same plan, section 17), each stated in the driver's
  `backend_notes`:
  - `qubit_ramsey_cryoscope`: the margins around the flux pulse differ. QM starts it 16 ns
    after the first x90 and plays the second x90 `max_duration_ns + 16` ns after the first,
    so the longest pulse ends exactly as the second x90 begins; Qblox starts it at the end
    of the first x90 and leaves `max_duration_ns + 8` ns. The time the falling edge has to
    settle before the second x90 therefore differs by 8 ns at every duration. The pi/2 knob
    split of `qubit_ramsey` holds here too (declared per driver in `requires`).
  - `qubit_spectroscopy_cryoscope`: the guard on the spectroscopy pulse's amplitude is not
    the same question on the two sides - QM refuses a pulse louder than the loudest
    operation stored on that drive line, Qblox one above the DAC's full scale - and the
    x180's area is read from the stored envelope on QM and computed from the DRAG gaussian
    on Qblox. (Qblox refusing the smooth `drive_shape`s by name is the allowed kind.)
- 2026-10-04, fifth batch of documents (same plan, section 18), each stated in the driver's
  `backend_notes`:
  - The two parity monitors: the pi/2 knob split of `qubit_ramsey` holds here too
    (declared per driver in `requires`). `qubit_parity_switch_discrete` pads its cycle on
    a 4 ns grid with a 16 ns floor on QM and on a 1 ns grid on Qblox, so one
    `cycle_period_ns` gives periods up to 16 ns apart; each probe reports the period it
    played, so the rate is right on both.
  - `qubit_resonator_stark` plays the same sequence on both (pinned by each driver's
    timing test); what differs is the amplitude bound (QM: `amp_prefactor` below 2, QUA's
    amplitude scale; Qblox: the absolute amplitude within the output's full scale).
- Done when: each item is either aligned (one realization, the other driver changed) or
  declared as an optional capability refused by name, and CLAUDE.md states what the code does.

### I20 QM `qubit_spectroscopy_flux_pulse` plays its drive and z pulses 4x too long (medium)
- Found 2026-09-21 while writing the `qubit_resonator_stark` QM probe. Read from the code,
  not reproduced on the instrument.
- `scqo-qm/scqo_qm/experiments/qubit_spectroscopy_flux_pulse.py:109-111` computes
  `length * u.ns` BEFORE `with program()`. qualang_tools' `u.ns` is 0.25 only while a
  `Program` is in scope and 1.0 outside it (`qualang_tools/units/units.py`), so the value
  stays in ns and is then passed as `duration=`, which QUA reads as 4 ns clock cycles. The
  scqo probe passes `operation_len=None`, so every run plays the saturation AND the z pulse at
  4x the saturation op's length. Silent: a longer saturation still fits.
- Done when: the builder converts with an explicit `// 4` (the `_cycles` helper of
  `qubit_spectroscopy.py` / `qubit_resonator_stark.py`) and a generated-QUA test pins the
  played duration against the op length.

**5Q4C q1_q2 `decouple_offset` = 0.08 V does not decouple (found 2026-09-15, hardware).**
Every probe parks the coupler there (`initialize_qpu` -> `apply_all_couplers_to_min()` ->
`to_decouple_idle()`), and coupler pulses ride ON TOP of it — so the park is the standing
condition for every run that plays no coupler pulse. Measured residual at that park:
t_pi ~ 145-152 ns, i.e. J/2pi ~ 1.7 MHz, a FULL swap whenever the members are brought into
resonance. The real J minimum is at a LINE voltage of ~0.148-0.165 V.
- Evidence: flux map `20260915-162437-647` (40 ns fixed) column maxima — line 0.080 V ->
  0.21 transfer, line 0.1475-0.160 V -> 0.01-0.02, line 0.190 V -> 0.45; and the chevron A/B
  `20260915-183235-061` (`coupler_flux_v=0.08`, line 0.16 V -> transfer 0.17, failed) vs
  `20260915-183332-183` (`coupler_flux_v=0.0`, line 0.08 V -> transfer 0.95, t_pi 152 ns).
- Worked around, NOT fixed: the `partial_swap` macro's coupler pulse was re-baked at 0.08 V
  so the GATE lands on the J zero (line 0.16 V). The park itself is untouched, so idle /
  readout / single-qubit runs still sit on the residual coupling. `interaction_offset` is
  also still 0.0 (unset).
- Side effect of that workaround: `partial_swap` now sits AT the J zero, so as a gate its
  angle is ~0. A real partial swap needs its coupler amplitude picked off a chevron theta
  curve instead.
- Done when: `decouple_offset` is re-measured (a `pair_swap_chevron` coupler scan, or
  `pair_zz_coupler`) and re-parked at the true zero, the `partial_swap` coupler bake is
  re-derived against the NEW park, and TUTORIAL section 12 step 0's premise ("the swap only
  happens while the coupler pulse plays") actually holds on this chip.

### I21 A pair map with a collapsed member readout passes as a result (medium)
- Found 2026-09-22 on 5Q4C (`20260922-181347-904`, `qc_swap_flux_stark` q1_q2). After the IQ
  phase drifted during the day, q1's stored threshold sat outside both blobs: q1's joint
  states "10"/"11" were exactly 0.000 across all 961 pixels, and q2's too-close threshold
  inflated "01" to ~0.4 far from resonance. The run reported SUCCESSFUL; only
  `resonance_unresolved` was set.
- Where: the pair estimators in scqat (`_pair_swap_maps` and the `qc_*` / `pair_swap_*`
  families), or one shared check in the pair readout reduction.
- Done when: a member whose marginal is identically 0 (or 1) over the whole map raises a
  named flag (e.g. `readout_suspect`) in `result.fit` and the figure title.

### I23 `uv.lock`'s editable version strings drift, unchecked (hygiene)
- Found 2026-09-26 while cutting v3.14.0, from a working tree that would not come clean:
  `uv run` had regenerated `scqo-qblox/uv.lock` with the new versions after the pyproject bump.
- Each repo's tracked `uv.lock` records a `version` for the editable path packages (`scqo`,
  `scqat`, and the repo itself). It is refreshed only when something runs `uv` in that repo,
  so it goes stale silently at every release, and the three disagree: at the v3.14.0 cut
  `scqo-qblox/uv.lock` said scqo 3.14.0 (regenerated during the release test run and
  committed), `SCQO/uv.lock` said 3.13.0, and `scqo-qm/uv.lock` said **3.0.0** — eleven minors
  behind, because `uv run` is FORBIDDEN in that repo (ENVIRONMENTS.md), so nothing ever
  regenerates it.
- Harmless today: they are derived data, and the one env built from a lockfile
  (`.venv-qm`) is built from `requirements-qm.lock.txt`, not from `uv.lock`. The cost is
  that a reader cannot tell a stale entry from a real pin, and a release diff picks one up
  at random depending on which suite happened to run through `uv`.
- `scq-reports/uv.lock` is a fourth one, outside the combo and so outside every release
  checklist: after each release `uv lock --check` fails there and the next `uv run` rewrites
  the tracked file. Refreshed by hand after v4.2.0 (2026-10-05, `uv lock` + commit; only the
  two version strings moved); it goes stale again at the next release.
- Done when: either the release checklist regenerates all three (and RELEASING.md step 2
  says so), or the repos that cannot regenerate theirs stop tracking it — `scqo-qm` is the
  clear case, since `uv run` is forbidden there and its lock has been wrong since v3.0.0.

### I24 scqat `ramsey` misreports frequency and T2* at a large virtual detuning (medium)
- Found 2026-09-26 parking 5Q4C by hand (plan doc §3). At 4 MHz detuning / 4 us / 201 points
  the fit's frequency was off by >1 MHz and T2* read 0.95 us / 62 us while the raw trace was
  clean (contrast 0.90; a periodogram reproduced the fringe to 3 kHz). The run still reported
  its fit, so any consumer that skips `outcomes` takes the wrong number.
- Where: `scqat/tools/ramsey_fit.py` seeding (`_fit_single` takes FitDampedOscillation's own
  guess unless `f_seed` is passed).
- Done when: seeding comes from a periodogram peak (`tools.fringe_frequency`) and the fit
  is rejected when it leaves that peak by more than half a bin.

### I25 A z PULSE moves the qubit ~10 % less than the same DC step (medium)
- Found 2026-09-26 on 5Q4C. `qubit_spectroscopy_flux_pulse` run from a park 6-10 mV off the
  apex (`20260926-145528-751`) put the apex 0.64-0.80 mV further out than DC Ramsey scans did
  (q1/q2/q3, same sign, ~10 sigma); re-run FROM the DC apex (`20260926-182548-238`) it lands
  within 0.05 mV. So zero offset at zero excursion, an error proportional to the excursion:
  the pulse-frame excursion reads 1.08-1.15x the DC one.
- Why it matters: every pulse-frame flux amplitude (swap resonance points, chevrons, flux
  maps) is on that scale. Candidates: a real pulse/DC gain on the line (predistortion DC gain,
  bias-tee), or an arch-fit bias from an asymmetric window. I20 (4x-long pulses) plays in the
  same probe.
- 2026-09-26 later: the pulse-frame RAMSEY prototype on q1 measured g = 0.958 / 0.960 (two
  methods) with zero offset against a same-hour DC reference - i.e. ~4 %, not 8-15 %. So the
  spectroscopy arch's larger number is probe-specific (I20 plays there), not the line alone.
- Done when: the spectroscopy arch's ratio is re-measured from a deliberate DC offset once
  I20 is fixed, and the difference from the Ramsey probe's g is explained or gone.

### I26 `pair_zz_coupler` writes a pulse amplitude back as an absolute `idle_flux` (medium)
- Found 2026-09-26 reading it for the coupler-readout design. The QM probe plays the coupler as
  a PULSE on top of `decouple_offset` (`check_flux_pulse_relative`, `amplitude_scale =
  amp / const.amplitude`), but SCQO's `update()` writes the fitted zero crossing straight into
  `<coupler>_z.idle_flux` (since 4.0.0 the coupler's flux LINE, `zc12.idle_flux` on 5Q4C q1_q2),
  and the axis text says "coupler standing bias". The write is off by
  the standing `decouple_offset` (0.16 V on 5Q4C q1_q2_c today). No Qblox probe; no run in this
  machine's index.
- Done when: the experiment takes one frame and says so in its name — either a DC probe
  (`set_dc_offset`, absolute, no suffix) or `_pulse` + re-referencing
  `idle_flux = old_idle + fitted` — with a test pinning the frame.

### I27 `fit_peaks`: a broad line's fit is captured by a stronger narrow neighbour (medium)
- Found 2026-09-27 building the coupler spectroscopy estimators; left open by the fix of three
  other `fit_peaks` defects the same day (fragment `peak-fit-merge-polarity-dip`).
- Problem: each detected line is fitted in a window of `fit_window_factor` (default 5)
  estimated widths, SEEDED ON THE WINDOW'S HIGHEST POINT, with x0 bounded only by the window. A
  broad line whose window holds a stronger narrow line fits that line instead, and the broad
  one is lost (the merge only sorts out the duplicate). Synthetic: a 0.15 x 30 MHz line 74 MHz
  from a 0.30 x 3 MHz one, 1 MHz steps, noise 0.01 - both found in 23 of 40 seeds at the
  default window, 40 of 40 at `fit_window_factor=2`. `coupler_ladder.find_lines` works around
  it with `fit_window_factor=2`.
- The obvious fix is NOT free: seeding on the feature `find_peaks` detected gets 40 of 40, but
  loses every line `find_peaks` only catches by a noise bump on its flank - a line at the sweep
  EDGE, whose maximum `find_peaks` cannot detect (5Q4C `qubit_spectroscopy_cryoscope`
  `20260907-232342`: 19 rows with a line fall to 2 with the other fixes in place, 6 without).
  The window's-highest-point seed rescues those.
- Where: `scqat/tools/peak_fit.py::fit_peaks` (the seed block before `fitter.fit()`).
- Done when: both cases pass together - e.g. seed on the detected feature unless it sits within
  a width of the window edge, or narrow the window to the neighbouring detections - pinned by a
  synthetic test of each, and the saved 5Q4C cryoscope runs keep their line counts.

### I28 A chain-power write moves an MW-FEM port shared by other channels, unrecorded (medium)
- Found 2026-09-28 designing F30. On MW-FEM, `readout_power_dbm` / `drive_power_dbm` pick the
  smallest `full_scale_power_dbm` keeping the amplitude <= 0.5 and write it on the PORT
  (`scqo-qm/scqo_qm/backend/qm_backend.py::_write_chain_power`). Every other channel on that
  port keeps its amplitude, so its absolute power moves by the full-scale step, and
  `RecordingDevice._sync_coupled` re-reads only the written entity: no history row, the stored
  `*_power_dbm` of the others goes stale.
- 5Q4C today: the five readouts share port con1/6/1 at full scale -11 dBm, so any
  `readout_power_dbm` above -17 dBm triggers it. v4.0.0's borrowed routes put a coupler route
  on q2's port too.
- v4.0.0 widened `_sync_coupled` to every owner on the same LINE, so the move is at least
  recorded when the owners share a roster line (two lines on one port still are not).
  Left open: the driver policy - hold a shared port's full scale and solve the amplitude only,
  refusing by name when the amplitude cannot absorb the change (the Octave branch already holds).
- coupler-transmon (2026-09-28): an ADOPTED borrowed channel (`xy2.q1_q2_c`) plays on q2's port
  at that port's full scale. Its own `drive_power_dbm` is refused by name for this reason, but a
  q2 `drive_power_dbm` write still moves the coupler route's absolute power.
- Done when: a power write on a shared port either keeps the other channels' absolute power or
  refuses, pinned by a two-channels-on-one-port test.

### I30 `qubit_deterministic_benchmarking` proposes a clipped fallback as a SUCCESSFUL amplitude (high)
- Found 2026-09-28 recalibrating 5Q4C q1's x90 on band 2 (run
  20260928-191126-666, `target_gate=x90`, window 0.8-1.0 x 21): the data are a clean V -
  |omega| 0.137 at 0.80, ~0.02 at 0.87-0.89, 0.22 at 1.00, both arms slope +-1.78 =
  (pi/2)/a_opt - so the optimum is ~0.877. The estimator returned `opt_factor` 0.5 and SCQO
  proposed `pi_amp_x90` 0.0528 (half the stored value) as SUCCESSFUL. REJECTED on the run.
- Cause: scqat `estimators/qubit_deterministic_benchmarking/estimator.py` signs each fitted
  omega by `a >= 1.0`, i.e. assumes the optimum sits at the stored amplitude; a window whose
  optimum is elsewhere gets one sign almost everywhere, the linear fit goes flat, and
  `np.clip(a_opt, 0.5, 1.5)` hides the result. SCQO's `estimate()` then marks every target
  SUCCESSFUL - there is no outcome gate at all.
- Workaround until fixed: put the stored amplitude near the optimum first, then benchmark a
  window straddling 1.0.
- Done when: the sign comes from the data (the |omega| minimum, or a V fit |k (a - a0)|), an
  optimum outside the swept window is a FAILED outcome with no suggestion (never clipped), and
  a synthetic test with an off-centre optimum pins both.

### I31 An MW-FEM band change shifts the port's latency ~19 ns; `adopt-channel` keeps the old `delay` (high)
- Found 2026-09-28 starting the q1_q2 partial swaps for `qc_unidirectional_trotter` on 5Q4C.
  `scqo-qm adopt-channel` (for `xy2.q1_q2_c` / `xy2.q2_q3_c`) moved the port pair con1/6/2
  (q1 xy) + con1/6/3 (q2 xy) from band 1 to band 2 and left both at `delay: 20` ns. On this
  setup the band-2 readout port con1/6/1 has delay 0 and the band-1 xy ports 20, so the 20 ns
  was compensating band-2 latency.
- Symptom: `pair_swap_flux_map` q1_q2 lost q1's excitation over the whole map (P00 ~0.9;
  runs 20260928-205021-088, -205723-918). Sweeping the z amplitude 0 -> -0.16 V
  (20260928-210338-650) gives a smooth loss, half at ~-52 mV: the 40 ns z pulse overlaps the
  16 ns pi pulse (off-resonant Rabi, Omega ~31 MHz). Rabi, readout and small-excursion Ramsey
  (no or small z pulse) look healthy, so nothing else flags it.
- Measured with `qubit_xyz_delay`: q1 +19.5 ns (20260928-210808-599), q2 +18.8 ns
  (20260928-210631-128), q3 (still band 1) +0.2 ns (20260928-210718-284). Their pending
  `flux_delay_s` suggestions (~113 ns) are the WRONG fix: delaying z1/z2 alone misaligns them
  from the coupler lines zc12/zc23, which a swap plays simultaneously.
- Pointer: `scqo-qm adopt-channel` (its CAUTION only asks for `qubit_power_rabi`), the MW port
  `delay` in `<setup>/backend_config/state.json` (`ports/mw_outputs/con1/<slot>/<port>/delay`).
  No operator command writes an MW port delay today.
- Done when: a band change keeps every port's latency consistent (adjusts `delay`, or refuses
  and names the `qubit_xyz_delay` re-check for every qubit on the port pair), and the XY-XY,
  XY-Z and XY-readout alignment across band-1 and band-2 ports is written down per setup.

### I32 The parametric-drive family's reported outputs mislead a reset calibration (medium)
- Found 2026-09-29 writing the q2 parametric-reset report from the 38 saved 5Q4C runs
  (`qubit_parametric_drive[_amp]` 20260821 .. 20260921, `qubit_parametric_drive_time`
  20260826-014448 .. 20260921-211249). Both experiments are now exercised on QM hardware.
- (a) scqat `parametric_drive_decoherence/visualization.py::plot_decoherence_params` draws
  the EP reference at 8*lambda^2/gamma^2 = 1, but the model's EP (d^2 = (gamma/2)^2 -
  4*lambda^2 = 0, which `ep_pipeline._decoh_result_dict`'s `regime` also uses) is at 1/2.
- (b) SCQO `qubit_parametric_drive_time.estimate()` reports `best_parametric_freq_hz` as the
  argmax of 8*lambda^2/gamma^2, which is not the resonance: run 20260921-211249-852 gives
  372.1 MHz against a global-fit f0 of 372.59 MHz (12.8 % residual there at 140 ns vs ~2 %
  on resonance), and early runs pick degenerate gamma -> 0 fits (metric ~1e19).
  `best_gamma_hz` / `best_lambda_hz` / `best_delta_hz` are angular rates in 1/s (1/ns x 1e9),
  not Hz.
- (c) The per-frequency fit has no readout floor and no shared detuning line. A global 2-D fit
  P = B + C*|c_e(t + t0)|^2 with Delta = 2*pi*k*(f - f0) reproduces all 13 usable runs
  (kappa/2pi 3.79 +- 0.23 MHz, k 4.5 +- 0.4, i.e. the 4th-harmonic sideband with q2_res).
- Done when: the EP line and `regime` agree; `_time` reports a resonance f0 (and the first
  zero t*) from a fit that ties Delta across frequencies; rate fields are named for their unit.

### I33 `ParametricReset.apply()` leaves the z-line oscillator at the reset frequency (medium)
- Found 2026-09-29 (same report). `scqo_qm/components/macros/parametric_reset_macro.py`
  calls `update_frequency(drive_frequency)` and never restores it, so every later pulse on
  that `q.z` in the same program plays modulated at 372.5 MHz. Harmless today: in
  `qc_unidirectional_trotter` / `qc_trotter_compensation` q2 is the TARGET of both pairs
  (controls q1, q3), so the swap flux pulses play on `q1.z` / `q3.z`.
- It also relies on `q2.z.intermediate_frequency` being 0, not None, in the 5Q4C state.json:
  with None the generated config has no z oscillator and the macro fails at compile (the
  chain shells do not apply the probes' `ensure_flux_oscillators` patch).
- Since 2026-10-01 q3 carries a `ParametricReset` too (355.0 MHz, `q3.z.intermediate_frequency`
  set to 0 for it). q3.z also plays other flux pulses (partial swaps), so a program that resets
  q3 and then plays one of them on q3.z hits this.
- Done when: `apply()` restores the element's IF after the play (or refuses a z line without
  an oscillator), pinned by a test over the compiled program.

### I34 `qc_unidirectional_trotter`'s transport summary is meaningless for a multi-qubit prep (low)
- Found 2026-09-30 with the new `prep_operations` map (hardware 5Q4C, tag `prep-map`, e.g.
  `20260930-002542-364`). With the sink prepared too (`{"q1": "x180", "q3": "x180"}`),
  `sink_p_max` / `n_at_max` report the N=0 prep (0.92, N=0), not transport, and the scqat
  estimator's figure has no ideal to draw (the closed form is single-excitation), so the
  run's own artifacts say nothing about the two-excitation dynamics. The analysis was done
  by hand against two theories, with the SAME single-excitation compensation (it is a
  property of the round, not of the state):
  - the cascaded master equation from |ee> (gamma = theta^2 per round): stimulated
    emission, the continuum physics;
  - the Trotter circuit itself, as a coherent 8-state model (two partial swaps + a full
    relay reset). It differs from the continuum only because the relay is a two-level
    ancilla: one round cannot carry two excitations.
  Both track the joint populations within the readout contrast (rms 0.04-0.06). At
  theta2 = 0.6 the data at N = 1-3 follow the CIRCUIT: P(sink only) at N=1 is 0.19,
  against 0.15 for the circuit and 0.07 for the ME (400 shots, sigma ~0.02).
- Done when: either the estimator overlays both theories for any computational-basis prep
  (joint panel included), or the summary keys are withheld / renamed when the prep is not
  the source alone. Decide which before building.

### I36 A strong stark tone on q3 adds population loss per round (medium)
- Found 2026-10-01 by `qc_n_swap_tomography` (5Q4C q2_q3 `partial_swap_040`, gap 260, run
  `20261001-200029-259`): q3's T1 loss per round is 0.047-0.073 at stark 0.86-0.96 (about 0.9
  of a turn), against 0.017 from its T1 (22 us) - and it grows with the amplitude. q1 under a
  0.45-0.5 tone (`20261001-200143-656`) loses 0.017, as its T1 predicts.
- Why it matters: the Trotter chain's sink q3 carries a compensation tone of ~0.76-0.82 every
  round; the 09-30 both-idle |100> runs already showed q3 creeping up under its own tone. A
  leak through the 60 ns Gaussian's spectral tail at 50 MHz detuning, or |1>->|2>, are the
  first suspects.
- Done when: the loss is explained (e.g. vs stark amplitude and detuning with the swap off)
  and the chain's sink model carries it, or the tone is reshaped so it vanishes.

### I37 `ParametricReset` has no ring-down wait (medium)
- Found 2026-10-01 writing `procedures/qubit-resonator-sideband-swap`. The sideband swap
  empties the qubit into its readout resonator; the photon then leaves at kappa. At the
  first zero a large part of the energy is still in the resonator (5Q4C q2: ~20 %,
  1/kappa 42 ns; q3 at 100 ns, measured 2026-10-01: 59 %, ~400 ns to fall below 1 %).
  `scqo_qm/components/macros/parametric_reset_macro.py` plays the pulse and returns, so a
  readout or a gate on the same qubit right after it sees the photon's dispersive shift.
- Done when: the macro waits a stored ring-down time after the pulse (or its `duration`
  includes it), and the reset's reported length is pulse + ring-down.

### I38 The QM gateway simulator shows the flux DC levels on the wrong ports (low)
- 2026-10-04, while checking `source_lead_time_ns` on the gateway simulator (5Q4C): the
  generated QUA sets every flux element's DC offset correctly (`set_dc_offset("q1.z", ..,
  0.2721)`, `q2.z` -0.0060, `q3.z` 0.0162, `q4.z` 0.1056, `q5.z` 0.0846, `q1_q2` 0.17006,
  `q2_q3` 0.07083), but `get_simulated_samples()` returns the standing level 0.2721 on
  analog keys 1-1 AND 1-2, -0.0060 on 1-3 and 1-4, 0.0162 on 1-5 and 1-6, 0.1056 on 1-7
  and 1-8: each value on two neighbouring keys, the later elements' values nowhere. The
  PULSES sit on the right keys with the right timing and height. So
  `scqo run --preview`'s `simulated_waveforms.html` draws wrong standing biases. The
  hardware is right (every apex sits where the stored bias says).
- Not investigated: a simulator artifact, or the key -> port reading in
  `QMBackend._simulated_waveforms`.
- Done when: explained, and the preview either shows the right levels or says they are not
  to be trusted.

### I39 QM `qubit_echo_flux_pulse` stores ONE ARM as `wait_time_ns`: T2 echo reads half (medium)
- Found 2026-10-04 while declaring the sequence diagrams (`docs/experiment-docs-plan.md`
  section 14). Read from the code, not reproduced on the instrument. (I37 and I38 are taken on main.)
- `scqo-qm/scqo_qm/experiments/qubit_echo_flux_pulse.py`: the shell turns the total idle into
  per-arm cycles (`round((wait_ns / 2) / 4)`) and each arm plays `t` cycles, which is right;
  but `build_program` labels the axis `4 * wait_times_cycles` - the length of one arm, under
  the long name "total wait time". The names already equal the Contract's, so
  `_to_canonical` passes the probe's coordinates through and `estimate()` fits the decay
  against half the true idle. `qubit_echo.py` labels the same quantity `8 * cycles`.
- No test covers the probe's axis values (`tests/` has no `echo_flux` test).
- Until fixed: `QMQubitEchoFluxPulse.backend_notes` says so in `scqo run ... --help`. Saved
  runs can be corrected offline by doubling the coordinate.
- Done when: the builder labels `8 * cycles`, a generated-QUA test pins the axis against the
  played arm length, and any stored `t2_echo` spectrum taken before the fix is marked.

### I40 `qubit_xyz_delay.simulate()` draws the peak AT the stored delay: an accept doubles it (low)
- Found 2026-10-04 while documenting it (`docs/experiment-docs-plan.md` section 17).
  Reproduced on the simulated backend: with `z_q0.flux_delay_s` set to 5 ns, two runs with
  `update="apply"` propose 10.0 ns and then 20.1 ns.
- `scqo/experiments/qubit_xyz_delay.py::simulate` centres the triangle on the line's stored
  `flux_delay_s`, and `estimate()` reports `old + fitted`, so the proposal is twice the
  stored value. The comment says the opposite ("so a re-run after accept sees the peak move
  to 0"). On an instrument the peak sits at the REMAINING misalignment, which the stored
  delay reduces. Hardware runs are not affected; the practice mode teaches the wrong
  behaviour for any line whose delay is not 0 (the demo device's is 0, so no test sees it).
- Where: `simulate()` (a hidden true delay per target, the peak at `true - stored`); a test
  that accepts once and finds the second run's `delay_shift_s` near 0.
- Done when: an accepted simulated run brings the next run's peak to 0, pinned by that test.

### I41 `pair_zz_coupler`: a ZZ below -2 x detuning reports a false decouple point (medium)
- Found 2026-10-04 while documenting it (`docs/experiment-docs-plan.md` section 19).
  Reproduced with the real estimator on the simulator's own signal model (detuning 1 MHz,
  31 biases over +-0.3 V, zz linear in the bias with its zero at +0.100 V): a slope of
  2.5 MHz/V reports the crossing at +0.099 V; a slope of 6 MHz/V, where zz reaches -2.4 MHz
  at the low edge, reports -0.233 V, SUCCESSFUL, and `update()` proposes it as the coupler's
  `idle_flux`.
- Cause: scqat `zz_interaction` fits the fringe frequency with `f >= 0`, and the experiment
  reads `zz = f - detuning_hz`. Where the true zz is below `-detuning_hz` the fringe folds
  (`f = |detuning + zz|`), so the reported zz turns back up and crosses zero again at
  `zz = -2 x detuning_hz`; `_zero_crossing` takes the FIRST sign change along the bias axis.
  A positive zz of any size is unaffected.
- `simulate()` can reach this range by itself: its slope goes up to 5 MHz/V and its zero up
  to +0.12 V, i.e. -2.1 MHz at -0.3 V. Only the corner of its draw does (not seen for the
  demo pair `q0_q1`), so an offline run of another pair name could propose a false point.
- The figures add to it: both `zz_interaction` figures draw the fitted `f` (in Hz, the
  detuning included) under the labels "ZZ strength" / "ZZ (MHz)", so the curve's MINIMUM
  reads as the decouple point while it is the place where zz = -detuning.
- Where: `scqo/experiments/pair_zz_coupler.py` (`estimate`, `_zero_crossing`), scqat
  `estimators/zz_interaction/` (the figure labels; the detuning has to reach it to draw zz).
- Done when: a fold inside the window is either refused by name (e.g. the fitted `f` comes
  within the fit's resolution of zero somewhere in the sweep) or unfolded by continuity, a
  test plants zz below -2 x detuning and gets the true crossing or a FAILED run, and the
  figures draw `f - detuning` with a correct unit. Fix together with I26 (the frame of the
  written value).

### I42 Pair family: presentation mismatches (hygiene)
- Found 2026-10-04 while documenting the seven `pair_*` experiments and the four
  swap-chain ones.
- `pair_coupler_crossing_pulse` puts a STRING into `result.fit` (`center_kind`), which is
  declared `dict[str, float]`: every run prints pydantic's "serialized value may not be as
  expected". The two punchouts do the same (`'punchout'`). Either an integer code, or a
  place for non-numeric results.
- `pair_swap_flux_map`: the module text, the field descriptions and the QM probe call the
  coupler amplitude the x axis and the member's the y axis; the scqat figures draw the
  member on x and the coupler on y (the shared plotter puts the first sweep axis on x).
- `pair_zz_coupler`: `idle_time_ns` is the length of ONE echo arm (the QM probe plays it
  per arm, and the fringe model is in that time), while the field text says "echo evolution
  time" and the `define_sweep` comment speaks of keeping "the two arms whole nanoseconds".
  Its bias field texts also say "standing bias" for what is played as a pulse (I26).
- `qc_n_swap_amp`: the registry description says the map "locates the correctly calibrated
  amplitude far more finely than a single swap", while `pair_swap_chevron`'s module text
  shows why the peak of a repeated-swap map is NOT the resonance (the between-swap phase
  moves it by about phi / t_pulse). The document follows the second.
- `qc_n_stark_amp`, `qc_n_swap_tomography` and `qc_swap_flux_stark` default
  `swap_operation` to `iswap`, the full swap, while their own field texts say the reading
  is meant for a PARTIAL swap (for `qc_n_stark_amp` a full swap sits on the limit where
  the period reading stops meaning anything). `pair_swap_angle` defaults to
  `partial_swap`.
- Done when: each is made consistent, on whichever side is judged right.

### I43 The QM gateway simulator returned no samples for the chain program (medium)
- 2026-10-08, measuring the `stark_timing="with_reset"` round of F17 on the gateway
  simulator (5Q4C, F16's method through `Session.preview`). `qmm.simulate` returned in
  about 10 s each time, and `job.get_simulated_samples()` then raised `QMSimulationError:
  Error while pulling samples`, on five calls between 12:09 and 12:28:
  `qc_unidirectional_trotter`, both stark timings, windows of 16, 20 and 26 us, 1 and 400
  averages, `thermalization_time_ns` 400 and 2000. The cluster listing answered throughout
  and the ten hardware runs made in between were normal.
- The same simulator returned samples on 2026-10-04 (I38), and for the chain on 2026-09-22
  (F16), so neither the two-upconverter config nor the chain program alone explains it.
- Not investigated, by the stop-at-the-first-problem rule: the gateway that day, or
  something those five requests share (the per-run thermal override was in all of them).
- Consequence: the `with_reset` round length is still unmeasured (F17).
- Done when: a chain preview simulates again, or the failing condition is named.

## Hardware validation owed (from earlier session notes — verify before acting)
- `qubit_ramsey_flux_crosstalk_pulse` (built 2026-10-04; F32). FIRST RUNS on 5Q4C the same
  day (tag `crosstalk-hwtest`, all `--no-update`, each SUCCESSFUL with 5/5 source points):
  q3 <- z2 m = +1.259 % +- 0.002 (`20261004-182639-890`), q1 <- zc12 m = -3.242 % +- 0.008
  (`-182937-908`), q3 <- zc12 m = +0.951 % +- 0.003 (`-183325-517`). The apex track is a
  line to 1-14 uV, m is the same in the first and the second half of the 1.6 us pulse, and
  a run takes 3-4 min. The zero-code reading of q3 <- z2 (tag `crosstalk-pretest`,
  `-182123-772`) gives |m| 1.34 % and is reproduced to 1.1 kHz by the new run's numbers.
  THE OTHER NINE CELLS of q1-q3 x (z1, z2, z3, zc12, zc23) the same evening at
  `num_averages=50` (tag `crosstalk-matrix`, runs `20261004-1911..1920`, about 1 min per
  cell, all SUCCESSFUL with 5/5 source points; a repeat of q3 <- z2 reads +1.254 % +- 0.008).
  Pulse-frame m in percent, one target per row:
    q1 <- z2 -0.328 +- 0.004, z3 -1.131 +- 0.011, zc12 -3.242 +- 0.008, zc23 -0.461 +- 0.006
    q2 <- z1 +1.600 +- 0.004, z3 -1.677 +- 0.032, zc12 +4.247 +- 0.016, zc23 -3.507 +- 0.008
    q3 <- z1 +0.725 +- 0.003, z2 +1.259 +- 0.002, zc12 +0.951 +- 0.003, zc23 +2.967 +- 0.014
  In all 12 cells the sign follows the side of the chain (q1, c12, q2, c23, q3) the source
  sits on: + from the q1 side of the target, - from the q3 side. Windows: z1/z2 +-100 mV,
  z3 +-40 mV, couplers -100..+30 mV. Largest line residual 33 uV (q2 <- zc12).
  `source_lead_time_ns` ran the same night (tag `crosstalk-lead`, 19 runs at leads of 0 to
  3 ms, 10-20 averages, all SUCCESSFUL; results under F32); on the gateway simulator the
  source pulse rises exactly the lead before the own one and falls with it.
  STILL OWED: a halved source window and a reversed sweep on one cell; `linearity_tol_v`
  (0.1 mV is 2x the largest residual seen - 51 uV, at a 1 ms lead).
- `qc_n_swap_tomography` (landed 2026-10-01). DONE on 5Q4C the same day for both 040 swaps at
  gap 260 after the re-park: theta' and the compensating amplitude agree with a same-session
  `qc_n_stark_amp` within 0.01 (plan doc section 12; two frame fixes were needed - per-shot
  frame reference with a baked-detuning `stark_detuned`, and the fitted `frame_step`).
  STILL OWED: a small angle (`partial_swap_013`, whose 09-30 calibration is void after the
  re-park) against `qc_n_stark_amp`; the per-step T1 loss against a same-session
  `qubit_relaxation` with the stark off (see I36); a run that proposes `theta_rad` end to end.
  After that the paused six-ratio |11> series resumes (session memory carries its state).
- `qubit_ramsey_flux_pulse` on QBLOX (F23 landed 2026-09-26, fragment `qubit-ramsey-flux-pulse`;
  QM validated on 5Q4C q1). The probe compiles and is pinned structurally; no cluster run
  exists. Check that the sticky `VoltageOffset` pair really holds idle + a for the whole
  `IdlePulse(tau)`, and measure its pulse/DC ratio g against a same-hour DC reference as
  `procedures/qubit-frequency-park` does. Active reset and `flux_component` stay refused
  there until then.
- Ramsey phasor family; cryoscope Qblox port;
  `qubit_tomography` interleaved noise; XY-Z delay (`qubit_xyz_delay`); readout average mode;
  broadband RESONATOR variant (offline-only on both
  backends); scqo-agent Phase C; `qm-session-hardening` fa1ba06 reverted, QPX1000_4 restart
  owed; the setup-snapshot feature's first real run (compare
  `<device>/setup_snapshots/<hash>/backend_config/state.json` with the setup's file, then
  `scqo restore` + `scqo doctor`); `QbloxBackend.release_instruments` (added 2026-09-04
  with the campaign accept step) — offline-pinned with fakes in
  `scqo-qblox/tests/test_release_instruments.py`, but that a real `Cluster.close()`
  returns inside `_CLUSTER_CLOSE_TIMEOUT_S` and actually frees the four sockets can
  only be seen on hardware: run a campaign at a terminal, leave the prompt open, and
  check that a second process can connect.
- `qubit_resonator_stark` (added 2026-09-21, fragment `qubit-resonator-stark`; offline-only
  on both backends). QM: before trusting a map, check in `--preview`'s simulated analog
  traces that the resonator's Stark tone and the xy drive really OVERLAP — same-core
  elements serialize and hand back a map with no shift and a clean fit. Qblox: the first
  cluster run of a non-`Measure` pulse on the readout port-clock. Both: once `chi_hz` is
  measured, sanity-check `n_readout` against an independent photon estimate.

**OPX+ / Octave (added 2026-09-11, scqo-qm)** - the whole family has NEVER run on
hardware: six startup audits, the Octave gain+amplitude power solve, the mixer
calibration CLI, the chain-filtered `scqo state --fields`, and the two broadband probes'
Octave LO path. Offline it is covered by 636 tests including 22 against a real tree built
by `quam_builder` (`scripts/make_opxp_fixture.py`), which is as far as offline can go.
The walkthrough is `scqo-qm/OPX-PLUS.md` and its ORDER matters: mixer calibration FIRST,
because every step after it depends on it and an Octave has no MW-FEM-style "it just
works" default. Watch two things in particular - whether any `*_power_dbm` write moved
the Octave gain (it invalidates that RF output's mixer calibration, and on a multiplexed
feedline it moved every qubit on the line), and whether `power_context` in the run record
carries the calibration db's digest.

