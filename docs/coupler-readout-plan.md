# coupler 狀態讀取：三個基礎工具實驗的設計

> 計畫文件（2026-09-27）。內容只有三個直接讀 coupler 的實驗該怎麼設計；其餘相關工作記在 BACKLOG F24。
> §3 實驗 1 的規格已於 2026-09-27 核可，實作中；§4、§5 仍待定。
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

1. 進入時 `ascending(dataset, "coupler_flux")`，並有 `order_free` 測試。
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
交叉點會落在可達範圍的邊緣，那時就能直接量到週期。

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

**上機驗證（5Q4C，要先問）**：q1_q2、`measure=both`、b 從 −0.5 到 +0.34（2 mV）、300 次平均、`--no-update`。
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

## 4. 實驗 3：swap 讀 coupler 頻率（部分已定）

- **已定**：ramp 用鋸齒波，也就是線性慢升，接著突然回到 idle（慢邊絕熱轉移、快邊非絕熱，激發留在 qubit），
  在 idle 讀取。ramp 打在哪條線由參數 `ramp_on: coupler | probe` 決定，因為 coupler 也可能被設計在
  qubit 下方。QM 用 QUA 的 `ramp()` 就能產生這個波形。
- 序列：reset → 在探針的 xy 上打 coupler tone（saturation）→ 鋸齒波 ramp 越過交叉點 → 讀探針。
  f = f_c 時 P_e 出現峰值。
- ramp 的終點取實驗 1 的交叉點再加一點餘量。
- ramp 時間：依 Landau–Zener，g_qc 為 50 MHz 時 ≥ 約 60 ns，20 MHz 時 ≥ 約 350 ns，預設 500 ns。快邊以
  約 3 ns 估算，g = 50 MHz 時約有 20 % 的激發會漏回 coupler。
- tone 結束後，探針的 xy 不再播任何東西，所以 LO 可以分段掃描（做法見 §7 的 broadband）。換 band 時會把
  同一組 port pair 的另一顆一起帶走。
- 要避開探針自己的躍遷（f01，以及雙光子的 f02/2），否則會出現假峰。
- **待定**：頻率視窗怎麼給（絕對 [start, stop]，比照 broadband）、coupler tone 的功率與長度，以及寫回
  （coupler mode 的 `f_01_hz` = 目前 idle 下的 f_c）。

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
