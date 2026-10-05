# resonator_photon_emission：記錄 readout resonator 放出的單光子時間軌跡

> 狀態：規格草案（2026-10-02），等待核可。§13 還有幾點待決定。
> 範圍：只設計一個實驗。用 parametric sideband swap 在 readout resonator 裡製備一顆光子，
> 讓它經由 resonator 對傳輸線的耦合漏出去，再在 ADC 端記錄它的功率時間軌跡，作法類似 time of flight。
> 已定案（使用者，2026-10-01/02）：
> - 每發之間不等 qubit 熱化，只等 10 倍 resonator 光子壽命（10/κ）。
> - 5Q4C 輸出鏈只有 HEMT，沒有 paramp。
> - v1 只記錄，不寫回。
> - 讓 qubit 上 excited 的 π pulse 和 ADC 同時開始，以 prep 開始的時刻當軌跡的 0（使用者，2026-10-02）。
>
> 依據：
> - 5Q4C q3 sideband swap 的校正，見 `procedures/qubit-resonator-sideband-swap`。run 為 `20261001-204331-847` …
>   `205026-414`，q3 的 `macros["reset"]` 已在 2026-10-01 存進設定。
> - 類比實驗：
>   - `readout_time_of_flight`：ADC 時間軌跡，以及 acquisition 原點的取法。
>   - `qubit_parametric_drive_*`：z oscillator 的設定與 config patch。
>   - `single_shot_readout`：兩個 arm 的資料形狀。
> - QUAM `InOutMWChannel.measure_sliced`：MW 的 sliced demod 用四個 `demod.sliced`（II、IQ、QI、QQ）組成。

## 0. 目的與不做的事

**一次 run 要量到的東西：**
1. 光子功率的時間軌跡 ΔP(t) = ⟨|S(t)|²⟩_on − ⟨|S(t)|²⟩_off，包括 swap 期間的上升和之後的指數衰減。
2. 時域的 κ。這是 chevron 擬合與 spectroscopy 之外的第三種量法，可以裁決 procedure 的 Trap 7（兩個 κ 不一致）。
3. 光子到達時間，也就是 z 路徑與 readout 輸出路徑的延遲差。
4. **讀取鏈換算到 chip 端的雜訊光子數 n_eff = n_noise/η**。這個量與增益無關，是這條讀取鏈第一次量到量測效率。
5. 同調部分 |⟨S⟩|²，用來檢查 Fock 態的 ⟨a⟩ = 0。

**不做的事（落地時寫進 BACKLOG）：**
- 多 target 同時量。
- FPGA 上做單一時間模態投影（§1.4）。
- 光子數的絕對校正，也就是用 Stark map 定增益。
- 光子的高階矩：⟨a²⟩、g²(0)、Wigner。
- 加 herald readout。
- Qblox：probe 依名稱拒絕。

## 1. 物理

### 1.1 製備：一顆 Fock 光子，⟨a⟩ = 0

先用 x180 把 q3 打到 |e,0⟩，再做 100 ns 的 sideband swap，得到 |g,1⟩，也就是 resonator 裡一顆光子的 Fock 態。
對 Fock 態來說，**不論相位能不能控制，⟨a⟩ 都是 0**，所以平均 I/Q 會得到 0。
要量的是每發的功率 |S|² = I² + Q²，再對所有 shot 平均。⟨|S|²⟩ ≠ |⟨S⟩|²，所以不能先平均 IQ 再算振幅。
平均後的 I/Q 仍然存下來，只當檢查用（§6 的 `coherent_ratio`）。

如果改用 x90，製備出來的是 (|0⟩+|1⟩)/√2，這時 ⟨a⟩ ≠ 0。它在 shot 之間會不會留下來，取決於 z oscillator 與
readout frame 的相位是否可重現。這是 §10 的驗證項。

### 1.2 時間包絡（5Q4C q3，2026-10-01 實測 g₂/2π = 2.77 MHz、κ/2π = 1.62 MHz）

- **swap 期間（0–100 ns）**：qubit 振幅與光子振幅滿足耦合方程，resonator 同時以 κ 漏光。這段漏掉 **40%**，
  光子流的峰值約在 82 ns。
- **swap 之後**：剩下的 **60%** 以 e^{−κt} 衰減，1/κ = 98 ns。
- 95% 的光子在約 360 ns 內離開。

光子頻率是 qubit 在 g 時的 resonator 頻率，也就是 `q3_res.f_dress0_hz` = 5867.77 MHz。它和 readout knob 5866.57 MHz
差 1.2 MHz。

### 1.3 效率與雜訊

- **η**：readout resonator 以 hanger 方式掛在 feedline 上，光子會往兩個方向走，只有一半朝放大器去，所以 η ≲ 0.5。
- **n_noise**：只有 HEMT 時約 20 顆光子/模態，因此 **n_eff = n_noise/η ≈ 40**。
- **換算關係**：每個 slice 是長度 L 的 boxcar demod，時間–頻寬積約為 1，等於一個模態。
  - off 的功率是 P_off,k = G·n_noise/L。
  - 光子在 slice k 的含量為 p_k 時，ΔP_k = G·η·p_k/L。
  - 光子頻寬 κ 遠小於 slice 頻寬 1/L，所以 Σ_k p_k = 1。
  - 因此 **n_eff = P_off,k / Σ_k ΔP_k**，增益 G 在比值裡消掉。

### 1.4 先濾波再平方；分 bin 的代價

- **原始 ADC 先平方會多付一個 √(B·T_bin)。** 1 GS/s 的原始 ADC 先平方再累加，SNR 比先 demod 再平方差這個因子；
  40 ns 時約 6，等於 shots 多約 40 倍。所以只用 `demod.sliced`，slice 長度決定濾波頻寬。
- **分 bin 平方會丟掉一部分 SNR。** 光子分散在多個 bin，每個 bin 各自平方，SNR² 只保留 Σp_k²：
  40 ns 時是 0.156，20 ns 時是 0.080。
  若先用光子包絡做加權（單一時間模態投影 Σ w_k S_k）再平方，可以保留全部 SNR²，overlap² = 0.993。
  v1 不做這件事，理由見 §13。不做也夠用，見 §9 的預算。

## 2. 序列（每一發，QM）與 shot 週期

```
q.resonator: update_frequency(IF_photon)      # 程式開頭設一次，對準 f_dress0
for batch in n_batches:                       # 每批 16384 發
  累加器歸零
  for n in 16384:
    for arm in (0: off, 1: on):               # Python 展開，逐發交替
      align(q.xy, q.z, q.resonator)
      # ---- t = 0：π pulse 與 ADC 同一個 clock cycle 開始 ----
      q.xy:        arm 1: play(prep_operation)          # x180（預設）或 x90；q3 是 16 ns
                   arm 0: wait 同樣長度                  # 兩個 arm 的時間軸完全相同
      q.resonator: measure("photon_listen", demod.sliced ×4)   # 振幅 0，長 window_ns
      q.z:         wait(t_prep + swap_delay_ns)          # prep 結束後才 swap
                   q.macros[swap_operation].apply()     # 355 MHz × 0.105 V × 100 ns（q3）
      align；逐 slice 的整數累加（§5）
      wait(ring-down 不足的部分)
  每批的累加器 save 到 stream
```

**「對齊」在 QM 上的意思：** π pulse 的 `play` 和 listen 的 `measure` 放在同一個 QUA 時刻。
acquisition 由 resonator element 的 `time_of_flight`（q3：384 ns）往後推，所以 sample 0 對應的是「在 t = 0 離開
readout 輸出埠的訊號繞一圈回來的時刻」。

這樣對齊的是儀器的時間軸，不是 chip 上的物理時刻。三條路徑在 chip 上各有自己的延遲：
- xy：MW-FEM con1/6/4，band 2，有自己的 port `delay`。
- readout 輸出：con1/6/1。
- z：LF-FEM，靠 `flux_delay_s` = 110 ns 對齊 xy。

所以光子在軌跡上出現的時間 = t_prep + swap_delay + (d_z − d_out)；z 已用 xyz delay 對齊 xy，因此這個差也就是
(d_xy − d_out)。不能假設它是 0，要由 estimator 量成 `latency_offset_ns`（§6）。

**shot 週期：** swap 本身就把 qubit 歸零，量到的 P(e)(100 ns) 已在讀取底線。下一發只需等 resonator 的光子漏掉。

- 等待時間取 `readout_depletion_s` knob，也就是 10/(2πκ)。q3 目前是 820 ns。
- 讀法沿用 `_depletion.depletion_wait_ns` 的優先順序：per-run 的 `readout_depletion_ns` 優先於 knob。
  兩者都沒有就**依名稱拒絕**，因為殘留光子會混進下一發。
- 計時的起點是 swap 結束，終點是下一發 window 打開。window 在 swap 之後還有
  window − t_prep − swap_delay − T = 1200 − 16 − 0 − 100 = 1084 ns，已經約等於 11/κ，所以 window 之後不必再等。
- 週期 = window（1.2 µs）加上 FPGA 運算時間。gateway simulator 實測 4.23 µs（§10），其中運算佔 3.03 µs。
- 比起 thermal wait（229 µs）快約 54 倍。

**qubit 起始狀態：** 前一發 swap 的殘留 ε，加上一個週期內的熱激發 Γ↑·週期 ≈ p_th·(3 µs/23 µs)，合計 < 1%，
比 thermal wait 還冷。

- off 發一定接在 on 發之後，所以會帶到 on 發的 ε，差值為 on − off ≈ 1 − 2ε。
- job 的第一發從熱態開始，可以忽略。

## 3. Parameters（SCQO）

| 欄位 | 預設 | 說明 |
|---|---|---|
| `targets` | 一顆 | v1 只接受單一 flux_transmon，帶 readout 和 drive |
| `num_averages` | 5_000_000 | **每個 arm** 的發數。QM 會補滿到整批（16384 的倍數），實際發數記在 attrs |
| `prep_operation` | `"x180"` | `Literal["x180", "x90"]`。x90 用於 §10 的線性與相位驗證 |
| `swap_operation` | `"reset"` | qubit 的 macro 名稱，必須是 `ParametricReset`；沒有就依名稱拒絕 |
| `window_ns` | 1200 | listen window 長度，從 π pulse 開始算，必須是 `slice_ns` 的倍數 |
| `swap_delay_ns` | 0 | prep 結束到 swap 開始的間隔。4 的倍數，且 t_prep + swap_delay + swap 長度 < window。設大於 0 時，同一發就有 swap 前的基線，也能看到 swap 前經 Purcell 漏出的少量光子 |
| `slice_ns` | 40 | slice 長度，4 的倍數，≥ 16 |
| `readout_depletion_ns` | None | ring-down 的 per-run 覆寫，None 時用 knob（§2） |

**刻意不放的欄位：**
- `reset_method` / thermal 等待：shot 間隔改由 resonator ring-down 決定。
- 任何 QM 數值欄位：整數位移由 probe 自動量測（§5）。

## 4. 資料形狀（DatasetContract）

- **維度：** `target` × `arm` × `time_ns`。
  - `arm`：0 = 參考（不做 prep），1 = 有 prep。命名見 §13。
  - `time_ns`：slice 中心，以 π pulse 開始（= window 打開）為 0。
- **變數：**
  - `power`：每發 |S_k|² 的平均，單位 V²，用 slice 長度做 demod→volts 換算。
  - `power_err`：由批間散佈算出的標準誤差。
  - `I`、`Q`：同調平均。
- **attrs：** 實際發數、`int_shift_bits`、`noise_rms_lsb`、`f_listen_hz`、swap 的 (f, A, T)（取自 macro）、
  `prep_len_ns`（prep 脈衝長度）、`swap_start_ns`（= prep_len + swap_delay，QUA 時間軸上的 swap 起點）、
  `ringdown_ns`、實測的 `cycle_ns`（wall time ÷ 發數）。

## 5. QM probe：FPGA 整數累加與自動量級

**為什麼不能交給 stream processing：** 每發 2×M = 60 個值，週期 2–3 µs 時約 2e7 個值/秒，超過 stream processing
的處理量（大約 1e6–1e7/s）。所以平方和累加在 FPGA 上做，stream processing 只處理每批的總和。

**為什麼不能用 fixed 平方：**
- q3 single-shot（800 ns 全積分）的雜訊 σ = 4.4e-5（run `20261001-192858-889`）。
- 換成 40 ns slice 時 σ ≈ 9.8e-6，平方約 9.7e-11，小於 4.28 fixed 的 LSB 3.7e-9，會被截成 0。

**每個 slice 的運算：**
- I_k = II_k + IQ_k，Q_k = QI_k + QQ_k。這是 MW sliced demod 四件組的組合方式，與 QUAM `measure_sliced` 相同。
- i = `Cast.unsafe_cast_int(I_k) >> s`（等於 ×2²⁸ 再 ÷2ˢ），q 同理。
- `accP[arm][k] += i·i + q·q`，`accI[arm][k] += i`，`accQ[arm][k] += q`，全部是 int32。

**量級條件：** 一批 16384 發的總和約為 16384 × 2σ²_lsb，要小於 2³⁰，所以 σ_lsb ≤ 181。目標區間是 σ_lsb ∈ [64, 181]，
此時量化 LSB/σ ≤ 1.6%。

**自動量級（同一個 probe 的第一個 job）：**
1. 只跑 off arm 1024 發，把 fixed 的 I_k 逐發 stream 出來（約 6e4 個值）。
2. 算出 σ，取 s = ⌈log₂(σ·2²⁸/128)⌉。
3. q3 的預估：σ_int ≈ 2640，所以 s = 4，σ_lsb ≈ 165。
4. 把 s 記進 attrs，再編第二個 job 正式量。

**stream processing 的工作：**
- 每批 save 6 個長度 M 的 int 陣列，每批只有 6·M 個值。
- `.buffer(M).average()` 給出平均。
- `(x*x).buffer(M).average()` 給出批間散佈，換算成 `power_err`。

**config patch，只改產生出來的 config dict，絕不改 QUAM tree：**
- 在 resonator element 加上 `photon_listen` operation：振幅 0 的常數波形，長 `window_ns`。
- 積分權重用 window 長度的常數 cos/sin/minus_sin。
- z element 沒有 oscillator 時，用 `ensure_flux_oscillators` 補上。q3 已經是 IF 0，這一步只是保持通用。

**事前檢查：**
- target 沒有 `macros[swap_operation]`，或它不是 `ParametricReset`：依名稱拒絕。
- 沒有 ring-down：依名稱拒絕。
- 以 `f_dress0_hz` 求 IF_photon；fact 不存在時退回 readout 頻率，並在 attrs 註明。

## 6. Estimator（scqat `photon_emission`，1:1 綁定）

- **輸入：** ΔP_k = power[arm=1] − power[arm=0]，σ_k 由兩個 arm 的 `power_err` 合成。
- **模型：** ΔP_k = A·∫_bin k f(t − t_arr) dt + c。
  - g 由 κ 決定：macro 是照「第一個零點落在 T」校正的，所以 g = g(κ, T) 是 t*(g, κ) = T 的解。
  - f(t) = κ|c₁(t)|²（0 ≤ t ≤ T），之後是 κ|c₁(T)|²·e^{−κ(t−T)}。
  - 自由參數：A、κ、t_arr、c。
  - 初值：κ 取 `kappa_tot_hz` fact，t_arr 取 `swap_start_ns`，A 取 ΣΔP。
- **fit keys：**

| key | 內容 |
|---|---|
| `kappa_hz`、`kappa_hz_stderr` | κ/2π，時域 |
| `arrival_ns` | t_arr：swap 在 ADC 時間軸上真正開始的時刻，從 π pulse 開始算 |
| `latency_offset_ns` | t_arr − `swap_start_ns`，即 (d_z − d_out) ≈ (d_xy − d_out)（§2） |
| `photon_power`、`photon_snr` | A 與 A/σ_A |
| `noise_photons_eff` | off arm 的 P_off 中位數 ÷ A（§1.3） |
| `coherent_ratio` | Σ_k \|⟨S_k⟩_on\|² / Σ_k ΔP_k，x180 時應 ≈ 0 |
| `window_coverage` | 模型下光子落在 window 內的比例 |

- **flags：**
  - `tail_truncated`：coverage < 0.99。
  - `quantization_coarse`：σ_lsb < 64。
  - `overflow_suspect`：任一批 accP < 0。平方和不可能是負的，出現負值就是 wrap。
- **outcome：** `photon_snr` ≥ 5 且擬合收斂時為 SUCCESSFUL。
- **圖（原始資料在前）：**
  1. P_on、P_off 對時間，標出 prep 與 swap 在 QUA 時間軸上的區間。
  2. ΔP 加擬合與殘差。
  3. 兩個 arm 的同調 |⟨S_k⟩|²，與 ΔP 對照。

## 7. update()：無

record-only。κ 是否作為 `kappa_tot_hz` 的另一種量法提出 suggestion，等看過硬體資料再決定（complementary methods）。

## 8. simulate()

用 §6 的模型合成 ΔP：κ 取 fact，A 任取，n_eff = 40，每個 bin 的雜訊由 `num_averages` 決定，同調部分為 0。
離線 end-to-end（simulate → estimate）要能把 κ、t_arr 找回來。

## 9. 5Q4C q3 的數字與預算（n_eff ≈ 40）

| 每 arm 發數 | 光子 SNR（40 ns bin 擬合） | 40 ns 峰值 bin SNR | 20 ns 峰值 bin SNR | 時間（4.23 µs 週期，40 ns slice） |
|---|---|---|---|---|
| 1e6 | 7 | 4.3 | 2.3 | 8 s |
| **5e6** | **16** | **9.5** | **5.1** | **42 s** |
| 2e7 | 31 | 19 | 10 | 2.8 min |

- 「光子 SNR」= √(N/2)/n_eff × √0.156（§1.4 分 bin 的代價）。之後若做單模投影，會是這個值的 2.5 倍。
- 改用 20 ns slice 時 slice 數加倍，FPGA 運算時間也大約加倍，週期約 7 µs。
- n_eff 實際落在 20–60 都有可能。第一個 run 就會量出來，之後再依它調整發數。

## 10. 驗證

1. **離線：** simulate → estimate 找回 κ 與 t_arr（誤差內）。量級邏輯的單元測試：給定 σ，s 的選法要讓 batch 總和 < 2³⁰。
2. **`scqo run --preview`（gateway simulator）：**
   - 能編譯。
   - 時間軸上 x180 與 listen 的 `measure` 在同一個 clock cycle 開始，listen 振幅為 0。
   - z swap 在 `swap_start_ns` 開始，也就是 x180 結束之後。
   - 量出週期長度與 FPGA 運算時間。
   **prototype 的結果（2026-10-03，scratchpad 的 QUA 程式，直接送 gateway simulator，q3）：**
   - 能編譯也能模擬：一個 `measure` 帶四個 `demod.sliced`、int 轉型與位移、FPGA 上用 `while_` 自動決定位移量。
     自動量級因此放在同一個程式裡，不必拆成兩個 job，`--preview` 的標準 probe 形狀也保得住。
   - **core 會串行。** `q3.xy` 和 `q3.resonator` 在 state.json 裡共用 core `"c"`，同一個 core 的 element 不能同時播。
     實測 listen window 要等 x180 播完才打開，晚了 16 ns。
     解法是在產生的 config 上把 resonator element 換到自己的 core，只 patch config，不動 QUAM tree。
   - **port delay 差 20 ns。** 換 core 之後兩者在同一個 QUA cycle 開始，但 xy 埠（con1/6/4）的 `delay` 是 20 ns，
     readout 輸出埠（con1/6/1）是 0，所以在儀器輸出端 x180 比 ADC 的參考時刻晚 20 ns。
     讓 listen 晚 (xy delay − readout delay) 再開，兩者在接頭上就對齊，模擬結果是 +1 ns。
   - **z 在輸出端看起來和 x180 同時開始。** 程式上 swap 排在 x180 之後 16 ns，但 z 埠 delay 110 ns、xy 埠 20 ns
     是 xyz delay 校正出來的，z 路徑實際多約 17 ns。到 chip 上仍是 x180 之後才 swap。
   - **shot 間隔 4.23 µs** = 1.20 µs window + 3.03 µs FPGA 運算（30 個 slice，每個約 100 ns）。
     5e6 發/arm 約 42 秒。
   - simulator 的 ADC 輸入是 0，所以算術路徑上的數值（位移量、累加值）沒有被驗到，要等硬體首測。
3. **硬體首測（1e6/arm，不到 1 分鐘）：**
   - P_off 平坦。
   - `coherent_ratio` < 0.05。
   - ΔP 在 swap 期間上升、之後衰減，形狀與 §1.2 一致。
   - `latency_offset_ns` 只有幾十 ns 以內。MW band 不同的 port 之間曾量到約 19 ns 的延遲差，所以非零是預期的。
   - 再跑一次 `swap_delay_ns` = 200：ΔP 應整段往後平移 200 ns，而 `latency_offset_ns` 不變。
     這可以確認時間原點，也能看到 swap 前的基線。
4. **x90 驗證：**
   - `photon_power` 應為 x180 的 0.5 倍（誤差內），驗證這是線性功率量測。
   - `coherent_ratio` 若接近 0，表示每發相位不可重現；若接近 0.5，表示可重現。這直接回答「相位能不能控制」。
5. **κ 交叉比對：** 時域 κ 對照 chevron 的 1.62–1.66 MHz 與 spectroscopy 的 1.94 MHz（procedure Trap 7）。
6. **n_eff 合理性：** 只有 HEMT 時應落在 20–60。

**不做的對照：** 關掉 swap 或讓 swap 失諧。這兩者都會讓 qubit 不再被歸零，破壞 shot 週期的前提。
對照改用 off arm，以及 `swap_delay_ns` > 0 時同一發 swap 前的那一段。

## 11. 陷阱

1. **Fock 態的 ⟨a⟩ = 0。** 平均 IQ 本來就是 0，不是因為相位失控。|⟨S⟩|² 不能拿來代表 ⟨|S|²⟩。
2. **先濾波再平方。** 對原始 ADC 先平方，40 ns 時 SNR 少約 6 倍（§1.4）。
3. **fixed 平方會下溢。** 一定要先轉 int 再位移；量級由 probe 自動量測，overflow 由負的總和偵測。
4. **stream processing 的處理量。** 逐發逐 slice 送出去，在快週期下塞不下，所以只送批總和。
5. **時間原點是 QUA 時間軸，不是 chip 時間。** π pulse 和 ADC 在 QUA 上同時開始，但 xy、readout 輸出、z 三條路徑的
   延遲各不相同。光子出現在 t_prep + swap_delay + (d_z − d_out)，要從資料讀出 `arrival_ns`，不能假設。
6. **ring-down 不足。** 殘留光子會變成下一發的假訊號，尤其是 off 發。沒有 knob 就拒絕，不猜。
7. **arm 順序。** off 發接在 on 發之後，帶到 ε，所以 ΔP ≈ (1 − 2ε)。
8. **hanger 分流。** η 最多約 0.5，這是物理上限，不是校正錯誤。
9. **listen pulse 必須是 0 振幅。** feedline 上其他四個 readout 在這段時間也不能發。v1 只接受單一 target，自然滿足。
10. **I33。** macro 播完後 z oscillator 留在 355 MHz。本實驗的 q3.z 只播 swap，所以不受影響。

## 12. 測試與落地順序（scqat → SCQO → scqo-qm，逐 repo 用 pathspec commit）

1. **scqat：** `estimators/photon_emission/{estimator,visualization}.py`。測試：合成資料找回 κ、t_arr、A；三個 flag 各自觸發。
2. **SCQO：** `scqo/experiments/resonator_photon_emission.py`，含物理半部、contract、simulate 與 Parameters 驗證。
   - `uv run pytest tests/test_model_experiments.py -k photon_emission -q` 加上 `tests/test_contract.py`。
   - 跑 `python scripts/update_docs.py`，更新 census 與 estimator map。
3. **scqo-qm：** `scqo_qm/experiments/resonator_photon_emission.py`（probe）。
   - 結構測試，比對編譯出的程式：
     - x180 只出現在 arm 1。
     - listen 振幅為 0。
     - 有 update_frequency 到 f_dress0。
     - prep 的 `play` 和 listen 的 `measure` 在同一個 QUA 時刻，swap 在 prep 加 `swap_delay_ns` 之後。
     - config patch 不會漏進 QUAM tree。
   - 拒絕情境：沒有 macro、沒有 ring-down、Qblox。
   - 在 `.venv-qm` 跑全套（scqo-qm 沒有 CI）。
4. 最後一個 commit 之後寫 `SCQO/RELEASES.d/resonator-photon-emission.toml`，並把 §0 的「不做的事」寫進 BACKLOG。

## 13. 待你決定（附我的建議）

1. **名稱 `resonator_photon_emission`。** 建議用這個。量的是 resonator 的輸出場；swap 只是製備。
2. **`arm` 軸的命名。** 建議用 `arm`。不用 `prepared_state` 的原因是 x90 時 1 不代表 |e⟩，借用會誤導。
3. **v1 就放 `prep_operation = x90`。** 建議要放。§10 的線性驗證和相位問題都靠它，成本只是一個 Literal 欄位。
4. **自動量級（兩個 job）或固定位移參數。** 建議自動量級。量級由輸入鏈決定，不該讓操作者猜，也不要把 QM 數值欄位放進中性的 Parameters。
5. **FPGA 單模投影延後。** 建議延後，寫進 BACKLOG。它要另一組整數權重和位移，而 v1 的分 bin 擬合在 5e6 發時已有 SNR 16。
   等第一次硬體量出 n_eff 再決定值不值得做。
