# DF90-001 交接简报

> **自动生成，勿手改。** 由 tools/case_watch.py 维护。
> 生成于 2026-09-20T07:41:48+08:00　·　当前阶段 **G5**　·　revision 101
> **新会话请先读完本文件再动手。**

## 一句话现状
已完成 G0/G1/G2/G4　**进行中 G5**　未开始 G6

**但工具不这么认为：**G2 最近一次闸门判定是 **WARN**
「已完成」说的是这一步**有产物**，闸门说的是这一步**过没过判据**。两者不一致时以后者为准 —— 明细见 LOG.md。

最近一次记录：2026-09-20T07:41:46+08:00　INFO　登记产物 04-solve/v3/g5/sweep_summary.csv

## 未登记的改动（近 14 天 71 条，历史共 71 条）

这些文件变了，但 LOG.md 里没有对应条目 —— 可能是 AutoBlade 等外部工具改的、
可能是另一个 agent 直接写的、也可能是人手工改的。**接手前请先确认它们是什么。**

- 04:26:29　**网格**　modified　03-mesh/v4/mesh-v4.config　13326 -> 13326 bytes
- 04:33:11　**算例参数**　added　04-solve/v3/n05000_p101325/n05000_p101325.run　0 -> 268409 bytes
- 05:03:43　**算例参数**　added　04-solve/v3/mesh-v4.iec　0 -> 24365931 bytes
- 05:17:50　**算例参数**　added　04-solve/v3/mesh-v4_n05000_p101325/mesh-v4_n05000_p101325.run　0 -> 268397 bytes
- 05:28:14　**算例参数**　deleted　04-solve/v3/mesh-v4.iec　24365931 -> 0 bytes
- 05:03:43　**算例参数**　added　04-solve/v3/mesh-v4.WRONG-topology.iec　0 -> 24365931 bytes
- 07:33:15　**算例参数**　added　04-solve/v3/g5/thrust_closure.csv　0 -> 741 bytes
- 07:39:22　**算例参数**　added　04-solve/v3/g5/sweep_summary.csv　0 -> 263 bytes
- …另有 63 条，见 _watch/changes.jsonl

## 最近 10 次变更

| 时间 | 类别 | 谁 | 改动 | 文件 | 大小变化 |
|---|---|---|---|---|---|
| 09-20 07:39:22 | 算例参数 | **unknown** | added | 04-solve/v3/g5/sweep_summary.csv | 0 -> 263 |
| 09-20 07:33:15 | 算例参数 | **unknown** | added | 04-solve/v3/g5/thrust_closure.csv | 0 -> 741 |
| 09-20 05:03:43 | 算例参数 | **unknown** | added | 04-solve/v3/mesh-v4.WRONG-topology.iec | 0 -> 24365931 |
| 09-20 05:28:14 | 算例参数 | **unknown** | deleted | 04-solve/v3/mesh-v4.iec | 24365931 -> 0 |
| 09-20 05:17:50 | 算例参数 | **unknown** | added | 04-solve/v3/mesh-v4_n05000_p101325/mesh-v4_n05000_p101325.run | 0 -> 268397 |
| 09-20 05:03:43 | 算例参数 | **unknown** | added | 04-solve/v3/mesh-v4.iec | 0 -> 24365931 |
| 09-20 04:33:11 | 算例参数 | **unknown** | added | 04-solve/v3/n05000_p101325/n05000_p101325.run | 0 -> 268409 |
| 09-20 04:26:29 | 网格 | **unknown** | modified | 03-mesh/v4/mesh-v4.config | 13326 -> 13326 |
| 09-20 04:26:29 | 网格 | **unknown** | modified | 03-mesh/v4/mesh-v4.bcs | 15981 -> 15981 |
| 09-20 04:26:29 | 网格 | **unknown** | modified | 03-mesh/v4/mesh-v4.igg | 459893 -> 459893 |

## 你接手前必须知道

**结论非 PASS 的产物（13 条）**

- [WARN] 02-geometry/v8/PROVENANCE.md　— 同时记录 build-par/v8_build_manifest.json 已过期（hub 与 lean 均与交付不符）
- [WARN] 02-geometry/v8/autoblade/R1_13span/R1.geomTurbo　— 转子；REVERSE_THETA=0，导出后负向，与 v7 交付件方向一致
- [WARN] 02-geometry/v8/autoblade/R2_13span/R2.geomTurbo　— 静子；REVERSE_THETA=0，导出后正向
- [WARN] 03-mesh/v1/mesh-v1.qualityReport　— new-project 基线，非交付件
- [WARN] 04-solve/v2/n05000_p101325/thrust_closure.csv　— 重登记（登记后文件被重新生成过，哈希不符）。未收敛中间值，不得用于任何结论。
- [FAIL] 04-solve/v2/n05000_p101325/anchor_comparison.json　— 跨血缘对照（环形几何差 22.7%）+ 扭矩超容差 6.53%
- [WARN] 01-scheme/v2/benchmark_gate.json
- [WARN] 01-scheme/v3/benchmark_gate.json

**待晋升的经验（2 条）**

- 2026-09-18 | AutoBlade 导出的叶型截面点是直角坐标，不是 (r, θ, z)
- 2026-09-19 | 单值设计参数与逐截面几何比对时，"落在区间内"是无效判据

## 未决问题（10 条）

- `environment.*`　来源：**assumed**　按 ISA 海平面（101325 Pa / 288.15 K）假设，用户未确认
- `materials.blade`　来源：open　叶片材料（注塑 / 复材 / 金属）
- `materials.duct`　来源：open　涵道材料
- `manufacturing.min_le_radius_m`　来源：open　前缘最小可制造半径（注塑件通常 ≥0.3–0.5 mm）
- `manufacturing.min_chord_m`　来源：open　最小弦长
- `manufacturing.process`　来源：open　制造工艺
- `shaft.tip_mach_limit`　来源：open　桨尖马赫数上限（民用常取 ≤0.7，军用 ≤0.85；**需用户确认适用值**）
- 涵道几何　来源：open　是否含扩张段 / 收缩段？唇口形式？
- 轴向长度　来源：open　轴向总长是否有约束
- `acceptance.ACC-1` 之外　来源：待细化　是否还有其他验收口径（如效率下限、噪声、重量）

## 产物（67 条）

| 阶段 | 结论 | 版本 | 路径 | sha256 |
|---|---|---|---|---|
| G0 | PASS | v1 | requirements.yaml | 32cdab3d |
| G0 | PASS | v1 | 00-brief/open_questions.md | f09eb2c3 |
| G1 | PASS | v1 | 00-brief/design_brief.md | 5ad3fa99 |
| G5 | INFO | v7 | _replay/v7/sweep_summary.csv | 7f10f7c1 |
| G5 | PASS | v7 | _replay/v7/replay_audit.json | 6460630d |
| G5 | PASS | v7 | _replay/v7/replay_report.md | 13502c72 |
| G6 | PASS | v1 | 06-delivery/v1/dashboard.html | 17b419d5 |
| G2 | PASS | v1 | 01-scheme/v1/流道尺寸表.csv | 799369fa |
| G2 | PASS | v1 | 01-scheme/v1/叶片几何参数表.csv | 6d00e19b |
| G2 | PASS | v1 | 01-scheme/v1/通流计算结果表.csv | 461c9766 |
| G2 | PASS | v1 | 01-scheme/v1/benchmark_gate.json | e338247f |
| G2 | PASS | v1 | 01-scheme/v1/benchmark_gate.md | a1210064 |
| G2 | PASS | v1 | 01-scheme/v1/inputs/turbo-flow-attempt3.json | 1f3fb70e |
| G3 | WARN | v8 | 02-geometry/v8/PROVENANCE.md | f41a2e7f |
| G3 | WARN | v8 | 02-geometry/v8/autoblade/R1_13span/R1.geomTurbo | 32abbbf6 |
| G3 | WARN | v8 | 02-geometry/v8/autoblade/R2_13span/R2.geomTurbo | ce0768ab |
| G4 | PASS | v2 | 03-mesh/v2/mesh-v2.igg | 433150fa |
| G4 | PASS | v2 | 03-mesh/v2/mesh-v2.qualityReport | 5b12a807 |
| G4 | PASS | v2 | 03-mesh/v2/mesh-v2.optimization.json | b9114d15 |
| G4 | WARN | v1 | 03-mesh/v1/mesh-v1.qualityReport | 4c849541 |
| G5 | PASS | v1 | 04-solve/v1/iec_build_audit.json | 7b717db3 |
| G5 | PASS | v1 | 04-solve/v1/scan_prelaunch_audit.json | 25ffd4d1 |
| G5 | PASS | v1 | 04-solve/v1/project_sync_audit.json | 6d0334e3 |
| G5 | INFO | v1 | 04-solve/v1/v8-optimized_n05000_p101325/v8-optimized_n05000_p101325.std | 349a129c |
| G5 | INFO | v8 | _external/v8-large-binaries.json | f03c9f6d |
| G5 | PASS | v8 | _automation/v8/scan_plan.csv | 2242a13f |
| G5 | INFO | v2 | 04-solve/v2/n05000_p101325/setup.json | 85578df6 |
| G5 | PASS | v2 | 04-solve/v2/n05000_p101325/outlet-area-audit.json | 542688cc |
| G5 | WARN | v2 | 04-solve/v2/n05000_p101325/thrust_closure.csv | 6649e94a |
| G5 | INFO | v2 | 04-solve/v2/n05000_p101325/convergence.json | 0c37c98c |
| G5 | FAIL | v2 | 04-solve/v2/n05000_p101325/anchor_comparison.json | 461fa73b |
| G2 | PASS | v2 | 01-scheme/v2/inputs/turbo-flow-v2.json | 7c0b3351 |
| G2 | PASS | v2 | 01-scheme/v2/流道尺寸表.csv | 82242eb8 |
| G2 | PASS | v2 | 01-scheme/v2/叶片几何参数表.csv | 4a0a7e0e |
| G2 | PASS | v2 | 01-scheme/v2/通流计算结果表.csv | dfe9fac0 |
| G2 | WARN | v2 | 01-scheme/v2/benchmark_gate.json | 17eb10ee |
| G2 | PASS | v2 | 01-scheme/v2/motor-envelope-check.json | 84d1b80f |
| G2 | INFO | v2 | 01-scheme/v2/NOTES.md | a1358b3e |
| G2 | PASS | v3 | 01-scheme/v3/inputs/turbo-flow-v3.json | c89df2e4 |
| G2 | PASS | v3 | 01-scheme/v3/流道尺寸表.csv | ce722e73 |
| G2 | PASS | v3 | 01-scheme/v3/叶片几何参数表.csv | 210e5597 |
| G2 | PASS | v3 | 01-scheme/v3/通流计算结果表.csv | 274149a9 |
| G2 | WARN | v3 | 01-scheme/v3/benchmark_gate.json | 79cc19a1 |
| G2 | WARN | v3 | 01-scheme/v3/thrust_1d.json | 637cace1 |
| G2 | WARN | v3 | 01-scheme/v3/thrust_1d.csv | 3cb8eb48 |
| G2 | INFO | v3 | 01-scheme/v3/NOTES.md | 6352f661 |
| G3 | PASS | v9 | 02-geometry/v9/autoblade/R1_13span/R1.geomTurbo | 4549d56f |
| G3 | PASS | v9 | 02-geometry/v9/autoblade/R2_13span/R2.geomTurbo | bc737130 |
| G3 | PASS | v9 | 02-geometry/v9/autoblade/R1_13span/R1.geomTurbo.manifest.json | 34a02fd5 |
| G3 | WARN | v9 | 02-geometry/v9/autoblade/R2_13span/R2.geomTurbo.manifest.json | 0af30532 |
| G3 | PASS | v9 | 02-geometry/v9/figures/R2/meridional.svg | cf6570dc |
| G3 | INFO | v9 | 02-geometry/v9/v9_build_report.json | 3e29de7b |
| G3 | PASS | v9 | 02-geometry/v9/figures/R1/meridional.svg | a028f475 |
| G3 | PASS | v11 | 02-geometry/v11/autoblade/R1_13span/R1.geomTurbo | 87dba87c |
| G3 | PASS | v11 | 02-geometry/v11/autoblade/R2_13span/R2.geomTurbo | 7ab3080a |
| G3 | PASS | v11 | 02-geometry/v11/autoblade/R1_13span/R1.geomTurbo.manifest.json | ddebdbb6 |
| G3 | PASS | v11 | 02-geometry/v11/autoblade/R2_13span/R2.geomTurbo.manifest.json | 96bb7ae2 |
| G4 | PASS | v3 | 03-mesh/v3/mesh-v3.igg | a11cef26 |
| G4 | PASS | v3 | 03-mesh/v3/mesh-v3.qualityReport | 15228615 |
| G4 | PASS | v4 | 03-mesh/v4/mesh-v4.igg | 2314a345 |
| G4 | PASS | v4 | 03-mesh/v4/mesh-v4.qualityReport | 824b2164 |
| G5 | INFO | v3 | 04-solve/v3/G5-REPORT.md | be872162 |
| G5 | PASS | v3 | 04-solve/v3/g5/convergence.json | e8e5a4ef |
| G5 | WARN | v3 | 04-solve/v3/g5/thrust_closure.csv | 98ea3fe3 |
| G5 | PASS | v3 | 04-solve/v3/g5/outlet-area-audit.json | 2660491f |
| G5 | FAIL | v3 | 04-solve/v3/g5/anchor_comparison.json | 502d8742 |
| G5 | INFO | v3 | 04-solve/v3/g5/sweep_summary.csv | ddb050e2 |

---

看守状态：监视 157 个文件　·　累计变更 90 条　·　历史库 353 份内容

**看守边界**：只记录四类工程实质变更 —— 设计参数 / 几何 / 网格 / 算例参数。
跑了什么检查、生成了什么报告、点了什么按钮，都不进变更流。

变更流明细：_watch/changes.jsonl　·　历史内容：_watch/history/<sha256>
