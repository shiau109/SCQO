# coupler 狀態讀取：證據與討論稿（獨立 session 處理）

> 未追蹤的計畫文件。2026-09-26 從 `docs/flux-parking-plan.md` 拆出來。使用者決定 coupler 的部分
> 交給另一個 session，並且**等真的動到 coupler 再談**：§4 的三題都還沒定案，動手之前先問使用者。
> qubit 停泊的規格（`qubit_ramsey_flux_pulse`，BACKLOG F23）留在原文件，這份文件只引用它的結論。
> BACKLOG：F24（本題）、I26（`pair_zz_coupler` 的 frame）。
> 腳本與原始結果：`scqat/temp/coupler_scan/`（gitignored）；run 都存在 datastore，
> 標記為 `--tag coupler-scan`。

## 1. 資料（2026-09-26 晚，5Q4C / cd2 / qm_5q）

> 以下都是用 **DC** 移動 coupler 的物理量測，用來確認機制。qubit 那邊的規格已改用 pulse frame，
> 理由是 DC 會讓 x90 和 readout 離開它們校準時的 idle 點；coupler 的讀法依同一個理由也應該用
> pulse frame。

### 1.1 鄰居頻率對 coupler DC 的掃描（`coupler_scan.py`）

`q1_q2_c_z.idle_flux`（即 QUAM 的 `decouple_offset`，目前 0.16 V）以 20 mV 為一步 ping-pong 掃描。
每一點量兩次 Ramsey（6 MHz detuning / 4 µs / 201 點 / periodogram）：q1+q3 一起量，q2 單獨量
（q1 和 q2 不能同時處於疊加態，否則會帶進 ZZ）。**q3 不是這個 coupler 的鄰居，當作對照組。**
數值是相對各自 drive 的 err（kHz）：

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

中心點前後各量一次（相隔約 12 分鐘），差距 ≤ 3 kHz。0.24 V 時 q1/q2 的對比度塌掉了：qubit 被
推開好幾 MHz，x90 就不再共振。

### 1.2 兩個 coupler 偏壓下的 qubit DC apex（`apex_vs_coupler.py`）

每個偏壓 5 點加 1 個重複點，q1 與 q3 一起量。m 的定義：coupler 線每 1 V 等效於 qubit 自己的線
+m V，所以 apex 位置移動 −m·ΔV_c。

| coupler 0.16 → 0.08 V | apex **位置**移動 | apex **高度**移動（kHz） |
|---|---|---|
| q1（鄰居） | +4.36 mV → m₁ = +5.45% | **+524**（coupler 的 Lamb shift） |
| q3（對照組） | +5.73 mV → m₃ = +7.16% | +119 |

- 在 0.16 V 時，兩顆的 apex 都落在當天停泊點的 +0.03 / +0.07 mV 以內（相隔約 2.5 小時）。
- 重建驗證：原始值 = 高度 − c·(m·ΔV)²。q1：541 − 281 = 260（實測 256 / 261）；
  q3：124 − 610 = −486（實測 −488）。

## 2. 讀法

- **q3 的原始曲線是 coupler 線串進它自己 SQUID 的串擾。** 220 mV 範圍內都是拋物線（rms 殘差
  2.6 kHz），頂點 152.5 mV（q3 是在 coupler = 0.16 V 時停上 apex 的），曲率 −0.095 kHz/mV²。
  由此推得 |m| ≈ 7.4%，和 §1.2 的 7.16% 一致。
- **鄰居的原始曲線是兩樣東西的和**：串擾移動 apex 的**位置**，coupler 頻率的 Lamb shift 移動
  apex 的**高度**。原始曲線的頂點（q1 在 101 mV、q2 在 143 mV）兩者都不是。
- **coupler 的可觀測量是鄰居的 apex 高度**；apex 位置則順便給出有號的串擾係數。
- 用 m₁ 扣掉串擾，還原出 q1 的純 Lamb 曲線：頂點約 74 mV（40–100 mV 局部拋物線，曲率
  −0.055 kHz/mV²），到 idle 0.16 V 時斜率 −15.6 kHz/mV。所以 **q1_q2_c 自己的 DC apex 大約在
  0.074 V**（還原值，誤差估計 ±2 mV），idle 在它上方 86 mV，位在陡的那一側。
- q3 還原出來的 Lamb 部分是單調的，約 −1.4 kHz/mV。推測是 q1_q2_c 線串進了 q2_q3_c（coupler
  之間的串擾），尚未證實。
- 有號的 m 要看兩個來源偏壓下的 apex 位置。qubit 停在 apex 上時，用 `flux_component` 掃只給得出
  |m|。
- 歷史紀錄也對得上：09-17 與 09-20 兩條 coupler 各被改了 20–220 mV，同一段時間三顆 qubit 的
  `flux_offset` 跳了數 mV 到二十幾 mV。

## 3. 已經定下來、qubit 規格也依賴的結論

1. **巢狀的讀法**：coupler 的讀法是「在幾個 coupler 偏壓下，各跑一次鄰居的
   `qubit_ramsey_flux_pulse` apex 模式」。內層的 target 仍然是被量的 qubit，所以 qubit 實驗
   不需要「探針」欄位（這一點已經寫進 F23）。
2. **姊妹實驗以 pair 為 target**：`target_kinds = ("qubit_pair",)`，coupler 取 pair 的 coupler
   role，探針用 `measure: Literal["high","low"]`（前例是 `pair_zz_coupler`）。它有自己的
   estimator 與寫回（coupler 的 z），用 pulse frame：鄰居的 x90 在 idle，τ 期間同時播 coupler
   脈衝與鄰居的 z 脈衝。暫名 `pair_ramsey_coupler_flux_pulse`。
3. `flux_component` 維持只記錄：用 coupler 當來源時，它的頂點是兩個機制的混合。
4. 對 qubit 端的約束（已寫進 qubit 規格）：**先停 coupler，再停 qubit**；qubit 的
   `flux_offset`/`f_q_max_hz` 只在目前 coupler 偏壓下成立。

## 4. coupler 的狀態要怎麼讀（討論稿，未定案）

### 4.1 「coupler 狀態」分成三層

| 層 | 存在哪裡 | 會怎麼壞 |
|---|---|---|
| 它站在自己 arch 的哪裡 | `q1_q2_c_z.flux_offset`（fact，catalog 已有、目前沒有寫入者） | offset 漂移，跟 qubit 一樣 |
| 靜置點（J≈0 或 ZZ≈0） | `q1_q2_c_z.idle_flux`（= `decouple_offset`） | 隨第一層一起漂 |
| 閘的工作點 | 各 operation 的 composite knob（脈衝振幅疊在 idle 上） | 疊在 idle 上，所以也跟著漂 |

J 和 ZZ 只透過 f_c 依賴 coupler，也就是只依賴 (V − `flux_offset_c`)。所以只要讀到第一層，
第二、三層就可以跟著漂移走：`idle_flux_c ← flux_offset_c(新) + (idle − flux_offset_c)_參考`。
依「同一個物理量有多種量法、各有長短」的原則，每一層都會有不只一種量法。

### 4.2 可行的讀法（依成本排）

- **A. 鄰居 apex 高度對 coupler 偏壓**（§2 的讀法）：讀出第一層。在 idle 處，q1 的高度斜率是
  −15.6 kHz/mV，3 kHz 的重現性對應約 0.2 mV。成本：巢狀 3D（coupler 5 點 × qubit 5 點 × τ）。
- **A′. 先補償串擾再掃（virtual flux）**：播 coupler 脈衝的同時給鄰居 −m·b，讓鄰居維持在自己的
  apex 上，變成 2D。前提是先有 m。
- **B. 直接量靜置點**：ZZ 零點（`pair_zz_coupler`，要先修 I26）或 J 零點（`pair_swap_flux_map` /
  chevron）。每個 cooldown 做一次，記下它離 coupler apex 多遠。
- **C. 透過鄰居的 xy 直接做 coupler 光譜**：拿得到絕對的 f_c，但 5Q4C 的 QUAM 裡沒有 coupler 的
  drive element。

### 4.3 用 A 時的陷阱

- 其他 coupler 必須固定，探針最好選端點 qubit：q1_q2_c 用 q1，q2_q3_c 用 q3（q3_q4_c 固定在 0 V）。
- 探針的 apex 會隨 coupler 移動 −m·ΔV，內層視窗要跟著走，或者直接用 ∓12 mV。
- 高電壓那側有極點（f_c 逼近 f_q），掃描範圍要停在它之前。
- coupler apex 附近的曲率很小（−0.055 kHz/mV²），要 ±40 mV 才能把 apex 釘到 0.2–0.5 mV。
- 停泊是 DC 的事，需要的是 DC 串擾；pulse frame 量到的串擾和 DC 的差距（I25 那類）要一併比對。

### 4.4 要請使用者決定的事（動手前先問）

1. **靜置點的判準**：J=0 還是 ZZ=0（兩者一般不在同一點）？還是保持現值、只跟著漂移走？目前的
   0.16 V 是 09-15 從 swap map 挑出來的 J 零點。
2. **串擾矩陣**：要不要升級成 fact，並且每次動 DC 都做補償（virtual flux，架構上的大改）？還是
   只量出來，交給 procedure 在動過 coupler 之後重新停泊 qubit？存成 fact 的形狀（dict 或平行
   list）也要一起定。
3. **依賴順序**：姊妹實驗建立在 `qubit_ramsey_flux_pulse`（F23）之上，而 F23 又在 F25 之後。

## 5. trotter 那條線的阻塞點（背景）

swap 的共振點沒有漂（`qc_swap_flux_stark` 量到 −0.149922 ± 0.00007，存著的是 −0.15004），但同一個
coupler 脈衝現在只給出 θ = 0.141（標稱 0.30），代表 coupler 自己的工作點也移了。鏈要能跑，得重挑
兩對的 coupler 振幅（`pair_swap_flux_map` → `register_partial_swap --update --coupler-amp`，會寫
QUAM state.json）。使用者已明確表示不急著優化 trotter，先把地基打穩。
