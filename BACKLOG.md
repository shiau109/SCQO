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

### F7 Lift the TEMPORARY push refusal when the qualibrate GUI stops writing QUAM
- Added 2026-09-03 (fragment `hardware-push-refusal`).
- Delete the guard in `scqo/labconfig.py::make_session` + its tests
  (`test_make_session_refuses_push_on_hardware_backends`,
  `test_hardware_setup_with_push_config_refuses_without_traceback`) and, for QM, the driver
  guard in `scqo-qm/scqo_qm/scqo_backend.py`; keep the `state_sync` parse validation.

### F8 PR #29 viewer dashboard — held pending a CHARTER decision
- Carried over; the reviewed defects live only in the session memory `pr29-viewer-dashboard-held`.
  Decide the charter, then either land with the fixes or close.

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
- Found 2026-09-03. `QMBackend.load` exports it; `QMDeviceModel(state_dir=None)` relies on
  it for `save()`; a second session or script in the same process inherits the folder.

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

### I10 Stale names and version lines (hygiene)
- `scqo/cli/__main__.py::_usage()` still names LCHQBDriver / LCHQMDriver.
- `scqo-qm/scqo_qm/backend/qm_backend.py` module docstring: "shared with the qualibrate
  writebacks" (retired).
- `scqo-qm/quam_state/` holds six `*.bak*` files; QUAM merges any `*.json` under its state
  directory, so a backup must never be named `*.json`.

## Hardware validation owed (from earlier session notes — verify before acting)
- Ramsey phasor family; parametric-drive family (`_amp` + `_time`); cryoscope Qblox port;
  `qubit_tomography` interleaved noise; XY-Z delay (`qubit_xyz_delay`); readout average mode;
  `qc_n_stark_amp` (+ `register_stark.py`); broadband RESONATOR variant (offline-only on both
  backends); scqo-agent Phase C; `qm-session-hardening` fa1ba06 reverted, QPX1000_4 restart
  owed; the setup-snapshot feature's first real run (compare
  `<device>/setup_snapshots/<hash>/backend_config/state.json` with the setup's file, then
  `scqo restore` + `scqo doctor`); `QbloxBackend.release_instruments` (added 2026-09-04
  with the campaign accept step) — offline-pinned with fakes in
  `scqo-qblox/tests/test_release_instruments.py`, but that a real `Cluster.close()`
  returns inside `_CLUSTER_CLOSE_TIMEOUT_S` and actually frees the four sockets can
  only be seen on hardware: run a campaign at a terminal, leave the prompt open, and
  check that a second process can connect.
