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

## turbo-flow 适配器（已实测）

### 两条硬要求

#### A. `annulus.strategy` 必须是 `custom`

默认的 `constant_mean` 会按"总状态定尺寸"**静默重算整个流道**。
实测：输入机匣 r=0.300 m，输出被改成 0.3486 m —— **违反被需求锁定的 D=0.600 m**。
且轮毂半径从 0.1035 被改成 0.0495。

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
