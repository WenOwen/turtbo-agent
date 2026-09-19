# 小白快速开始：从零到第一个网格

> 目标读者：**会用命令行，但没做过涵道风扇气动设计**。
> 全程只用到本仓库的脚本；NUMECA 用你已装好的正版。

**这份文档里的「第 N 步」和命令里的 `G0`-`G6` 是一回事。**
标题写中文是因为你要照着做；命令里写编号是因为脚本和工程日志只认它。
界面上你看到的也是中文，右上角的灰色小字才是编号。

| 第几步 | 干什么 | 命令里的编号 |
|---|---|---|
| 第 1 步 | 说清你要什么 | `G0` |
| 第 2 步 | 先算一笔账，看这事靠不靠谱 | `G1` |
| 第 3 步 | 出一版流道和叶片方案 | `G2` |
| 第 4 步 | 把叶片真正画出来 | `G3` |
| 第 5 步 | 划网格 | `G4` |
| 第 6 步 | 跑 CFD 算一遍 | `G5` |
| 第 7 步 | 出报告和交付表 | `G6` |

---

## 先看这里：工作台

设计过程中随时开一个本地工作台，**agent 改了什么，你立刻看得见**：

```powershell
python tools/liveview.py
```

浏览器自动打开 `http://127.0.0.1:8899/`。左侧对话、右侧看图。

**你只需要看三张：**

| 想看什么 | 看哪张 | 回答的问题 |
|---|---|---|
| **方案**对不对 | **方案 → 和基准对一对** | 和已知基准比，效率 / 功率 / 扭矩 / 机匣半径对得上吗 |
| 几何对不对 | **设计值对照** | 参数表写的和几何做出来的逐项对得上吗；**这套几何能不能从参数表复现** |
| 叶片长什么样 | **几何 → 子午面** | 流道形状、叶片从哪个半径伸到哪个半径 |

网格和 CFD 那两组是排查问题用的，平时可以不管。
图会**自动跟着 agent 的操作更新**，不用点刷新。

---

## 0. 一次性环境检查（30 秒）

```powershell
cd D:\Project\Research\turtbo-agent
python tools/preflight.py all
```

**应该看到**：8 项检查，P-1 projectRoot、P-3 NUMECA 安装、P-4 授权守护进程全部 `v PASS`。

**看到 `x P-4`** → 先启动 NUMECA 授权服务（lmtools → Start Server），后面全是白干。
**看到 `x P-1`** → 有人在上层目录建了 `.git`，导致工作区 skill 全部失效。删掉它。

---

## 1. 建一个案例

```powershell
python tools/case_ledger.py new --case-id DF90-002 --root cases
```

**应该看到**：`cases/DF90-002/` 下有 8 个目录 + `LOG.md` / `STATE.json` / `manifest.json` / `memory.md`。

---

## 2. 第 1 步 · 说清你要什么

用 `ask_user_question` 或直接对话回答 11 项（见
`.agents/skills/ducted-fan-aero-design/references/requirements-interview.md`）。

**最少要答出 4 项**：推力目标、环境条件、桨盘直径、转速上限。

产出 `requirements.yaml` 后跑：

```powershell
python tools/gate_check.py requirements --case cases/DF90-002
python tools/case_ledger.py stage --case cases/DF90-002 --stage G0 --status done
```

**应该看到**：`第 1 步检查（G0）：通过`。
（括号里的 `G0` 是内部编号，工程日志里会见到它，平时可以不管。）

---

## 3. 第 2 步 · 先算一笔账（设计大纲）

让 agent 按 `.agents/skills/ducted-fan-aero-design/references/gates.md#G1` 写
`00-brief/design_brief.md`，然后：

```powershell
python tools/gate_check.py brief --case cases/DF90-002
```

**应该看到**：盘载荷与诱导速度落在工程区间（`disk_loading=... v_i=...`）。

---

## 4. 第 3 步 · 一维通流方案

> ⚠️ **这一段是手工的，不会自动跑。** 没有任何代码会替你调用 turbo-flow ——
> 下面两条命令要你自己抄。`tools/turboflow_adapter.py` 只负责把**已经跑出来的**
> `result.json` 翻成三表 + 一份「和基准对一对」的结论。

按 `.agents/skills/ducted-fan-1d-scheme/SKILL.md` 准备两个 JSON：

- `01-scheme/v1/inputs/turbo-flow-attempt3.json`（照 reference 抄，改转速/流量）
- `01-scheme/v1/inputs/benchmark-targets.json`（基线来源必须写清）

**关键**：`annulus.strategy` 必须是 `custom`，`rows` 必须显式给。这两条不满足会得到**看起来合理的错误答案**。

```powershell
$TF = "D:\Project\Research\turbo-flow\.venv\Scripts\python.exe"
& $TF -m turboflow design "<case>/01-scheme/v1/inputs/turbo-flow-attempt3.json" `
      --output "<case>/01-scheme/v1/turbo-flow-attempt3"

python tools/turboflow_adapter.py `
  --result "<case>/01-scheme/v1/turbo-flow-attempt3/result.json" `
  --targets "<case>/01-scheme/v1/inputs/benchmark-targets.json" `
  --out "<case>/01-scheme/v1"
```

**应该看到**：三张 CSV + `benchmark_gate.json` / `.md`，最后一行是
`和基准对一对：通过　(通过 6 / 注意 1 / 没通过 0)` ——
意思是「和基线对上了：6 项通过、1 项注意、0 项没通过」。

跑完再让工具自己查一遍这一步：

```powershell
python tools/gate_check.py scheme --case cases/DF90-002
```

它会查八件事：三表齐不齐、列名对不对、流道自洽不自洽、叶排数与需求一不一致、
基准数字有没有出处、质量守不守恒、**这三表是哪一次求解生成的**、
以及「工程可行 = False」到底能不能解释。

> 最后两条是最值钱的。案例 `01-scheme/v1` 下曾经同时躺着三份 `result.json`
> （效率 0.7597 / 0.7976 / 0.8794），只有一份对得上交付的三表，
> 而**没有任何记录说明用的是哪一份**。

> ⚠️ turbo-flow 会在写出结果**之后**尝试渲染 PDF，在受限环境里会抛
> `PermissionError` 并返回非 0。**先检查 result.json 在不在**，不要在就不管退出码。

---

## 5. 第 4 步 · 把叶片画出来

见 `.agents/skills/cascade-forge-geometry-handoff/SKILL.md`。

> 🛑 **这一步目前走不通，原因不在命令抄得对不对。**
> cascade-forge 的翼型库 `UDF/datasets/geometry-v2.1.0/catalog.duckdb` 是**空的**
> （`geometries_v2` 0 行）。没有翼型可取，`build-blade` 第一步就会失败。
> 要打通得先 `ingest-anchors` 灌锚点翼型。

几何出来之后，让工具自己查一遍：

```powershell
python tools/gate_check.py geometry --case cases/DF90-002
```

它查九件事。**其中两件是这一步真正的价值所在：**

- **几何与参数表一致** —— 稠度**必须按同一半径比**。几何侧取截面平均半径、
  设计侧取流道中径，会凭空造出 3.6% 的假偏差（踩过）。
- **由参数表导出** —— 几何必须带机器可读的 `*.manifest.json`，其源参数与参数表对得上。
  没有它就无法证明这套几何是算出来的，还是手工调出来的。
  DF90-001 的 v8 就是手工调过轮毂、手工选过弯掠的 —— 这条判它 **FAIL**。

> 界面上的「**设计值对照**」组会同时画出逐项对照和溯源链图，
> 哪一环没有证据一眼能看出来。

---

## 6. 第 5 步 · AutoGrid 划网格

先跑一遍检查，看还缺什么：

```powershell
python tools/gate_check.py mesh --case cases/DF90-002 --version v1
```

没有 `03-mesh/v1/` 时它会如实报 `SKIP`（**不是 PASS** —— 缺数据不等于做完了）。
生成后会自动查五件事：文件齐不齐、质量报告空不空、有没有负体积单元、
大二进制（`.cgns`）在不在外部索引里、以及**块签名**（块数、块名、每块的 IMAX/JMAX/KMAX）。
最后一条最关键：网格块和 `.trb` 声明对不上，求解器会在别处报一个看不懂的错。

---

## 7. 第 6、7 步 · 跑 CFD 与交付

```powershell
# 第 6 步：拿 sweep_summary.csv 跑检查
python tools/gate_check.py solve --case cases/DF90-002 --summary "<...>/sweep_summary.csv"

# 第 7 步：检查交付表干净
python tools/gate_check.py post --case cases/DF90-002 --version v1
```

---

## 8. 出看板

```powershell
python tools/build_dashboard.py --case cases/DF90-002 --version v1
```

**应该看到**：`06-delivery/v1/dashboard.html`。双击打开——阶段时间线、产物溯源链、
性能散点图、回放审计、经验记录、工程日志，**断网也能看**。

---

## 9. 随时检查案例健康度

```powershell
python tools/case_ledger.py verify --case cases/DF90-002   # 产物存在性与哈希
python tools/case_ledger.py show   --case cases/DF90-002   # 阶段与产物总览
```

`verify` 有"缺 provenance"警告是**正常的**，但要在 `LOG.md` 里说明理由
（根文件没有上游；外部证据快照的上游不在本案例内）。

---

## 五句最该记住的话

1. **残差不是成绩单，末段质量流量稳定才是。**
2. **静推力只有控制体口径，XMF 壁面轴向力不是。**
3. **一个网格一个 `.iec`。**
4. **中文路径会让 AutoGrid 撒谎。**
5. **缺数据记 SKIP，不许记 PASS。**

---

## 出问题了看哪里

| 症状 | 先看 |
|---|---|
| 任何报错 | `.agents/skills/ducted-fan-aero-design/references/failure-diagnosis.md`（14 条诊断树） |
| 推力/功率/角度符号口径 | `.../references/ducted-fan-contracts.md`（C-001…C-010） |
| 不知道这一步到底查什么 | `.../references/gates.md`（每步的完整检查清单）|
| 版本/日志/溯源怎么写 | `.agents/skills/turbomachinery-case-ledger/SKILL.md` |
| turbo-flow 配置 | `.agents/skills/ducted-fan-1d-scheme/references/turbo-flow-config.md` |
