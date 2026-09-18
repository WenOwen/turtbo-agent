# 90kg 涵道风扇 v8 — 几何 / 网格 / 计算 工作区

**当前状态（2026-09-18 22:2x）**

| 阶段 | 状态 | 说明 |
|---|---|---|
| 几何 AutoBlade | ✅ 完成 | R1 已由用户手工调整（10 点 hub + 弯掠），R2 流道已同步为 R1 的流道；两者已重新导出 GeomTurbo 与 XMT |
| 网格 AutoGrid | ✅ 完成 | `mesh-v1` 为 new-project 基线（最小偏斜角 9.45°，warn），`mesh-v2` 为交付网格（16.406°，通过） |
| 计算 FINE | 🟡 已布置并启动锚点 | 57 个 computation 已登记并物化 `.run`，预启动审计通过；`n05000_p101325` 锚点已在迭代中，其余 56 点等待按重启动链推进 |

---

## 1. 目录

```text
run/90kg-duct-fan-v8/
├─ autoblade/
│  ├─ R1_13span/{R1.par, R1.abp, R1.geomTurbo, R1/model*.abm}
│  ├─ R2_13span/{R2.par, R2.abp, R2.geomTurbo, R2/model*.abm}
│  └─ xmt/{R1-model.xmt_txt, R2-model.xmt_txt}
├─ mesh/
│  ├─ mesh-v1/    new-project 基线（保留作为优化来源与证据）
│  └─ mesh-v2/    交付网格：+ row1 流向 97 点
├─ fine/v8-optimized/
│  ├─ v8-optimized.iec            单网格专属工程（57 computations）
│  ├─ v8-optimized_<case>/        每工况一个 ICE 原生同级目录
│  ├─ scan_plan.csv, materialize_report.json
│  ├─ iec_build_audit.json, scan_prelaunch_audit.json, project_sync_audit.json
│  └─ v8-optimized_n05000_p101325/  ← 正在计算
├─ figures/        3 张图
├─ automation/     可复跑脚本与证据 JSON
└─ README.md
```

---

## 2. 几何（v8）

R1 的 10 点 hub（用户手工调整后为当前值）：

| 点 | z [m] | r [m] | 直径 [mm] |
|---|---|---|---|
| P1 | 0.000000 | 0.080000 | 160.00 |
| P2 | 0.033631 | 0.084553 | 169.11 |
| P3 | 0.067521 | 0.090687 | 181.37 |
| **P4** | **0.103045** | **0.094000** | **188.00** |
| **P5** | **0.187000** | **0.094000** | **188.00** |
| P6 | 0.213289 | 0.096003 | 192.01 |
| P7 | 0.236971 | 0.100910 | 201.82 |
| P8 | 0.258612 | 0.106227 | 212.45 |
| P9 | 0.277802 | 0.110725 | 221.45 |
| P10 | 0.300000 | 0.113178 | 226.36 |

- |P5 − P4| = **83.96 mm**（电机 79 mm + 预留），P4–P5 直径为 **Ø188 mm**。
- 机匣保持 Ø600 直筒；hub 全程非降（整体收缩）。
- **R2 的流道已按用户要求改成与 R1 完全一致**（hub 10 点 + shroud 2 点逐点复制，其余 R2 参数不动）。
- 13 个展向截面（余弦分布），弯/掠由 simple Bezier 堆叠律控制（`LEAN_BETA`=3°，掠用 `BEZIER_BETA1_BETA2`）。
- 转静方向门禁：两排 `REVERSE_THETA = 0`，导出后转子负向、静子正向，与 v7 交付件一致。

导出：`R1.geomTurbo` / `R2.geomTurbo` 各含 13 个截面；XMT 为**整模型** Parasolid 文本
（批处理 API 只能导出整模型；v7 的 hub/shroud/repeat-blade 分文件来自 GUI 对话框，无法用批处理等价复现）。

---

## 3. 网格

模式为 `new-project`（流道变化后禁止 `template-replace`，否则工程级 CHANNEL 仍保留旧流道）。

| | 点数 | 最小偏斜角 | 最大长宽比 | 最大膨胀率 |
|---|---:|---:|---:|---:|
| mesh-v1（基线，81 点） | 1,686,584 | 9.4508° ⚠ | 1078.7 | 2.0682 |
| **mesh-v2（交付，97 点）** | **1,779,880** | **16.406°** | 1078.7 | 2.5335 |

- 物理合同：row1 转子 9 叶、2 mm 叶顶间隙、5000 rpm、73 层；row2 静子 11 叶、无间隙、57 层；第一层 1e-5 m。
- 单因素扫描 89 → 93 → 97（12.919° → 14.544° → 16.406°），97 点为首个通过项（+5.53% 点数）。
- 网格 `.geomTurbo` 的 hub/shroud 点数与哈希等于 R1 AutoBlade 源（由审计器核对）。
- v7 已验证过的候选值不能直接套用：本次 81 点基线的 9.45° 比 v7 基线 11.65° 更差，需重扫。

---

## 4. 计算布置

- 网格身份：`mesh-v2.igg`，SHA256 `433150fa…fac3d`；专属工程 `v8-optimized.iec`（一网格一 IEC）。
- 计划：3 条转速线（4500 / 5000 / 5500 rpm）× 19 个出口静压点 = 57 工况，冷启动锚点 `n05000_p101325`，
  入口总压 101325 Pa、总温 288.15 K；其余点按分支重启动链推进（`automation/scan_plan.csv`）。
- 57 个 computation 全部登记进 IEC 并物化为 ICE 原生同级目录
  `vv8-optimized_<case>/v8-optimized_<case>.run`。
- 审计全通过：
  - `iec_build_audit.json` → passed（57/57，转速、出口静压、11 个转子载荷面）；
  - `scan_prelaunch_audit.json` → passed（57/57，冷启动锚点识别为 `cold_start`）；
  - `project_sync_audit.json` → `project_without_run=0`、`run_not_registered=0`、`layout_mismatch=0`、无重名、网格一致。
- 已启动：**`n05000_p101325` 冷启动锚点**（`euranusx86_64 -seq -batch`，PID 见进程表），
  当前处于细网格迭代（残差有限，尚未收敛验收）。

### 尚未做的事

- 其余 56 个工况**未启动**（依赖链：每条速度线的锚点必须先通过收敛与工程量验收）。
- 未做收敛验收、未做网格无关性、未做后处理与性能曲线。

---

## 5. 本次沉淀到 skill 的问题

已写入 skill（通用规则与坑，未写入本项目的具体数值）：

`numeca-autoblade-geometry` — 新增 `references/par_rebuild_pitfalls.md`，SKILL.md 加了最小清单：
- 改写 `VALUE` 类字段必须用 `[ \t]{2,}`（`\s{2,}` 会跨行吃掉下一行且不报错）；
- `NUMBER_OF_PARAMETERS` 要按"任意父容器"统计，写成 `+0` 会让 AutoBlade 静默改用默认叶型；
- 同截面同名参数可重复出现，必须按文档顺序重建；重建后要用"骨架比对"做门禁；
- `SPLINE_N` 端壁是过控制点的全局曲线，"长直段 + 扩张"必然下沉，等直径段不能靠共线控制点保证；
- GeomTurbo 截面点可能是直角坐标（`r = hypot(x, y)`）；
- `.par` 里的 `REVERSE_THETA` 不等于交付件实际使用的值，必须重跑比对（本项目发现 v7 的 R1 就属于这种情况）；
- 批处理只能导出整模型 Parasolid，GUI 的按对象分文件导出不可等价复现。

`numeca-autogrid-meshing` — SKILL.md 补了：
- `new-project` 之后是"质量重置"，不会继承旧网格已调好的 B2B 控制，必须重扫单因素；
- 脚本用 `ensure_ascii=False` 打印中文审计时，中文 Windows 会在产物写完后抛 `UnicodeEncodeError`，
  不要据此判失败（本次优化即如此，产物与优化记录齐全）。

`numeca-fine-solver` — `references/multispeed_characteristic_scan.md` 新增 6.5–6.9，并修了两个脚本缺陷：
- **`finebatch -index` 是零基**：传一基位置会物化下一个 computation 却写进你给的文件名（本次已实际踩到，
  锚点一度被写成了 4500 rpm 的工况）；物化后必须逐项核对 `.run`；
- **冷启动不能写 `START_FROM_INITIAL_SOLUTION_FILE yes`**：`build_multispeed_iec.py` 已修正为
  `no` + `INITIAL_SOLUTION_FILE unknown`，`audit_characteristic_scan.py` 已把空 restart 识别为冷启动；
- `.run` 的转速是 rad/s，IEC 是 rpm，不能直接比数；
- 字段正则不要用 `\s`（`INITIAL_SOLUTION_FILE` 在一个 `.run` 里可能出现多次）；
- 转子载荷面白名单要在 `.run` 的 `boundary_condition` 块上核对，`.bcs` 里没有这些名字。

---

## 6. 复跑命令

```powershell
$A = 'D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v8\automation'
$env:PYTHONIOENCODING = 'utf-8'

# 几何：同步 R2 流道 + 重新导出 geomTurbo / XMT
python $A\export_v8.py

# 网格：基线（new-project）与单因素优化
python C:\Users\Administrator\.agents\skills\numeca-autogrid-meshing\scripts\build_autogrid_mesh.py $A\mesh_job.json
python C:\Users\Administrator\.agents\skills\numeca-autogrid-meshing\scripts\optimize_existing_mesh.py $A\mesh_optimize_job.json

# 计算：计划 -> IEC -> 物化 -> 审计
python $A\build_scan_plan.py
python C:\Users\Administrator\.agents\skills\numeca-fine-solver\scripts\build_multispeed_iec.py --help
python $A\materialize_runs.py
python $A\audit_run.py <case.run>
python $A\compare_run_surfaces.py
```

## 7. 图

| 文件 | 内容 |
|---|---|
| `figures/v8-flowpath-hub-line.png` | 子午流道：v7 hub / v8 hub（10 控制点）+ 机匣 + 电机包络 |
| `figures/v8-sections-vs-v7.png` | R1 展向分布：安装角 / 轴向弦长 / 切向包角，v8 13 截面 vs v7 5 截面 |
| `figures/v8-lean-sweep-delta.png` | simple Bezier 弯/掠调整量（输入 JSON 需由 `v8_leansweep_delta.py` 重新生成） |
