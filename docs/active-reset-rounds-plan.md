# 固定 N 輪 active reset 的逐輪測試：`qubit_active_reset_rounds`

> 狀態：規格草稿（2026-09-30），待核可；尚未動任何程式。
> 範圍：一個新實驗，兩個 backend 播同一個序列。設計以 Qblox 做得到的為準。
> 依據：
> - 模型與 5Q4C 的輸入：scq-reports `reports/active_reset_error_model_20260930`（commit 06e5da6）。
> - 兩邊現有的 active reset：
>   - scqo-qm `experiments/_reset.py`，以及 QUAM 的 `reset_qubit_active`（quam_builder `base_transmon.py:275`）；
>   - scqo-qblox `experiments/_reset.py`，以及 qblox-scheduler 的 `ConditionalReset`。
> - 逐次讀取的前例：`qubit_parity_switch_discrete`（三個 repo）。
> - 本文的預測數字由 `scq-reports/scratch/active_reset_rounds_predictions.py` 算出（gitignored，本機）。

## 0. 已定（使用者 2026-09-30）

1. **另開一個實驗**，專門測 active reset 的表現隨輪數 N 的變化，不改動現有 carrier 的 reset。
2. **以 Qblox 做得到的為準：**
   - 固定 N 輪、一個門檻；
   - 每次讀取只記判定（0/1）。
   QM 版照同一套做，不多記 I。
3. **不做 QM 限定的離線「最多 N 輪」模擬**（評估時的 (d)），移到 §10。

## 1. 設計理由

- **一次 run 就拿到整條曲線。** 固定 N 時，第 m 次讀取（`meas_idx = m`）量到的是 m 輪之後的狀態。所以一次
  N = 10 的 run 就涵蓋 m = 0–10，不必掃 N。這只在固定 N 成立：「最多 N 輪」會中途離開，後面的讀取就不存在了。
- **要看的三個特徵**（模型見 scq-reports 報告）：
  - (a) 從第 4 次讀取起停在同一個下限，三種 prep 的下限一樣。
  - (b) 下限由讀取的 ε_g 決定：讀錯成 e 的 |g⟩ 被 π 打到 e，而且最後一輪沒有人再檢查。
  - (c) 翻轉指紋：P(e_{m+1} | e_m) 遠大於 P(e_{m+1} | 非 e_m)。在下限附近讀到 e 的 shot，有三到五成是 π 自己
    打上去的。
- **比的是讀到 e 的比例，不反推真實 P_e。** 模型直接預測讀到 e 的比例（已含 ε_g 與讀取中的 T1）。反推要用
  confusion matrix，而校準用的「prepared g」裡本身就含 n_th，會變成循環論證。
- **shot 之間用 thermal reset。** 被測的 N 輪是實驗本身的內容，不是它的 `reset_method`。這和
  `qubit_thermal_population` 拒絕 active reset 的理由相同。
- **不沿用產線的 active reset。** 兩邊都拿不到每輪的判定：
  - QM 的 QUAM 迴圈是「最多 N 輪」，而且不存每輪的值；
  - Qblox 每輪的判定寫進 `cond_<q>`，但在 `_to_canonical` 被丟掉（`_reset.py` 的 KNOWN GAP）。

## 2. 每一發（一個 target）

迴圈順序：shot（外，real-time）→ prep 角度（Python 展開）→ 讀取序號。

| 步驟 | 內容 |
|---|---|
| 1 | thermal reset：`thermalization_time_s`（5Q4C q1 / q2 / q3 = 301 / 192 / 229 µs） |
| 2 | prep：θ = 0°（不打）、90°（`x90` / `X90`）或 180°（`x180` / `X`） |
| 3 | 第 m 次讀取（m = 0..N−1），thresholded，記進 `state` |
| 4 | 積分窗關閉後 `DECISION_DELAY_NS` = 364 ns：條件 x180（讀到 e 才打；沒打時空等一個 π 長） |
| 5 | 等 `readout_depletion_s`（兩個 element 都等） |
| 6 | 步驟 3–5 共 N 輪 |
| 7 | 第 N 次讀取（`meas_idx = N`）只觀察，不打 π |

**364 ns 的由來：** 這是 Qblox 的 `TRIGGER_DELAY`，是固定的硬體延遲。QM 可以更晚，所以 QM 墊到同一個時間點，
兩邊每一輪就完全相同。這個常數放在 SCQO 的實驗模組裡，兩個 driver 都 import 它。

**Qblox 的一輪：**
- `Measure(q, acq_protocol="ThresholdedAcquisition", feedback_trigger_label=q, acq_channel=f"S_21_{q}",
  coords={shot, prep, meas})`；
- `ConditionalOperation(body=X(q), qubit_name=q)`，`rel_time = 364 ns`，接在 Measure 結束之後；
- `IdlePulse(depletion)`。

Measure 結束的時間是 `acq_delay + integration_time`，也就是積分窗關閉的時刻。

**QM 的一輪：**
- `resonator.measure` → `assign(fire, I > threshold)` → 以整數存下 `Cast.to_int(fire)`；
- `align(xy, resonator)`；
- `xy.wait()`，長度 = TOF + (積分窗 − 脈衝長) + 364 ns，換成 4 ns 的 cycle；
- `xy.play("x180", condition=fire)`；
- `align()` 之後兩個 element 都等 depletion（ns // 4）。

不要沿用 QUAM 的 `depletion_time // 2`：`wait()` 以 4 ns 為一個 cycle，`// 2` 等於等了 2 倍 depletion。

**5Q4C 的一輪（讀取 + 364 ns 前的等待 + π + depletion）：**

| | 一輪 | 一發（3 個 prep） | 1 萬發 |
|---|---|---|---|
| q1 | 800 + 748 + 16 + 400 = 1964 ns | 約 0.97 ms | 約 10 s |
| q2 | 800 + 740 + 16 + 204 = 1760 ns | 約 0.64 ms | 約 6 s |
| q3 | 800 + 748 + 16 + 820 = 2384 ns | 約 0.76 ms | 約 8 s |

一發的時間主要花在 thermal wait。

## 3. Parameters

```python
class QubitActiveResetRoundsParameters(TargetSelection, QubitResetParameters):
    num_rounds: int = Field(10, ge=1, le=15)          # the tested rounds; readout N observes only
    prep_angles_deg: tuple[Literal[0, 90, 180], ...] = (0, 90, 180)   # non-empty, unique
    num_shots: int = Field(10000, gt=99)
    # validators: reset_method must be 'thermal'; exactly one target
```

- `num_rounds` 刻意不叫 `active_reset_rounds`。後者是 shot 之間那個 reset 的欄位，由 mixin 繼承而來，在這裡因為
  active 被拒而不起作用，跟 `qubit_thermal_population` 的情況一樣。
- 上限 15 同 `active_reset_rounds`。

## 4. Dataset contract

```python
DatasetContract(sweeps=("shot_idx", "prep_angle_deg", "meas_idx"),
                sweep_units=("shot", "deg", ""), variables=("state",))
```

- `meas_idx` 從 0 到 N，N 是只觀察的那一次讀取。命名沿用 `qubit_parity_switch_discrete`。
- 只有 `state`，沒有 I/Q 模式：
  - Qblox 的回授量測只能是 ThresholdedAcquisition；
  - QM 多記 I 就是 (d)。
- 每一輪的實際時序記進 dataset：讀取、π 前的等待（TOF + 364）、π 長、depletion、一輪總長。scq-reports 的模型
  比對直接從 `dataset.nc` 讀這些值。記錄方式同 parity 實驗的 `probe_shot_period_s`，由 probe 回報、經
  `attach_acquisition_coords` 寫入。

## 5. Estimator `active_reset_rounds`（scqat，只做計數）

`fit[q]`：

| 鍵 | 內容 |
|---|---|
| `p_first_0` / `p_first_90` / `p_first_180` | 第 0 次讀取讀到 e 的比例，每個 prep 一個 |
| `p_second_180` | x180 prep 後第 1 次讀取讀到 e 的比例（一輪 reset 的效果） |
| `floor_start_meas` | 從這個讀取序號起，每個 prep 都與合併後的下限相差在 3σ 內 |
| `p_floor`、`p_floor_stderr` | 下限：`floor_start_meas` 之後所有讀取、所有 prep 合併 |
| `floor_prep_spread_sigma` | 下限區各 prep 與合併值的最大偏差，以 σ 計 |
| `p_e_after_e`、`p_e_after_not_e`（各附 stderr） | 條件於前一次讀取的結果，在下限區合併 |
| `p_last` | 第 N 次讀取，各 prep 合併 |

- **Outcome：**
  - SUCCESSFUL：`floor_start_meas ≤ N − 1`，也就是下限區至少有兩次讀取；
  - FAILED：到最後都沒降下來。常見原因是 π 或門檻錯了，x180 prep 那條一直偏高。
- **圖：**
  - 讀到 e 的比例對讀取序號，每個 prep 一條線，對數 y 軸，標出下限帶；
  - 兩個條件機率。
- **不擬合 Markov 模型，也不寫回任何值**（`update()` 保持 no-op）。和模型的比對由 scq-reports 另出報告；模型仍只
  住在 scq-reports（「一個模型一個家」）。

## 6. 5Q4C 的預測

報告的模型，零自由參數，輸入同報告（09-29/30 的實測）：

| | q1 | q2 | q3 |
|---|---|---|---|
| 第 0 次讀取讀到 e，θ = 0 / 90 / 180 | 4.33 / 49.42 / 94.52 % | 7.83 / 49.23 / 90.63 % | 7.34 / 49.72 / 92.10 % |
| 第 1 次讀取讀到 e，θ = 180 | 6.10 % | 5.89 % | 8.53 % |
| 下限（從 `meas_idx = 3` 起），讀到 e 的比例 | 2.91 % | 1.68 % | 5.32 % |
| 下限，真實 P_e（只供對照，estimator 不報） | 1.56 % | 1.05 % | 2.92 % |
| P(e \| 前一次 e) / P(e \| 前一次非 e) | 47.2 / 1.58 % | 32.8 / 1.15 % | 46.0 / 3.03 % |

**1 萬發的統計誤差：**
- 每次讀取、每個 prep：±0.17 / 0.13 / 0.22 個百分點。
- 合併的下限：每發有 8 次讀取 × 3 個 prep 可用，約 ±0.03 / 0.03 / 0.05 點。相鄰讀取因翻轉而相關，實際會略大。
- P(e | 前一次 e)：約 ±0.6 / 0.8 / 0.5 點（6k / 3.5k / 11k 個事件）。
- P(e | 前一次非 e)：約 ±0.03 點。

**Qblox 的成本：**
- 編譯：conditional playback 在 Python 裡展開迴圈，舊的量測約每個 70 µs。3 × 10 × 1 萬 = 30 萬個約 21 s。
- bins：1 萬 × 3 × 11 = 33 萬，遠低於上限 3e6。

## 7. 按名稱拒絕

| 條件 | 在哪裡拒絕 |
|---|---|
| `reset_method='active'` | 中立的 validator |
| 一個以上的 target（Qblox 同時只能有一個 feedback label；v1 兩邊都只做一個） | 中立的 validator |
| discriminator 未校正（只需要 `readout_threshold`，不需要 `readout_rus_threshold`） | 兩邊 driver 既有的 helper |
| depletion 未校正（None；QM 另拒 16 ns 出廠值） | 同 active reset 的規則 |
| shots × prep 數 × (N+1) > 3e6 bins | Qblox probe；訊息指向 `--repeat` |

## 8. 各 repo 的改動（落地順序 scqat → SCQO → drivers）

- **scqat：**
  - `scqat/estimators/active_reset_rounds/`；
  - 測試用合成的 Markov 鏈：下限偵測、條件機率、x180 一直降不下來時判 FAILED。
- **SCQO：**
  - `scqo/experiments/qubit_active_reset_rounds.py`，內含：
    - Parameters、contract、`define_sweep`、`estimate`、`DECISION_DELAY_NS`；
    - `simulate`：Markov 鏈，ε_g = 1 − `fidelity_g`、ε_e = 1 − `fidelity_e`、n_th 取 mode fact，π 誤差 1 %，不含 T1。
  - `experiments/__init__.py` 加 import；跑 `scripts/update_docs.py` 更新 CLAUDE.md 的實驗清單與 estimator 對照表。
  - 測試：`tests/test_model_experiments.py -k active_reset`，加上 validator 的測試。
- **scqo-qm：**
  - `scqo_qm/experiments/qubit_active_reset_rounds.py`（`build_program` 與 class）；`__init__` 加 import。
  - 在產生的 QUA 上測：
    - 每個 prep 有 N+1 次 measure、N 次條件 play；
    - xy 的等待 = (TOF + 364) / 4 cycle；
    - depletion 以 `// 4` 換算；
    - 沒有呼叫 `reset_qubit_active`。
- **scqo-qblox：**
  - `_reset.py` 新增 `add_recorded_round(...)`：回授的 gate 仍只在 `_reset.py` 裡建，`Reset(` 的字面掃描測試不必
    放寬。docstring 要寫明：這裡的回授量測刻意走 `S_21_<q>`、帶 coords，因為它們就是資料（parity 實驗的模式）；
    carrier 那邊 `cond_<q>` 的規則不變。
  - probe `qubit_active_reset_rounds.py`；`__init__` 與 `__all__`。
  - 測試：
    - 編譯（`test_probe_surface` 自動涵蓋）；
    - 在編譯後的樹上測時序：π 在 Measure 結束後 364 ns，接著 depletion idle；每個 prep 有 N 個帶 feedback label
      的量測，加 1 個一般的 thresholded 量測，全部在 `S_21_q` 上；
    - `TRIGGER_DELAY == DECISION_DELAY_NS`；
    - bin 上限的拒絕。
- **release fragment：** 最後一個 commit 落地後寫 `SCQO/RELEASES.d/qubit-active-reset-rounds.toml`。

## 9. 驗證

**離線：**
1. **先做 Qblox 的小試驗**，這是唯一沒驗證過的 vendor 行為。
   - 要確認：一個 Measure 同時帶 `coords` 和 `feedback_trigger_label` 能不能編譯；`_to_canonical` 能不能把 bins
     摺回 (shot, prep, meas)。
   - 不行的話改走 `cond_<q>`，並讓 `_to_canonical` 讀它（順便補上 KNOWN GAP）。
   - 在寫其他程式之前先決定走哪條路。
2. **各 repo 的測試**，環境照 `ENVIRONMENTS.md`。
3. **QM 的 gateway simulator**（`scqo run qubit_active_reset_rounds --preview`）要看到兩件事：
   - π 在脈衝結束後 TOF + 364 ns 開始（誤差一個 cycle 內），沒有被即時運算拖延；
   - 下一次讀取前有 depletion。

**硬體（5Q4C，QM）：**
- 先測 q2：讀取最好、一發最短。
- 用 campaign 跑「`single_shot_readout` → `qubit_relaxation` → 本實驗」三次，讓每次測試的輸入都在前後十分鐘內量
  到。`single_shot_readout` 的結果不接受，除非門檻已經過時。
- 檢查：
  - a. θ = 0 的第 0 次讀取，和同一個 campaign 裡 `single_shot_readout` 的 `p_e_given_g` 比。兩者都是「從熱平衡起
    讀到 e」，q2 的預測是 7.8 %，前次實測 8.2 %。
  - b. `floor_start_meas ≤ 3`，而且 `floor_prep_spread_sigma < 3`。
  - c. P(e | 前一次 e) / P(e | 前一次非 e) > 10（模型給 20–40）。
  - d. 下限和模型比，模型用 campaign 量到的輸入。這一項由 scq-reports 報告呈現，不當成通過門檻：模型沒有
    量測引起的躍遷，而報告已經看到 prepared e 比預測多 0.7–1.9 點落在 g。

**Qblox 硬體：** 等 cluster 上有晶片。

## 10. 之後（核可時移進 BACKLOG，不屬於本計畫）

- (d)：QM 每輪存 I，用同一份資料離線模擬「最多 N 輪」，離開門檻任選。
- π 門檻掃描：需要逐 run 覆寫門檻；Qblox 的 `acq_threshold` 是 sequencer 的靜態設定。
- `active_reset_rounds` 在兩邊實際播的迴圈不同（QM 最多 N 輪、Qblox 固定 N 輪）。等本測試有資料，再決定要不要加
  `fixed | until_ground` 欄位。
- QUAM `reset_qubit_active` 的時序問題，用 gateway simulator 確認：
  - x180 有沒有等 depletion；
  - `// 2` 等於 2 倍 depletion；
  - 迴圈後固定的 2 µs 尾巴。
- 多 target。

## 11. 未定

- **Qblox 硬體測試用哪顆晶片？** 5Q4C 目前只登記了 QM 的 setup（cd2 `qm_5q`）。chipA cd1 有 qblox setup，但最後的
  紀錄是 8 月初狀況不好。
- **名稱：** `qubit_active_reset_rounds`，estimator 叫 `active_reset_rounds`。
