# coupler 狀態讀取：三個基礎工具實驗的設計

> 計畫文件（2026-09-27）。內容只有三個直接讀 coupler 的實驗該怎麼設計；其餘相關工作記在 BACKLOG F24。
> §3 實驗 1 已於 2026-09-27 實作並上機（5Q4C q1_q2、q2_q3，只有 QM 版）；§4 實驗 3 已於同日實作（只有 QM 版，
> 離線驗證），上機驗證待做；§5 仍待定。
> 驗證用的腳本與原始結果在 `scqat/temp/coupler_scan/`（gitignored），run 標記為 `coupler-scan`。

## 1. 三個實驗

1. **coupler 的 flux 週期**：用已知頻率驅動 qubit，同時掃 coupler flux。coupler 靠近 qubit 時，qubit 會被推開、
   打不上去，從打不上去的位置推出週期。
2. **coupler 頻率 by ZZ**：掃 coupler tone 的頻率，打完之後對 qubit 打 π 再讀取。coupler 被激發時，ZZ 會讓
   π 打偏。
3. **coupler 頻率 by swap**：掃 coupler tone 的頻率，打完之後用慢速 ramp 讓 coupler 與 qubit 絕熱交叉，
   coupler 的激發因此轉到 qubit 身上。

順序是 **1 → 3 → 2**：實驗 1 給出實驗 3 的 ramp 目標；實驗 3 找到 f_c 之後，才能決定實驗 2 的 port 要怎麼設。

## 2. 5Q4C 上的硬體事實（2026-09-27 從 state.json / wiring.json 讀出）

- **coupler 線**：LF-FEM analog 輸出，`direct` 模式，**±0.5 V**。q1_q2_c 的 `decouple_offset` 是 0.16 V，
  q2_q3_c 是 0.06 V，q3_q4_c 與 q4_q5_c 是 0 V。`const` 振幅 0.25 V，QUA 的 `amplitude_scale` 必須小於 2，
  所以 |b| < 0.5 V。q1_q2_c 的脈衝 b 只能在 **−0.5 … +0.34 V**（線上電壓 −0.34 … +0.5 V）。
- **q1 的 xy**：MW-FEM `con1/6/2`，band 1，LO 4.9 GHz。q2 的 xy 是 `con1/6/3`，跟 q1 同一組 port pair，
  共用 band。band 1 的 LO 範圍是 0.05–5.5 GHz，band 2 是 4.5–7.5 GHz，band 3 是 6.5–10.5 GHz。
- **idle 時 coupler 在 qubit 上方**（q1_q2_c）。證據有兩個：0.16 V 是 J=0 的點，而這種抵消只在 coupler 高於
  qubit 時才會發生；另外 coupler 電壓越高，q1 被往下推得越快（§6.1：0.20 / 0.22 / 0.24 V 時分別是
  −1.1 / −2.4 / −5.5 MHz）。用極點外推，**q1 的交叉點約在 0.27 V（DC）**；以 coupler apex 0.074 V（§6.1）為
  中心，鏡像約在 −0.12 V。
- **成員頻率**：q1 5.1446 GHz（high）、q2 4.8421 GHz（low）。q1 的 arch 曲率是 −14.8 kHz/mV²；
  q1_q2_c 對 q1 的串擾 m 是 5.45 %（§6.1）。

## 3. 實驗 1：`pair_coupler_crossing_pulse`（暫名，feature `pair-coupler-crossing-pulse`）

**問題**：coupler 在哪些 flux 越過鄰居 qubit？由這些交叉點推出 coupler 的 apex 位置、週期與 f_c_max。

**原理**：探針在 idle 時的頻率 f_q 已知（`drive_freq_hz`）。coupler 越過 f_q 時，兩者混成（分裂 2g），qubit 被推離
f_q，x180 就打不上去。x180 的頻寬約 ±12 MHz，所以只有在交叉點附近才會失效，dip 很乾淨。串擾造成的偏移對它
影響不大：b = −0.28 V 時，q1 自己的 flux 只移了 −15 mV，頻率約 −3.7 MHz。

**target**：一個 `qubit_pair`（依 coupler role 找到 coupler 與它的 flux channel；high/low 兩個成員要有 drive 與
readout）。**一次只准一對**：coupler 線對非鄰居也有 5–7 % 的串擾，兩對同時量會互相污染。

**Parameters**

| 欄位 | 型別 / 預設 | 意義 |
|---|---|---|
| `start_coupler_flux_v` / `end_coupler_flux_v` | −0.45 / +0.30 | coupler 脈衝振幅，**相對 coupler 的 `idle_flux`**，依 start → end 的順序掃。超出 rail 或 `amplitude_scale` 範圍時，driver 依名稱拒絕並報出可用範圍 |
| `num_coupler_flux_points` | 376 | 預設 2 mV 一步（理由見下方「精度」） |
| `measure` | `Literal["both","high","low"]` = `"both"` | 哪些成員打 x180。兩個成員**一律都讀** |
| `coupler_side` | `Literal["auto","above","below"]` = `"auto"` | idle 時 coupler 在探針上方或下方。`auto`：兩個成員都量時由資料判斷（estimator 第 5 步）；只量一個時只報對稱點，不宣稱它是 apex |
| `coupler_ec_hz` | `float \| None` = None | arch 模型用的 coupler Ec。None 表示先用 coupler mode 的 `ec_hz` fact，沒有就用 0.2 GHz；實際用的值記在 `ec_hz_used`。在 5Q4C 的數字下，Ec 從 0.2 改到 0.3 GHz，週期變不到 1 % |
| `flux_buffer_ns` | int = 100（0，或 ≥16 且為 4 的倍數） | coupler 脈衝開始後等多久才打 x180，以及打完後再等多久 coupler 才回 idle。coupler 線沒有 predistortion，要給它時間穩定 |
| `num_averages` | 300 | |
| `reset_method` 等 | `QubitResetParameters` | 同其他實驗 |

需要 state discrimination（輸出是 `joint_population`）。沒有 threshold 時由 driver 依名稱拒絕。

**coupler 視窗做成 capability `coupler_flux`**：`_capabilities/coupler_flux.py` 提供
`CouplerFluxPulseSweepParameters`（上表前三欄）、軸名 `coupler_flux_v`，以及
`coupler_anchor_v(experiment, pair)`（pair → coupler role → coupler flux channel 的 `idle_flux`）。這個視窗
只有相對 frame，所以 carrier 的名稱必須以 `_pulse` 結尾，這條規則寫進 `test_capabilities`；`test_sweep_order`
也要涵蓋它。動到 capability 算共用核心，SCQO 要跑全套測試。

**序列（每一發）**

1. reset 兩個成員。
2. coupler：播 `const × (b / ref)`，長度 T = 2 × `flux_buffer_ns` + x180 長度。
3. 成員：等 `flux_buffer_ns` → 被量的成員同時打 x180（頻率 = 各自的 `drive_freq_hz`）→ 再等 `flux_buffer_ns`。
4. coupler 回到 idle → `align` → 兩個成員都讀取（2-level）→ 存四個 joint indicator。

迴圈順序：averages（外）→ b（內，依 start → end）。以 q1 的 thermalization 估，一次 run 約 30 秒。

已知的系統誤差：b 越過交叉點之後，x180 可能又打得上去；但脈衝結束時 coupler 會快速掃回、再越過一次
交叉點，Landau–Zener 會把一部分激發留在 coupler。所以交叉點外側的基準線可能比內側低，estimator 不能
假設兩側基準線相同。

**contract**：sweeps `("coupler_flux_v",)`，variables `("joint_population",)`，readout_dims
`("joint_state",)`，`target_kinds = ("qubit_pair",)`。

**simulate**：用 stable seed 放一條隱藏的 coupler arch（F、P、x0、Ec、g），成員頻率固定為 5.1 / 4.8 GHz
（simulate 不讀 device 狀態）。用兩能階模型算每個 b 下 qubit 被推開的量 δ，用 Rabi 公式算 x180 的激發率，
再乘出 joint 分佈並加雜訊。放的時候確保兩對交叉點都在視窗內。

**estimator（scqat，新的，1:1）：`pair_coupler_crossing`**

1. 進入時 `ascending(dataset, "coupler_flux_v")`，並有 `order_free` 測試。
2. 從 joint 分佈算邊際：P_high = P10 + P11，P_low = P01 + P11。
3. 每個被量的成員：基準線取高分位數（例如第 90 百分位），正規化 s = P / 基準線，s < `dip_threshold`
   （預設 0.5）的連續區段算一個 dip。dip 中心取 (1 − s) 的加權質心，並報寬度與最低值。
4. 配對：取夾住 b = 0（idle）的最近兩個 dip，左右各一，得到對稱點 c_k 與半距 d_k。夾不住就設
   `crossings_not_bracketed_<role>`。
5. 兩個成員都量時：
   - 兩個對稱點要一致，差太多就設 `center_mismatch`。
   - **判斷方向**：高頻成員的交叉點在內圈 → idle 時 coupler 在上方，中心是 apex；低頻成員在內圈 →
     coupler 在下方，中心是 anti-apex。跟 `coupler_side` 指定的方向矛盾時設 `side_conflict`。
   - **arch 模型**：f_c(x) = (F + Ec)·√|cos(π(x − x0)/P)| − Ec。中心是 apex 時 cos(π d_k / P) =
     ((f_k + Ec)/(F + Ec))²；中心是 anti-apex 時把 cos 換成 sin。兩個方程式解 F 與 P：d_high/d_low 是 F 的
     單調函數，先一維求根得到 F，再算 P。無解時設 `arch_unsolved`。誤差用數值 Jacobian 傳遞。
6. 只量一個成員時只報對稱點；只有 `coupler_side` 有指定時，才判定它是 apex 還是 anti-apex。

**精度**（以 5Q4C 的數字估：q1 半距 0.196 V，兩顆相差 300 MHz）：兩個半距只差 4–14 %，所以結果是「估計」。
5 mV 的步距下 F 約 ±0.6 GHz、P 約 10–15 %；2 mV 時約 ±0.25 GHz、5 %。若 F ≥ 8 GHz，P ≈ 0.5 V，下一個週期的
交叉點會落在可達範圍的邊緣，那時就能直接量到週期。實作後用 5Q4C 的數字做離線合成資料（2 mV、300 次平均）：
F 偏差 < 0.1 GHz、P < 1.5 %，報的 stderr 約 0.07 GHz。這個 stderr 只含取樣與雜訊，不含 g_c、LZ 基準線這類
系統誤差，上機時要以 §6.2 的比對為準。

**Result（`fit[pair]`）**

- 每個成員的交叉點（pulse frame）：`crossing_<role>_lower_v`、`crossing_<role>_upper_v`、dip 寬度與最低值。
  這也是實驗 3 的 ramp 目標。
- `center_from_idle_v`、`center_kind`（`apex` / `anti_apex` / `unknown`）、`old_coupler_idle_flux`。
- 寫回值（絕對）：`flux_offset`（apex）、`flux_per_phi0`、`f_q_max_hz`，各附 stderr；以及 `ec_hz_used`。
- 旗標（0/1）：`crossings_not_bracketed_high/low`、`center_mismatch`、`side_conflict`、`arch_unsolved`。
- SUCCESSFUL：每個被量的成員都夾到一對交叉點，而且沒有 `center_mismatch`、`side_conflict`。
  `arch_unsolved` 不算失敗，只是不提議週期與 f_c_max。

**寫回**（單一 pair、SUCCESSFUL 才提議；**永遠不動 coupler 的 `idle_flux`**）

- `<coupler>_z.flux_offset`：apex 已判定時（兩個成員都量，或 `coupler_side` 有指定）。
- `<coupler>_z.flux_per_phi0`、`<coupler>.f_q_max_hz`：arch 模型有解時。描述要寫明這是依賴模型的估計，
  直接量 f_c 的是實驗 2、3。

**pulse frame 的代價**：交叉點、中心與週期都以 pulse 伏特表示。qubit 線的 pulse/DC 比例 g 約 0.96，coupler 線
的還沒量過；中心離 idle 約 −86 mV，所以絕對的 `flux_offset` 可能偏約 3 mV，週期偏約 4 %。g_c 的量法見 §6.2。

**事前拒絕**：多於一對 target；pair 沒有 coupler，或 coupler 沒有 flux channel；成員缺 drive 或 readout；視窗
零寬度。driver 端：rail 與 `amplitude_scale`（沿用 `check_flux_pulse_relative`）。

**只做 QM 版**：Qblox 那邊沒有帶 coupler 的晶片，Qblox 不註冊這個實驗。

**測試**

- scqat：`tests/test_pair_coupler_crossing_estimator.py`：apex 中心與 anti-apex 中心兩種合成資料都要還原出
  中心、方向、F、P；`order_free`；只量一個成員的路徑；夾不住時報 FAILED；擬合失敗時圖仍要畫得出來。
- SCQO：`test_model_experiments -k crossing`；`test_capabilities` 與 `test_sweep_order` 涵蓋新的
  capability；frame 測試（`flux_offset = old_coupler_idle_flux + 中心`）；simulate → estimate 要還原放進去的值；
  多對 target 被拒絕；`update()` 只提議 fact、從不提議 `idle_flux`。跑 `update_docs.py`，再跑 SCQO 全套。
- scqo-qm：用 live quam_state 建 q1_q2 的程式，確認 QUA 裡有 coupler 的 const 播放、兩個成員的 x180 與
  讀取；超出 rail 時依名稱拒絕；註冊 census；qm 全套。

**上機驗證（5Q4C，要先問）**：q1_q2、`measure=both`、b 從 −0.498 到 +0.34（2 mV，420 點；b = −0.5 需要
`amplitude_scale` = 2，會被拒絕）、300 次平均、`--no-update`。
預期 q1 的交叉點在線上電壓約 0.27 V（b ≈ +0.11）與 −0.12 V（b ≈ −0.28），q2 的在兩者外側；高頻成員在內圈，
也就是中心是 apex。之後換 q2_q3（idle 0.06 V）。結果的比對方法見 §6.2。

**實作參考點**（2026-09-27 讀過，照這些模式做）

- scqat：`estimators/qubit_ramsey_flux_pulse/`（subpackage 的樣子）、`tools/sweep_order.ascending`、
  `core/figures.render_figures`、`tests/conftest.py` 的 `order_free` fixture、`tools/fit_transmon_freq_flux`
  （arch 的頻率公式）、`estimators/__init__.py`（要加匯出）、`scripts/update_docs.py`。
- SCQO：`_capabilities/flux.py`（mixin、`flux_anchor_v`、敘述常數的寫法）、`_window.py`（只拒絕零寬度）、
  `tests/test_capabilities.py`（`test_flux_pulse_names_carry_the_suffix`、`CAPABILITY_SUMMARIES`）、
  `tests/test_sweep_order.py`；`experiments/pair_zz_coupler.py`（`validate_targets` 檢查 coupler 的 flux
  channel）、`experiments/pair_swap_flux_map.py`（`joint_population` 的 contract、`readout_coords`、
  `_role_names`）；`scripts/update_docs.py`。
- scqo-qm：`experiments/pair_zz_coupler.py`（`select_qubit_pairs`、`vendor_pair_name`、`role_side`、coupler
  以 `amplitude_scale` 播 `const`）、`_pair_roles.JointPopulationMixin`、`_flux_limits.check_flux_pulse_relative` /
  `declared_idle_offset_v`、`_amp_limits.MAX_AMP_SCALE`（= 2）、`experiments/__init__.py` 的 import 行與
  census 測試。

**施工**：一個 feature，落地順序 scqat → SCQO → scqo-qm，最後寫一個 `RELEASES.d` fragment，不切 release。
上機遇到第一個硬體或 gateway 錯誤就停下來回報，動過的 knob 全部還原。

## 4. 實驗 3：`pair_coupler_spectroscopy_swap`（暫名，feature `pair-coupler-spectroscopy-swap`）

> 規格 2026-09-27 寫成並核可。已定的四點（使用者，2026-09-27）：ramp 兩種形狀都可選；
> 一次 run 只用一個 LO、跨距 ≤ 500 MHz；每個頻率點穿插不做 ramp 的參考組；SUCCESSFUL 時提議 coupler 的
> `f_01_hz`。

**問題**：coupler 在目前 idle 下的 0→1 頻率 f_c。

**原理**：在探針（pair 的一個成員）的 xy 上打頻率 f 的 tone。f = f_c 時，tone 透過探針與 coupler 的混成把
coupler 激發起來。接著用 flux ramp 讓 coupler 與探針**慢慢**越過彼此：絕熱通過把 coupler 的激發轉到探針上；
然後**突然**回到 idle（非絕熱，激發留在探針），在 idle 讀取。探針的 P_e 對 f 在 f_c 出峰。參考組完全一樣，
只是不做 ramp，coupler 的激發就留在 coupler 裡衰減，所以參考組只會看到直接激發探針的特徵（探針的躍遷、
讀取、TLS）。**只在 ramp 組出現的峰才是 coupler**。

**5Q4C 的數字**（實驗 1 的兩次上機結果與 live config）

- f_c 預測（實驗 1 的 arch 在 idle 處）：q1_q2_c **6.80 GHz**、q2_q3_c **7.17 GHz**（統計誤差約 ±0.1 GHz，另有
  對稱 SQUID 模型的系統誤差）。讀取共振腔在 5.87–6.08 GHz，探針自己的 f01、f02/2 都 ≤ 5.2 GHz，都不在視窗內。
  coupler 自己的雙光子 f02/2 約在 f_c − 100 MHz，功率高時可能出現第二個較小的峰。
- g_qc：由實驗 1 的 dip 寬度估約 50–70 MHz。tone 只能從探針的線打，coupler 的 Rabi 約是
  Ω_q·g/Δ ≈ 3 % 的 Ω_q（Δ ≈ 1.65 GHz）。q1 的 16 ns x180 相當於 −6 dBm、峰值 Rabi 約 62 MHz，所以
  −20 dBm 給 coupler 約 0.4 MHz 的 Rabi，足以飽和（估計誤差約 ±10 dB）。
- ramp（q1_q2，ramp 打在 coupler）：q1 的交叉點在 b = +0.109 V，coupler 在那裡的斜率 22 MHz/mV。0.15 V/µs
  越過交叉點時，g = 50 MHz 的絕熱率 99 %、30 MHz 時 82 %。快邊約 3 ns，漏回 coupler 約 2 %。
- band：q1 的 xy 在 MW-FEM `6/2`、band 1、LO 4.9 GHz，band 1 最多到 5.75 GHz。LO 移到 6.8 GHz 要把 port
  pair（`6/2` + `6/3`）換到 band 2。band 2 的 LO 範圍 4.5–7.5 GHz 也包含 q2 的 4.9 GHz，所以 q2 的 LO
  不用動，只換 band。q3（`6/4`）換 band 會帶著 q4（`6/5`）。

**target**：一個 `qubit_pair`，理由同實驗 1（coupler 線對非鄰居也有 5–7 % 串擾）。`probe` 選哪個成員接收激發。

**Parameters**

| 欄位 | 型別 / 預設 | 意義 |
|---|---|---|
| `start_tone_freq_hz` / `end_tone_freq_hz` | 6.55e9 / 7.05e9 | tone 的**絕對**頻率，依 start → end 的順序掃。跨距 ≤ 500 MHz（LO 放在中心、\|IF\| ≤ 250 MHz），超過時依名稱拒絕。以實驗 1 的 `f_c_at_idle_hz` 為中心 |
| `num_tone_freq_points` | 251 | 預設 2 MHz 一步 |
| `tone_power_dbm` | −20 | 探針 xy 的 tone 功率（儀器端 dBm），沿用 `drive_power_boundary`：run 前寫入、run 後精確還原 |
| `tone_len_ns` | 10000 | tone 長度；比 coupler 的 T1 長就是飽和，峰高最多約 0.5 |
| `probe` | `Literal["high","low"]` = `"high"` | 接收激發的成員。ramp 必須**先**越過它：coupler 在兩者上方時（5Q4C）是 high，在下方時是 low |
| `ramp_on` | `Literal["coupler","probe"]` = `"coupler"` | ramp 打在哪條 flux 線。5Q4C 的 q1 在 apex、coupler 在上方，只能動 coupler；coupler 設計在 qubit 下方時可以改動探針 |
| `ramp_shape` | `Literal["slow_then_fast","fast_then_slow"]` = `"slow_then_fast"` | 慢段的方向。`slow_then_fast`：由 `ramp_start_v` 慢慢走到 `ramp_end_v`，再突然回 idle，swap 發生在去程。`fast_then_slow`（使用者 2026-09-27 提議）：先突然跳到 `ramp_end_v`，再慢慢走回 `ramp_start_v`，swap 發生在回程。5Q4C 的 coupler（6.99 GHz）在讀取共振腔（5.87–6.08 GHz）上方、共振腔又在 qubit 上方，回程慢段開始時激發還沒交出去，但要等交給 qubit 之後才會再經過共振腔。回程慢段第一個碰到的是外圈成員，所以 `ramp_end_v` 越過兩個交叉點時，探針要選 low |
| `ramp_start_v` | 0.0 | 線性段的起點，相對於被 ramp 那條線的 `idle_flux`。0 = 從 idle 慢升（原本的鋸齒波）；設在交叉點前約 30 mV = 先跳過去再慢升（激發待在 coupler 的時間約短 4 倍）。跳的那一段不能越過任何交叉點 |
| `ramp_end_v` | `float \| None` = None | 線性段的終點，要越過交叉點。None 時依名稱拒絕，並提示用實驗 1 的交叉點再加約 30 mV（q1_q2：+0.14） |
| `ramp_rate_v_per_us` | 0.15 | 線性段的斜率。Landau–Zener 只看越過交叉點時的斜率，所以兩種形狀在同一個斜率下絕熱性相同，差別只剩 coupler 的 T1 衰減 |
| `flux_buffer_ns` | 100（0，或 ≥16 且為 4 的倍數） | tone 結束到 ramp 開始、以及 ramp 回到 idle 到讀取之間的等待 |
| `num_averages` | 300 | |
| `reset_method` 等 | `QubitResetParameters` | 只能用 thermal：active reset 需要探針的 xy 在 f_q，但這個實驗把 LO 移走了 |

需要 state discrimination（輸出是 `joint_population`），規則同實驗 1。

**序列（每一發）**

1. reset 兩個成員。
2. 探針的 xy 播 `saturation`（`duration` = `tone_len_ns`），頻率由 `update_frequency` 設成 f − LO。
3. 等 `flux_buffer_ns`。
4. ramp 組：被 ramp 的線播一段 arbitrary waveform：第一個取樣就在 `ramp_start_v`，以 `ramp_rate_v_per_us`
   線性走到 `ramp_end_v`，結束時輸出回到 idle（突然）。參考組：同樣長度的 `wait`。
5. 等 `flux_buffer_ns` → `align` → 兩個成員都讀取（2-level）→ 存四個 joint indicator。

迴圈順序：averages（外）→ f（依 start → end）→ ramp 組、參考組（內，同一個 f 背靠背，漂移互相抵消）。
q1_q2 預設值下一次 run 約 50 秒。ramp 的長度：從 idle 到 +0.14 是 933 ns，從 +0.08 起跳是 400 ns。

**contract**：sweeps `("tone_freq_hz", "ramp_played")`（`ramp_played` 的座標是 [1, 0]），variables
`("joint_population",)`，readout_dims `("joint_state",)`，`target_kinds = ("qubit_pair",)`。

**simulate**：用 stable seed 在視窗內放一個 f_c，ramp 組探針的邊際出現 Lorentzian 峰（高約 0.35、寬約 3 步）。
另外在**兩組都有**的位置放一個假峰，讓 estimator 的拒絕路徑有被測到。

**estimator（scqat，新的，1:1）：`pair_coupler_spectroscopy_swap`**

1. 進入時 `ascending(dataset, "tone_freq_hz")`，並有 `order_free` 測試。
2. 算探針的邊際：ramp 組 P_r(f)、參考組 P_0(f)，差值 D = P_r − P_0。
3. 對 D 用 `tools.peak_fit.fit_peaks`（實數訊號），取最強的峰：f_c、FWHM、高度、SNR。其他峰列出來
   （可能是 coupler 的 f02/2），並設 `multiple_peaks`。
4. 對參考組 P_0 也找峰：若在 f_c 的一個 FWHM 內有峰，設 `reference_feature`。
5. 峰離視窗邊緣不到一個 FWHM 時設 `peak_at_edge`。
6. SUCCESSFUL：D 有通過 SNR 的峰，而且沒有 `reference_feature`、`peak_at_edge`。

**Result（`fit[pair]`）**：`f_c_hz`（附 stderr）、`fwhm_hz`、`peak_height`、`snr`、`other_peaks_hz`、`lo_hz`、
`ramp_duration_ns`，旗標 `multiple_peaks`、`reference_feature`、`peak_at_edge`。

**寫回**：單一 pair、SUCCESSFUL 才提議 coupler mode 的 `f_01_hz`（目前 idle 下的 f_c，fact）。不動任何 knob。

**QM 的 band / LO**：LO 放在視窗中心。這個 LO 超出 port 目前 band 的範圍時，把整組 port pair 換到涵蓋它的
band；partner 的 LO 若仍在新 band 內就不動，不在的話比照 broadband 停到 band 下限。probe 直接產生**一份
config**（LO、band 已改好），產生完立刻把 QUAM tree 還原，所以不會有 drift；再把綁好這份 config 的
`_lib.acquire` 當成 3-tuple 的 acquire callable 交給 backend。`--preview` 可用，QUA 內容正確，但 preview
用的是 LO 沒移動的 config（它不經過 acquire callable）。

**事前拒絕**：多於一對；coupler 沒有 flux channel；探針缺 drive、readout 或 threshold；`ramp_on=probe` 而
探針沒有 flux channel；`ramp_end_v` 是 None；`ramp_start_v == ramp_end_v`；跨距超過 500 MHz；零寬度頻率
視窗；rail 與取樣範圍（被 ramp 的線上 idle + max(|start|, |end|)，沿用 `_flux_limits`）；active reset。

**只做 QM 版**，理由同實驗 1。

**測試**

- scqat：`tests/test_pair_coupler_spectroscopy_swap_estimator.py`：合成的真峰被找到；兩組都有的假峰被拒絕
  （`reference_feature`）；`order_free`；貼邊的峰；沒有峰時報 FAILED 且圖仍畫得出來。
- SCQO：`test_model_experiments -k spectroscopy_swap`（simulate → estimate 還原放進去的 f_c；只提議
  `<coupler>.f_01_hz`；多對被拒絕；`ramp_end_v=None` 被拒絕；跨距 > 500 MHz 被拒絕），`test_capabilities`
  的 `EXPECTED_CAPABILITIES` 加一列（`qubit_reset`；頻率是絕對 Hz，不是 detuning capability），跑
  `update_docs.py`。沒動到 capability mixin，只跑相關的測試檔。
- scqo-qm：用 live quam_state 建 q1_q2 的程式：`update_frequency` 在迴圈內、`saturation` 的長度、ramp
  waveform 的起點／終點／長度、參考組同長度的 `wait`、兩個成員的讀取；產生的 config 裡 q1 的 port 在 band 2、
  LO 在視窗中心，而 QUAM tree 保持原狀；超過 rail 時依名稱拒絕；census；qm 全套。

**上機驗證（5Q4C，要先問）**

1. q1_q2、probe=high、ramp_on=coupler、6.55–7.05 GHz（251 點）、−20 dBm、10 µs、`ramp_start_v=0.08`、
   `ramp_end_v=0.14`、0.15 V/µs、`--no-update`。
2. 同樣設定改 `ramp_start_v=0`（從 idle 慢升）：兩次的 f_c 應該一致，峰高差距反映 coupler 的 T1。
3. q2_q3、probe=high（q3）、6.92–7.42 GHz、`ramp_end_v=0.136`（交叉點 +0.106 加 30 mV）。

找不到峰時先移視窗（±250 MHz），再調功率（±10 dB）。

**實作參考點**：scqat `tools/peak_fit.fit_peaks`、實驗 1 的 estimator（subpackage、`render_figures`、
`order_free`）；SCQO `pair_coupler_crossing_pulse.py`（validate_targets、`_role_names`、joint readout）、
`broadband_qubit_spectroscopy.py`（絕對 Hz 視窗）、`_drive_power.drive_power_boundary`；scqo-qm
`pair_coupler_crossing_pulse.py`、`broadband_qubit_spectroscopy.py`（`_MW_FEM_BANDS`、`_partner_port_id`）、
`qm_backend.acquire` 的 3-tuple acquire callable 路徑、`_lib.acquire(config=)`。

## 5. 實驗 2：ZZ 讀 coupler 頻率（等實驗 3 之後再定）

- 序列：reset → coupler tone → 探針的 π → 讀取。f = f_c 時出現 dip。
- **port 問題**：coupler tone 和 π 要從同一個 port 送出。q1 的 port LO 在 4.9 GHz，只靠 IF 最多到約 5.3 GHz；
  f_c 更高的話要在這個 port 加第二個 upconverter，超過 5.5 GHz 還得換到 band 2，連帶拖著 q2。這些都是
  vendor config 的修改，等實驗 3 找到 f_c 再決定。
- **選擇性**：χ_qc 估計在 2–8 MHz（g 50–100 MHz、Δ ≈ 1 GHz），40 ns 的 x180 只會部分失效。把 `x180_Square`
  用 `duration=` 拉長、振幅按比例縮小（例如 400 ns、頻寬約 1 MHz），不需要重新校正。
- 跟實驗 3 互補：不需要越過交叉點。

## 6. 驗證方法與參考數據

### 6.1 透過鄰居讀 coupler（2026-09-26 的 DC 量測；優先度低，只拿來驗證）

**鄰居頻率 vs coupler DC**（`coupler_scan.py`）：`q1_q2_c_z.idle_flux` 以 20 mV 為一步 ping-pong 掃描，每點量兩次
Ramsey（6 MHz detuning / 4 µs / 201 點 / periodogram）。q1+q3 一起量，q2 單獨量（q1 和 q2 同時處於疊加態會
帶進 ZZ）。q3 不是這個 coupler 的鄰居，當作對照組。數值是相對各自 drive 的偏差（kHz）：

| coupler (V) | q1（鄰居，high） | q2（鄰居，low） | q3（對照組） |
|---|---|---|---|
| 0.020 | −494 | −4645 | −1663 |
| 0.040 | −153 | −3269 | −1193 |
| 0.060 | +93 | −2136 | −804 |
| 0.080 | +260 | −1227 | −490 |
| 0.100 | +347 | −558 | −254 |
| 0.120 | +344 | −116 | −93 |
| 0.140 | +242 | +82 | −6 |
| **0.160**（idle） | +19 / +19 | +29 / +28 | +3 / +6 |
| 0.180 | −381 | −321 | −56 |
| 0.200 | −1083 | −1013 | −201 |
| 0.220 | −2393 | −2201（c=0.44） | −424 |
| 0.240 | −5508（c=0.23） | −4320（c=0.10） | −724 |

中心點前後各量一次（相隔約 12 分鐘），差距 ≤ 3 kHz。0.24 V 時 q1/q2 的對比度塌掉：qubit 被推開好幾 MHz，
x90 就不再共振。

**兩個 coupler 偏壓下的 qubit DC apex**（`apex_vs_coupler.py`）：每個偏壓 5 點加 1 個重複點，q1 與 q3 一起量。
m 的定義：coupler 線每 1 V 等效於 qubit 自己的線 +m V，所以 apex 位置移動 −m·ΔV_c。

| coupler 0.16 → 0.08 V | apex **位置**移動 | apex **高度**移動（kHz） |
|---|---|---|
| q1（鄰居） | +4.36 mV → m₁ = +5.45 % | **+524**（coupler 的 Lamb shift） |
| q3（對照組） | +5.73 mV → m₃ = +7.16 % | +119 |

**讀法**

- 鄰居的原始曲線是兩樣東西的和：串擾移動 apex 的**位置**，coupler 的 Lamb shift 移動 apex 的**高度**。
  原始曲線的頂點（q1 在 101 mV、q2 在 143 mV）兩者都不是。q3 的曲線則是純串擾（220 mV 內都是拋物線，
  |m| ≈ 7.4 %，與上表一致）。
- 用 m₁ 扣掉串擾，還原出 q1 的純 Lamb 曲線：頂點約 74 mV，所以 **q1_q2_c 的 DC apex 約在 0.074 V**
  （誤差估計 ±2 mV）。idle 0.16 V 在它上方 86 mV，位在陡的那一側。

### 6.2 怎麼驗證三個實驗的結果

- **實驗 1 的中心**跟 §6.1 還原的 DC apex 0.074 V（±2 mV）比。兩者的差距來自 coupler 線的 pulse/DC 比例 g_c。
- **g_c**：同一小時內，用 DC 移動 coupler 量一次 apex（§6.1 的鄰居 apex 掃描，或把實驗 1 的序列改成 DC 版），
  再跟實驗 1 的 pulse frame 結果比。qubit 線的 g ≈ 0.96 就是用同樣方式量的（在 `qubit_ramsey_flux_pulse` 上，
  拿同一小時的 DC 參考比）。
- **實驗 1 的交叉點**跟 §2 的外推比：q1 約在線上電壓 0.27 V 與 −0.12 V，q2 在兩者外側。
- **實驗 3 與實驗 2**在同一個 coupler 偏壓下量到的 f_c 要一致，而且要落在實驗 1 的 arch 模型在 idle 處預測的
  f_c 範圍內（在實驗 1 的精度以內）。
- 在兩個 coupler 偏壓下各跑一次實驗 3，f_c 的變化要符合實驗 1 的 arch。

## 7. 類比用的既有實驗

- **`qubit_spectroscopy`**：1D 驅動頻率掃描加上 saturation drive。實驗 2、3 的 coupler tone 就是它的 coupler 版。
- **`broadband_qubit_spectroscopy`**：用絕對的 [start, stop] 頻率視窗，分段換 LO，換 band 時會拖著 port pair 的
  另一顆，並在 `finally` 還原。實驗 3 的頻率掃描沿用這個做法。
- **`qubit_spectroscopy_flux_pulse`、`qubit_ramsey_flux_pulse`**：pulse frame（脈衝疊在 idle 上）、名稱以
  `_pulse` 結尾、寫回時重新參照成絕對值（`old_idle + 擬合值`）。實驗 1 的 coupler 視窗照這個模式。
- **`pair_zz_coupler`**：pair 為 target、用 `measure` 選成員、coupler 以 `const` 脈衝疊在 `decouple_offset` 上
  （`check_flux_pulse_relative` 做 rail 檢查），也是只做 QM 版的前例。它的寫回 frame 有問題（I26），這裡只借它
  的 target 與 probe 形狀。
- **`pair_swap_flux_map`、`pair_swap_chevron`**：`coupler_flux_v` 軸的意思（疊在 coupler idle 上的脈衝振幅），
  以及透過 `JointPopulationMixin` 讀成 `joint_population`。
