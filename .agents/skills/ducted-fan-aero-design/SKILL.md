---
name: ducted-fan-aero-design
description: "涵道风扇气动设计全流程编排 / ducted-fan aerodynamic design orchestration. 从一句推力需求出发，经需求→设计大纲→1D通流方案→叶片造型→AutoGrid 网格→FINE 求解→CFView 后处理→交付三表，用七道闸门（G0-G6）串起整条链。用于\"设计一台 XX kgf/kW 的涵道风扇\"、\"涵道风扇方案\"、\"ducted fan preliminary design\"、\"风扇气动设计\"、需要从需求走到 CFD 交付的场合。含面向小白的引导、需求问答清单、失败诊断树与可执行判据库。"
---

# 涵道风扇气动设计｜全流程编排

**一句话**：把「我要一台 90 kgf 的涵道风扇」变成「有版本、有日志、可追溯的 CFD 交付物」。

## ⚠ 对用户说话的方式（先看这条）

**用户是来做设计的，不是这个仓库的开发者。** 他不需要知道 G0-G6、C-001、闸门、判据是什么。

内部编号和内部术语 **只准出现在工程日志、文件内容、命令行里**，
**不准出现在你对用户说的话里**。

| 别说 | 要说 |
|---|---|
| 「G4 闸门 FAIL」 | 「划网格这步没过：有 3 个负体积单元，得重划」 |
| 「合同 C-007 要求…」 | 「有条规矩：…（直接说内容）」 |
| 「判据不满足」 | 「判断标准没达到」 |
| 「产物已登记」 | 「文件已经记进清单了」 |
| 「归因 unknown」 | 「有人改了文件但日志里没说，接手前看一眼」 |

**说话顺序**：先说让他做什么 → 再说会发生什么 → 最后才给结论。
**编号只在必要时出现**，出现时后面必须跟人话，例如「第 5 步（G4）划网格」。

白话对照表（唯一的翻译源，界面也读它）：
`references/plain-language.json`

## ⚠ 开工前第一件事：读交接简报

**任何会话接手本案例时 —— 新开的、被压缩过的、换了个 agent 的 —— 第一件事是读：**

```
cases/<ID>/HANDOFF.md
```

它由 `tools/case_watch.py` 自动维护，永远是最新的、**≤120 行**：

| 段 | 作用 |
|---|---|
| 一句话现状 | 到哪一步了 |
| **未登记的改动** | **文件变了但日志里没记录 —— 有人绕过账本改了东西** |
| 最近 10 次变更 | 谁在什么时候动了什么 |
| 你接手前必须知道 | 结论非 PASS 的产物、待晋升的经验、手工补充的注意事项 |
| 未决问题 | 需求里还没定的项 |
| 产物表 | 全部产物与哈希 |

**为什么必须做**：agent 的上下文是文件系统的**缓存**，缓存会过期。
而你无法被"推送" —— 只有主动读，才知道世界变了。

配套命令：

```powershell
python tools/case_watch.py --case cases/<ID> --status    # 看守状态
python tools/case_watch.py --case cases/<ID> --once      # 手动跑一轮检测
python tools/case_watch.py --case cases/<ID> --restore <路径> --sha <哈希>   # 从历史库还原
```

**写任何案例文件之前，先看 HANDOFF 的「未登记的改动」。**
如果那里有你想改的文件，说明有人刚动过它 —— 先搞清楚为什么。

> 边界：看守**不阻止**写入（它是摄像头不是锁），也**不保证**你一定会读。
> 唯一有牙齿的强制点是把"存在未登记改动"写进闸门判据 —— 那是下一步的事。

---

## 何时用 / 何时不用

**用**：从需求开始的完整方案设计；需要向他人证明结果来源；第一次做这个方向需要引导。

**不用**：
- 只画一个网格 → 直接用 `numeca-autogrid-meshing`
- 只有算例要出图 → 直接用 `numeca-cfview-post`
- 没有明确推力/功率目标的探索性试算 → 建 `_scratch/`，不进闸门

## 前置依赖（先确认，缺失即停）

| 依赖 | 检查 | 缺失处置 |
|---|---|---|
| 案例账本 | 本仓库 `.agents/skills/turbomachinery-case-ledger/` | 必须先读，否则产物无处登记 |
| 工具 | `tools/case_ledger.py`、`tools/gate_check.py`、`tools/preflight.py` | 报错退出，不要手工伪造 manifest |
| NUMECA | `tools/preflight.py numeca` | 授权/MPI/磁盘未就绪 → G4 前阻塞 |
| 工作路径 | 全链路 **ASCII-only** | 中文路径会让 AutoGrid 把合法 geomTurbo 误报为格式错误 |
| 阶段技能 | 见下表 | 缺哪个就停在哪一步，不自行降级 |

### 阶段技能路由（不重写，只调用）

| 闸门 | 阶段技能 | 职责 |
|---|---|---|
| G0-G1 | 本 skill | 需求问答、设计大纲 |
| G2 | `ducted-fan-1d-scheme` | 一维/通流方案、三表 |
| G3 | `cascade-forge-geometry-handoff` | 叶栅参数 → `.geomTurbo` |
| G4 | `numeca-autogrid-meshing`、`numeca-igg-skills` | 结构化网格与审计 |
| G5 | `numeca-fine-solver`、`numeca-cli-automation` | 求解编排与收敛审计 |
| G6 | `numeca-cfview-post`、`extract-fine-autoblade-tables`、`cfd-report-postprocess` | 后处理与交付三表 |

---

## 三条不可违背的合同（违反即停止）

1. **整机静推力只认控制体口径**
   `T = ṁ_out·Vx_out + (p_out − p_∞)·A_out`
   XMF 壁面轴向力**不是**整机净推力。详见 [ducted-fan-contracts.md](references/ducted-fan-contracts.md#c-004)。

2. **一个唯一网格 ↔ 一个独立 `.iec`**
   网格身份 = 规范化路径 + SHA256 + 块签名。不同网格共用工程 = 硬失败。

3. **收敛主判据是末段质量流量稳定性，不是残差数值**
   残差只用于识别 NaN、爆炸、持续恶化。正常结束标记不是收敛证明。

---

## 七道闸门

每道闸门统一是 **读 → 做 → 写 → 判 → 出口** 五拍。详细判据见 [gates.md](references/gates.md)。

```
G0 需求(需求问答 11 项) → G1 设计大纲 → G2 1D/通流方案 → G3 叶片造型
                                                          ↓
      G6 后处理与交付 ← G5 求解 ← G4 网格 ←────────────────┘
```

| 闸门 | 读 | 做 | 写 | 判（硬） |
|---|---|---|---|---|
| **G0** 需求 | 用户口述 | 11 项需求问答 | `requirements.yaml`、`00-brief/open_questions.md` | 推力目标、环境条件、桨盘直径、转速上限四项齐全且带单位 |
| **G1** 设计大纲 | `requirements.yaml` | 反算流量/压比/功率量级；列设计变量与约束 | `00-brief/design_brief.md` | 需求→方案的物理链闭合（量纲、量级、效率上限） |
| **G2** 1D/通流方案 | `requirements.yaml`、`design_brief.md` | 一维平均线 + 径向平衡 | `01-scheme/vN/` 三表 + `scheme.json` | 对标闸门：与已知基准的压比/效率/流量偏差在阈内，或如实记 FAIL |
| **G3** 叶片造型 | `叶片几何参数表.csv`、`流道尺寸表.csv` | 二维叶型拟合 → 三维积叠 | `02-geometry/vN/<stem>.geomTurbo` + manifest + preview | 截面数、点序闭合、节距/稠度回算一致、前尾缘半径非负 |
| **G4** 网格 | `.geomTurbo` + TRB | AutoGrid 生成 | `03-mesh/vN/` 网格六件套 + `mesh_audit.json` | 负单元=0；块签名与 TRB 一致；`.qualityReport` 存在 |
| **G5** 求解 | `.iec` + `.igg` | 物化独立 `.run` → EURANUS | `04-solve/vN/` + `.std` + `convergence.csv` + `verdict.json` | 末段 `MF_IN/MF_OUT` 相对极差 ≤0.2%、质量不平衡 ≤1%、正常结束、CGNS 完整 |
| **G6** 后处理与交付 | accepted 工况 | CFView 出图 + 静推控制体 | `05-post/vN/`、`06-delivery/vN/` 三表 + `dashboard.html` | 静推闭合 `T = 动量项 + 压力项`；三表无路径/无质量状态字段 |

### 每道闸门的标准动作

```powershell
# 1. 状态置为进行中
python tools/case_ledger.py stage --case cases/<ID> --stage G4 --status in_progress

# 2. 做这一步的工作（调用对应阶段技能）

# 3. 跑闸门判定（自动写 LOG.md，PASS 才放行）
python tools/gate_check.py mesh --case cases/<ID> --version v1

# 4. 登记产物（带上游溯源）
python tools/case_ledger.py add --case cases/<ID> --stage G4 --kind mesh \
  --path 03-mesh/v1/mesh-v1.igg --version v1 --verdict PASS \
  --from 02-geometry/v1/<stem>.geomTurbo --criteria "<判据>"
```

### 失败出口（不允许硬冲）

| 现象 | 出口 |
|---|---|
| G2 对标不通过 | **如实记 FAIL**，降级为"专家表格 + 文档化 1D 闭合"，**不阻塞 G3+**；结论写入 `memory.md` |
| G3 点序/闭合不通过 | 停在 G3，回退改造型参数，不开新版本以外的手工修补 |
| G4 负单元或块签名不一致 | 停在 G4，回退 TRB/几何；**不得"先算了再说"** |
| G5 末段振荡不衰减 | 保存退出，状态 `stopped/persistent_flow_oscillation` → `rejected`；**不得标为有效性能点** |
| G5 边界读回不一致 | 停在 G5，重新物化 `.run`；不得靠"求解器能启动"代替绑定正确性 |

---

## 面向小白的引导

第一次做这个方向时，**按 [beginner-walkthrough.md](references/beginner-walkthrough.md) 逐步走**，
它写明每一步「在屏幕上应该看到什么」。三个最容易劝退的点，先知道：

1. **AutoGrid 说 geomTurbo 格式错误** → 九成是路径里有中文。换 ASCII 路径再试，不要改文件语法。
2. **FINE 点 Run 没反应** → 先看授权（`preflight.py numeca`），再看 MPI。分区成功 ≠ MPI 能跑。
3. **残差不动了但没"收敛"** → 本项目不看残差判收敛，看末段质量流量是否稳定。

术语见 [beginner-walkthrough.md](references/beginner-walkthrough.md#术语表)。

---

## 参考文件

| 文件 | 什么时候读 |
|---|---|
| [references/ducted-fan-contracts.md](references/ducted-fan-contracts.md) | 每次涉及推力、功率、角度符号、收敛判据时——**先读这里再下结论** |
| [references/gates.md](references/gates.md) | 实现或修改 `tools/gate_check.py` 的判据时 |
| [references/requirements-interview.md](references/requirements-interview.md) | G0 问用户需求时 |
| [references/beginner-walkthrough.md](references/beginner-walkthrough.md) | 用户是新手，或需要解释"这一步在干嘛" |
| [references/failure-diagnosis.md](references/failure-diagnosis.md) | 任何一步报错时 |

---

## 报告纪律

向用户汇报时必须区分五种状态，**不得混用**：

`已准备` / `已排队` / `正在运行` / `已正常退出` / `已验收`

进入迭代只代表"正在运行"。没有任何一步可以因为"退出码是 0"就被称为"收敛"或"验证通过"。
