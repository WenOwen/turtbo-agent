---
name: ducted-fan-1d-scheme
description: "涵道风扇一维/通流方案段合同 / ducted-fan meanline & throughflow scheme contract. 定义 G2 闸门的输入需求 schema、必须输出的三表 schema、对标闸门判据，以及 turbo-flow 适配器的可用配置与两个口径陷阱。用于从需求推导流道与叶栅参数、生成流道尺寸表/叶片几何参数表/通流计算结果表、判定一维方案是否可信、或把一个新的一维工具接入本工作流。"
---

# G2｜涵道风扇一维与通流方案

**职责**：把 `requirements.yaml` 变成**三张表**，并用**对标闸门**判定这版方案可不可信。

**不负责**：几何造型（G3）、网格（G4）、CFD（G5）。

## 输入契约

`cases/<ID>/requirements.yaml` —— 至少要有：

| 必需 | 字段 |
|---|---|
| 推力 | `thrust.value_n`、`thrust.condition`、`thrust.definition` |
| 环境 | `environment.p_inf_pa`、`environment.t_inf_k`、`environment.density_kg_m3` |
| 几何 | `geometry.tip_radius_m`（是否锁定由 `geometry.constraint` 说明） |
| 轴系 | `shaft.rpm_design` 或允许 G2 自选的标记 |
| 叶排 | `rows.count`、`rows.configuration` |
| 动力 | `motor.*`（用于交叉检查轴功率） |
| **电机包络** | `motor.outer_diameter_m`、`motor.axial_length_m`、`motor.axial_clearance_m` |

### 电机包络是**硬输入**，不是备注

**为什么单列**：DF90-001 的 v8 几何在轮毂上人工调出一段 Ø188 平段来装 EMRAX 188，
而当时需求里只有 `motor.model: EMRAX 188`，没有外径与轴向长度 ——
G1/G2 因此**推不出轮毂最小直径**，只能在 G3 手工满足，
结果 `gate_check.py geometry` 的 G3-9「由参数表导出」判 FAIL，几何证明不了由参数表导出。

**补进需求之后，G2 必须做三件事：**

1. 轮毂型线在**电机轴向占位内**保持 `>= outer_diameter_m / 2`，两端各留 `axial_clearance_m`
2. 把占位区间与实测最小轮毂半径写进产物（DF90-001 的样例：`01-scheme/v2/motor-envelope-check.json`）
3. **逐条给出实测**，不是声明"已考虑"

### 另外两条 G2 常常漏掉的几何约束

- **流道长度必须装得下全部叶排**：两排各 `chord_m` + 排间间隙。
  DF90-001 的 v1 流道 180.135 mm，两排各 90 mm 弦长至少需要 200 mm —— **装不下**。
  v8 把流道加到 300 mm 是对的，但它的理由写成了"电机包络"，而电机包络并不要求加长。
- **入口轮毂半径通常不是自由变量**：它由设计流量系数反解。
  `phi_tip` → `Va = phi_tip * U_tip` → `A = mdot / (rho * Va)` → `r_hub = sqrt(r_tip^2 - A/pi)`。
  DF90-001：0.2581 → 49.462 m/s → 0.249106 m² → **r_hub = 0.103475**，与参数表的 0.103457 差 0.018 mm。
  **选它之前先反解一次**，别默默抄一个数。

## 输出契约

`cases/<ID>/01-scheme/vN/`：

| 文件 | 内容 | 列/字段要求 |
|---|---|---|
| `流道尺寸表.csv` | 站位几何 | 站位 / 类型 / 序号 / 轴向坐标(m) / 轮毂半径(m) / 机匣半径(m) / 中径半径(m) / 通流面积(m2) |
| `叶片几何参数表.csv` | 叶排几何 | 叶排 / 类型 / 级 / 轴向坐标(m) / 叶片数 / 弦长(m) / 稠度 / 展弦比 / 进口金属角(deg,相对轴向) / 出口金属角(deg,相对轴向) / 叶尖间隙(m) / 堵塞 |
| `通流计算结果表.csv` | 性能与约束 | 参数类别 / 参数名称 / 单位 / 数值 |
| `benchmark_gate.json` | 对标闸门机器可读结果 | 逐项 target/actual/delta/verdict/source |
| `benchmark_gate.md` | 对标闸门人类可读报告 | 含口径说明 |
| `scheme.json` | 方案元数据（求解器、版本、口径声明） | — |

三表**不带路径、不带版本号、不带质量状态字段**（C-003）。

---

## 对标闸门判据（G2 硬闸门）

| id | 项目 | 判据 | 容差 | 性质 |
|---|---|---|---|---|
| B-1 | 总总效率（绝对偏差） | |Δη_tt| | ≤ 0.02（2 个百分点） | 硬 |
| B-2 | 轴功率（相对偏差） | |ΔP|/P | ≤ 5% | 硬 |
| B-3 | 扭矩（相对偏差） | |ΔQ|/Q | ≤ 5% | 硬 |
| B-4 | 机匣半径（绝对偏差） | |Δr_tip| | ≤ 1e-4 m | 硬（需求锁定值时） |
| B-5 | 叶排数 | 等于 `rows.count` | 0 | 硬 |
| B-6 | 工程约束 | 0 条 `kind=engineering` 不通过 | 0 | 硬 |
| B-7 | 输入设计目标自洽 | 0 条 `kind=design` 不通过 | 0 | **软（WARN）** |

**B-7 为什么是软判据**：design 类约束不通过通常源于**输入口径定义错误**，不是求解器缺陷。
必须逐条归因并写进 `benchmark_gate.md`，不能直接放行也不能直接判死。

**基线来源必须写进 `benchmark-targets.json` 的 `source` 字段**，不允许引用无出处的数字。

---

## 这一步的判据（G2-1..G2-8）

**这张表已经是机读的**：`python tools/gate_check.py scheme --case <case>` 逐条实现。
编号必须与代码一致 —— 改这里就要改 `tools/gate_check.py`，否则 `audit` 会报漂移。

| id | 判据 | 没通过怎么办 |
|---|---|---|
| G2-1 | 三表齐全且非空 | 回第 3 步重出 |
| G2-2 | 三表列名齐全（按上面的输出契约，含单位后缀） | 改适配器，别在表上手工补列 |
| G2-3 | 流道自洽：站位轴向单调；轮毂 < 中径 < 机匣；**被需求锁死的机匣半径不得被静默改动** | 硬停，改用 `annulus.strategy=custom` 重跑 |
| G2-4 | 叶排数 == `requirements.yaml` 的 `rows.count` == 计算表自述 | 硬停，显式给 `rows` |
| G2-5 | 对标结论可读、逐项带出处。**对标不通过记「注意」不阻塞下一步**，但必须在设计大纲与交付说明里标注「G2 未通过独立验证」 | 逐条归因 |
| G2-6 | 质量守恒：进出口流量相对差 ≤ 1e-6（一维平均线下这是结构性的，证据力弱） | 查连续性 |
| G2-7 | **三表可溯源**：能按效率/功率/扭矩三项认出是哪一份 `result.json` 生成的；目录里有多份候选时必须唯一命中 | 把用不上的候选移走或改名 |
| G2-8 | 「工程可行」结论可解释：写 `False` 时必须能由约束清单解释（是工程约束真不通过，还是只是设计目标没全中） | 在交付说明里写清是哪种 |

**G2-7 为什么单列**：实测 `01-scheme/v1` 下同时躺着三份 `result.json`
（效率 0.7597 / 0.7976 / 0.8794），只有一份对得上交付的三表，
而**没有任何记录说明用的是哪一份**。旁边那两份会给出一套完全不同的方案。

**G2-8 为什么单列**：`通流计算结果表.csv` 里只写 `工程可行 = False`，
会被读成「这个方案不可行」；而实际是 8 条工程约束全通过、只有 3 条**设计目标**没全中。
这两件事在表里都叫「约束」，很容易看混。

---

## turbo-flow 适配器（已实测）

### 两条硬要求

> **这两条不是"最好这样"，是"不然会得到看起来合理的错答案"。**
> 默认的 `annulus.strategy=constant_mean` 会**静默重算整个流道** ——
> 它既不知道**被需求锁死的机匣半径**，也不知道**电机占位**，
> 两样都会在你没察觉的情况下被改掉。所以必须 `custom` + 显式 `hub_curve`。

#### A. `annulus.strategy` 必须是 `custom`

默认的 `constant_mean` 会按"总状态定尺寸"**静默重算整个流道**。
实测：输入机匣 r=0.300 m，输出被改成 0.3486 m —— **违反被需求锁定的 D=0.600 m**。
且轮毂半径从 0.1035 被改成 0.0495。

**电机包络只有在 `custom` 下才可能被满足**：`hub_curve` 是你给的，
你才能保证它在电机轴向占位内 `>= outer_diameter_m / 2`。
交给工具自动生成，它没有任何理由知道那里要装一个 Ø188 的电机。

必须显式给出 `hub_curve` / `shroud_curve`（`[{x, r}, ...]`）：

```json
"annulus": {
  "strategy": "custom",
  "inlet_hub_radius_m": 0.103457,
  "inlet_tip_radius_m": 0.300,
  "length_m": 0.180135,
  "hub_curve": [
    {"x": 0,        "r": 0.103457},
    {"x": 0.023915, "r": 0.103457},
    {"x": 0.074194, "r": 0.113681},
    {"x": 0.098407, "r": 0.115980},
    {"x": 0.176808, "r": 0.125168},
    {"x": 0.180135, "r": 0.125500}
  ],
  "shroud_curve": [{"x": 0, "r": 0.300}, {"x": 0.180135, "r": 0.300}],
  "inlet_blockage": 0.0,
  "outlet_blockage": 0.0
}
```

约束：两条曲线都必须**从 x=0 覆盖到 x≥length_m**，且 x 单调递增。

#### B. `rows` 必须显式给出

留空 `rows: []` 会触发"按级数自动生成叶排"。实测 `stage_count=1` 时它生成了
**IGV + R1 + OGV 三排**，叶片数 36/34/37、弦长 0.04/0.045/0.045 全是默认值，
OGV 扩散因子 0.978（限值 0.6）、de Haller 0.377（限值 0.72）。

显式给两排（与 `rows.configuration: rotor_stator` 一致）：

```json
"rows": [
  {"id": "R1", "row_type": "rotor",  "stage": 1, "x_m": 0.049,  "blade_count": 9,
   "chord_m": 0.090, "solidity": 0.639, "aspect_ratio": 2.0,
   "metal_angle_in_deg": 71.918, "metal_angle_out_deg": 56.144},
  {"id": "S1", "row_type": "stator", "stage": 1, "x_m": 0.1376, "blade_count": 11,
   "chord_m": 0.090, "solidity": 0.70,  "aspect_ratio": 2.0,
   "metal_angle_in_deg": 56.144, "metal_angle_out_deg": 0.0}
]
```

`x_m` 必须落在 `[0, annulus.length_m]` 内。

### 两个口径陷阱

#### C. `flow_coefficient` 按**中径**定义，不是桨尖

实测：桨尖口径 `phi_tip = Va/U_tip = 0.2581` 输入后，
工具报告的 `flow_coefficient_target` 是 **0.3864**。

换算关系：

```
phi_mean = phi_tip * (r_tip / r_mean)
```

（本案例 r_tip=0.300、r_mean=0.2017 → 0.2581 × 1.4871 = 0.3838 ≈ 0.3864 ✓）

**给 turbo-flow 的 flow_coefficient 必须用中径口径**，否则 B-7 会误报。

#### D. `target_efficiency_tt` 不是强制结果

`result.metadata.target_efficiency_role` 原文：
「initial work estimate and feasibility constraint, not imposed result」。
它只用于初始功估算与可行性判断。达不到不等于算错。

---

## 三组 A/B 实测结论（2026-09-17）

| 配置 | 机匣半径 | 叶排 | η_tt | 功率 | 工程约束 |
|---|---|---|---|---|---|
| attempt-1 `constant_mean` + 自动叶排 | 0.3486（**违反锁定值**） | IGV+R1+OGV (36/34/37) | 0.7597 | 67.72 kW | R1 de Haller 0.654❌、OGV DF 0.978❌ |
| attempt-2 `custom` + 自动叶排 | 0.3000 ✓ | IGV+R1+OGV (36/34/37) | 0.7976 | 64.50 kW | OGV DF 0.765❌ |
| **attempt-3 `custom` + 显式 R1/S1** | **0.3000 ✓** | **R1(9)+S1(11) ✓** | **0.8794** | **58.50 kW** | **0 条不通过 ✓** |

**目标**（v7/PPT 6100 rpm 设计点）：η_tt 0.8931、功率 57.696 kW、扭矩 90.32 N·m。

**attempt-3 偏差**：η_tt **−1.37 个百分点**、功率 **+1.40%**、扭矩 **+1.41%**、机匣半径 **0**、叶排数 **0**。
对标闸门结论：**PASS**（6 PASS / 1 WARN / 0 FAIL）。

> ⚠️ **总压比与目标一致不构成证据**：它是反设计的射击目标（shooting target）。
> 真正的证据只有效率、功率、扭矩、几何约束。

---

## 标准流程

```powershell
# 1. 准备 targets（基线来源必须可追溯）
#    cases/<ID>/01-scheme/v1/inputs/benchmark-targets.json

# 2. 用 workflow 的 venv 跑 turbo-flow（输出必须落在工作区内）
& "<turbo-flow>/.venv/Scripts/python.exe" -m turboflow design `
    "<case>/01-scheme/v1/inputs/turbo-flow-attemptN.json" `
    --output "<case>/01-scheme/v1/turbo-flow-attemptN"

# 3. 转三表 + 对标闸门
python tools/turboflow_adapter.py `
    --result "<case>/01-scheme/v1/turbo-flow-attemptN/result.json" `
    --targets "<case>/01-scheme/v1/inputs/benchmark-targets.json" `
    --out "<case>/01-scheme/v1"

# 4. 登记产物（带 --from 溯源）
python tools/case_ledger.py add --case <case> --stage G2 --kind scheme `
    --path "01-scheme/v1/通流计算结果表.csv" --version v1 --verdict PASS `
    --from "01-scheme/v1/叶片几何参数表.csv" --criteria "<判据>"
```

### 已知的 CLI 副作用（非阻塞）

- `turboflow design` 会在结果写出**之后**尝试渲染 PDF 报告，使用系统临时目录 + Playwright。
  在受限环境里该步骤会抛 `PermissionError`，但 `result.json` 与 `designed_project.json`
  **已成功落盘**。**不要因为退出码非 0 就认为方案失败** —— 先检查产物是否存在。
- 输出目录必须指定在**可写工作区内**；默认的 `artifacts/design` 在 turbo-flow 仓库里，
  会被沙箱拒绝。

---

## 失败出口

| 现象 | 处置 |
|---|---|
| B-1/B-2/B-3 任一 FAIL | **如实记 FAIL**，不调数字凑合；在大纲与交付说明中标注"G2 未通过独立验证"，**不阻塞 G3+** |
| B-4 FAIL（机匣半径被改） | **硬停**。改用 `annulus.strategy=custom` 重跑；这是需求被静默违反，不是数值问题 |
| B-5 FAIL（叶排数不符） | **硬停**。显式给 `rows`；自动生成的三排不满足需求 |
| B-6 FAIL（工程约束） | 检查叶排几何输入（弦长/稠度/金属角）；多数是给了默认值而非设计值 |
| B-7 WARN | 逐条归因：是输入口径错（如 flow_coefficient 按桨尖给的）还是真的不满足目标 |

## 接入新的一维工具

任何一维/通流工具接入本工作流，只需满足：

1. 能读 `requirements.yaml` 的字段子集
2. 能输出上述**三表 schema**
3. 能跑出**对标闸门可评的指标**（η_tt、功率、扭矩、机匣半径、叶排数）
4. 工具自身的约束检查结果能导出为 `{kind, passed, value, limit}` 列表

满足这四条即可复用 `tools/turboflow_adapter.py` 的对标闸门逻辑
（把 `--result` 换成该工具的结果文件，或写一个薄的 result 转换器）。
