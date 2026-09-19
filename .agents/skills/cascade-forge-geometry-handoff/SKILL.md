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

**这张表已经是机读的**：`python tools/gate_check.py geometry --case <case>` 逐条实现。
编号必须与代码一致 —— 改这里就要改 `tools/gate_check.py`，否则 `audit` 会报漂移。

| id | 判据 | 失败处置 |
|---|---|---|
| G3-0 | 几何产物可用（目录在、有 `.geomTurbo`、能解析出截面） | 先把产物做出来 |
| G3-1 | 输出路径**纯 ASCII** | 移路径；不要改文件语法 |
| G3-2 | 截面数与上游 `SectionSchedule`（`_automation/g3/schedule-<叶排>.json`）一致 | 回 G2 |
| G3-3 | 相对展向位置单调递增且覆盖 0→1 | 回 G2 |
| G3-4 | 每个截面点序闭合、无自交、无重复点 | 回 G2 或改造型参数 |
| G3-5 | 几何实测与参数表**逐项**一致：稠度（**必须同一半径比**）、弦长、叶片数 | 回 G2 |
| G3-6 | 弦长 > 0 | 回 G2 |
| G3-7 | 行名、周期数、`SIDES_EXCHANGE`、`REVERSE_THETA` 已核对 | 修正导出设置 |
| G3-8 | 预览图存在（**目视像不像叶片由人判断**，工具只查在不在） | 回造型参数 |
| **G3-9** | **由参数表导出**：几何必须带机器可读的 `*.manifest.json`，其源参数与参数表对得上 | **回 G2**，不许手工改几何 |

**G3-5 的措辞为什么改了**：原判据写的是「`pitch = 2πr/Z`、`solidity = chord/pitch` 回算
相对误差 ≤ 1e-6」。那是**定义式恒等** —— 按定义算出来的值当然等于定义，永远通过，
没有判别力。有判别力的是「几何实测的稠度与参数表写的稠度对不对得上」，
而且两边**必须取同一半径**（几何侧取截面平均半径、设计侧取流道中径，会凭空造出 3.6% 的假偏差）。
阈值与 `tools/geom_check.py` 同源，不在这里另写一份。

**G3-9 为什么必须单列**：原先只在下面「禁止项」里写着「不手工编辑几何文件」，
没有检查 id，于是人工调过轮毂、人工选过弯掠的几何在工具眼里完全合法。
DF90-001 的 v8 就是这么过去的 —— 见 `02-geometry/v8/PROVENANCE.md`。

**G3-7 说明**：`SIDES_EXCHANGE` / `REVERSE_THETA` 错会导致叶片整体镜像或吸力面/压力面互换。
这类错误在网格阶段**不会报错**，要到 CFD 出图才发现。

---

## 金属角：一维方案 → AutoBlade 的 `CAMBER_BETA`

**约定已实测确认（2026-09-20）**，全文见 `references/metal-angle-contract.md`。三条要点：

1. **两边都是从轴向量起，符号也一致 —— 换算就是直通**，不需要 `90 − x` 之类的变换。
   证据：`.par` 的 `CAMBER_GAMMA` 与从 `geomTurbo` 反算的截面安装角逐截面吻合（叶尖差 0.0000°），
   `BETA1/BETA2` 与中弧线前后缘切线角同样吻合；用 turbo-flow 的公式重算 v3 的参数表，
   R1 的出口金属角**差 −0.000°**。
2. **一维给不出展向分布** —— `result.json` 的 `metal_angle_in_profile` / `metal_angle_out_profile`
   **全是空数组**。从一维到几何，展向律是**设计选择**，不是数据。
   用 `python tools/metal_angle_convert.py --case <case> --scheme <vN> --row <叶排>` 展开，
   它会把所有假设写进 `assumptions`，**不许当数据用**。
3. **数值对不上不等于约定错。** 实测 v8 的叶片来自 **v7 的 AutoBlade**（`v8_build_par.py` 自己写着
   "5-section -> 13-section PCHIP 插值，nothing else is touched"），而 v3 的金属角来自 turbo-flow ——
   **两条独立来源**。G3-5 里 `S1 出口金属角` 那条 FAIL 是**真差异**，要消掉它必须真的按参数表重做叶片，
   **不许改比对口径**。

---

## cascade-forge 调用面（已探明，端到端未验证）

> ⚠️ **状态声明**：以下命令面已通过 `--help` 探明，**尚未在本工作流内完成端到端验证**。
> 首次跑通后必须回填实测结论，并把本条状态改为"已验证"或如实记录失败原因。

### 可执行入口

> ⚠️ **dataset 路径**：真实位置是 `<cascade-forge>/UDF/datasets/…`，
> 不是 `<cascade-forge>/datasets/…`（后者不存在，照抄会报"目录不存在"）。

> 🛑 **当前阻塞（2026-09-19 实测）**：`UDF/datasets/geometry-v2.1.0/catalog.duckdb`
> 里 `geometries_v2` = **0 行**、`anchor_fits_v2` = **0 行**，全库只有
> `schema_info` / `schema_migrations` 各 1 行。配置文件写着 `target_valid: 20000`，实际是 0。
> 有数据的只有 NACA65 那几套基准库（36 / 36 / 36 / 9 条）。
> **没有翼型可取，`build-blade` 无论怎么调都会在第一步失败。**
> 要打通这一条，得先 `ingest-anchors` 把锚点翼型灌进去 —— 那是另一件事，
> 不是"把命令抄对"能解决的。

> 📌 **`--schedule` 收的是 JSON，不是 CSV**。`build_blade` 内部调
> `SectionSchedule.model_validate_json()`，喂 `叶片几何参数表.csv` 会报
> `Invalid JSON: expected value at line 1 column 1`。
> 用 `python tools/g3_schedule.py --case <case> --row R1 --geometry-id <id>` 转换；
> 它同时写一份 `.notes.md` 说明哪些字段是原生、哪些是推算的。

```powershell
$CF = "D:\Project\Research\cascade-forge\UDF\.venv\Scripts\python.exe"
$DS = "D:\Project\Research\cascade-forge\UDF\datasets"

# 生成叶片（写入 dataset）
& $CF -m cascade_forge.cli build-blade `
    --dataset   "$DS\geometry-v2.1.0" `
    --destination <输出目录> `
    --schedule  <SectionSchedule.json> `
    --raw-root  "D:\Project\Research\cascade-forge\UDF"

# 导出几何（按 geometry_id）
& $CF -m cascade_forge.cli export <geometry_id> `
    --dataset   "$DS\geometry-v2.1.0" `
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
