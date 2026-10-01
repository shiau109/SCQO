# qc_n_swap_tomography：重複 swap 後做雙比特 tomography

> 狀態：規格已核可（2026-10-01，使用者：§11 四點都照建議），同日實作並合併到 main。
> 硬體首測（同日）暴露兩個 frame 問題，修正後在 5Q4C 兩對 040 通過 §10 的比對，見 §12。
> 實作與硬體修正時改動的地方已寫進本文：§2 的序列、§3 的 `round_duration_ns` 與 `stark_operation`、
> §5 的 frame step、§6 的一致性門檻。
> 範圍：只設計一個實驗。在一對 qubit 上重複 N 次 partial swap（swap 之間照舊有 gap 與 stark 補償），
> 再對兩顆成員做雙比特 state tomography。從同一次 N 掃描讀出每步的交換角、每步的總相位與每步的
> 非相干誤差。
> 依據：
> - 5Q4C 2026-09-30 的 swap 校正，run 見 `procedures/pair-partial-swap`。
> - `scqo-qm/scqo_qm/experiments/qc_n_stark_amp.py`（本實驗沿用它的 round）與
>   `qubit_tomography.py`（沿用它的 pre-rotation 慣例）。
> - Monte Carlo：`scq-reports/scratch/swap_tomography_20261001/precision_mc2.py`。

## 0. 目的與不做的事

**一次 N 掃描要量到：**
1. **θ′**：每步交換角，也就是 chain 理論要用的角度。
2. **φ**：每步 swap 之間的總相位，也就是補償要抵消的量。
3. **每步非相干誤差**：兩顆成員各自的 T1 損失、合計的 dephasing、漏到 |11⟩ 的量。

**它取代的：** `pair-partial-swap` 的 Step 4，也就是 `qc_n_stark_amp` 那張 stark × N 二維圖。

**它不做的：** 找共振，也就是 detune = 0。這仍然交給 Step 3 的 `qc_swap_flux_stark`，理由見 §1.1。

## 1. 物理

### 1.1 detune 對角度是二階，對相位是一階

在單激發子空間 {|10⟩, |01⟩}（成員順序 high, low）裡，有 detune δ 的 swap 精確等於「角度稍小的赤道
swap，前後各夾一個相同的 Z」：

    exp(-i(δ/2·Z + J·X)·t) = Rz(β) · Rx(2θ′) · Rz(β),   sin θ′ = (J/Ω)·sin(Ωt),   Ω = √(J² + δ²/4)

證明：左邊是對稱矩陣（X、Z 都對稱），而 ZXZ 分解 Rz(a)Rx(b)Rz(c) 的轉置是 Rz(c)Rx(b)Rz(a)，所以 a = c。

後果：
- **對角度的影響是二階的。** 40 ns 脈衝下，θ′ ≈ θ·(1 − (δt/2)²/6)，1 MHz 只少 0.26%，而且跟角度大小
  無關。
- **對相位的影響是一階的。** 每步多出 2β ≈ δ·t_p，1 MHz 就是 0.25 rad。q3 在 swap 點約
  4.5–5 MHz/mV，所以 0.3 mV 的漂移就是每步約 0.35 rad。
- **任何 tomography 都分不開 detune 的 Z 和其他 Z**（見 §1.2）。所以本實驗不聲稱量到 detune。
  detune 只需要在校正和使用之間保持穩定。

### 1.2 每步的組合與 φ 的來源

每步的操作是 C = Rz(φ) · Rx(2θ′)。φ 是以下各項的總和：
- stark 相位，大約正比於 a²，其中 1.0 = 一整圈。
- frame 項：−Δ_idle·(T_round − t_p)。q2_q3 的 Δ ≈ 350 MHz，所以差一個 4 ns 就是 1.4 圈。
- detune 項：δ·t_p。
- z 脈衝邊緣與 flux 失真尾巴造成的動態相位。
- 兩顆成員的 drive frame 與實際頻率失配。

一個補償值就要抵消這整個總和。所以 φ 只在同一個 round 長度下有效，跟現在的補償值一樣。

### 1.3 為什麼要 tomography

只看 population 時，看到的是混在一起的 θ_eff，滿足 cos θ_eff = cos(φ/2)·cos θ′。要分開 θ′ 和 φ，
只能掃 stark 找最小值，這就是 `qc_n_stark_amp` 的做法。

雙軌 Bloch 向量 r(N) 在三維裡畫出一條軌跡，從軌跡可以同時得到每步旋轉的角度與轉軸：
- cos(ω/2) = cos θ′·cos(φ/2)
- 轉軸 ∝ (sin θ′·cos(φ/2), sin θ′·sin(φ/2), cos θ′·sin(φ/2))

所以任何一個 stark 值都能量到 φ，不必剛好在補償點上。

### 1.4 非相干誤差要用實體通道來擬合

Monte Carlo 證明，用「每步一個等向收縮因子」的簡化模型，在 φ ≠ 0 時會把 θ′ 拉偏：
- θ = 0.4 時偏 −6%
- θ = 0.126 時偏 −14% 到 −31%

原因有三：dephasing 只縮橫向分量；T1 把 population 移出子空間；兩顆成員的 T1 不同，會讓 Z 分量偏移。

所以模型改用實體通道。每步的順序是：C，接著 high 成員的 T1 損失 p_h，接著 low 成員的 T1 損失 p_l，
再加上合計的 dephasing λ。在同一組模擬上，這個模型無偏（見 §9）。

## 2. 序列（每一發，QM）

沿用 `qc_n_stark_amp` 的 round（物理上同一個 round），但 frame 的處理不同（§12）：

1. `reset(reset_type)`，作用在所有相關的 qubit，然後 `align()`。
2. **每發重設兩顆成員的 frame：** `reset_frame`、`reset_if_phase`（兩顆的 xy），再
   `reset_global_phase()`（含 upconverter），然後 `align()`。
3. control 成員做 `x180`，準備成 |10⟩ 或 |01⟩（看 control 是 high 還是 low），然後 `align()`。
4. 重複 N 次：swap macro `apply()`，接著 `wait(gap)`，接著
   `ctrl.xy.play("stark_detuned", amplitude_scale=a)`，然後 `align()`。
   - **不切頻率。** `stark_detuned` 把 50 MHz 失諧直接做進波形（`DragGaussianPulse`，alpha 0，
     包絡和 `stark` 相同，`quam_config/register_stark_detuned.py` 產生），和 `qc_n_stark_amp` 的
     `stark` + `update_frequency` 是同一個 tone。
   - `qc_n_stark_amp` 仍走原本的 `update_frequency` 路線、不重設相位，QUA 逐字不變。
6. **tomography pre-rotation**：兩顆成員同時做，沿用 `qubit_tomography` 的慣例——z 不做事，x 做
   `-y90`，y 做 `x90`。然後 `align()`。
7. 兩顆成員一起讀出（multiplexed），用 state discrimination。

**迴圈順序：** shots → stark amp → N → basis。basis 有 9 個，用 `for_each_` 加上 `switch_`。

**round 長度與 `qc_n_stark_amp` 完全相同。** gap 260 時是 368 ns，所以兩者的補償值可以直接比對。

**程式結構：** 把兩個 shell 共用的步驟 1–5 抽成 `scqo_qm/experiments/_pair_swap_round.py`。
`qc_n_stark_amp` 改用它之後，`generate_qua_script` 的輸出必須跟改之前逐字相同。

**順便修正一個小不一致：** `qc_n_stark_amp` 的 docstring 和欄位說明寫 gap 在「swap+stark 之後」，
但程式實際上是 swap → gap → stark。抽出共用程式時一併把說明改對，程式行為不變。

## 3. Parameters（SCQO）

> `stark_operation` 的預設是 `"stark_detuned"`：它必須把 `stark_detuning_hz` 做進自己的波形，否則 QM
> 端按名稱拒絕（§2、§12）。

`QcNSwapTomographyParameters(TargetSelection, AveragingParameters, QubitResetParameters, ReadoutModeParameters)`

| 欄位 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `swap_operation` | str | `"iswap"` | 重複的 pair 操作（跟 `qc_n_stark_amp` 相同） |
| `swap_counts` | list[int] | 0..10 | 必須包含 0，不可重複，至少 4 個 |
| `stark_amps` | list[float] | `[0.0]` | 每個 ≥ 0，不可重複；只有一個值時就不提出補償值 |
| `stark_operation` | str | `"stark"` | |
| `stark_detuning_hz` | float | 50e6 | |
| `operation_gap_ns` | int | 0 | QM 要求是 4 的倍數 |
| `drive_side` / `flux_side` | high \| low | `"low"` | QM 要求兩者都對到 vendor 的 control（跟 `qc_n_stark_amp` 相同） |
| `readout_mode` | average \| shot | `"average"` | |
| `readout_calibration_shots` | int | 1000 | §5 第 1 步的四態校正，每個態的發數；0 表示不做 |
| `round_duration_ns` | float \| None | None | 只用於分析：一個 round 的實際長度（5Q4C gap 260 時 368 ns），有它和兩顆成員量過的 T1/T2\* 才算 §5 的 `predicted_*` |

- basis 固定 9 個，不開放成參數。
- `num_averages` 就是每個 (a, N, basis) 的發數，建議值見 §9。

**拒絕的情況（在 probe 之前）：**
- `swap_counts` 缺 0、有重複、有負數，或少於 4 個。
- `stark_amps` 是空的、有重複，或有值不在 [0, 2) 內（與振幅 mixin 的中立邊界相同；一圈的上限仍由 procedure 把關）。
- `readout_calibration_shots` < 0，或 `round_duration_ns` ≤ 0。
- 目標不是 `qubit_pair`。
- QM 端另外拒絕：操作不存在；兩顆成員上缺 `x90` / `-y90`；control 上缺 `stark`；stark 振幅超出
  `check_amp_scale_window` 的範圍。
- Qblox：這個家族是 QM-only，跟 `qc_n_stark_amp` 相同，沒有 Qblox 的 probe。

## 4. 資料形狀（DatasetContract）

- **sweeps：** `("stark_amp", "swap_count", "basis")`。
  - `basis` 的 9 個 label 是 `"zz","zx","zy","xz","xx","xy","yz","yx","yy"`，第一個字母是 high 成員，
    跟 `joint_state` 的位數順序一致。
- **average 模式：** `joint_population`，形狀 (target, joint_state, stark_amp, swap_count, basis)。
- **shot 模式：** `state`，形狀 (target, member, stark_amp, swap_count, basis, shot_idx)。`estimate()`
  會先把它化成 joint 分佈，跟 `qc_n_stark_amp` 的做法一樣。
- **讀出校正：** 另存一個變數 `calibration_population`，形狀 (target, prepared_state, joint_state)。
  prepared_state 是 00 / 01 / 10 / 11，由兩顆成員的 x180 組合準備。
  - 這跟 `qubit_tomography` 的 training shots 一樣，需要一個自訂的 contract validate。

## 5. Estimator（scqat `qc_n_swap_tomography`）

每一對 qubit：

1. **讀出校正。** 用同一次 run 量到的 4×4 confusion matrix（包含兩顆成員之間的讀出串擾）去還原每個
   (a, N, basis) 的 joint 機率。
   - 如果 `readout_calibration_shots = 0`，改用兩顆成員存的 `fidelity_g` / `fidelity_e` 的乘積，並標記
     `readout_correction = "stored_product"`。
2. **線性反演。** 得到 15 個雙比特 Pauli 期望值與 ρ(N)（4×4）。
   - 報告 purity、p00 / p01 / p10 / p11、coherence ρ_{10,01}。
3. **每個 stark 值各自擬合實體通道。**
   - 參數：θ′、φ、a_off（最後一步的 Z 偏移）、p_h、p_l、λ，以及 p11 的增長率。
   - 擬合對象是特徵 [2Re c, −2Im c, ρ_1010, ρ_0101, ρ_0000]，用 shot noise 加權，作 least squares。
   - 初值：θ′ 取 N=1 的轉移量；φ 取橫向分量的方位角逐步增量（Kabsch）。
4. **跨 stark 值：**
   - φ(a) 先 unwrap，再求根，得到 `compensating_stark_amp`。有 3 個以上的點時用局部二次內插。根落在
     範圍外時標記 `compensation_extrapolated`。
   - θ′ 應該跟 a 無關。它們之間的離散度當作模型檢查。

**metadata 主要鍵：**
- 角度與相位：`theta_rad`、`theta_rad_err`（取最接近補償點的那個 stark 值，因為那裡最準）、
  `theta_spread_rad`、`theta_consistency_sigma`（各 stark 值的 θ′ 與報告值相差幾個合併標準誤差，取最大）、
  `theta_per_amp`、`phase_per_step_rad`、`phase_err_rad`、`frame_offset_rad`。
- 補償：`compensating_stark_amp`、`compensation_extrapolated`。
- 非相干：`t1_loss_per_step_high`、`t1_loss_per_step_low`、`dephasing_per_step`、`leak_to_11_per_step`。
- 與成員 T1/T2\* 的對照：`predicted_*`，由凍結快照裡兩顆成員的 `t1_s` / `t2_star_s` 和 round 長度算出，
  另有 `excess_dephasing_per_step`。
- 其他：`readout_correction`、`fit_rms`、`success`。

**圖：**
1. `bloch_swap_frame`：雙軌 Bloch 軌跡，扣掉每個 stark 值擬合出的 frame 轉動
   `a_off + N·frame_step`（swap frame，每一輪都是同一個 Rz(φ)Rx(2θ′)）。正視（y–z）：補償時是
   通過兩極的大圓；側視（x–z）：補償時是 x = 0 的鉛直線，φ 讓它往左或往右傾。資料點加擬合線。
2. `bloch_drive_frame`：同樣的向量，照 drive frame 原樣畫（xy、xz 投影）。每一點都疊了 frame
   轉動，所以是鋸齒狀；這是沒經過擬合的原始樣子。
3. 各分量、p_sub、p00、p11 對 N 的圖，附擬合。
4. φ 與 θ′ 對 stark 值的圖，標出根。

## 6. update()（寫回）

**寫回 `theta_rad` 到 `<pair>.<op>`**（operation 的 monitor，跟 `qc_n_stark_amp` 相同），條件是全部成立：
- outcome 是 SUCCESSFUL；
- 各 stark 值的 θ′ 都在報告值的 3 個合併標準誤差內（`theta_consistency_sigma` ≤ 3）。
  - 用 σ 而不用固定弧度：離補償點越遠，θ′ 定得越差。實作時發現原本的 max(2σ, 0.01 rad) 會擋掉正常的 run：
    a = 0 與 0.5 兩點的 θ′ 差 0.029 rad，但遠離補償點那點本身的誤差就大好幾倍。
- `fit_rms` ≤ 0.08（特徵值是 population 與 Bloch 分量，0.08 代表模型不對，不是 shot noise）；
- 這個操作有在 roster 宣告。

**不寫回的：**
- 補償值：它只對同一個 round 長度有效，`qc_n_stark_amp` 現在也不寫回。
- 非相干誤差：v1 只放在 `result.fit`（見 §11 第 3 點）。

## 7. simulate()

用跟 estimator 相同的實體通道產生資料：
- **θ：** 取操作的 `theta_rad` monitor；沒有的話用 0.3。
- **φ(a)：** φ₀ + 2π·a²，φ₀ 用固定種子隨機給。
- **T1 / T2\*：** 取兩顆成員的 fact；沒有的話用預設值。
- **讀出：** 取存的 fidelity，含四態校正區塊。
- **抽樣：** 以 multinomial 抽發數。種子用 `stable_seed`。

**離線來回測試：** 估出來的 θ′、φ、p_h、λ 要落在 §9 精度的 3σ 以內。

## 8. QM shell

- **self-acquiring**，跟 `qc_n_stark_amp` 相同：
  - 有 `preview_program()`，並加進 `test_preview.py` 的 `SELF_ACQUIRING`。
  - `probe()` 直接回傳 Dataset，並重排成 member = [high, low]。
- **stream：** `buffer(9).buffer(len(N)).buffer(len(a)).buffer(shots)`；校正區塊另外一條 stream。
- **reset_method：** 只支援 thermal。不加進 `CARRIERS`，要呼叫 `check_reset_method`。
- **註冊：** 在 `experiments/__init__.py` 加 import。這個 shell 不適用 `test_sequential_probe`。

## 9. 5Q4C 的數字與精度（Monte Carlo）

**條件：**
- q2_q3：high = q3，T1/T2\* = 22 / 12.4 µs；low = q2，T1/T2\* = 20 / 10 µs。
- 讀出 fidelity 用 2026-09-30 的值。
- round 368 ns（gap 260）。
- 每組條件模擬 20 次。
- 實際每步的 T1 損失是 high 0.0166、low 0.0182；合計 dephasing 約 0.049。

| θ | φ（rad/步） | N | 每 setting 發數 | σθ′ | σφ（rad） | T1 損失 high | dephasing |
|---|---|---|---|---|---|---|---|
| 0.126 | 0（已補償） | 0..12 | 200 | ±0.0033 | ±0.009 | ±0.003 | ±0.005 |
| 0.126 | 0 | 0..12 | 1000 | ±0.0013 | ±0.004 | ±0.0013 | ±0.002 |
| 0.126 | 1.3（未補償） | 0..12 | 1000 | ±0.0064 | ±0.010 | ±0.0006 | ±0.009 |
| 0.126 | 1.3 | 0..25 | 1000 | ±0.0043 | ±0.005 | ±0.0003 | ±0.004 |
| 0.4 | 0 | 0..6 | 200 | ±0.0043 | ±0.024 | ±0.012 | ±0.012 |
| 0.4 | 0 | 0..6 | 1000 | ±0.0016 | ±0.011 | ±0.006 | ±0.005 |
| 0.4 | 1.3 | 0..10 | 1000 | ±0.0066 | ±0.009 | ±0.002 | ±0.003 |

- 所有條件下平均值都沒有偏差：θ′、φ、p_h、λ 都落在真值的 1σ 內。
- low 成員的 T1 損失只有在已補償時才定得準（±0.003）；未補償時是 ±0.01–0.03。
- **角度要量在補償點附近。** 那裡的 σθ′ 比 `qc_n_stark_amp` 在 0.12 rad 的 ±2–3% 好一到兩倍。
- **φ 在任何 stark 值都準到約 0.01 rad。** 換成補償振幅，在 a ≈ 0.45 時約 ±0.002。
- **儀器時間：** 1000 發 × 9 settings × 13 個 N × 3 個 stark 值，每發約 0.31 ms（thermal），合計約 110 秒。
  `qc_n_stark_amp` 是 60–95 秒。

## 10. 驗證

**離線：**
- contract 與拒絕條件的測試。
- simulate → estimate 來回測試。
- `qc_n_stark_amp` 抽出共用 round 之後，QUA 輸出要逐字相同。
- scqat estimator 對 §9 模擬資料的測試。

**硬體（5Q4C，先照「頻率優先」把 qubit 和 coupler park 好）：**
1. **preview 與 simulator：** 確認 round 是 368 ns，basis 的 switch 正確。
2. **q2_q3 `partial_swap_040`，gap 260：**
   - 設定：`stark_amps` = [0.40, 0.45, 0.50]，N = 0..8，1000 發。
   - 同一段時間跑一次 `qc_n_stark_amp` 對照。
   - θ′ 要在 ±0.01 內一致。
   - 補償振幅要在 ±0.01 內一致。這是 §2 第 5 步 frame 處理正確與否的關鍵驗證。
3. **N=0：** 經讀出校正後，雙軌向量應該約為 (0, 0, 1)。p_sub 應該約等於 1 減去熱激發與準備誤差。
4. **非相干：**
   - 同一段時間跑 `qubit_relaxation`，比對兩顆成員的 T1 損失。
   - 用 Ramsey 的 T2\* 預測 dephasing，看量到的超出多少。
5. **小角度 `partial_swap_013`：** N = 0..14，在補償點附近量，比對 `qc_n_stark_amp` 的 0.1223。

## 11. 待你決定（附我的建議）

1. **名稱：** `qc_n_swap_tomography`。沿用 `qc_n_*` 家族，後綴是第二個軸。
2. **共用 round：** 建議抽出 `_pair_swap_round.py`，讓 `qc_n_stark_amp` 的 QUA 逐字不變。另一個選項是
   複製一份，但兩邊以後可能會分歧。
3. **非相干誤差要不要寫回裝置：** 建議 v1 只放在 `result.fit`。要寫回就得在 `catalog.py` 新增 operation
   monitor，屬於 shared core，得跑 full suite。
4. **讀出校正：** 建議在同一次 run 裡量 4×4 confusion matrix（§5 第 1 步）。它包含兩顆成員之間的讀出
   串擾，也不依賴已經過期的 single_shot_readout。代價是多 4 × 1000 發，約 1.2 秒。

## 12. 硬體首測與修正（5Q4C，2026-10-01）

**問題 1：每發的 frame 參考不同。** swap 產生的相干性在 lab frame 裡有固定相位，但 pre-rotation 用的是
兩顆成員各自的 drive frame，兩者在 swap 時的相對相位是 (f_high − f_low) × 該發的絕對開始時間。每發開始
時間都不同，橫向分量平均後只剩雜訊（|r⊥| 0.01–0.1），z 分量則乾淨。離線模擬每發用同一個 frame 偏移，
所以沒抓到。

**問題 2：相位重設和 `update_frequency` 不能混用。** 加上每發相位重設後，stark tone 變成共振打在 control
上（stark 0.91 時一次 swap 後 P(00) 0.54–0.61），相干性也沒回來。拿掉頻率切換（stark 振幅 0）做對照：
不重設時 |coh| 0.02–0.06，重設後 0.55–0.68。所以修法是 §2 的「每發重設 + 不切頻率 + `stark_detuned`」。

**問題 3：drive frame 每 round 轉一個 frame step β。** 即使每發都參考好，兩個 drive frame 之間每 round 仍
轉 β = 2π (f_high − f_low) T_round。量到的軌跡是 Rz(a + Nβ)·C^N·v₀，不是一個圓，原本的模型擬合不上
（rms 0.17–0.26）。模型加上 `frame_step` 後 rms 0.02–0.04；φ 則是在每 round 都是同一個交換的 frame 裡讀，
也就是 population 看到的那個，補償要歸零的就是它。β 也可以從 drive 頻率和 round 長度預測，當作 round
長度的檢查。

**驗證結果**（gap 260，N 0–8，每 setting 1000 發，run `20261001-200029-259`、`-200143-656`，以修正後的
estimator 重新擬合）：

| | θ′ | `qc_n_stark_amp` θ | 補償振幅 | `qc_n_stark_amp` 補償 | β 量測 / 預測 |
|---|---|---|---|---|---|
| q2_q3 040 | 0.4256 ± 0.0022 | 0.434 | 0.905 | 0.908 | −99.2° / −100.3° |
| q1_q2 040 | 0.4353 ± 0.0019 | 0.437 | 0.487 | 0.496 | +110.7° / +108.6° |

θ′ 與補償都在 §10 的 ±0.01 內。另外，q3 每步的 T1 損失 0.05–0.07，是它 T1 預測（0.017）的 3–4 倍，
而且隨 stark 振幅變大；q1 在較弱的 stark（0.45–0.5）下則和 T1 一致。強 stark tone 會額外把 q3 的
population 拉走，這是 population 型實驗看不到的資訊。
