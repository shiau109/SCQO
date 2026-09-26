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
  (a NEGATIVE amplitude means a badly-conditioned fit, not a dip). `peak_inverted` (per
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

### F17 A shorter Trotter round: the stark tones during the relay reset (medium)
- Added 2026-09-22 after the `partial_swap_030` chain run `20260922-202034-457`.
- Problem: 80 ns of the 360 ns round swaps; the rest is three gaps (60), the relay reset
  (140 + overhead) and the stark tones (60). The sink decays with ~19 rounds (6.9 us),
  close to the q1-q3 combined dephasing, so round length is the lever. The tones act on the
  source and sink, the reset on the relay, so they could play concurrently (~280 ns round).
- Where: the round body of `scqo-qm` `qc_unidirectional_trotter.py` /
  `qc_trotter_compensation.py` (the align before the tones), the Qblox probes for parity,
  and the SCQO docs.
- Done when: a Parameters switch plays the tones during the reset on both backends, the
  compensation is re-measured, and the sink curve is compared with the 360 ns round.

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

### F23 `qubit_ramsey_flux_pulse` — park a qubit by a Ramsey flux map (spec 2026-09-26) (high)
- Spec: `docs/flux-parking-plan.md` §4 (untracked plan doc, Chinese), revised with the user's
  three corrections. Automates the manual `scqo set idle_flux` + `qubit_ramsey` + periodogram
  loop used on 5Q4C 2026-09-26, which re-parked all three qubits after a +6..+10 mV DC drift
  (q3 T1 +48%).
- PULSE frame, not DC (user, 2026-09-26): a DC move takes the x90s and the readout off the
  idle point they were calibrated at. x90 at idle -> square z pulse (relative amplitude a,
  length tau) -> x90 with the virtual ramp -> readout at idle; averages OUTER / flux
  start->end / tau inner. `park_frequency_hz: float | None` (None = apex), `flux_side`; the
  experiment picks the SIGN of the virtual detuning so the excursion pushes the fringe away
  from zero, and refuses `folding_risk` / `undersampled` pre-probe from the arch facts. New
  scqat estimator + `tools.fringe_frequency` (periodogram-seeded).
- COMPLEMENTARY, not an authority (user, 2026-09-26): `resonator_spectroscopy_flux`,
  `qubit_spectroscopy_flux_pulse` and this one each may propose `idle_flux`; each has its own
  strengths (plan doc §4.0 table) and the first two feed this one's window and folding
  prediction. Rewrite the "AUTHORITY for idle_flux" / "BRING-UP seed" wording in the two
  existing descriptions into strengths and weaknesses when this lands.
- Known cost of the pulse frame: I25 (excursions read 8-15 % large, exact at zero excursion),
  so a large park move converges by re-running from the new point.
- PROGRESS: scqat half LANDED 2026-09-26 as scqat `37a41ee` - `tools.fringe_frequency` and the
  `qubit_ramsey_flux_pulse` estimator (full scqat suite green; offline on the 2026-09-26 5Q4C DC
  scans it reproduces the manual apexes within 0.02 mV). The estimator's `ramp_detuning_hz` is
  the SIGNED detuning in the qubit_ramsey convention; its result key is `question`
  (apex|park), NOT `mode` (a netCDF3 global attr named `mode` breaks scipy's writer).
  SCQO experiment + probes WAIT for F25: overriding the window defaults by the old names
  after F25's rename would silently ADD a stray `min_flux_v` field, not fail.
- HARDWARE PRE-TEST DONE 2026-09-26, 5Q4C q1, with a scratch QUA builder (prototype in
  `scqat/temp/ramsey_flux_pulse_pretest/`, becomes the real probe after F25). The pulse-frame
  Ramsey agrees with a same-hour DC reference after one gain factor g ~ 0.96 (apex shift
  8.0 / 8.35 mV = 0.958; curvature ratio sqrt(0.0141/0.0153) = 0.960) and NO constant offset.
  Phase is linear in tau (no us tail on a 4 us square pulse). Two lessons for the spec: the DC
  apex drifts ~0.2 mV/h, so every comparison needs a same-hour DC reference; and the
  estimator's `apex_flux_stderr` (0.001-0.003 mV) is ~30x smaller than the run-to-run scatter
  (0.1 mV over 4 min).
- Done when: landed in all four repos, QM hardware checklist §4.10 passed on 5Q4C (q1 apex
  within 0.1 mV of the DC apex 0.261019 V at coupler 0.16 V; the +8 mV excursion ratio
  measured), Qblox structurally tested, and `procedures/qubit-frequency-park` written.

### F25 Sweep windows `start`/`end` mean traversal ORDER - flux, detuning AND amplitude (medium)
- Decided 2026-09-26 by the user. Consecutive points are not always independent, so the
  sweep order must be explicit and visible when debugging. Three rules:
  1. Flux: rename `min_flux_v`/`max_flux_v` -> `start_flux_v`/`end_flux_v` on
     `FluxSweepParameters` (both frames). No aliases.
  2. Detuning: its `start_*`/`end_*` stop being a window only. Drop the ascending
     normalisation (`_capabilities/detuning.py::_window_sweep` / `window_bounds`) and rewrite
     the module docstring that justified it.
  3. The dataset keeps the REALIZED order (never re-sorted), and **the order must not affect
     any estimator**: the same data swept in either direction gives the same result.
- Prerequisite, in scqat FIRST (it is why detuning normalised): `tools/peak_fit.py:289`
  `gamma_max = detuning[-1] - detuning[0]` goes negative on a descending axis, and a 4 MHz
  line came back as 174 MHz with no flag. `tools/fit_notch_circle.py:155/162/185` has the same
  form. Then audit every estimator/tool using `np.interp` (silently wrong for decreasing
  xp), `searchsorted` or `np.gradient`: `_twin_axis.py`, `dip_fit.py`, `peak_fit.py`,
  `pulse_arrival.py`, and the `qc_n_stark_amp`, `qc_swap_flux_stark`,
  `resonator_spectroscopy`, `resonator_spectroscopy_power` estimators. Every estimator that
  reads a flux or detuning axis gets a "descending == ascending" test.
- Landing order: scqat -> SCQO (both capabilities, carriers
  `qubit_spectroscopy_flux_pulse`, `resonator_spectroscopy_flux`, `qubit_echo_flux_pulse`,
  `qubit_relaxation_flux_pulse` + every detuning carrier; `tests/test_capabilities.py`;
  shared-core mixin = full suite) -> drivers (both already sweep a descending axis, per the
  detuning docstring; `scqo-qblox/tests/test_flux_limits.py`). `pair_zz_coupler`'s
  `min/max_coupler_v` follow with I26.
- Amplitude too (user, 2026-09-26): `min_amp_factor`/`max_amp_factor` ->
  `start_amp_factor`/`end_amp_factor` on `AmplitudeSweepParameters`. Its `_window_ordered`
  validator (min < max) becomes a zero-width refusal, and the bounds (>= 0, < 2) apply to BOTH
  edges. Carriers: `qubit_power_rabi`, `readout_power`, `qubit_resonator_stark`,
  `qubit_pi_pulse_error`, `qubit_deterministic_benchmarking` (a carrier overriding
  `amp_values()` must honour the order too). Both drivers' `_amp_limits.py` and many
  scqo-qblox tests name the fields.
- Done when: all three capabilities carry the order meaning, no estimator can tell the
  direction, and the plan doc's F23 builds on it.

### F24 Coupler state readout through a neighbour's apex height + the crosstalk matrix (medium)
- Found 2026-09-26 (hardware 5Q4C, `--tag coupler-scan`). Evidence + open decisions:
  `docs/coupler-readout-plan.md` (untracked); scripts/raw results in `scqat/temp/coupler_scan/`.
  The user deferred it: separate session, and only when the coupler is actually touched. A
  neighbour's raw frequency vs coupler DC MIXES two effects: coupler-line crosstalk into the
  probe's own SQUID (moves the probe's apex LOCATION: q1 -0.055, q3 -0.072 mV per coupler mV
  on the q1_q2_c line) and the coupler's Lamb shift (moves the apex HEIGHT: q1 +524 kHz for
  -80 mV). The apex height is the coupler observable: q1_q2_c's own DC apex ~0.074 V
  (reconstructed), idle 0.16 V sits 86 mV above it.
- Plan: a PAIR-targeted sibling of F23 (`measure: high|low`, as `pair_zz_coupler`) that nests
  the F23 apex reading inside a coupler-bias loop -> writes `<coupler>_z.flux_offset`
  (catalogued, no writer today) and moves the coupler `idle_flux` with its drift.
- Blocked on the user's decisions (coupler doc §4.4): J=0 vs ZZ=0 as the idle criterion;
  crosstalk matrix as facts + compensated (virtual-flux) moves, or measured only.
- Also: note in `catalog.py` that a qubit's `flux_offset` / `f_q_max_hz` are measured AT THE
  CURRENT COUPLER BIASES on a coupler chip.
- Done when: the sibling experiment exists, one coupler is parked by it on 5Q4C, and the
  crosstalk matrix (incl. coupler columns) has a home.

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
- Done when: seeding comes from a periodogram peak (F23's `tools.fringe_frequency`) and the fit
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
  `<coupler>_z.idle_flux`, and the axis text says "coupler standing bias". The write is off by
  the standing `decouple_offset` (0.16 V on 5Q4C q1_q2_c today). No Qblox probe; no run in this
  machine's index.
- Done when: the experiment takes one frame and says so in its name — either a DC probe
  (`set_dc_offset`, absolute, no suffix) or `_pulse` + re-referencing
  `idle_flux = old_idle + fitted` — with a test pinning the frame.

## Hardware validation owed (from earlier session notes — verify before acting)
- Ramsey phasor family; parametric-drive family (`_amp` + `_time`); cryoscope Qblox port;
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

