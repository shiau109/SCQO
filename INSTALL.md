# SCQO installation & verification

One-time setup per machine: build the Python environment, write the lab config, and
verify the stack — first offline, then against your instrument's real config files.
Done once (usually by the lab manager); students then follow [TUTORIAL.md](TUTORIAL.md).

The stack is cross-platform: the full test suite runs on **Windows, macOS and Linux**
in CI on every push (`.github/workflows/tests.yml`). Windows commands are shown first;
macOS/Linux equivalents follow where they differ.

## 1. The Python environment

**Policy: every environment is a plain venv managed by `uv`.** Conda is retired: an
audit (2026-07-05) showed the lab's conda envs used conda only as a Python installer
(all 180+ scientific/vendor packages came from pip) — uv does that job faster, with
lockfiles, and without licensing questions. One venv per vendor stack:

| venv | contents | used for |
|---|---|---|
| `D:\github\.venv` | scqo + scqat + LCHQBDriver (+ qblox-scheduler) | analysis, Qblox, all student scripts |
| `D:\github\.venv-qm` | scqo + scqat + LCHQMDriver + pinned QM stack | anything touching qm-qua/quam/qualibrate |

Rebuild `.venv-qm` anywhere from the committed pin list (exact versions proven
against the lab's QOP):

```powershell
cd D:\github
uv venv .venv-qm --python 3.11
uv pip install --python .venv-qm\Scripts\python.exe -r .\LCHQMDriver\requirements-qm.lock.txt
uv pip install --python .venv-qm\Scripts\python.exe -e .\SCqubit-analysis-tool -e .\SCQO -e .\LCHQMDriver --no-deps
```

(Transition note: the qualibrate GUI launcher `qm.bat` still targets the old conda
`LCHQM_test` env until the lab flips it after an at-instrument validation; both
environments import scqo/scqat from the same editable checkouts, so they never drift
on the neutral layer.)

`uv` creates a standard venv and also downloads Python itself if the machine has none.

The repos must sit next to each other in one folder (`SCQO` and `SCqubit-analysis-tool`
as siblings) — on the lab PC that folder is `D:\github`; on your own Mac clone them:

```bash
mkdir -p ~/github && cd ~/github
git clone https://github.com/shiau109/SCQO.git
git clone https://github.com/shiau109/SCqubit-analysis-tool.git
git clone https://github.com/shiau109/LCHQBDriver.git
```

**Windows (PowerShell)** — on the lab PC this env already exists at `D:\github\.venv`:

```powershell
cd D:\github
uv venv .venv --python 3.12
uv pip install --python .venv\Scripts\python.exe -e .\SCqubit-analysis-tool -e .\SCQO pytest
uv pip install --python .venv\Scripts\python.exe -e .\LCHQBDriver   # + qblox-scheduler (vendor stack)
.venv\Scripts\Activate.ps1          # activate (Git Bash: source .venv/Scripts/activate)
```

**macOS / Linux** — install uv once with `brew install uv` (or
`curl -LsSf https://astral.sh/uv/install.sh | sh`), then:

```bash
cd ~/github
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -e ./SCqubit-analysis-tool -e ./SCQO pytest
uv pip install --python .venv/bin/python -e ./LCHQBDriver   # + qblox-scheduler (vendor stack)
source .venv/bin/activate
```

(The second install line adds the Qblox driver and its vendor stack — needed for the
driver scripts and the self-test in section 4. Skip it on a pure analysis machine;
finding/loading saved data works without it.)

## 2. The lab config: `~\.scqo\config.toml`

This one small file tells every script where data goes, which device you are on,
and which backend runs. Create it at `~\.scqo\config.toml` (Windows:
`C:\Users\<you>\.scqo\config.toml`; macOS: `/Users/<you>/.scqo/config.toml`).

**Backend modes** — pick how real the setup is:

| `backend =` | device tree | data | writebacks persist to |
|---|---|---|---|
| `"simulated"` | built-in demo qubits | synthetic | scqo state file (use `state_sync="push"`) |
| `"qblox_sim"` | **your REAL dut config** (working copy) | synthetic | the working `dut_config.json` |
| `"qm_sim"` | **your REAL QUAM state** (working copy) | synthetic | the working `state.json` |
| `"qblox"` / `"qm"` | real instrument | real | vendor config (QM: keep `state_sync="pull"`) |

The `*_sim` modes are the **virtual twin**: real qubit names and calibration values as
starting points, no hardware needed — the recommended practice mode for students. Set
them up once by copying your vendor config into a working folder (originals stay
pristine), e.g. `copy dut_config_AS_QRC.json D:\qpu_data\SQ_demo\qblox_state\dut_config.json`.

Windows (virtual-twin example):

```toml
[lab]
data_root   = 'D:\qpu_data'                          # all measurement data lands here
device_name = "SQ_demo"                              # your chip / sample name
state_path  = 'D:\qpu_data\SQ_demo\scqo_state.json'  # change history (provenance)
backend     = "qblox_sim"                            # REAL device tree, synthetic data
default_tags = ["cooldown1"]                         # stamped on EVERY run; edit each cooldown

[qblox]
config_dir = 'D:\qpu_data\SQ_demo\qblox_state'       # working copy of dut_config.json (+ hw_config.json for "qblox")

# QM virtual twin instead: backend = "qm_sim" plus
# [qm]
# state_dir = 'D:\qpu_data\SQ_demo\qm_state'         # working copy of state.json + wiring.json
```

macOS / Linux (`~` is expanded for you; plain-simulated example):

```toml
[lab]
data_root   = "~/qpu_data"
device_name = "SQ_demo"
state_path  = "~/qpu_data/SQ_demo/scqo_state.json"
backend     = "simulated"
state_sync  = "push"
default_tags = ["cooldown1"]
```

State persistence: in the `*_sim` twin modes the working vendor config **is** the
device state — it updates on every successful run, so calibrations persist across
invocations with the default `state_sync = "pull"`. Only the plain `"simulated"` demo
needs `state_sync = "push"` to persist, since its device is created fresh in memory
each time. On QM control PCs `"pull"` is mandatory — see LCHQMDriver's CLAUDE.md.

Other notes:
- A temporary alternative config can be selected per shell
  (PowerShell: `$env:SCQO_CONFIG = "path\to\other.toml"`; bash/zsh:
  `export SCQO_CONFIG=path/to/other.toml`) or per command with `--config`.
- A mistyped `$SCQO_CONFIG` **fails loudly** — it will not silently run unsaved.

## 3. Offline verification

The full test suite passes with no instrument attached (CI runs this exact suite on
Windows, macOS and Linux):

```bash
cd SCQO
python -m pytest -q        # expect: all passed
```

## 4. Self-test against your REAL device config (no hardware needed)

Before ever touching an instrument, verify the whole stack against your lab's actual
config files: each driver has a `check_real_config.py` that loads them, runs the full
pipeline with **simulated data over the real device tree** (read neutral fields → run
experiments → fit → write back → save in vendor format → reload and compare), and
prints PASS/FAIL. It works on a **temporary copy** — your originals are never opened
for writing, and nothing lands in your real data_root.

**Qblox** — works in the section-1 venv (the `-e ./LCHQBDriver` install brought
`qblox-scheduler`; the lab's `conda activate LCHQB` env works too). Point it at any
folder holding `dut_config*.json` + `hw_config*.json`:

```powershell
cd D:\github\LCHQBDriver
python scripts\check_real_config.py D:\qpu_data\SQ_demo\QBLOX_config
```

**QM / OPX1000** (needs the QM stack; lab: `conda activate LCHQM_test`). Point it at
any folder holding `state.json` + `wiring.json`:

```powershell
cd D:\github\LCHQMDriver
python scripts\check_real_config.py D:\qpu_data\SQ_demo\QM_OPX1000_config
```

Expected output: 5 numbered steps, each OK, ending in
`PASS - scqo works against this real config`. A qubit whose state is uncalibrated
(fields `None`) is skipped automatically; on the Qblox device the coupler (`c12`) is
excluded by the `q*` default — pass `--qubits` to choose explicitly. Both lab configs
passed on 2026-07-04 (and this test caught three real integration bugs before any
hardware time was spent — that's its job).

## 5. Install troubleshooting

| Symptom | Cause / fix |
|---|---|
| `ModuleNotFoundError: scqo` | venv not activated — Windows: `.venv\Scripts\Activate.ps1`; macOS/Linux: `source .venv/bin/activate` |
| `lab config not found` | your `--config`/`$SCQO_CONFIG` path is wrong (intentional loud failure — better than silently unsaved) |
| `# lab config: built-in defaults ...` in the catalog header | no `~\.scqo\config.toml` yet: runs work but are **not saved** — do section 2 |
| self-test: `missing package: qblox_scheduler` | install the driver into this env (section 1, second install line) or use the lab conda env |

Setup done → hand the machine to the student and point them at
[TUTORIAL.md](TUTORIAL.md).
