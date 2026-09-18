---
name: cascade-forge-geometry-handoff
description: "G3 闸门：把叶片几何参数表与流道尺寸表转成 AutoGrid 可用的 geomTurbo / G3 叶片造型交接合同. Use when a ducted-fan or compressor scheme (流道尺寸表 + 叶片几何参数表) must become 2D airfoil sections and a 3D stacked blade, or when handing geometry to NUMECA AutoGrid/AutoBlade. 含 cascade-forge CLI 调用面、输出前自查清单、以及与 numeca-autogrid-meshing 的交接检查。"
---

# G3｜叶片造型与 geomTurbo 交接

**职责**：把 `01-scheme/vN/` 的两张表变成 `02-geometry/vN/<stem>.geomTurbo` + manifest + 预览图。

**不负责**：网格（G4）、求解（G5）。也**不负责**改设计参数——参数不对要回 G2，不能在这里手工修。

## 输入契约

| 文件 | 必需列 |
|---|---|
| `01-scheme/vN/流道尺寸表.csv` | 站位 / 轴向坐标(m) / 轮毂半径(m) / 机匣半径(m) |
| `01-scheme/vN/叶片几何参数表.csv` | 叶排 / 类型 / 叶片数 / 弦长(m) / 稠度 / 进口金属角(deg,相对轴向) / 出口金属角(deg,相对轴向) |

**角度约定**：金属角**相对轴向**测量。若来源是"相对切向"，换算
`metal_angle_axial_deg = 90 - metal_angle_tan_deg`。**安装角不适用这条换算。**

**积叠方式**：默认 **重心极叠（centroid-polar）**。
只有在用户明确要求前缘积叠或做历史对照时才用 leading-edge。

## 输出契约

```
02-geometry/vN/
  <stem>.geomTurbo            <- 交给 AutoGrid 的主交付物
  <stem>.manifest.json        <- 行名/周期数/截面数/方向开关/源参数
  preview.png                 <- 必须人工看一眼
  sections/                   <- 各截面坐标（便于 diff 与审计）
  build.log                   <- 生成日志
```

## 输出前自查清单（G3 硬闸门）

| id | 判据 | 失败处置 |
|---|---|---|
| G3-1 | 输出路径**纯 ASCII** | 移路径；不要改文件语法 |
| G3-2 | 截面数与参数表一致 | 回 G2 |
| G3-3 | 相对展向位置单调递增且覆盖 0→1 | 回 G2 |
| G3-4 | 每个截面点序闭合、无自交、无重复点 | 回 G2 或改造型参数 |
| G3-5 | `pitch = 2πr/Z`、`solidity = chord/pitch` 回算相对误差 ≤ 1e-6 | 回 G2 |
| G3-6 | 前缘/尾缘半径非负；弦长 > 0 | 回 G2 |
| G3-7 | 行名、周期数、`SIDES_EXCHANGE`、`REVERSE_THETA` 已核对 | 修正导出设置 |
| G3-8 | 预览图目视通过（像叶片、前缘不畸变） | 回造型参数 |

**G3-7 说明**：`SIDES_EXCHANGE` / `REVERSE_THETA` 错会导致叶片整体镜像或吸力面/压力面互换。
这类错误在网格阶段**不会报错**，要到 CFD 出图才发现。

---

## cascade-forge 调用面（已探明，端到端未验证）

> ⚠️ **状态声明**：以下命令面已通过 `--help` 探明，**尚未在本工作流内完成端到端验证**。
> 首次跑通后必须回填实测结论，并把本条状态改为"已验证"或如实记录失败原因。

### 可执行入口

```powershell
$CF = "D:\Project\Research\cascade-forge\UDF\.venv\Scripts\python.exe"

# 生成叶片（写入 dataset）
& $CF -m cascade_forge.cli build-blade `
    --dataset   <cascade-forge>/datasets/geometry-v2.1.0 `
    --destination <输出目录> `
    --schedule  <叶片几何参数表.csv> `
    --raw-root  <cascade-forge>/UDF

# 导出几何（按 geometry_id）
& $CF -m cascade_forge.cli export <geometry_id> `
    --dataset   <cascade-forge>/datasets/geometry-v2.1.0 `
    --destination <输出目录>

# 圆尾缘 NACA65 路线（另一条入口）
& $CF -m cascade_forge.cli naca65 fit     ...
& $CF -m cascade_forge.cli naca65 export <fit_id> --dataset <...> --destination <...> `
    --source native|fitted --layout closed|split

# 浏览器工作台（交互造型时用）
& $CF -m cascade_forge.cli serve --dataset <...> --v2-dataset <...> --workspace <...> --port 8000
```

### 已知产物形态

`cascade-forge` 已产出过 `<geometry_id>.geomTurbo` + `<geometry_id>.geomTurbo.manifest.json`
（见 `cascade-forge/UDF/artifacts/NASA120859-R1/`）。manifest 是溯源的关键，必须一并保留。

### 与 AutoGrid 的交接检查（G3 → G4）

交给 `numeca-autogrid-meshing` 之前必须确认：

1. `.geomTurbo` 在**纯 ASCII 路径**下能被打开
2. 行名与参数表一致；周期数 = 叶片数
3. 截面数与参数表一致；两侧（suction/pressure）点序都已检查
4. `preview.png` 已看过
5. manifest 里的源参数与 `01-scheme/vN/叶片几何参数表.csv` 的值逐项对得上

任一项不满足 → **停在 G3**，不要进 G4。几何错了，后面的网格和 CFD 全是浪费。

---

## 登记

```powershell
python tools/case_ledger.py add --case cases/<ID> --stage G3 --kind geometry `
  --path "02-geometry/v1/<stem>.geomTurbo" --version v1 --verdict PASS `
  --from "01-scheme/v1/叶片几何参数表.csv" `
  --criteria "截面数=N；节距/稠度回算误差<=1e-6；点序闭合；ASCII 路径"
```

预览图与 manifest 也要分别登记，且 `--from` 指向上游产物以保持溯源链完整。

## 失败出口

| 现象 | 处置 |
|---|---|
| 点序不闭合 / 自交 | 停在 G3，回 G2 改弦长或厚度分布；**不手工编辑几何文件** |
| 前缘半径过小（注塑件 <0.3–0.5 mm） | 读 `requirements.manufacturing.min_le_radius_m`；未定义则在 `open_questions.md` 里补问 |
| geomTurbo 被 AutoGrid 报格式错误 | 先查 F-001（中文路径），不要改文件语法 |
| 叶片镜像 / 吸力压力面互换 | 查 `REVERSE_THETA` 与 `SIDES_EXCHANGE`；这是设置错误不是几何错误 |

相关：`ducted-fan-aero-design/references/failure-diagnosis.md#F-001`
