# 實驗說明文件：每個實驗一份（序列示意圖、預期結果、理論）

> 狀態：全部核可（2026-10-04）。§8 五點都照建議；§9 的分類同日追加，三點也已決定。
> 階段 0 同日在 worktree `feature/experiment-docs` 實作完成，尚未提交、尚未合併回 main，
> 實作紀錄與待你過目的事在 §10。
> 前置條件、產出與後端特有規則的設計在 §11，同日核可並實作，紀錄在 §12；理論章節的寫法與深度暫不決定。
> 範圍：讓 `scqo.experiments` 裡每個已註冊實驗都有一份說明文件，固定包含脈衝序列示意圖、
> 預期結果、背後的理論。本文定檔案配置、程式架構、防止文件過期的檢查，以及分批順序。
> 不做的事：不改任何實驗的物理或 `probe()`；不取代 `procedures/`（跨實驗的流程）與
> TUTORIAL（教工具怎麼用）。
> 已決定的事在 §8 與 §9.5；共用實驗與專題實驗的分類在 §9。

## 0. 現況（已對照程式）

- 核心有 51 個已註冊實驗，一個實驗一個模組 `scqo/experiments/<name>.py`。QM 驅動 51 個都有
  `probe()`，Qblox 驅動有其中 28 個。另一個工作階段正在加第 52 個
  （`qubit_ramsey_flux_crosstalk_pulse`，尚未提交），本文的數量以已提交的 51 個為準。
- 每個實驗已有的說明只有兩種：類別上的 `description`（給目錄用的一段話）與 Parameters 每個欄位的
  說明，兩者都由 `scqo run <name> --help` 顯示。
- 物理說明散在六個地方：核心模組的 docstring、兩個驅動的 docstring、scqat 估計器、TUTORIAL §12、
  `docs/*-plan.md`、`procedures/`。沒有任何一處是「這個實驗」的完整說明。
- **序列只存在於驅動的 `probe()` 裡**（QUA 程式或 Qblox 的 `Schedule`）。核心沒有中立的序列描述，
  只有個別的時序輔助，例如 `_overlap.py`，它的 docstring 裡有一張手畫的文字圖。
- `scqo run <name> --preview` 輸出的是廠商原生的東西：QM 是 `qua_script.py`，加上要連閘道才有的
  `simulated_waveforms.html`；Qblox 是 `pulse_diagram.html` 與 `timing_table.html`，上限 256 個
  shot。模擬後端直接拒絕 preview。這些需要真實的硬體設定、兩家長得不一樣、而且只有 QM 有的 23 個
  實驗在 Qblox 沒有圖，所以不適合當文件的圖源。
- 每個核心實驗都有 `simulate()`。`tests/test_model_experiments.py::test_every_experiment_runs_clean`
  只給 `targets` 就能在模擬後端跑完全部 51 個；有資料庫時 scqat 的圖會寫到
  `analysis/<target>/*.png`。所以預期結果的圖可以自動產生。
- 防止文件過期的機制已有先例：`scripts/update_docs.py` 產生 CLAUDE.md 的兩個區塊，
  `tests/test_docs_current.py` 檢查；另有「只能縮小的清單」（`tests/test_one_estimator_per_experiment.py`）。
- 檢視器是 FastAPI 加 Jinja2，目前沒有實驗頁，`viewer` 這組相依套件裡也沒有 Markdown 轉換器。

## 1. 原則

1. **文件跟程式住在一起，同一次提交一起改。** 與 `procedures/README.md` 的規則相同。
2. **手寫的只有散文**：目的、理論、怎麼讀結果、陷阱。能從程式導出的不抄進文件，包括參數表、
   估計器綁定、能力分類、哪個後端有實作。這些由 `--help` 與檢視器當場組出來。
   理由是這棵樹有多個代理同時工作：`qubit_reset` 這個能力的欄位被 42 個實驗繼承，如果參數表
   抄進每份文件，改一行說明就要重新產生 42 份文件，直接撞上「一個代理一組檔案」的規則。
3. **圖都是產生的，不手畫。** 序列圖來自核心裡的中立宣告；預期結果圖來自模擬後端加 scqat 的圖。
4. **清冊測試加上只能縮小的未完成清單。** 可以分批鋪開，而且新實驗沒帶文件就過不了測試。

## 2. 檔案配置

```
SCQO/
  scqo/
    sequence_diagram.py        # 新。序列示意圖的資料結構與 SVG 輸出，只用標準庫
    experiment_docs.py         # 新。讀取並驗證一份文件（front matter、章節），
                               #   並組出 CLI 與檢視器要顯示的資料
    experiment.py              # Experiment 增加 classmethod sequence_diagram(params)
    experiments/
      <name>.py                # 每個實驗實作 sequence_diagram，約 8 到 15 行
      _capabilities/*.py       # 共用片段：reset、measure、磁通視窗
      _docs/
        README.md              # 產生。依家族分組的索引
        <name>/
          README.md            # 手寫。固定章節，見 §5
          sequence.svg         # 產生。逐位元組比對
          sequence-<variant>.svg   # 產生。有參數變體時才有
          expected.png         # 產生（模擬），或手動放入（硬體實測）
  scripts/update_docs.py       # 增加 experiment-docs：產生 SVG、PNG、索引；支援 --check
  tests/test_experiment_docs.py    # 清冊、章節、掃描軸、SVG 是否最新、圖檔是否存在
```

文件放在套件裡面（`scqo/experiments/_docs/`）而不是版本庫頂層，理由與 `viewer/templates/` 相同：
跟著套件走，CLI 與檢視器不必知道版本庫的目錄結構就找得到。每個實驗一個資料夾、檔名用
`README.md`，在 GitHub 上點進資料夾就直接顯示。

三個驅動都不用改：文件全部在 SCQO。

## 3. 序列示意圖

### 3.1 為什麼用核心的中立宣告

三個來源比較：

| 來源 | 問題 |
|---|---|
| 廠商的 preview 輸出 | 需要硬體設定；QM 的波形圖要連閘道；Qblox 上限 256 個 shot；兩家不同；是波形不是示意圖 |
| 每個實驗手畫一張 | 51 張，風格不一，程式改了圖不會跟著改 |
| **核心宣告加一個繪圖器** | 每個實驗多寫十行左右；圖的風格一致；宣告就在物理那一半旁邊 |

第三種還有一個附帶的好處。CLAUDE.md 的「後端一致」規則要求兩個 `probe()` 實現同一個序列，但目前
那個「同一個序列」沒有寫在任何地方，只能拿兩份廠商程式互相比。中立宣告就是那份規格。

實例：寫 `qubit_ramsey` 的宣告時必須先決定第一個脈衝是哪一個。現在 QM 用 `y90`
（`scqo-qm/scqo_qm/experiments/qubit_ramsey.py:102`），Qblox 用 `X90`
（`scqo-qblox/scqo_qblox/experiments/qubit_ramsey.py:60`）。這對擬合有沒有影響我沒有查，
但它正是宣告會逼出來的那種差異，留到樣板階段處理。

### 3.2 資料結構

```python
# scqo/sequence_diagram.py - stdlib only; a SCHEMATIC, never an executable sequence

@dataclass(frozen=True)
class Block:
    lane: str                  # lane key
    label: str                 # text on the block: "X/2", "pi", "swap", "readout"
    shape: Literal["gate", "square", "flattop", "tone", "acquire", "wait", "offset"]
    swept: str | None = None   # the sweep AXIS this block varies with (a Contract.sweeps name)
    note: str | None = None    # footnote text

class SequenceDiagram:
    def __init__(self, lanes: dict[str, str]) -> None: ...   # key -> label
    def step(self, *blocks: Block) -> None: ...              # one time column; simultaneous
    def repeat(self, label: str): ...                        # context manager: "x N (num_swaps)"
    def swept_axes(self) -> set[str]: ...

def render_svg(diagram: SequenceDiagram) -> str: ...         # deterministic text
```

幾個刻意的選擇：

- **軌道是角色，不是裝置名稱。** 單比特用 `q.xy`、`q.z`、`q.ro`；比特對用 `control.xy`、
  `target.xy`、`control.z`、`coupler.z`。文件不綁特定晶片。
- **不按比例。** 一欄是一個時間步，寬度只是示意。被掃描的方塊畫雙箭頭並標上軸名。
- **只用標準庫輸出 SVG 文字。** 不用 matplotlib，因為它的輸出會隨版本變，沒辦法逐位元組比對。
- **`sequence_diagram` 是 classmethod，只吃 Parameters。** 不讀裝置、不需要後端，所以產生文件與
  跑測試都不用建 Session；參數選項（例如 `readout_overlap`、`reset_method`）可以畫成變體。

### 3.3 實驗這一側怎麼寫

```python
# scqo/experiments/qubit_ramsey.py
@classmethod
def sequence_diagram(cls, params):
    d = SequenceDiagram({"drive": "q.xy", "readout": "q.ro"})
    reset_block(d, params)                    # _capabilities/qubit_reset.py
    d.step(Block("drive", "X/2", "gate"))
    d.step(Block("drive", "tau", "wait", swept="idle_time_ns"))
    d.step(Block("drive", "X/2", "gate",
                 note="phase = -2*pi * frequency_detuning_hz * tau"))
    measure_block(d, params)                  # _capabilities/state_readout.py
    return d
```

重設與讀出這種每個實驗都有的片段放在對應的能力模組裡。那裡本來就是 Parameters mixin、資料集
契約片段、模擬輔助的家，多一個示意圖片段是同一個模式。

### 3.4 示意圖與程式的連結

宣告是第二份描述，`probe()` 才是實際執行的東西，所以要有東西拉住它：

- **每個 `Contract.sweeps` 的軸都必須標在某個方塊或重複括號上。** 新增掃描軸而沒改圖，測試會失敗。
- **`sequence.svg` 逐位元組等於現場重新輸出的結果。** 改了宣告沒重新產生，測試會失敗。
- **規則**：`probe()` 的脈衝順序變了，同一次提交改宣告。寫進兩個驅動的「新增實驗」步驟。
- **不在這次範圍**：自動比對宣告與驅動編譯出來的序列。兩個驅動各有一個結構測試可當先例
  （`test_sequential_probe.py`、`test_sequential_timing.py`），通用的比對器留到之後。

## 4. 預期結果

- `python scripts/update_docs.py --figures [<name> ...]`：用 `scqo.testing` 的示範裝置與模擬後端，
  在暫存的資料目錄跑一次 `session.run(name, {"targets": ...}, update="none")`，把 scqat 寫出的圖
  複製成 `_docs/<name>/expected.png`。挑哪一張由 front matter 的 `expected_figure` 指定。
  好處是文件裡的圖跟操作者在 run 資料夾裡看到的是同一種圖。
- 選目標的邏輯現在有兩份：`cli/_backends.default_targets` 與測試裡的 `_targets_for`。產生器沿用
  其中一份，不寫第三份。
- **PNG 不做逐位元組比對，只檢查檔案存在。** matplotlib 的輸出會隨版本變，位元組比對只會製造
  假警報。重新產生的時機：該實驗的 `simulate()` 或估計器的圖改了，以及每次發布前。
- **可以換成硬體實測的圖。** front matter 寫 `expected: hardware <chip> <date> <run_id>`，
  產生器就不覆蓋它。有些實驗的 `simulate()` 很粗略，實測圖更有說服力。
- 產生時順便核對：文件裡列出的 fit 鍵若不在這次模擬的 `result.fit` 裡，直接報錯。

這一節的手寫部分：圖怎麼讀；每個 fit 鍵的意義，以及 `update()` 把它寫到哪裡（旋鈕、事實、
監測值）；判定成功的條件；常見的失敗長什麼樣。

## 5. 文件範本

```yaml
---
experiment: qubit_ramsey            # = the folder name = the registered name
validated: hardware <chip> <date>   # offline | hardware <chip> <date> | unverified
expected: simulated                 # or: hardware <chip> <date> <run_id>
expected_figure: time_domain        # which scqat figure becomes expected.png
---
```

front matter 只放單層的 `key: value`。SCQO 的相依套件裡沒有 YAML 解析器，單層的格式用幾行程式就能讀，
GitHub 也照樣顯示成表格。需要巢狀結構的參數變體改放在類別上，由 Parameters 驗證：

```python
# scqo/experiments/qubit_ramsey.py
doc_variants: ClassVar[dict[str, dict]] = {"beat": {"ramsey_model": "beat"}}
```

`validated` 沿用升級檢查表已有的三種寫法。正文固定七節，順序不變，讓人與代理都能直接跳到要的那節：

1. **Purpose**：回答什麼問題；執行前要先校正好什麼；結果餵給哪個實驗。
2. **Pulse sequence**：`sequence.svg`，加上圖說：掃的是什麼、迴圈順序、兩個後端寫法上的差別。
3. **Theory**：座標系與哈密頓量、估計器擬合的訊號模型（寫出公式）、成立的假設與適用範圍。
4. **Expected result**：`expected.png`，加上 §4 列的手寫內容。
5. **Traps**：硬體上遇過的失敗，每條附症狀。
6. **Backend notes**：只寫導不出來的東西，例如哪個後端會依名稱拒絕、有什麼上限。
7. **References**：論文、相關實驗、用到它的流程。

公式用 `$...$`，GitHub 直接顯示。篇幅以「一張序列圖、一張結果圖、理論一個畫面以內」為準。

## 6. 檢查

`tests/test_experiment_docs.py`，不跑任何模擬，幾秒內結束：

- 每個核心實驗都有 `_docs/<name>/README.md`，除非列在 `UNDOCUMENTED`。這份清單只能縮小，
  而且清單上的名字如果其實已經有文件，測試也會失敗，所以清單本身不會過期。
- 沒有孤兒：每個文件資料夾都對應一個已註冊的實驗。
- front matter 的鍵合法，`experiment` 等於資料夾名；`doc_variants` 的每一組都能建出合法的 Parameters。
- 七個章節都在，順序正確。
- §3.4 的兩項：掃描軸都有標，`sequence.svg` 是最新的。
- `expected.png` 存在，文件裡的圖片連結都找得到檔案。
- `_docs/README.md` 索引是最新的。

連帶要改的文字：CLAUDE.md 的升級檢查表加一行（文件與 `sequence_diagram`）；測試選擇表加一列
（改了文件或 `sequence_diagram` 就跑 `tests/test_experiment_docs.py -k <stem>`）。

## 7. 分階段

**階段 0：樣板，只做一個實驗。** `sequence_diagram.py` 與繪圖器、`Experiment` 上的掛鉤、
`qubit_ramsey` 的宣告與完整文件、產生器、測試（`UNDOCUMENTED` 放其餘 50 個）。
交給你看的是一份真的文件，格式不對就在這裡改，之後才鋪開。

**階段 1：依家族鋪開。** 每批是一次普通的工作階段，每批結束交給你審理論的部分。順序照開機流程：

| 批 | 家族 | 數量 |
|---|---|---|
| 1 | 讀出與共振腔：`resonator_spectroscopy*`（4）、`broadband_resonator_spectroscopy`、`readout_*`（3）、`single_shot_readout` | 9 |
| 2 | 單比特頻率與相干：`qubit_spectroscopy`、`broadband_qubit_spectroscopy`、`qubit_spectroscopy_flux_pulse`、`qubit_power_rabi`、`qubit_ramsey*`（3，不含 cryoscope）、`qubit_relaxation*`（2）、`qubit_echo*`（2）、`qubit_thermal_population`、`qubit_t1_*`（2） | 14 |
| 3 | 閘校正與基準測試：`qubit_drag_*`（2）、`qubit_pi_pulse_error`、`qubit_deterministic_benchmarking`、`qubit_sqrb`、`qubit_tomography` | 6 |
| 4 | 磁通線與時序：`qubit_xyz_delay`、兩個 cryoscope | 3 |
| 5 | Stark、參數驅動、電荷宇稱：`qubit_resonator_stark`、`qubit_stark_phase_echo`、`qubit_parametric_drive_*`（2）、`qubit_parity_switch_*`（2） | 6 |
| 6 | 比特對與耦合器：`pair_*` | 7 |
| 7 | 比特對的 partial swap 校正：`qc_n_swap_amp`、`qc_n_stark_amp`、`qc_n_swap_tomography`、`qc_swap_flux_stark` | 4 |
| 8 | 專題 `MpembaEP_trotter`（見 §9）：`qc_unidirectional_trotter`、`qc_trotter_compensation` | 2 |

共用實驗先做（第 1 到 7 批），專題實驗最後。

**階段 2：呈現。** 互相獨立，可以挑著做：

- `scqo run <name> --doc`：印出文件與圖檔的路徑。跟 `--help`、`--preview` 一樣掛在 `run` 上，
  不新增子命令。
- 檢視器增加 `/experiments` 與 `/experiment/<name>`：散文轉成 HTML，旁邊當場組出參數表、估計器、
  目前註冊的是哪個後端的類別；run 頁加一個連到該實驗說明的連結。需要在 `viewer` 這組相依套件裡
  加一個 Markdown 轉換器，公式的顯示也要另外處理。
- 模擬後端的 preview 改成輸出中立序列圖，不再拒絕。

每個階段、每一批落地後各寫一個 `RELEASES.d` 片段。

## 8. 已決定的事（2026-10-04，五點都照建議）

1. **文件語言：英文。** 與 TUTORIAL、`procedures/` 一致；圖裡的字本來就一律英文。
2. **序列圖的來源：§3 的核心中立宣告。** 每個實驗各多一段宣告。
3. **檔案位置：`scqo/experiments/_docs/<name>/README.md`。**
4. **樣板實驗：`qubit_ramsey`。**
5. **產生的圖進版本庫：SVG 與 PNG 都進。**

## 9. 分類：共用實驗與專題實驗

有些實驗人人都用（`qubit_ramsey`），有些只服務一個研究題目（`qc_unidirectional_trotter`、
`qc_trotter_compensation`）。這一節定怎麼分、分類寫在哪裡、對文件有什麼影響。

### 9.1 現有的四種區分都不是這個軸（已對照程式）

- **`maturity`（`core` 或 `contrib`）** 回答的是「升級了沒有」。兩個 Trotter 實驗都在核心、有自己的
  估計器、有硬體驗證、有流程文件，所以是 `core`。這個欄位目前唯一的作用是清單上的 `[contrib]` 字樣。
- **能力** 是從 Parameters 的 mixin 導出來的，描述的是參數的形狀。
- **名稱前綴** 分不出來：六個 `qc_*` 裡，四個在校正一對比特的 partial swap，兩個是 Trotter 鏈。
- **是否寫回裝置** 也分不出來：測試裡的 `RECORD_ONLY`（不提出任何寫回的實驗）已提交的有 18 個，
  包含 `qubit_tomography`、`qubit_sqrb` 這種人人都用的。

所以需要一個新的軸，而且只能用宣告的。

### 9.2 定義：依用途的層級分，不依人分

- **共用（裝置層）**：量的是晶片本身的性質，或調的是晶片帶著走的東西，例如頻率、相干時間、讀出、
  單比特閘、一對比特的交換操作。判斷句：**換一顆晶片、換一個人來做校正，還會不會跑它？** 會就是共用。
- **專題（應用層）**：在已經校正好的晶片上，執行某個研究題目的線路。結果是那個題目要的物理量，
  在裝置模型裡沒有位置。

標記用**專題名稱**，不用人名，三個理由：

1. 這些版本庫是公開的，人名寫進程式不合適。
2. 人會換。第二個人加入同一個題目，或原作者離開，以人為名的標記就錯了；專題名稱不會。
3. 專題名稱順便把同一個題目的實驗、流程文件、報告串在一起。

兩個 Trotter 實驗在結構上確實不一樣，可當佐證：全部實驗裡只有它們呼叫 `whole_dataset_results`，
也就是分析對象是整組目標（一條鏈），不是每個目標各一份；依 `procedures/chain-trotter-compensation`，
它們的產出是鏈的參數檔與一條曲線，不是裝置欄位。但這只當佐證，**不拿來自動推導**：將來的共用實驗也可能
一次分析整組目標，專題實驗也可能只量一顆比特。

### 9.3 程式架構

```python
# scqo/experiment.py
class Experiment(ABC):
    #: the research project this experiment serves; None = shared (device-level
    #: calibration or characterization, for every chip and every operator)
    project: ClassVar[str | None] = None

# scqo/experiments/qc_unidirectional_trotter.py
    project: ClassVar[str | None] = "MpembaEP_trotter"

# scqo/experiments/__init__.py
PROJECT_SUMMARIES = {
    "MpembaEP_trotter": "<one line; wording to be confirmed>",
}
```

- 一個欄位同時回答兩件事：`None` 就是共用；有值就是專題，而且值就是分組的鍵。
- `catalog()` 每筆多一個 `project` 鍵，所以 CLI、檢視器、代理讀的是同一個來源。
- `PROJECT_SUMMARIES` 仿照既有的 `CAPABILITY_SUMMARIES`：每個專題一行說明，測試把它的鍵釘在
  「實際宣告的專題集合」上，兩個方向都檢查。宣告了沒說明、或有說明沒人宣告，都會失敗。
- `scqo run` 不給名稱時的清單：共用實驗照舊列出，專題實驗不混在裡面，尾端多一行
  `# projects: MpembaEP_trotter(2)`，並增加 `scqo run --project <name>` 篩選，寫法與 `--capability` 相同。
- 文件索引 `_docs/README.md` 依同一個欄位分成兩大段：共用的依家族，專題的依專題。
- 文件的 front matter **不**重複寫專題（§1 原則 2：導得出來的不抄）。
- 給代理的規則：`project` 有值的實驗，除非任務點名該專題，否則不選。與 `contrib` 的處理相同。
- `maturity` 不動。兩個軸互相獨立：`maturity` 是可不可以信任，`project` 是給誰用。

要動的檔案：`experiment.py`、`experiments/__init__.py`、`cli/_engine.py`、兩個實驗模組、一個新測試。
其中 `experiments/__init__.py` 目前有另一個工作階段的未提交修改，得等它提交，或另開 worktree。

### 9.4 對文件的影響

| | 共用 | 專題 |
|---|---|---|
| 章節 | 七節 | 同樣七節 |
| Purpose | 它在開機與校正流程裡的位置 | 必須寫明專題，以及要先完成哪些流程 |
| Theory | 自成一篇，附參考文獻，新學生讀得懂 | 可以引用專題自己的計畫文件或報告，不必重寫推導 |
| 預期結果圖 | 模擬產生即可 | 建議放硬體實測 |
| 鋪開順序 | 先 | 最後 |

專題實驗的文件要求不降低。只有一個人懂的實驗，反而更需要寫下來。

### 9.5 已決定的事（2026-10-04）

1. **分類軸叫專題，欄位名 `project`。** 理由見 §9.2。
2. **歸類。** 專題 `MpembaEP_trotter` 只有兩個實驗：`qc_unidirectional_trotter` 與
   `qc_trotter_compensation`。其餘全部共用，包括當時列為邊界的這些：
   - `qc_n_swap_amp`、`qc_n_stark_amp`、`qc_n_swap_tomography`、`qc_swap_flux_stark`、`pair_swap_angle`
   - `qubit_stark_phase_echo`
   - `qubit_parametric_drive_amp`、`qubit_parametric_drive_time`
   - `qubit_parity_switch_continuous`、`qubit_parity_switch_discrete`
   - `qubit_t1_ade`、`qubit_t1_bayesian`
3. **專題名稱是 `MpembaEP_trotter`。** 大小寫照這個寫法。`PROJECT_SUMMARIES` 裡那一行說明的文字
   在實作時請你過目。

## 10. 階段 0 實作紀錄（2026-10-04）

在 worktree `D:\project\scqo_system\SCQO-wt-experiment-docs`（分支 `feature/experiment-docs`，
起點 `9e8ba6f`）完成。三個驅動與 scqat 都沒有動。

### 10.1 做了什麼

| 檔案 | 內容 |
|---|---|
| `scqo/sequence_diagram.py`（新） | `Block`、`SequenceDiagram`（`step`、`repeat`、`swept_axes`、`notes`）、`render_svg` |
| `scqo/experiment_docs.py`（新） | front matter 解析、`check_doc`、`sequence_svgs`、`expected_requests`、`fit_keys_listed`、`render_index` |
| `scqo/experiment.py` | `project`、`doc_variants`、`sequence_diagram(params)` |
| `scqo/experiments/__init__.py` | `PROJECT_SUMMARIES`；`catalog()` 多一個 `project` 鍵 |
| `scqo/experiments/_capabilities/qubit_reset.py` | `reset_step`：重設那一段的示意圖片段 |
| `scqo/experiments/_capabilities/state_readout.py` | `measure_step`：讀出那一段的示意圖片段 |
| `scqo/experiments/qubit_ramsey.py` | `sequence_diagram` 與 `doc_variants = {"beat": ...}` |
| `scqo/experiments/qc_unidirectional_trotter.py`、`qc_trotter_compensation.py` | `project = "MpembaEP_trotter"` |
| `scqo/experiments/_docs/qubit_ramsey/` | `README.md`（手寫）、`sequence.svg`、`expected.png`、`expected-beat.png` |
| `scqo/experiments/_docs/README.md` | 產生的索引 |
| `scqo/cli/_engine.py` | 清單只列共用實驗、`# projects:` 一行、`--project <name>`、`--help` 顯示專題 |
| `scripts/update_docs.py` | 產生序列圖與索引、`--check` 一併檢查、`--figures [NAME ...]` 重畫預期結果圖 |
| `tests/test_sequence_diagram.py`、`test_experiment_docs.py`、`test_experiment_projects.py`（新） | 見 §6 |
| `CLAUDE.md`、`AGENTS.md`、`CONTRIBUTING.md` | 配置、「Experiment documents」一節、升級檢查表、測試選擇表 |

### 10.2 與計畫不同的地方

- **哪些圖要產生，由文件決定。** 文件連結了 `sequence-<variant>.svg` 或 `expected-<variant>.png`
  才會產生那一張；資料夾裡有圖但文件沒連結，測試會當成孤兒檔報錯。這樣不會留下沒人看的圖。
- **fit 鍵的核對有固定寫法。** 表頭第一格是 `fit key` 的表格，第一欄用反引號標出的名字就是要核對的鍵。
  `--figures` 會把預設參數與所有 `doc_variants` 都模擬一次，文件列出的鍵必須出現在其中。
- **索引先按字母排，沒有分家族。** 目前只有一份文件，家族分組留到階段 1 有內容時再做。
- **專題那一行放在能力那一行之前。** 清單結尾兩行維持原樣，既有的清單測試一行都不用改。
- **`--capability` 也只看共用實驗。** 專題實驗一律從 `--project` 進去，兩者不能同時給。
- **驅動的「新增實驗」步驟沒有改。** 「脈衝順序變了就同一次提交改宣告」這條規則改寫在 SCQO 的
  `CLAUDE.md`（*How a driver adds an experiment*），兩個驅動本來就指向那裡，所以這次不用開它們的 worktree。
- **公式的寫法比 §5 多一條規則。** 行內公式用 `$...$`，獨立公式改用 `math` 圍欄區塊。GitHub 會先對
  行內公式套 Markdown，所以 `*` 要寫成 `\ast`，也不用 `\,`、`\!` 這類反斜線加標點的寫法。
- **`--check` 以文字比對，不是逐位元組。** Windows 檢出時會把換行轉成 CRLF，逐位元組比對會全部誤判過期。

### 10.3 待你過目

1. **`qubit_ramsey` 文件的理論章節。** 這是唯一手寫的物理內容，請確認寫法與深度是不是你要的樣板。
2. **`validated: offline`。** 我只驗證了離線模擬，所以這樣寫。它在硬體上驗證過的晶片與日期請你填。
3. **`PROJECT_SUMMARIES["MpembaEP_trotter"]` 的說明文字。** 目前是依兩個實驗的 docstring 寫的
   「unidirectional (cascaded) coupling along a qubit chain by Trotterized partial swaps with a relay
   reset」，沒有提到 Mpemba 或 EP。
4. **`qubit_ramsey` 第一個脈衝在兩個後端不同。** QM 是 `y90`，Qblox 是 `X90`；scqat 的
   `tools/ramsey_fit.py` 開頭寫的是 `x90 -> idle -> y90`，並把相位的初始值設在 0。擬合的相位是自由參數，
   所以兩邊都擬合得出來，但 Qblox 的條紋相位離初始值差四分之一圈。離線模擬的資料本身就是這種
   餘弦型（擬合出的相位是 -1.57），擬合正常，所以我判斷這不影響結果，只是兩個後端不一致。目前只在文件的 Backend notes 與
   示意圖的註腳裡照實寫出，沒有改任何 `probe()`。要不要統一、統一成哪一個，由你決定；
   決定後應記進 `BACKLOG.md`（該檔現在有別的工作階段的修改，我沒有碰）。

### 10.4 還沒做的事

- 提交。worktree 裡的修改都還沒提交。
- 合併回 main。要等另一個工作階段提交它的 `qubit_ramsey_flux_crosstalk_pulse`；合併時
  兩邊都改到的檔案只有 `experiments/__init__.py` 與 `CLAUDE.md`，可能要手動解衝突；另外它的新實驗
  要補進 `UNDOCUMENTED`（或直接寫文件）。
- `RELEASES.d/experiment-docs.toml` 片段。照規則等最後一次提交落地後才寫。

## 11. 前置條件、產出、後端特有規則（2026-10-04 核可）

使用者看過樣板後的指示：理論章節的寫法與深度先不定；先專心處理「執行前要先有什麼」與
「這個實驗產出什麼」。並提出兩點：改名時怎麼知道某個欄位是誰的前置條件；後端特有的規則該不該寫在驅動裡。

### 11.1 現況（已對照程式）

- **前置條件沒有一個地方列出來。** 結構層的已經有宣告（`target_kinds`、`required_operations`，
  51 個實驗都有，由 Session 的閘門在執行前檢查）。但「哪些欄位要先有值」散在各處：`anchor()` 缺值時拒絕、
  `reset_wait_ns` 缺值時拒絕、各個 probe 自己拒絕。樣板文件裡那一段是我用手寫的。
- **沒辦法從讀取紀錄推導。** QM 的 probe 多數直接讀 QUAM：在它的實驗資料夾裡搜尋中立介面的讀法
  （`self.device.channel`、`reset_wait_ns` 這幾種），只有 8 個檔案用到。
- **產出可以驗證。** 在模擬後端跑一次，`suggestions` 就列出每一筆寫回的 `(entity, field, role)`，
  `fit` 列出所有鍵。測試裡的 `_suggest()` 已經這樣用。
- **現值的來源已經查得到。** `provenance.live_sources` 對每個有值的 `(entity, field)` 回報
  `run`、`campaign`、`manual`、`external`、`unrecorded` 五種狀態之一。
- **欄位名稱有唯一的權威。** `catalog.ALL_FIELD_NAMES`，目前 77 個。

### 11.2 設計：宣告成資料，文字由資料產生

前置條件由三層合成，實驗自己要寫的只有第三層：

1. **操作需要的欄位**：核心裡一張表，例如 `readout` 需要 `readout_freq_hz`、`readout_duration_s`
   等。實驗已經宣告了 `required_operations`，所以這一層自動帶入。
2. **能力附帶的條件式需求**：寫在能力模組裡，跟 `reset_step`、`measure_step` 同一個位置。例如
   `reset_method=thermal` 需要 `thermalization_time_s`；`use_state_discrimination=true` 需要
   `readout_rotation_rad` 與 `readout_threshold`。
3. **實驗自己的需求**：例如 `qubit_parity_switch_*` 需要 `parity_delta_f_hz`。

```python
# scqo/experiment.py
@dataclass(frozen=True)
class Requirement:
    field: str                              # a catalog field name
    why: str                                # one line: what the experiment uses it for
    when: tuple[str, object] | None = None  # (parameter, value); None = always

class Experiment(ABC):
    requires: ClassVar[tuple[Requirement, ...]] = ()   # the experiment's own
    writes: ClassVar[tuple[str, ...]] = ()             # fields update() may propose
    extracts: ClassVar[dict[str, str]] = {}            # fit-only keys -> meaning
```

`catalog()` 多出 `requires` 與 `writes`，CLI、檢視器、代理讀同一份。

**怎麼保證宣告是對的：**

- 每個欄位名都必須在 `catalog.ALL_FIELD_NAMES` 裡。改名就是改 `catalog.py`，每一處宣告的測試會立刻失敗，
  並指出是哪個實驗或哪個能力。
- 模擬跑一次：寫回的欄位必須等於 `writes`，`fit` 的鍵必須等於 `writes` 加 `extracts`。
- `estimate()` 實際讀過的欄位（已有 `inputs_used` 紀錄）必須包含在 `requires` 或 `writes` 裡。
- 做不到的：驅動在 QUAM 裡直接讀的值查不到，所以 `requires` 無法證明完整，只能證明沒有寫錯名字。

**「誰是誰的前置條件」是算出來的，不另外保存一份。** 把所有實驗的 `requires` 與 `writes` 以欄位名相接，
就得到「這個欄位被誰需要、由誰寫入」。這張反查表產生成一個檔案放在 `_docs/`，`scqo state --fields`
也顯示同樣兩欄。改名之前先看這張表就知道影響範圍。

**對文件的影響：** 「執行前要先有什麼」與「產出什麼」兩節改成產生的，樣板裡手寫的清單與表格拿掉。
「由哪個實驗提供」那一欄來自上面的反查，不用人寫。

### 11.3 延伸到檢視器：標記，不隱藏

有了 `requires`，加上已有的來源狀態，每個（實驗，目標）可以算出三種狀態：

| 狀態 | 條件 |
|---|---|
| 不能跑 | 有必要欄位沒有值。列出缺哪些，以及哪個實驗會寫入它 |
| 能跑但未驗證 | 值都在，但有的值背後沒有量測（`external`、`unrecorded`，或來自 `design.toml`） |
| 就緒 | 值都在，而且都來自某次量測或人工設定 |

建議標記而不隱藏：隱藏會讓清單每次長得不一樣，而且「缺什麼、先跑哪個」正是開機時最需要的資訊。
這個狀態只能說明必要條件，不保證充分（例如「驅動頻率離比特 1 MHz 以內」查不出來）。

### 11.4 後端特有的規則放在驅動

同意。核心文件只寫每個後端都成立的事；只對一個驅動成立的事跟著那個驅動的 `probe()`，由驅動那邊的人在
同一次提交裡維護。

- **做法**：驅動的實驗子類別宣告 `backend_notes`（一組短句），跟現有的 `probe_self_acquires = "<why>"`
  同一種寫法。在驅動的環境裡註冊的類別就是驅動的子類別，所以 `scqo run <name> --help` 與檢視器
  顯示的自然是正在使用的那個後端的註記。核心文件的「Backend notes」一節取消。
- **後端特有的前置條件也放驅動**：例如 Qblox 沒有實現 `pi_amp_x90`，它的 x90 由 `pi_amp` 導出，
  所以「x90 校正過」在兩個後端對應不同欄位。驅動子類別可以在核心的 `requires` 上追加。
- **QM 把時間軸取到 4 ns 並去掉重複點**：這是後端註記，搬到 QM 的 `qubit_ramsey`。
- **第一個脈衝 QM 是 `y90`、Qblox 是 `X90`**：這不是後端註記，是兩個 probe 不一致。「後端一致」規則
  只允許寫法不同，不允許脈衝不同。核心的序列宣告應該只寫一個答案，另一邊修掉。

### 11.5 已決定的事（2026-10-04，四點都照建議）

1. **產生的兩節放在各實驗的 `README.md` 裡**，用標記框住。
2. **檢視器對未滿足的實驗：標記，不隱藏。**
3. **`qubit_ramsey` 的序列以兩個脈衝互相垂直為準**（`y90`、等待、`x90`），也就是 QM 現在的做法。
   Qblox 待修。
4. **順序**：先做宣告、測試、文件兩節的產生，樣板仍用 `qubit_ramsey`。就緒狀態與檢視器標記排後面，
   變成執行前的閘門放最後。

## 12. 第二輪實作紀錄（2026-10-04）：前置條件、產出、後端註記

三個 worktree，分支都叫 `feature/experiment-docs`：`SCQO-wt-experiment-docs`、
`scqo-qm-wt-experiment-docs`、`scqo-qblox-wt-experiment-docs`。都還沒提交。

### 12.1 做了什麼

| 位置 | 內容 |
|---|---|
| `scqo/requirements.py`（新） | `Requirement(field, why, when)`、`collect`、`writers`、`dependents`、`field_owner`、`field_spec` |
| `scqo/experiment.py` | `requires`、`writes`、`extracts`、`backend_notes`、`requirements()` |
| `_capabilities/qubit_reset.py`、`state_readout.py` | 各自的 `REQUIRES`，條件式（`reset_method`、`use_state_discrimination`） |
| `scqo/experiments/_requires.py`（新） | 共用的一組：`CALIBRATED_READOUT` |
| 30 個實驗模組 | 各加一行 `writes`；連同 `qubit_ramsey` 共 31 個會寫回，其餘 20 個不寫回 |
| `qubit_ramsey.py` | `requires`、`writes`、`extracts`；序列宣告的第一個脈衝定為 `y90` |
| `catalog()`、`scqo run <name> --help` | 多出 `requires`、`writes`、`backend_notes` |
| `scqo/experiment_docs.py`、`scripts/update_docs.py` | 兩節由宣告產生；新增產生的 `_docs/DEPENDENCIES.md` |
| `qubit_ramsey/README.md` | 章節改為八節；「Before running it」「Outputs」改為產生；「Backend notes」一節取消 |
| `tests/test_experiment_outputs.py`（新） | 見 12.2 |
| scqo-qm、scqo-qblox 的 `qubit_ramsey.py` | 各自的 `backend_notes`，以及追加在 `requires` 上的後端專屬旋鈕 |
| 三個版本庫的 `CLAUDE.md`、SCQO 的 `BACKLOG.md` I19 | 規則與今天的決定 |

### 12.2 檢查

- 每個宣告的欄位名都在 `catalog.ALL_FIELD_NAMES` 裡；條件裡的參數名都是該實驗真的有的參數。
- 51 個實驗各在模擬後端跑一次（含 `doc_variants`）：`update()` 提出的欄位都必須在 `writes` 裡。
- 有文件的實驗要求更嚴：`writes` 的每個欄位都要真的被提出過，`fit` 的鍵必須等於 `writes` 加 `extracts`。
- 文件裡的兩個產生區塊必須等於現場重新產生的結果。

### 12.3 與 §11 提案不同的地方

- **操作那一層沒有做成自動帶入。** §11.2 原本說 `required_operations` 會自動帶入欄位需求。實作時發現
  這對開機實驗是錯的：`resonator_spectroscopy` 需要 `readout` 這個操作，但它就是用來找 `readout_freq_hz`
  的，自動帶入會說它需要自己要量的東西。所以改成共用的一組一組需求，由實驗明確列入。
  能力那一層仍是自動的。
- **`writes` 一次補齊了全部 51 個實驗**，不只樣板。「由誰提供」那一欄要有意義，每個實驗的寫回都得先知道；
  而 `writes` 可以用模擬驗證，補齊的風險低。`requires` 則仍然只有樣板與兩個能力有寫。
- **`requires` 沒有「只要有起始值就好」這個層級。** 開機實驗只需要 `design.toml` 給的起始值，
  校正實驗需要量測過的值，兩者目前不分。樣板用不到，留到第 1 批（共振腔）再加。
- **`y90` 對 `X90` 早就記在 `BACKLOG.md` 的 I19 裡**（2026-09-21），不是這次才發現。今天的決定補進了那一條。

### 12.4 還沒做的事

- `requires` 還沒涵蓋其他 50 個實驗自己的需求，所以 `DEPENDENCIES.md` 的「required by」一欄大多只有
  能力帶來的那些。隨各批文件補上。
- 就緒狀態的計算、檢視器標記、執行前的閘門（§11.3、§11.5 第 4 點）。
- `single_shot_readout` 的鑑別旋鈕是驅動自己寫回的，核心的 `writes` 沒有它們，所以反查表裡
  `readout_rotation_rad` 與 `readout_threshold` 顯示「沒有共用實驗提供」。驅動的子類別補上 `writes` 後才會完整。
- 提交、合併、`RELEASES.d` 片段，同 §10.4。合併順序是 SCQO 先，兩個驅動後。
  SCQO 這邊與另一個工作階段都改到的檔案現在是三個：`experiments/__init__.py`、`CLAUDE.md`、`BACKLOG.md`。
  它的新實驗 `qubit_ramsey_flux_crosstalk_pulse` 合併後要補 `writes`（有寫回的話測試會指名）
  並加進 `UNDOCUMENTED` 或直接寫文件。

## 13. 第 1 批實作紀錄（2026-10-04）：共振腔與讀出，九個實驗

`resonator_spectroscopy`、`resonator_spectroscopy_flux`、`resonator_spectroscopy_power_amp`、
`resonator_spectroscopy_power_chain`、`broadband_resonator_spectroscopy`、`readout_frequency`、
`readout_power`、`readout_time_of_flight`、`single_shot_readout`。連同樣板，51 個裡有 10 個有文件。
只動了 SCQO，兩個驅動這一批沒有改。

### 13.1 每個實驗做了什麼

- `sequence_diagram`、`requires`、`extracts`，需要時加 `doc_variants`（`writes` 上一輪已補）。
- 文件八節：Purpose、Pulse sequence、Expected result、Traps、References 是手寫的；
  Before running it 與 Outputs 是產生的；**Theory 一律留空**，只寫一行 *To be written.*。
- 序列圖與預期結果圖都是產生的。九張預期結果圖我逐張看過，「怎麼讀圖」的文字是對著圖寫的。

### 13.2 為了這一批加進核心的東西

- **`Requirement.seed_ok`**：§12.3 留下的那個層級。開機實驗對它要量的欄位只需要一個起始值
  （現值，或 `design.toml` 的設計值），文件與 `--help` 會明講「有起始值就夠」。
  `resonator_spectroscopy` 對 `readout_freq_hz` 就是這種需求。
- **一個方塊可以標兩個掃描軸**：punchout 的讀出脈衝同時掃頻率與功率。
- **`experiments/_diagrams.py`**：共用的示意圖片段（讀出後的等待、先重設再視情況打 `x180`）。
- **`experiments/_requires.py`** 多兩組：`CALIBRATED_PI_PULSE`、`READOUT_WINDOW_CENTRE`。
- **挑預期結果圖的規則改成比對檔名結尾**：`readout_frequency` 的六張圖檔名都含 `fidelity`，子字串比對挑不出來。
- **產圖用的示範裝置改成可調頻的**：否則磁通實驗沒有磁通線可掃。

### 13.3 與之前不同的地方

- **Outputs 區塊不再列「哪些實驗需要這些欄位」。** 第一次產生時 `resonator_spectroscopy` 那一行列了 45 個實驗，
  而且只要任何實驗新增一條需求，這一行就會變。這正是 §1 原則 2 要避免的事，所以拿掉；完整的反查在
  `DEPENDENCIES.md`。「由誰提供」那一欄保留。

### 13.4 待你過目

1. **Traps 一節只寫了我能從程式與欄位說明確認的事。** 硬體上實際遇過、我不知道的問題需要你補。
2. **`validated` 九份都寫 `offline`。** 哪些在哪顆晶片上驗證過，請你填。
3. **前置條件是我讀程式後列的。** 請特別看 `readout_frequency`、`readout_power`、`single_shot_readout`
   三個：我列了讀出頻率、讀出功率或振幅、驅動頻率、`pi_amp`。
4. **這一批沒有加後端註記。** `BACKLOG.md` I19 記著兩個後端在 `resonator_spectroscopy` 的差異
   （兩次量測之間的等待不同；`readout_amplitude` 這個參數兩邊都沒有讀）。這些是待修的不一致，
   我沒有寫進核心文件，也沒有寫成驅動的註記。

### 13.5 批次進度

| 批 | 內容 | 狀態 |
|---|---|---|
| 樣板 | `qubit_ramsey` | 完成 |
| 1 | 讀出與共振腔，9 個 | 完成（理論留空） |
| 2 | 單比特頻率與相干，其餘 13 個 | 完成（理論留空），見 §14 |
| 3 | 閘校正與基準測試，6 個 | 完成（理論留空），見 §15 |
| 4 | 磁通線的時間對齊與失真，3 個 | 完成（理論留空），見 §17 |
| 5 到 8 | 見 §7 | 未開始 |

## 14. 第 2 批實作紀錄（2026-10-04）：單比特頻率與相干，十三個實驗

`qubit_spectroscopy`、`broadband_qubit_spectroscopy`、`qubit_spectroscopy_flux_pulse`、
`qubit_power_rabi`、`qubit_ramsey_phasor`、`qubit_ramsey_flux_pulse`、`qubit_relaxation`、
`qubit_relaxation_flux_pulse`、`qubit_echo`、`qubit_echo_flux_pulse`、`qubit_thermal_population`、
`qubit_t1_ade`、`qubit_t1_bayesian`。連同前面的，51 個裡有 23 個有文件。
這一批三個版本庫都有改：SCQO 是主體，兩個驅動各補了宣告與註記。

### 14.1 每個實驗做了什麼

做法與第 1 批相同（§13.1）。差別只有一點：這一批的序列我先對照了兩個驅動的 probe 才宣告，
因為相干實驗的脈衝順序是結果的一部分。對照的結果在 §14.3 與 §14.4。

十三張預期結果圖與十四張序列圖（`qubit_spectroscopy` 多一張重疊模式的）都逐張看過。

### 14.2 為了這一批加進核心的東西

- **重複括號可以巢狀。** `qubit_t1_bayesian` 是「每個區塊重設一次，區塊裡重複 `num_probes` 次探測」，
  一層括號畫不出來。外層括號畫在內層外面，各有自己的標籤列；只有一層括號的圖位置不變
  （已提交的圖逐位元組相同）。這也修掉第 1 批留下的一個洞：`single_shot_readout` 在
  `reset_method=active` 且 `active_reset_rounds` 大於 1 時，`sequence_diagram` 會直接報錯。
- **`collect()` 會丟掉兩種條件式需求。** 一種是同一個欄位本來就無條件需要
  （`qubit_t1_ade` 每一發都要鑑別，重設那條「active 才需要門檻」就是多餘的）；
  另一種是實驗的 Parameters 根本拒絕那個設定
  （`qubit_thermal_population` 拒絕 active 重設，所以不該列出 active 重設需要什麼）。
  第二種是用 Parameters 自己的驗證判斷的，不是另外宣告。
- **`experiments/_requires.py`** 多四組：`DRIVE_WINDOW_CENTRE`（驅動頻率只需要起始值）、
  `FLUX_PULSE_ORIGIN`（`_pulse` 實驗的磁通視窗從 `idle_flux` 算起）、
  `DRIVE_CHAIN`（飽和驅動會暫時移動驅動鏈功率，所以鏈上要先有值）、
  `CALIBRATED_DISCRIMINATOR`（每一發都鑑別的實驗）。
- **`experiments/_diagrams.py`** 多四個片段：含磁通線的三條軌、磁通線的標籤
  （指定 `flux_component` 時標成 `source.z`）、echo 的三個脈衝、「等待期間維持磁通脈衝」的一步。
  `mapped_measure_steps` 放在 `mapped_readout.py`：`qubit_power_rabi` 量耦合器時的三步映射讀出。
- **`scripts/update_docs.py` 的 `FIGURE_PREREQUISITES`**：`qubit_thermal_population` 沒有存好的雲團中心就拒絕執行，
  所以產圖前先在同一個示範裝置上跑一次 `single_shot_readout` 並接受。只列真的有硬性門檻的實驗。

### 14.3 驅動端的宣告

- **π/2 脈衝的振幅旋鈕**，做法與 `qubit_ramsey` 相同：QM 的 `qubit_echo`、`qubit_ramsey_phasor`、
  `qubit_ramsey_flux_pulse`、`qubit_echo_flux_pulse` 加上 `pi_amp_x90`；
  Qblox 的 `qubit_ramsey_phasor`、`qubit_ramsey_flux_pulse` 加上 `pi_amp`（以一半振幅打）。
  兩個驅動各有一個 `experiments/_requires.py` 放這條共用的需求。
- **後端註記**，只寫「這個 probe 與宣告的序列不同」或「只有這個後端才有的限制」：
  - QM `qubit_relaxation_flux_pulse`：`prepare_state` 沒有實作，不論設多少都會打 `x180`。
  - QM `qubit_spectroscopy_flux_pulse`：飽和脈衝與磁通脈衝的長度取自已存的飽和操作，沒有參數可設
    （而且目前打了四倍長，`BACKLOG.md` I20）。
  - Qblox `qubit_spectroscopy_flux_pulse`：驅動是在重設等待期間持續打的連續波，不是等待之後的一個脈衝。
  - QM 與 Qblox 的 `broadband_qubit_spectroscopy`：QM 換頻帶時會連帶移動同一對輸出埠的另一個通道；
    Qblox 一次只能掃一個目標。
  - QM `qubit_echo`：每一臂對齊到 4 ns，所以總等待時間以 8 ns 為一步。
- 沒有為「這個後端拒絕 active 重設」寫註記。那是從類別屬性就能推出來的事，手寫會過期。

### 14.4 對照驅動時發現的問題

1. **QM 的 `qubit_echo_flux_pulse` 把單臂時間存成 `wait_time_ns`**，所以擬合出來的 T2 echo 是真實值的一半。
   每一臂實際打的長度是對的，錯的是座標的標示（`4 * cycles` 應為 `8 * cycles`；`qubit_echo` 是對的）。
   這是讀程式得到的結論，沒有在儀器上重現。**我沒有修**：它不在這個功能的範圍內，而且會改變硬體上的資料。
   已記在 `BACKLOG.md` I38，並寫進該類別的後端註記。
2. `qubit_relaxation_flux_pulse.prepare_state` 只有模擬在讀，唯一的 probe（QM）沒有實作。記在 I19。
3. `qubit_spectroscopy_flux_pulse` 沒有驅動長度的參數，兩個驅動實際打的驅動不同。記在 I19（QM 那一半原本就在 I20）。

`qubit_echo` 的 π/2 脈衝在兩個後端都是 `x90`，序列順序一致，只有振幅旋鈕不同，所以沒有 `qubit_ramsey` 那種順序問題。

### 14.5 待你過目

1. **Traps 仍然只寫我能從程式、欄位說明、`BACKLOG.md` 確認的事。** 物理上常見但我沒有依據的說法都拿掉了。
2. **`validated` 十三份都寫 `offline`。**
3. **`qubit_ramsey_flux_pulse` 的 park 模式沒有預期結果圖。** 文件變體需要一個絕對頻率，
   只能寫死示範裝置的驅動頻率，所以沒有加；`park_excursion_v` 這個鍵因此只在文字裡提到，不在產生的表裡。
4. **`qubit_t1_ade` 與 `qubit_t1_bayesian` 的文件寫了「目前只有 QM 驅動有 probe」。**
   這是後端的事實，但核心的實驗說明本來就寫了，而且原因（需要儀器即時運算）是中立的，所以保留。
5. **`qubit_echo_flux_pulse` 的預期結果圖看起來很亂，文件裡有說明原因**：模擬的 T2 echo 約 50 us，
   預設視窗只到 40 us。要不要把預設的 `max_wait_ns` 加長，請你決定。

## 15. 第 3 批實作紀錄（2026-10-04）：閘校正與基準測試，六個實驗

`qubit_drag_alternating`、`qubit_drag_equator`、`qubit_pi_pulse_error`、
`qubit_deterministic_benchmarking`、`qubit_sqrb`、`qubit_tomography`。連同前面的，51 個裡有 29 個有文件。
三個版本庫都有改，做法與第 2 批相同（先對照兩個驅動的 probe 再宣告）。

### 15.1 為了這一批加進核心的東西

- **條件可以是「幾個值之一」。** `qubit_deterministic_benchmarking` 有六種目標閘，分屬兩個振幅旋鈕。
  `Requirement.when` 的值現在可以是一組值（`("target_gate", ("x90", "y90", "-x90", "-y90"))`），
  文件上印成 `target_gate=x90 / y90 / -x90 / -y90`，不必一個閘寫一行。
- **`experiments/_requires.py`** 多一組 `GATE_AMPLITUDE`：`target_gate` 只有 `x180` 與 `x90` 兩個值的實驗用。
- **外層括號只在與內層共用邊界的那一側外擴。** `qubit_tomography` 有兩個並排的括號，其中一個含內層；
  原本外層兩側都外擴，會壓到隔壁的括號。`qubit_t1_bayesian` 的圖因此左緣移了 4 px。
- **改了一段錯的實驗說明。** `qubit_drag_equator` 的登錄說明寫的是「三條序列、`(Y180)^N`」，
  但程式（定義掃描、模擬、兩個 probe、估計器）都是兩條序列：`x180` 接 `y90`，以及 `y180` 接 `x90`。
  說明已改成與程式一致；`pulse_repetitions` 這個參數的說明也改成「沒有 probe 會讀」。

### 15.2 驅動端的宣告

- **QM**：`qubit_drag_equator`、`qubit_sqrb`、`qubit_tomography` 加上 `pi_amp_x90`；
  `qubit_drag_alternating` 加上 `drag_beta` 或 `drag_beta_x90`（它是把已存的脈衝按比例縮放來實現掃描的，
  所以已存的係數是輸入，而且不能是 0）。四個類別有後端註記。
- **Qblox**：`qubit_drag_equator` 加上 `pi_amp`。四個類別有後端註記。

### 15.3 對照驅動與估計器時發現的問題

都沒有修，只記錄；各自寫進該文件的 Traps 或該驅動的後端註記。

1. **`qubit_drag_equator.pulse_repetitions` 沒有任何 probe 或模擬在讀**（I19）。
2. **掃 DRAG 係數的方式有三種**（I19）：QM 的 `qubit_drag_alternating` 用「係數除以已存係數」縮放已存脈衝，
   已存係數取自第一個目標，已存為 0 時整個掃描無效；QM 的 `qubit_drag_equator` 只把參考係數寫進被校正的那一族閘，
   同一條序列裡另一族的脈衝帶的不是掃描的係數；Qblox 的 `qubit_drag_equator` 逐點改裝置上的 `drag_beta`，
   `target_gate=x90` 時仍然掃同一個係數，卻提出 Qblox 沒有實作的 `drag_beta_x90`。
3. **三個估計沒有失敗判斷**（I17）：`qubit_drag_alternating` 永遠成功；`qubit_drag_equator` 算出交點是否在視窗內後又丟掉，
   外插的交點也算成功；`qubit_pi_pulse_error` 把結果夾在視窗邊界，仍然算成功。
4. **`qubit_tomography`：Qblox 沒有讀 `qubit_configs` 裡的 `amp` 與 `detuning`**（I19）。
5. **`qubit_sqrb`：單位 Clifford 在 QM 是一段等待、在 Qblox 什麼都不打**，平均每個 Clifford 的脈衝數因此是
   1.875 與 1.83，而估計器一律除以 1.875（I19）。
6. **`qubit_sqrb` 沒給 `seed` 時兩個後端都用固定的 42**，所以每次跑的序列都一樣。這不是錯，但文件的 Traps 有寫。

### 15.4 待你過目（累積到 §16）

1. 三份文件（兩個 DRAG、tomography）的模擬資料是示意用的，不是真實脈衝的模型；文件裡有明說。
   換成硬體的圖會比較有用。
2. `qubit_deterministic_benchmarking` 預設只量一個振幅，卻仍然提出「不變的」`pi_amp` 並算成功。文件照實寫了。
3. `qubit_pi_pulse_error` 只有 QM 有 probe；文件沒有寫這件事（核心的實驗說明也沒寫）。

## 16. 待你處理的事項總表

你在 2026-10-04 決定：這些都等整體鋪開完成後再處理，各批之間不再逐項詢問。每批結束時把新的項目加到這裡。

**每份文件都有的**

- `validated` 全部寫 `offline`，硬體驗證過的晶片與日期要你填。
- Traps 只寫了能從程式、欄位說明、`BACKLOG.md` 確認的事，硬體上遇過的問題要你補。
- Theory 一節的形式與深度未定（`qubit_ramsey` 那段是草稿）。

**需要你決定的**

- `PROJECT_SUMMARIES["MpembaEP_trotter"]` 的一行說明沒提到 Mpemba 或 EP（§10.3）。
- `readout_frequency`、`readout_power`、`single_shot_readout` 的前置條件請過目（§13.4）。
- `qubit_echo_flux_pulse` 的預設 `max_wait_ns`（40 us）比常見的 T2 echo 短，要不要加長（§14.5）。
- `qubit_ramsey_flux_pulse` 的 park 模式要不要有預期結果圖（§14.5）。
- 三份示意用模擬資料的文件要不要換成硬體的圖（§15.4）；第 4 批的 `qubit_xyz_delay` 也是示意用的（§17.4）。
- 只有一個後端有 probe 的實驗（`qubit_pi_pulse_error`、`qubit_xyz_delay`），文件要不要寫明（§15.4、§17.4）。
- 核心的實驗登錄說明裡還有描述後端的句子（兩個 cryoscope 寫了「兩個後端都有 probe」「Qblox 只有方波」），
  要不要一併搬到驅動的後端註記（§17.4）。

**發現但沒有修的問題（都在 `BACKLOG.md`）**

- I38：QM 的 `qubit_echo_flux_pulse` 把單臂時間存成總等待時間，T2 echo 讀成一半。
- I19：兩個後端不一致的地方，第 2、3 批各補了幾條（`prepare_state`、`qubit_spectroscopy_flux_pulse` 的驅動、
  `pulse_repetitions`、DRAG 係數的三種掃法、tomography 的 `amp` 與 `detuning`、SQRB 的單位 Clifford）。
- I17：沒有失敗判斷的估計，第 3 批補了三個。
- I20、I25、I30、I13、I31：原本就在，文件的 Traps 有引用。
- I39：`qubit_xyz_delay` 的模擬把峰畫在已存的延遲上，接受一次就把延遲加倍（只影響模擬）。
- I19 第 4 批補了兩條：`qubit_ramsey_cryoscope` 兩個後端在磁通脈衝前後留的時間不同；
  `qubit_spectroscopy_cryoscope` 兩邊對頻譜脈衝振幅的防護不是同一個問題。

**還沒做的功能**

- 就緒狀態、檢視器標記、執行前閘門、`scqo run <name> --doc`、檢視器的實驗頁（§7 階段 2、§11.3）。
- 「這個後端拒絕 active 重設」目前沒有顯示在任何地方；可以從驅動的類別屬性推出來，不該手寫。
- 合併回 main 與 `RELEASES.d` 片段（§10.4）。

## 17. 第 4 批實作紀錄（2026-10-04）：磁通線的時間對齊與失真，三個實驗

`qubit_xyz_delay`、`qubit_ramsey_cryoscope`、`qubit_spectroscopy_cryoscope`。連同前面的，51 個裡有 32 個有文件。
三個版本庫都有改，做法與前兩批相同（先對照兩個驅動的 probe 與估計器再宣告）。

### 17.1 為了這一批加進核心的東西

- **脈衝可以跨欄持續。** `qubit_spectroscopy_cryoscope` 的磁通脈衝要一直維持到驅動脈衝結束：
  驅動那條軌先等待、再打脈衝，是兩欄；磁通那條軌是同一個脈衝橫跨這兩欄。原本一欄一個方塊，
  只能畫成兩個分開的脈衝，或是畫成磁通脈衝在驅動之前就結束，兩種都是錯的。
  現在下一欄可以寫 `held("flux")`，表示「上一欄那個脈衝還在」，繪圖時畫成一個橫跨兩欄的形狀。
  沒有用到的圖位置不變（已提交的圖逐位元組相同）。後面幾批（耦合器維持偏壓、Stark 訊號與驅動重疊）也會用到。
- 沒有新增共用的需求組合。三個實驗的需求都是各自寫的，因為用途的說法各不相同。

### 17.2 驅動端的宣告

- **QM**：`qubit_ramsey_cryoscope` 加上 `pi_amp_x90`。三個類別都有後端註記：
  `qubit_xyz_delay`（脈衝是烘焙波形、`x180` 必須是取樣波形；`flux_delay_s` 是輸出埠的延遲，
  整數奈秒、同一個埠上的訊號一起移動、負值會被拒絕）、`qubit_ramsey_cryoscope`（16 ns 以內用烘焙波形，
  更長的用拉長的常數脈衝加餘數；磁通脈衝前後留的時間）、`qubit_spectroscopy_cryoscope`
  （頻譜脈衝是為這次執行建立的操作，比該線上最大的已存脈衝還大就拒絕）。
- **Qblox**：`qubit_ramsey_cryoscope` 加上 `pi_amp`。兩個類別有後端註記：`qubit_ramsey_cryoscope`
  （`max_duration_ns` 超過 512 會被拒絕；磁通脈衝的組成方式與前後留的時間）、
  `qubit_spectroscopy_cryoscope`（只有方波；振幅超過輸出滿刻度就拒絕；磁通脈衝是維持住的電壓偏移）。
- `qubit_xyz_delay` 只有 QM 有 probe，`flux_delay_s` 在 Qblox 是未實作的欄位。這是當初移植時的決定，不是這一批發現的。
- 三個實驗在兩個後端都不接受 active 重設（驅動端以名稱拒絕）。照 §14.3 的做法，沒有寫成後端註記。

### 17.3 對照驅動與模擬時發現的問題

都沒有修，只記錄。

1. **`qubit_xyz_delay` 的模擬把三角形的峰畫在「已存的延遲」上**，而估計回報的是「已存的值加上擬合到的位移」，
   所以在模擬後端接受一次，延遲就變成兩倍，再跑一次再加倍。我實際重現過：先把延遲設成 5 ns，
   連續兩次接受後變成 10.0 ns 與 20.1 ns。硬體不受影響（硬體上峰的位置是「還差多少」）；
   示範裝置的延遲是 0，所以現有測試看不到。記在 `BACKLOG.md` I39，文件的 Traps 也有寫。
2. **`qubit_ramsey_cryoscope` 兩個後端在磁通脈衝前後留的時間不同**（I19）：QM 在第一個 `x90` 之後 16 ns 才開始，
   最長的脈衝結束時第二個 `x90` 剛好開始；Qblox 緊接著第一個 `x90` 開始，最後留 8 ns。
   脈衝下降沿到第二個 `x90` 之間能安定的時間因此每一點都差 8 ns。
3. **`qubit_spectroscopy_cryoscope` 兩邊對頻譜脈衝振幅的防護不是同一個問題**（I19）：
   QM 拒絕「比該線上最大的已存操作還大」，Qblox 拒絕「超過輸出滿刻度」。
4. **在 QM 上，`flux_delay_s` 是負值時接受會失敗。** 線的延遲是 0 而量到的位移是負的（磁通線本來就比驅動線晚到）時，
   提出的值是負的，寫入時被拒絕。這是輸出埠延遲的性質，不是錯誤，但第一次對齊時會遇到；
   這時只能改驅動線那一側的延遲，而目前沒有指令做這件事（`BACKLOG.md` I31 提過同一個缺口）。
   「負值會被拒絕」寫在 QM 的後端註記裡。

### 17.4 待你過目（已加進 §16）

1. `qubit_xyz_delay` 的模擬資料是示意用的（只有 |e> 那一條有三角形），文件裡有明說。
2. `qubit_xyz_delay` 只有 QM 有 probe，文件沒有寫（與第 3 批的 `qubit_pi_pulse_error` 做法一致）。
3. 兩個 cryoscope 的核心登錄說明裡有描述後端的句子，這次沒有動。
4. 兩個 cryoscope 的 Traps 裡有三條是從程式推出來的，不是硬體上記錄過的：
   「閒置點不在拱頂時，頻率換算成磁通的關係不成立」、「紀錄結束時還沒安定的成分會被併進安定值」、
   「已經套用濾波器時量到的是殘餘」。硬體上實際遇過的狀況（例如先長後短的順序）要請你補。
