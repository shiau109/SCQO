# 有隱藏真值的虛擬晶片 backend（暫名 `emulated`）— 實作計畫

狀態：**計畫，未實作**（2026-09-21）。整個功能落地後刪除本文件，內容移入 TUTORIAL / CLAUDE.md 的對應段落。
這是「自動量測」的測試台：之後的 runner / AI agent 要在它上面驗證；runner 本身不在本計畫內。

## 0. 要解決的事

現在的 simulated backend 為了讓 46 個實驗都能跑，把隱藏真值放在掃描窗口附近：resonator 的 dip 落在窗口中心
±15% 窗寬內、Rabi 的 π 點永遠是「目前 `pi_amp` × 0.85–1.15」、亂數種子固定。所以它**永遠命中，也永遠不收斂**
（Rabi accept 之後再跑一次，倍率還是一樣）。它能測程式流程，測不到「決策」：runner / agent 的失敗恢復、
estimator 在峰偏心或貼邊時的行為、一步的誤差傳到下一步。

目標：一顆有隱藏真值的單比特晶片（固定頻率 transmon + readout resonator）——

1. **所有實驗共用一個物理模型**，而且像 driver 一樣讀**目前的 knob**，算出實際打出去的頻率、功率、脈衝；
2. 真值有兩種來源：**情境一** = 真實樣品某個 context 的量測值；**情境二** = design（純理論，不需要樣品）；
3. 可重現、可評分（最後的 state 對真值）。

### 非目標（本計畫不做）

- 不取代 simulated：它繼續負責所有實驗的管線測試、CI、練習模式、scqo-agent 的 sim 部署。
- 不做 sequence IR。emulator 等於第三個 backend，但只為 bring-up 用到的實驗寫 adapter，而且它翻譯的是物理、
  不是 vendor 語法——「出現第三個 vendor 就重新評估 IR」的條件不適用。
- 不做 flux-tunable、pair、多比特串擾（§8）。
- 不改任何 scqat estimator，也不改兩個 driver。driver 之間的語意差異另記 `BACKLOG.md` I19。

## 1. 需要你拍板的決定（都附建議）

| # | 決定 | 建議 | 理由 |
|---|---|---|---|
| D1 | 家族名稱 | `emulated` | `virtual` 在這個系統已經是 virtual detuning / virtual Z；`twin` 已經是 fact twin、`stderr_twin`。`emulate` 在四個 repo 裡只出現在一處 scqat 的 docstring |
| D2 | 程式位置 | SCQO 新 package `scqo/emulated/` | 只用 numpy / scipy / xarray；不需要新 repo、新 venv，也不多一個 combo 成員。P1 幾乎全是新檔 |
| D3 | 語意以誰為準 | **catalog 的中立語意**；兩個 driver 不一致處照 catalog 做，差異記 BACKLOG I19 | 例：Ramsey 的 π/2 在 QM 用 `pi_amp_x90`、在 Qblox 用 `pi_amp/2`（§2）。emulator 只能選一種，選 catalog 定義的那種，它因此也成為中立語意的參考實作 |
| D4 | 能階數 | 3 能階（0、1、2）Lindblad | α、f01+α/2 的雙光子峰、1→2 躍遷、強脈衝的洩漏都會自動出現；9×9 superoperator 的 `expm` 成本可忽略 |
| D5 | readout / drive 鏈 | emulator 自己的 channel view：**固定 full scale、power ↔ amp 一對一換算**，寫一邊另一邊跟著動 | 不耦合的話，`qubit_spectroscopy` 的 `drive_power_dbm` set→revert 改不到 probe 實際播放的 `drive_amp`；`readout_power` 寫回的 `readout_amp` 也影響不到 `resonator_spectroscopy`。耦合後 `_sync_coupled` 會像硬體一樣記下 coupled 回聲。QM 的粗調階梯（讓 `pi_amp` 的物理意義隨 `drive_power_dbm` 漂移）留到 P3 |
| D6 | 每個 run 記錄用了哪份真值 | backend 的 `versions()` 回傳 `{"scqo-emulated-truth": <digest>}` | 進 `record.versions` 與 `dataset.nc` attrs，零 core 改動。若改用 `vendor_config_snapshot()`，整個 `backend_config/`（含真值檔）會被複製進 `setup_snapshots/`，agent 就讀得到答案 |
| D7 | 產生器入口 | Python API ＋ `python -m scqo.emulated`；要不要升成 `scqo` 子命令，等用過再決定 | 和 `python -m scqo.browse` / `scqo.viewer` 同一先例，不碰「`scqo run` 是唯一入口」 |
| D8 | scipy | 在 SCQO 的 `pyproject.toml` 直接宣告 | 已透過 scqat 裝在每個 venv（SCQO venv 是 1.18）；`scipy.linalg.expm` 對非正規矩陣比 numpy 特徵分解穩。這是 `scqo/` 第一次直接用 scipy |

## 2. 現況（都已對照程式碼查證）

**simulated 為什麼不能直接用**
- `SimulatedBackend.acquire` 只呼叫 `experiment.simulate(sweep)`，而 `simulate()` 從不讀 device：真值由窗口加
  `stable_seed(實驗名, targets)` 決定（例：`resonator_spectroscopy.py:108-127`）。真值檔影響不了它，emulator 必須
  自己實作 `acquire`。
- IQ 平面的位置也是各實驗自己擲亂數（`_sim.iq_from_population`），彼此不一致；relaxation 與 echo 各自擲 T1 與
  T2e，連 T2e ≤ 2·T1 都不保證。

**要動到的地方**
- 家族清單是封閉的：`SETUP_BACKENDS = ("qblox", "qm", "simulated")`（`datastore.py:79`），driver 的 entry
  point 也必須先列在這裡。`load_cooldowns` 只對 simulated 不注入 `instrument_config`（`datastore.py:1334-1338`），
  所以 emulated 會自動有 `<cid>/<setup>/backend_config/`，正好放真值檔。
- 其他寫死家族的地方：`cli/_backends.py`（`SERVED_BY`；`build_session` 的 simulated 分支；`_demo_session` 寫死
  `backend_label="simulated"`）、`labconfig.py:259/285`（push 只准 simulated，而且強制）、`cli/doctor.py`
  （`:70`；`:77` 的 `VENDOR_CONFIG_FILES[backend]` 沒有條目會 KeyError；`:86`；`:92`）、`datastore.py:89`
  `VENDOR_CONFIG_FILES`、`cli/device.py:67/72` 的骨架註解。**沒有測試釘住這些清單的內容。**
- `scqo restore` 照抄 record 的 backend 標籤，emulated 不用改就能用。

**可以直接沿用的**
- simulated 在強制 push 下：knob 只經 `scqo_state.json` + `history.sqlite` 持久化，`InMemoryDevice.save()` 不做事，
  setup snapshot 為 `{}`。emulated 沿用這套，knob 不需要自己的 vendor 檔。
- `Session` 接受任意 `backend_label`：`Session(EmulatedBackend(...), backend_label="emulated", state_sync="push")`
  不動家族清單就能測（`tests/test_model_run.py:17-26` 是同一種寫法）。**所以 P1 可以只加新檔。**
- 讀另一個 context：`load_cooldowns` / `resolve_setup` / `setup_scqo_dir`（`datastore.py`）、`ChangeDB` 的讀取方法
  唯讀且不建檔、`provenance.live_sources` 對每個欄位給 status / run_id / timestamp。**注意** `stores.py` 的建構子
  會把非 schema 3 的檔案改名，不是嚴格唯讀，所以產生器直接讀 JSON（同 viewer，`viewer/app.py:74-81`）。

**真值檔要用的 catalog 名稱**
- transmon facts：`f_01_hz`、`anharmonicity_hz`、`ec_hz`、`t1_s`、`t2_star_s`、`t2_echo_s`、`n_th`（還有
  `parity_rate_hz` 等本計畫用不到的）。
- resonator facts：`f_bare_hz`、`f_dress0_hz`、`f_dress1_hz`、`kappa_tot_hz`、`g_hz`、`g_coeff`、`chi_hz`
  （定義為 `(f_dress0_hz − f_dress1_hz) / 2`）。
- design-legal：transmon `f_01_hz` / `anharmonicity_hz` / `ec_hz` / `gap_delta_hz`；resonator `f_bare_hz` /
  `f_dress0_hz` / `kappa_tot_hz` / `g_hz` / `g_coeff`。channel knob 都沒有 design：`drive_freq_hz` 由 `f_01_hz` 播種，
  `readout_freq_hz` 由 `f_dress0_hz` 播種。

**功率語意**
- `readout_power_dbm` / `drive_power_dbm` 是**儀器 output port 的絕對功率**（portable）。硬體寫入時會重解鏈，
  把 `readout_amp` / `drive_amp` 當 coupled change 記下；只寫 amp 時 power 也會跟著動。
- `pi_amp`（和 `pi_amp_x90`）與 `drive_amp` 共用同一條 drive 鏈。
- simulated 的 in-memory device 兩者不耦合（`testing.py:162-164`），種子值（readout 0.08 / −30 dBm、drive
  0.05 / −13 dBm）也對不上任何一種鏈。

**第一步六個實驗的取數語意**（兩個 driver 的共同部分）

| 實驗 | 掃描軸（預設） | 每個 shot 的序列 | 讀的 knob | 寫回 |
|---|---|---|---|---|
| `resonator_spectroscopy` | `detuning_hz` −10…+10 MHz、101 點，相對 `readout_freq_hz` | 只有 readout（不 reset、不 drive） | `readout_freq_hz`、常駐 readout 脈衝的 amp / duration / integration | `readout_freq_hz`、`f_dress0_hz`、`kappa_tot_hz`、`readout_depletion_s` |
| `qubit_spectroscopy` | `detuning_hz` −30…+30 MHz、201 點，相對 `drive_freq_hz` | reset → 飽和脈衝 `drive_len_ns`（20 µs）→ readout（drive 已關） | `drive_freq_hz`；`drive_power_dbm` 由 Parameter（−25 dBm）在 `run()` 的 boundary 內暫時寫入、事後還原 | `drive_freq_hz`、`f_01_hz` |
| `qubit_power_rabi` | `amp_prefactor` 0…1.9 × `pi_amp`、101 點 | reset → x180（振幅 a·`pi_amp`、長度 `pi_duration_s`）→ readout | `pi_amp`、`pi_duration_s` | `pi_amp` = 舊值 × 最佳**格點** |
| `qubit_ramsey` | `idle_time_ns` 16…3916 ns、101 點；δ = 1 MHz | reset → π/2 → idle τ → 相位 −2πδτ 的 π/2 → readout（負號兩個 driver 相同） | `drive_freq_hz`、π/2 的 knob（見下） | `drive_freq_hz` = 舊值 + (條紋頻率 − δ)、`f_01_hz`、`t2_star_s` |
| `qubit_relaxation` | `wait_time_ns` 16…200 000 ns、51 點（線性） | reset → x180 → wait → readout | `pi_amp`、`pi_duration_s` | `t1_s`、`thermalization_time_s` = 10·T1 |
| `qubit_echo` | 總 idle 32…400 000 ns、51 點（線性） | reset → x90 → τ/2 → x180 → τ/2 → x90 → readout | x180 與 π/2 的 knob | `t2_echo_s` |

共通：平均是外層迴圈；`num_averages` 預設 100；四個時域實驗可選 `use_state_discrimination`（輸出 `population`）與
`reset_method="active"`；`qubit_spectroscopy` 另有 `readout_overlap`。

**driver 之間的不一致**（emulator 照 catalog 做；差異記在 BACKLOG I19）
- Ramsey / echo 的 π/2：QM 是 `y90`（Ramsey 的第一個）＋ `pi_amp_x90` ＋ vendor 專屬的 x90 長度；Qblox 是 `X90` =
  `pi_amp/2` ＋ `pi_duration_s`（`pi_amp_x90` 在 Qblox 是 Unrealized）。
- 時間座標：QM 存實際落在格點上的時間，Qblox 存名目軸值。
- Rabi 振幅上限：Qblox 擋 factor × `pi_amp` > 1，QM 只擋 factor ≥ 2（CLAUDE.md 說兩邊都擋前者）。
- `resonator_spectroscopy` 的 shot 間隔：QM 等 `readout_depletion_s`，Qblox 寫死 10 µs；它的 `readout_amplitude`
  參數兩個 driver 都沒讀。
- `reset_wait_ns` 的邊界規則兩個 driver 都沒照做。
- 沒有任何基本 bring-up 步驟校 `pi_amp_x90`（只有 QM 上的 `qubit_deterministic_benchmarking`）。

## 3. 設計

### 3.1 兩個情境、一個 backend

```
情境一：真實樣品的 context（device / cooldown / setup）──┐
                                                        ├─ 產生器 ─→ truth.toml（固定）─→ emulated backend ─→ run
情境二：design.toml ────────────────────────────────────┘
```

- backend 只讀真值檔，不知道、也不在乎真值從哪裡來。
- 真值檔**產生一次就固定**。session 啟動時不重讀 `physical.json` / `design.toml`；否則真實樣品一有新量測、或有人改了
  datasheet，虛擬晶片就在測試途中變了。
- 重新產生是明確的動作：舊檔改名為 `truth-<digest8>.toml` 留在原處，所以任何 run 的 `versions` 裡的 digest 都找得到
  對應的真值。

### 3.2 真值檔 `truth.toml`

位置：`<data_root>/<device>/<cid>/<setup>/backend_config/truth.toml`（emulated 的 `backend_config/` 由
`load_cooldowns` 注入）。只放**獨立**參數；dressed 頻率、χ、n_crit 等由 backend 推導，不重複存。

```toml
schema = 1
seed = 20260921                      # 雜訊種子
generated = "2026-09-21T15:00:00+08:00"
source = { kind = "design" }         # 情境一：{ kind = "context", device = "chipA", cooldown = "cd1", setup = "qblox" }

[q1]                                 # roster 名稱、catalog 欄位名
f_01_hz = 4.73e9
anharmonicity_hz = -2.0e8
t1_s = 5.0e-5
t2_echo_s = 6.0e-5
t2_star_s = 3.0e-5
n_th = 0.01

[q1_res]
f_bare_hz = 5.9375e9                 # 由 design 的 f_dress0_hz = 5.94e9 反推
g_hz = 5.5e7
kappa_tot_hz = 5.0e5
kappa_ext_fraction = 0.8             # emulator 專屬：notch 的深度

# emulator 專屬：儀器鏈與雜訊（不是 catalog 欄位）。數值只是示意，P1 依 §3.3 的原則定案
[chain]
drive_full_scale_dbm = 10.0          # amp = 1 對應的 port 功率（D5）
drive_rabi_hz_at_full_scale = 2.0e8  # amp = 1、常數包絡時的 Rabi 頻率
readout_full_scale_dbm = -10.0
readout_signal_at_full_scale = 1.0   # IQ 訊號尺度（任意單位）
readout_noise_per_shot = 0.03        # 單發 IQ 雜訊 σ，於 readout_integration_ref_s
readout_integration_ref_s = 1.0e-6
iq_phase_rad = 0.7                   # IQ 平面的整體旋轉

[provenance]                         # 每個欄位的來源
"q1.f_01_hz" = "design"
"q1.t1_s" = "default"
"q1_res.f_bare_hz" = "derived: f_dress0_hz, g_hz, f_01_hz, anharmonicity_hz (design)"
# 情境一的量測值："measured: cd1/qblox run 20260710-..."
```

驗證（產生與載入時都做，違反就指名拒絕）：T2* ≤ T2E ≤ 2·T1；0 ≤ n_th < 0.5；κ、g > 0；0 < `kappa_ext_fraction` ≤ 1；
色散條件 |Δ|/g 太小時警告。

### 3.3 產生器

每個欄位依序取值，前面沒有才往後：**手動覆寫 > 量測值（指定的 context）> design > 內建預設**。
情境二只是「沒有量測值」的特例。這和 `Experiment.fact_sourced()` 的 measured → design → default 是同一條規則。

**情境一（`source = context`）**
- 讀指定 context 的 `physical.json`、`scqo_state.json`（直接讀 JSON）和 `live_sources`；每個量測值的 run_id 寫進
  provenance。
- **觀測量優先**：`f_dress0_hz`、`f_01_hz`、`kappa_tot_hz` 原樣保留，`f_bare_hz` 由模型反推。g 依序取：量到的
  `g_hz` → 由量到的 `chi_hz` 反推 → design 的 `g_hz` / `g_coeff` → 預設。α 沒量過時用 design，再不行用
  α ≈ −`ec_hz`。
- 量測值之間不一定自洽（例：punchout 量到的 `f_bare_hz` 和由 `f_dress0_hz` 反推的不同）。產生器列出殘差表；
  這張表本身也是對量測的一種檢查。
- knob 也是量測結果：provenance 為 run 的 `pi_amp` 決定 emulator 的 drive 耦合，讓這個值恰好是 π。P1 的 full scale
  用 emulator 預設；之後可以從產生該值的 run 的 `power_context` 取真實鏈值。P2 起 `pos_*` / `fidelity_*` 決定 IQ
  幾何與雜訊。
- 初始 knob 兩種：`design`（**預設**；預演 bring-up，答案已知）或 `source`（照抄真實 setup 的 knob；預測「現在跑 X
  會看到什麼」，也可以比對同 knob 下的虛擬與真實 dataset，檢查模型像不像）。
- **monitor 永遠不抄**：`pos_*` 是真實 readout 鏈的座標。抄過來的話，`qubit_spectroscopy` 與 Rabi 附加的
  `ref_pos_*` 會和 emulator 的 IQ 座標系不一致（scqat 量的是 |IQ − ground point|）。
- 虛擬晶片是**獨立的 device**，真值檔記下來源；不要當成來源 device 底下的 setup，否則模擬值會混進來源 device 的跨
  setup 比較與 lab report。
- 來源 context 只讀不寫。
- chipA 的現況見 BACKLOG I18：`cd1/qblox_q2` 存的是另一顆 qubit、design.toml 可疑 → 情境一從 `cd1/qblox` 或
  `cd1/qm_OPX1000` 取。

**情境二（`source = design`）**
- design ＋ 預設；可選逐欄手動覆寫，以及（P3）有 seed 的製程偏差 `scatter`。
- 要測 estimator 在峰偏心、貼邊、低 SNR 時的反應，可以覆寫真值，也可以用 `scqo set` 把 knob 設偏——數據只取決於
  「真值和 knob 的差」，兩種效果相同。

**預設值的選法**：讓標準流程從初始 knob 出發**可行**。
- 真正的 π amp 落在初始 `pi_amp` 的 Rabi 預設窗口（0–1.9 倍）內，例如 1.25 倍；
- −25 dBm 的 spectroscopy 線寬約數 MHz（60 MHz 窗口、201 點看得到），雙光子峰在窗口外；
- 預設 readout 功率下單發 SNR 約 2–3，平均 100 次後約 20。

情境二的 closed-loop 測試（§5）就是這組預設的驗收。預設值集中在一處並逐一附理由。

**入口**（D7）：`scqo.emulated.generate(...)` 與

```
python -m scqo.emulated init --device <twin> --setup <name> --from design
python -m scqo.emulated init --device <twin> --setup <name> --from context:chipA/cd1/qblox [--knobs design|source]
                             [--seed N] [--set q1.t1_s=1e-4 ...]
```

device 資料夾（`components.toml` / `design.toml` / `cooldowns.toml` 的 emulated setup）P1 先手動建；要不要由產生器
代建，用過再決定。

### 3.4 Backend

- `EmulatedBackend(device, truth, *, seed)`。**不繼承** `SimulatedBackend`（免得繼承到 `simulate()` 路徑與寫著
  "simulated" 的 preview 拒絕訊息）。
- `acquire(experiment)` 依註冊名分派到 adapter。
  - 沒有 adapter 的實驗 → 指名拒絕，並列出已實作的實驗。
  - P1 不支援的讀取形式同樣指名拒絕：`use_state_discrimination=True`、`reset_method="active"`、
    `readout_overlap=True`。
  - **絕不靜默退回佔位數據。**
- 資料組裝：adapter 回傳和 `simulate()` 同形狀的 dict。把 `SimulatedBackend.acquire` 裡組裝 `xr.Dataset` 的約 20
  行抽成 `testing.py` 的共用函式（行為不變），兩個 backend 共用。
- 裝置：`EmulatedDevice`（`InMemoryDevice` 子類）＋耦合的 drive / readout channel view（D5）。
  - 初始 knob = design 種子（`seed_value`）＋ emulator 預設；成對的 power / amp 依固定 full scale 一致化。
  - push 時 catalog 先推 amp 再推 power，所以 power 為準，和硬體相同。
- 雜訊：`default_rng([truth.seed, acquisition_index])`。
  - P1 的序號只在行程內累加。
  - P1b 起序號存在 `backend_config/emulator_state.json`：CLI 每次 run 的雜訊不同（campaign 統計才有真實散佈；
    simulated 的 std 永遠是 0），但從同一份初始狀態重跑整段流程會得到相同結果。
- `versions()` 回傳真值 digest（D6）；`preview()` 指名拒絕。

### 3.5 物理模型

**共振腔**
- notch 響應：S21(f) = 1 − κ_ext/κ / (1 + 2i(f − f_r|j)/κ)，j 是 qubit 能階。
- 多能階色散（Koch et al. 2007）：Δ = f01 − f_bare，χ01 = g²/Δ，χ12 = 2g²/(Δ + α)；
  f_r|0 = f_bare − χ01，f_r|1 = f_bare + χ01 − χ12。catalog 的 `chi_hz` = (f_r|0 − f_r|1)/2。
- 以 §3.2 的範例參數：f_bare ≈ 5.9375 GHz（Lamb shift ≈ 2.5 MHz）、`chi_hz` ≈ +0.36 MHz、
  n_crit = (Δ/2g)² ≈ 120。
- P1 取低功率極限（與功率無關）；P2 加光子數、punchout（dressed → bare）、Kerr。

**Qubit**
- 3 能階，驅動頻率的旋轉座標 ＋ RWA。
- Lindblad：
  - T1 含 n_th 的向上速率，使靜態分佈 = 熱分佈；
  - 白雜訊 Tφ；
  - 準靜態失諧 σ，用 Gauss–Hermite 節點平均。
- 由真值換算：Γφ = 1/T2E − 1/(2·T1)；σ 取使 Ramsey 包絡 e^(−t/T2E)·e^(−(2πσt)²/2) 在 t = T2* 時等於 1/e。
  echo 會自動抵消準靜態項，所以 T2E > T2* 自然出現。
- 注意：estimator 用指數模型擬合這個包絡，擬合出的 T2* 不會正好等於真值，容差要涵蓋（§3.7）。

**脈衝**
- 分段常數傳播子，每段一次 `expm(L·t)`（9×9）。
- P1 用矩形包絡，面積等於 cosine 包絡（A·T/2）；不模擬 DRAG（`drag_beta` 在 P1 不影響物理，文件寫明）。
- x180 = `pi_amp`、`pi_duration_s`；x90 = `pi_amp_x90`、`pi_duration_s`。這是 catalog 語意（D3）：catalog 有獨立的
  `pi_amp_x90`，但沒有 x90 長度的欄位。
- Ramsey 的虛擬失諧實作為第二個 π/2 的相位 −2πδτ。條紋頻率因此是 |f01 − f_d + δ|，也會重現「f01 < f_d − δ 時修正
  方向反轉」的真實陷阱。

**每個 shot 的起點**：熱分佈（1 − n_th, n_th, 0）。P1 假設 reset 夠長；P3 加入「reset 等待不足 → 殘餘激發」。

**Readout**
- 平均 IQ：z = A_ro·G·e^(iθ)·Σ_j p_j·S21(f_ro; f_r|j) ＋ 雜訊 N(0, σ²/N_avg)。
- σ ∝ 1/√`readout_integration_s`；A_ro 由 readout 功率經固定 full scale 決定（P1 只影響 SNR）。
- P2：shot 模式（Gaussian blobs）、用 `readout_rotation_rad` / `readout_threshold` 判別、readout 期間的 T1 衰減。

### 3.6 第一步的六個 adapter

| 實驗 | adapter 做的事 | 注意 |
|---|---|---|
| `resonator_spectroscopy` | f_ro = `readout_freq_hz` + detuning；qubit 在熱分佈；只算 readout | `readout_amplitude` 兩個 driver 都忽略 → emulator 也忽略，並在 docstring 寫明（I19） |
| `qubit_spectroscopy` | f_d = `drive_freq_hz` + detuning；3 能階在 `drive_len_ns` 的飽和脈衝下演化（暫態，不假設穩態）；drive 關掉後 readout | 讀取時 `drive_power_dbm` 就是 boundary 寫入的 Parameter 值；強功率時 f01+α/2 的雙光子峰自動出現 |
| `qubit_power_rabi` | 每個 a：x180 振幅 a·`pi_amp` | factor × `pi_amp` > 1 指名拒絕（catalog 的規則） |
| `qubit_ramsey` | π/2 – τ – π/2（相位 −2πδτ） | 時間座標用名目軸；QM 的格點化記在 I19 |
| `qubit_relaxation` | x180 – τ – readout | |
| `qubit_echo` | x90 – τ/2 – x180 – τ/2 – x90 | 終態回到 \|0⟩：population 由約 0 升到 0.5（simulate() 是 1 → 0）；estimator 的 a·e^(−t/τ)+c 兩種都能擬合 |

每個 adapter 的 docstring 指名它實作的中立語意，以及兩個 driver 在這裡的差異。

### 3.7 評分

`scqo.emulated.score(truth, physical, state) -> rows`：
- 每個 fact（`f_01_hz`、`f_dress0_hz`、`kappa_tot_hz`、`t1_s`、`t2_star_s`、`t2_echo_s`…）與真值比；
- 每個 knob 與它的「理想值」比（`drive_freq_hz` = f01、`pi_amp` = 真正的 π amp、`readout_freq_hz` = f_r|0、
  `thermalization_time_s` = 10·T1）；
- 給絕對 / 相對誤差與容差判定。

初步容差：頻率在 Ramsey 之後 < 50 kHz、`pi_amp` 在 1 個 Rabi 格點內、T1 / T2 在 ±15% 內（擬合模型差異加雜訊）；
P1 定案。用於測試，之後用來評估 runner / agent。

## 4. 逐檔變更

**P1**（新檔為主；不碰另一個 session 正在改的檔案）
- 新：
  - `scqo/emulated/__init__.py`
  - `truth.py`：schema、載入、驗證、推導量
  - `generate.py`：兩種來源、優先序、provenance、殘差
  - `physics.py`：共振腔、3 能階 Lindblad、readout
  - `device.py`：耦合的 channel view
  - `adapters.py`：六個實驗
  - `backend.py`、`score.py`
  - `__main__.py`：`python -m scqo.emulated`
- 改：`scqo/testing.py`（抽出 dataset 組裝函式，行為不變）、`pyproject.toml` ＋ `uv.lock`（scipy，D8）。
- 測試：`tests/test_emulated_physics.py`、`test_emulated_truth.py`、`test_emulated_backend.py`、
  `test_emulated_bringup.py`。

**P1b 接上 CLI**（會碰共用檔，開工前對 SCQO 跑 `git status`）
- `datastore.py`：`SETUP_BACKENDS`、`VENDOR_CONFIG_FILES`（emulated 對應 `truth.toml`）。
- `cli/_backends.py`：`SERVED_BY`、`build_session` 分支、emulated 的 session 建構（讀 `instrument_config/truth.toml`，
  缺檔指名拒絕）。
- `labconfig.py`：push 規則改成「simulated 與 emulated 都強制 push」。
- `cli/doctor.py`：兩處分支 ＋ truth.toml 檢查；`cli/device.py` 的骨架註解。
- 測試：`test_labconfig.py`（emulated 版的 push 測試）、`test_cli_backends.py`、`test_cli_doctor.py` 各加 case。
- 文件：CLAUDE.md 的 package layout 加 2–3 行（只寫結構，不寫 changelog）、TUTORIAL 新段、INSTALL 的家族清單。

**不改**：scqat、scqo-qm、scqo-qblox。落地後寫一個 `RELEASES.d/emulated-backend.toml` 片段（additive）；不自行發版。

## 5. 測試

1. **物理單元測試**（對照解析解）：
   - 兩能階極限的 Rabi 週期；
   - 飽和穩態 ρ_ee = ½·s/(1 + s + (2πδ·T2)²)，s = (2πΩ)²·T1·T2（長脈衝極限）；
   - Ramsey 條紋頻率 |f01 − f_d + δ| 與負號；
   - T1 衰減；echo 抵消準靜態失諧；靜態分佈 = n_th；
   - 色散公式對照 Jaynes–Cummings 直接對角化（範例參數下誤差在幾 % 內）。
2. **真值 / 產生器**：
   - 優先序、provenance、固定（重新產生時舊檔保留）、驗證的指名拒絕；
   - 情境一用 `tmp_path` 造出的 context（`physical.json` + `scqo_state.json` + `history.sqlite`）；
   - 殘差表、monitor 不抄、來源 context 未被寫入。
3. **backend**：
   - 未實作的實驗與讀取形式指名拒絕；
   - 雜訊可重現（同 seed、同序號），不同 run 則不同；
   - 耦合 view 的 coupled 回聲進 history；digest 進 `record.versions`。
4. **closed-loop 驗收**（情境二、真值 = design）：
   - 依序跑六步；
   - 「Rabi 再跑一次，倍率在 1 ± 一個格點內」；
   - 一次長窗口 Ramsey（δ = 50 kHz、idle 到 200 µs，同 `stability.toml`）；
   - `score()` 全部在容差內；
   - 另加一個 f01 手動偏 +20 MHz（仍在窗口內）的案例，也要收斂。
5. **I17 重現**（P3）：T1 大於窗口 / 4、dip 貼邊等「estimator 應該失敗卻報成功」的案例。
6. **既有測試不受影響**：simulated 沒動；`testing.py` 的抽取跑一次完整的 `tests/test_model_experiments.py` 確認。

指令：
- 局部：`uv run pytest tests/test_emulated_physics.py tests/test_emulated_truth.py tests/test_emulated_backend.py tests/test_emulated_bringup.py -q`
- 改到 `testing.py` 時加跑：`uv run pytest tests/test_model_experiments.py -q`
- P1b 加跑：`test_labconfig.py`、`test_cli_backends.py`、`test_cli_doctor.py`、`test_datastore.py`

## 6. 分階段

| 階段 | 內容 | 驗收 |
|---|---|---|
| **P1 核心** | §3.1–3.7、六個 adapter、測試 1–4 與 6 | closed-loop 驗收通過；在 Python 裡用 `Session(EmulatedBackend(...))` |
| **P1b CLI** | §4 的 P1b | 在 `backend = "emulated"` 的 setup 上用 `scqo run` 跑完六步；`scqo doctor` 綠 |
| **P2 readout** | 功率相依（光子數、punchout）；shot 模式與判別；readout 期間的 T1；`readout_overlap` 的 AC Stark；由 `pos_*` 推導 IQ 幾何。adapter：`resonator_spectroscopy_power_amp`、`readout_frequency`、`readout_power`、`single_shot_readout`（順帶 `single_shot_readout_gef`、`qubit_thermal_population`） | 含 readout 最佳化的完整 bring-up closed-loop 通過 |
| **P3 偏差與故障** | `scatter`；兩個 `broadband_*` adapter；故障注入（壞 qubit、resonator 撞頻、TLS、reset 太短、drift 與虛擬時鐘）；QM 式粗調階梯；I17 測試；（選配）由 SCQ.jl 產生真值 | runner 在有偏差的晶片上可以量化成功率 |

P1 不依賴 P1b，可以先落地；P2、P3 各自獨立。

## 7. 風險

- **parity 漂移**：driver 改了序列，emulator 要跟著改。緩解：adapter 的 docstring 指名它對應的中立語意；Ramsey
  符號等慣例用測試釘住；I19 的差異修好時同步調整。
- **過度相信模型**：矩形脈衝、無 DRAG、色散近似、低功率極限。不要依 emulator 的特性去調 estimator。
- **預設值不現實**，會讓情境二的結論失真。緩解：預設值集中一處、附理由；情境一可以拿真實量測對照。
- **estimator 的缺陷會在 emulator 上現形**（例如 I17）：這是預期，測試要揭露而不是繞開。
- **多 agent**：2026-09-21 另一個 session 正在修改 SCQO 的 `CLAUDE.md`、`scqo/experiments/__init__.py`、
  `_capabilities/amplitude.py` 等檔案。P1 不碰它們；P1b 的 CLAUDE.md 更新要等那些變更 commit 之後。開工前對
  SCQO 跑 `git status`，重疊的檔案走 worktree。
- 產生器只寫目標 device 的 `backend_config/`；來源 context 唯讀。

## 8. 延後（落地時寫進 BACKLOG.md）

- flux-tunable、pair、多比特與串擾。
- runner / agent 本身。本計畫只做它們要用的晶片；P1b 之後 scqo-agent 的 sim 部署可以改指向 emulated setup。
- 標準 bring-up 缺一個校 `pi_amp_x90` 的步驟（I19）；emulator 上的 Ramsey / echo 會因此對比度偏低，但頻率與衰減
  擬合不受影響。
- 真值檔和 SCQ.jl 的雙向橋接。
