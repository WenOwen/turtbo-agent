# 工程日志 | DF90-001

> 只追加，不复写。每条含 时间 / 阶段 / 动作 / 输入哈希 / 实测 / 判据 / 结论 / 产物。
> 由 tools/case_ledger.py 或 tools/gate_check.py 自动写入。

## 2026-09-17T14:56:27+08:00 | 案例创建 | DF90-001
- 命令行：case_ledger.py new --case-id DF90-001
- 结论：案例骨架已建立，当前阶段 G0

## 2026-09-17T15:02:34+08:00 | G0 需求 | PASS
- 动作：登记产物 requirements.yaml
- 输入：requirements.yaml  sha256=76749d8bbef054a0  bytes=3853
- 上游：无
- 产物：requirements.yaml  sha256=76749d8bbef054a096235800aab48bb1e540e157f65eae56450f0c3f446f35a1
- 判据：11 项问答完成 6 项；推力口径/直径/电机/叶排/交付/首轮点已验证；未决项全部落在 open_questions.md
- 结论：PASS
- 备注：环境按 ISA 海平面假设，待用户确认

## 2026-09-17T15:02:34+08:00 | G0 需求 | PASS
- 动作：登记产物 00-brief/open_questions.md
- 输入：00-brief/open_questions.md  sha256=f09eb2c3627a72f8  bytes=1994
- 上游：requirements.yaml
- 产物：00-brief/open_questions.md  sha256=f09eb2c3627a72f8ed5633610d81cac682bc7262b6a8549e5b2afa7db8461eac
- 判据：每个 source=open/assumed 字段都有对应条目
- 结论：PASS

## 2026-09-17T15:02:35+08:00 | G0 需求 | PASS
- 动作：阶段状态 -> done
- 判据：四项必填齐全且带单位；未决项已落盘
- 结论：PASS

## 2026-09-17T15:02:35+08:00 | G1 设计大纲 | PASS
- 动作：登记产物 00-brief/design_brief.md
- 输入：00-brief/design_brief.md  sha256=5ad3fa996275ed72  bytes=6118
- 上游：requirements.yaml
- 产物：00-brief/design_brief.md  sha256=5ad3fa996275ed725e5ba6765287fdad0645ff5ab1dbe04580732998136216ea
- 判据：量纲正确；盘载荷 3.12 kPa、v_i 35.70 m/s 落在常见区间；FM 反推 0.668；动力包线已交叉检查
- 结论：PASS
- 备注：带条件 PASS：6100 rpm 设计点超出 EMRAX 188 连续包线，需用户确认任务剖面

## 2026-09-17T15:02:36+08:00 | G1 设计大纲 | PASS
- 动作：阶段状态 -> done
- 判据：设计变量与约束分开；未做确定性性能预测
- 结论：PASS

## 2026-09-17T15:06:03+08:00 | G5 求解 | INFO
- 动作：登记产物 _replay/v7/sweep_summary.csv
- 输入：_replay/v7/sweep_summary.csv  sha256=7f10f7c1ec9c93b7  bytes=7178
- 上游：无
- 产物：_replay/v7/sweep_summary.csv  sha256=7f10f7c1ec9c93b70f12b4e9bf230d142180fd300df070db51b013fd362fc644
- 判据：只读证据快照，源：Ducted-Fan/run/90kg-duct-fan-v7/fine/v7-optimized/sweep_summary.csv
- 结论：INFO
- 备注：内容逐字节来自基准，未修改

## 2026-09-17T15:06:03+08:00 | G5 求解 | PASS
- 动作：登记产物 _replay/v7/replay_audit.json
- 输入：_replay/v7/replay_audit.json  sha256=6460630d85d00864  bytes=9896
- 上游：_replay/v7/sweep_summary.csv
- 产物：_replay/v7/replay_audit.json  sha256=6460630d85d00864a066cb72596bb03200820a60bd389ebf2e33f22c81a8fe24
- 判据：10 项检查全 PASS；复现 45/10/2 与逐转速范围
- 结论：PASS
- 备注：回放审计，只读

## 2026-09-17T15:06:04+08:00 | G5 求解 | PASS
- 动作：登记产物 _replay/v7/replay_report.md
- 输入：_replay/v7/replay_report.md  sha256=13502c722d9323ae  bytes=3209
- 上游：_replay/v7/replay_audit.json
- 产物：_replay/v7/replay_report.md  sha256=13502c722d9323ae937ca75871902a077357e3d96f4d88977a7de729fa3ab204
- 判据：人类可读报告
- 结论：PASS

## 2026-09-17T15:06:04+08:00 | G6 后处理与交付 | INFO
- 动作：登记产物 06-delivery/v1/dashboard.html
- 输入：06-delivery/v1/dashboard.html  sha256=d9fb6231a005edac  bytes=19950
- 上游：无
- 产物：06-delivery/v1/dashboard.html  sha256=d9fb6231a005edacc17abd8c7e21ec02920e9c8d98f0698f0d85ba6296af425d
- 判据：单文件自包含，无外部依赖
- 结论：INFO

## 2026-09-17T15:06:17+08:00 | G0 需求 | INFO
- 动作：provenance 例外说明
- 实测：2 个缺失：requirements.yaml 与 _replay/v7/sweep_summary.csv
- 判据：G2 之后产物应带 provenance.from；缺失必须说明理由
- 结论：INFO
- 备注：requirements.yaml 是全案溯源根，无上游；_replay/v7/sweep_summary.csv 是外部基准的只读证据快照，上游不在本案例内。两者均属合同允许的例外。

## 2026-09-17T15:10:54+08:00 | G2 1D通流方案 | PASS
- 动作：登记产物 01-scheme/v1/流道尺寸表.csv
- 输入：01-scheme/v1/流道尺寸表.csv  sha256=799369fac0efd5eb  bytes=352
- 上游：requirements.yaml
- 产物：01-scheme/v1/流道尺寸表.csv  sha256=799369fac0efd5eb8a9b61921606af0ef63dee9c4c07eeb0f86ddea99112c1af
- 判据：5 站位；机匣半径恒 0.300（锁定值）；轮毂 0.1035->0.1255
- 结论：PASS

## 2026-09-17T15:10:54+08:00 | G2 1D通流方案 | PASS
- 动作：登记产物 01-scheme/v1/叶片几何参数表.csv
- 输入：01-scheme/v1/叶片几何参数表.csv  sha256=6d00e19b7dd70d13  bytes=338
- 上游：01-scheme/v1/流道尺寸表.csv
- 产物：01-scheme/v1/叶片几何参数表.csv  sha256=6d00e19b7dd70d137e78b99e86886f8ba8ae5682066785fc647a5b553622e67b
- 判据：2 叶排（R1 转子 9 叶 / S1 静子 11 叶）；与 requirements.rows 一致
- 结论：PASS

## 2026-09-17T15:10:55+08:00 | G2 1D通流方案 | PASS
- 动作：登记产物 01-scheme/v1/通流计算结果表.csv
- 输入：01-scheme/v1/通流计算结果表.csv  sha256=461c97666be8ce1e  bytes=873
- 上游：01-scheme/v1/叶片几何参数表.csv
- 产物：01-scheme/v1/通流计算结果表.csv  sha256=461c97666be8ce1eefcc1dfb9598a1b14985e27b6a01dbd670fed19a751ababa
- 判据：23 项指标；含效率/功率/扭矩/扩散因子/相对马赫数
- 结论：PASS

## 2026-09-17T15:10:55+08:00 | G2 1D通流方案 | PASS
- 动作：登记产物 01-scheme/v1/benchmark_gate.json
- 输入：01-scheme/v1/benchmark_gate.json  sha256=e338247f00b948db  bytes=3938
- 上游：01-scheme/v1/通流计算结果表.csv
- 产物：01-scheme/v1/benchmark_gate.json  sha256=e338247f00b948db31e4b738241a81418e9e39c19378b6b115f3c51cdfd53b9c
- 判据：PASS 6 / WARN 1 / FAIL 0；效率偏差 -1.37 pts、功率 +1.40%、扭矩 +1.40%、机匣半径偏差 0
- 结论：PASS

## 2026-09-17T15:10:56+08:00 | G2 1D通流方案 | PASS
- 动作：登记产物 01-scheme/v1/benchmark_gate.md
- 输入：01-scheme/v1/benchmark_gate.md  sha256=a1210064de503141  bytes=1743
- 上游：01-scheme/v1/benchmark_gate.json
- 产物：01-scheme/v1/benchmark_gate.md  sha256=a1210064de5031414f018249535f9ee16764c2a36ba069b77a187d52d80a4086
- 判据：人类可读对标报告，含口径说明
- 结论：PASS

## 2026-09-17T15:10:56+08:00 | G2 1D通流方案 | PASS
- 动作：登记产物 01-scheme/v1/inputs/turbo-flow-attempt3.json
- 输入：01-scheme/v1/inputs/turbo-flow-attempt3.json  sha256=1f3fb70eaf9fcf70  bytes=2560
- 上游：requirements.yaml
- 产物：01-scheme/v1/inputs/turbo-flow-attempt3.json  sha256=1f3fb70eaf9fcf700d389898c60e1611f99e93e62fa8a99397a205c9ba154d2f
- 判据：适配配置：annulus.strategy=custom + 显式 rows；可复现 attempt-3
- 结论：PASS

## 2026-09-17T15:10:57+08:00 | G2 1D通流方案 | PASS
- 动作：turbo-flow 涵道风扇适配 A/B/C 三组验证
- 实测：attempt-1(constant_mean+auto rows) eta=0.7597 pw=67.72kW 机匣r=0.3486; attempt-2(custom+auto rows) eta=0.7976 pw=64.50kW; attempt-3(custom+显式R1/S1) eta=0.8794 pw=58.50kW 机匣r=0.3000
- 产物：01-scheme/v1/benchmark_gate.json  sha256=e338247f00b948db31e4b738241a81418e9e39c19378b6b115f3c51cdfd53b9c
- 判据：对标闸门：效率绝对偏差 <=2 pts、功率与扭矩相对偏差 <=5%、机匣半径偏差 <=1e-4 m、叶排数与需求一致、工程约束 0 条不通过
- 结论：PASS
- 备注：结论：默认配置不可用（静默改掉锁定直径并自动生成三排默认几何）；必须 custom annulus + 显式 rows。flow_coefficient 按中径定义，桨尖口径需换算。B-7 WARN 归因于输入口径而非求解器缺陷。

## 2026-09-17T15:10:57+08:00 | G2 1D通流方案 | PASS
- 动作：阶段状态 -> done
- 判据：三表 schema 通过；质量守恒（进出口 15.09343 一致）；对标闸门 PASS（带 1 条 WARN 且已归因）
- 结论：PASS

## 2026-09-17T15:14:55+08:00 | G6 后处理与交付 | PASS
- 动作：看板重建并原地换版（同版本，无下游引用）
- 实测：dashboard.html 19950 -> 31599 bytes
- 判据：内容变更后必须重登记，否则 verify 会报哈希不符
- 结论：PASS
- 备注：G6 闸门原先漏认 .html 交付物，已修正 gate_check.py 的交付文件类型集合。

## 2026-09-18T22:19:20+08:00 | G0 需求 | INFO
- 动作：skill 改名：ducted-fan-kickoff-design -> ducted-fan-aero-design
- 实测：目录 1 处、文件引用 9 个、中文措辞 6 处、frontmatter name 1 处，全部更新；残留引用扫描 0 条
- 判据：用户澄清「启动设计」为「气动设计」笔误；kickoff 是误译，正名为 aerodynamic
- 结论：INFO
- 备注：已运行的 turbo-flow attempt-1 输入与其 result.json/designed_project.json 保留原描述字符串，作为历史运行记录不复写（符合本合同「只追加、不复写」）。看板已重生成并原地换版。

## 2026-09-18T22:19:32+08:00 | G0 需求 | INFO
- 动作：skill 改名 ducted-fan-kickoff-design -> ducted-fan-aero-design
- 实测：目录 1 处、文件引用 9 个、中文措辞 6 处、frontmatter name 1 处；残留引用扫描 0 条
- 判据：用户澄清「启动设计」为「气动设计」笔误；kickoff 是误译，正名 aerodynamic
- 结论：INFO
- 备注：已运行的 turbo-flow attempt-1 输入及其 result.json/designed_project.json 保留原描述字符串，作为历史运行记录不复写（符合本账本「只追加、不复写」合同）。看板已重生成并原地换版。

## 2026-09-18T22:20:51+08:00 | G3 叶片造型 | PASS
- 动作：v8 几何重建：13 截面 + 10 点 hub + 手工调整后重导出
- 实测：R1/R2 各 13 截面；hub P4=(0.103045,0.094) P5=(0.187,0.094) |P5-P4|=83.96mm；转子负向/静子正向与 v7 一致；重开 2/2 通过
- 判据：截面数=13（硬）| hub 控制点=10、|P5-P4|=84mm、P4-P5 直径=188mm（硬）| 转静切向缠绕方向与 v7 交付 geomTurbo 一致（硬）| 工程 ab_project_open 重开通过（硬）
- 结论：PASS
- 备注：产物在 Ducted-Fan/run/90kg-duct-fan-v8/autoblade/{R1_13span,R2_13span,xmt}；R1.par 由用户手工调整，R2 流道按用户要求逐点复制 R1；尚未登记进 manifest（路径不在案例目录下，待用户确认是否入库）

## 2026-09-18T22:20:51+08:00 | G4 网格 | PASS
- 动作：v8 网格：new-project 基线 + row1 流向单因素优化
- 实测：mesh-v1 基线 1686584 点/9.4508deg/2.0682；候选 89->12.919deg、93->14.544deg、97->16.406deg；选定 mesh-v2 1779880 点/16.406deg/2.5335/长宽比 1078.7 不变，点数 +5.53%
- 判据：负单元=0（硬）| 最小偏斜角>=15deg（沿袭 v7 工程合同）| 最大膨胀率<=3（沿袭）| 点数增幅<=10%
- 结论：PASS
- 备注：流道变化后必须 new-project，禁止 template-replace；v7 的候选值不可套用，需重扫。产物 mesh/mesh-v2

## 2026-09-18T22:20:51+08:00 | G5 求解 | INFO
- 动作：v8 求解布置：单网格 IEC + 57 工况物化 + 预启动审计
- 实测：57/57 computation；iec_build_audit passed；scan_prelaunch_audit passed；project_sync_audit 全 0（未登记/未物化/布局错位/重名）
- 判据：一网格一 IEC（硬）| IEC 登记数与计划一致（硬）| 每个 .run 的 GRID_FILE 指向本次网格（硬）| 11 个转子载荷面精确匹配（硬）| 冷启动工况为 START_FROM=no（硬）
- 结论：INFO
- 备注：锚点 n05000_p101325 正在迭代；其余 56 点未启动。仅代表 running，未做收敛验收

## 2026-09-18T22:20:51+08:00 | G3 叶片造型 | PASS
- 动作：阶段状态 -> done
- 判据：（阶段状态变更）
- 结论：PASS

## 2026-09-18T22:20:51+08:00 | G4 网格 | PASS
- 动作：阶段状态 -> done
- 判据：（阶段状态变更）
- 结论：PASS

## 2026-09-18T23:06:12+08:00 | G3 叶片造型 | WARN
- 动作：登记产物 02-geometry/v8/PROVENANCE.md
- 输入：02-geometry/v8/PROVENANCE.md  sha256=f41a2e7f37d9dd70  bytes=4697
- 上游：01-scheme/v1/叶片几何参数表.csv
- 产物：02-geometry/v8/PROVENANCE.md  sha256=f41a2e7f37d9dd700ea1bd4a4a10313f0828fc7fb0856d5e52ce1047c6bb77f5
- 判据：手工调整声明：R1 轮毂 10 点由用户按电机包络(EMRAX 188 = Ø188mm x 79mm)调整；13 截面；LEAN_BETA=3度。G3-7「由参数表导出」不成立。
- 结论：WARN
- 备注：同时记录 build-par/v8_build_manifest.json 已过期（hub 与 lean 均与交付不符）

## 2026-09-18T23:06:12+08:00 | G3 叶片造型 | WARN
- 动作：登记产物 02-geometry/v8/autoblade/R1_13span/R1.geomTurbo
- 输入：02-geometry/v8/autoblade/R1_13span/R1.geomTurbo  sha256=32abbbf639c150ad  bytes=204473
- 上游：02-geometry/v8/PROVENANCE.md
- 产物：02-geometry/v8/autoblade/R1_13span/R1.geomTurbo  sha256=32abbbf639c150adf47a66db20d083ff347728a46f948a0fe473b06ab695a0d4
- 判据：13 截面导出件；含人工调整的轮毂型线与弯掠，不可由参数表复现
- 结论：WARN
- 备注：转子；REVERSE_THETA=0，导出后负向，与 v7 交付件方向一致

## 2026-09-18T23:06:12+08:00 | G3 叶片造型 | WARN
- 动作：登记产物 02-geometry/v8/autoblade/R2_13span/R2.geomTurbo
- 输入：02-geometry/v8/autoblade/R2_13span/R2.geomTurbo  sha256=ce0768ab5b2e04ff  bytes=202807
- 上游：02-geometry/v8/PROVENANCE.md
- 产物：02-geometry/v8/autoblade/R2_13span/R2.geomTurbo  sha256=ce0768ab5b2e04ffb06add624cdfc3800fb0c7e071f95786149ee774e5257dd8
- 判据：13 截面；流道逐点复制为与 R1 一致，其余参数不动
- 结论：WARN
- 备注：静子；REVERSE_THETA=0，导出后正向

## 2026-09-18T23:06:12+08:00 | G4 网格 | PASS
- 动作：登记产物 03-mesh/v2/mesh-v2.igg
- 输入：03-mesh/v2/mesh-v2.igg  sha256=433150fa56c18eca  bytes=483468
- 上游：02-geometry/v8/autoblade/R1_13span/R1.geomTurbo
- 产物：03-mesh/v2/mesh-v2.igg  sha256=433150fa56c18ecaa91e4190dc2f078bbabaf3f19ad4de08c22d9f45d00fac3d
- 判据：最小偏斜角 16.406度 (>=10)；1,779,880 点；new-project 模式；单因素扫描 89->93->97 的首个通过项
- 结论：PASS
- 备注：交付网格。网格身份 SHA256 433150fa...fac3d（见 README-v8）

## 2026-09-18T23:06:12+08:00 | G4 网格 | PASS
- 动作：登记产物 03-mesh/v2/mesh-v2.qualityReport
- 输入：03-mesh/v2/mesh-v2.qualityReport  sha256=5b12a8079755b3c5  bytes=4442
- 上游：03-mesh/v2/mesh-v2.igg
- 产物：03-mesh/v2/mesh-v2.qualityReport  sha256=5b12a8079755b3c569cebb4fede061211073242c297658efd6c229ba8ca62784
- 判据：质量报告存在且非空
- 结论：PASS

## 2026-09-18T23:06:12+08:00 | G4 网格 | PASS
- 动作：登记产物 03-mesh/v2/mesh-v2.optimization.json
- 输入：03-mesh/v2/mesh-v2.optimization.json  sha256=b9114d1520433722  bytes=3124
- 上游：无
- 产物：03-mesh/v2/mesh-v2.optimization.json  sha256=b9114d1520433722645ad9391e4a036659eab2546502c8a35c0fbe754f50f682
- 判据：单因素扫描记录 89/93/97 -> 12.919/14.544/16.406 度
- 结论：PASS
- 备注：注：脚本在产物写完后抛 UnicodeEncodeError，产物完整

## 2026-09-18T23:06:12+08:00 | G4 网格 | WARN
- 动作：登记产物 03-mesh/v1/mesh-v1.qualityReport
- 输入：03-mesh/v1/mesh-v1.qualityReport  sha256=4c849541dafa1215  bytes=4473
- 上游：02-geometry/v8/autoblade/R1_13span/R1.geomTurbo
- 产物：03-mesh/v1/mesh-v1.qualityReport  sha256=4c849541dafa12150cb4312c92db54e24a8b8bb2da1ed461329edfd8489e91c6
- 判据：基线网格最小偏斜角 9.4508度，低于 10 度阈值；保留作为优化来源与证据
- 结论：WARN
- 备注：new-project 基线，非交付件

## 2026-09-18T23:06:12+08:00 | G5 求解 | PASS
- 动作：登记产物 04-solve/v1/iec_build_audit.json
- 输入：04-solve/v1/iec_build_audit.json  sha256=7b717db31d854649  bytes=13116
- 上游：无
- 产物：04-solve/v1/iec_build_audit.json  sha256=7b717db31d8546497d128ac2486833eb68f49e8fefabada1f700fd45b459efc3
- 判据：57/57 通过：转速、出口静压、11 个转子载荷面
- 结论：PASS

## 2026-09-18T23:06:12+08:00 | G5 求解 | PASS
- 动作：登记产物 04-solve/v1/scan_prelaunch_audit.json
- 输入：04-solve/v1/scan_prelaunch_audit.json  sha256=25ffd4d1ad2746c3  bytes=53528
- 上游：无
- 产物：04-solve/v1/scan_prelaunch_audit.json  sha256=25ffd4d1ad2746c37ebaea8f0b2f29697ca536b97489eec340274d51feb57478
- 判据：57/57 通过；冷启动锚点识别为 cold_start
- 结论：PASS

## 2026-09-18T23:06:12+08:00 | G5 求解 | PASS
- 动作：登记产物 04-solve/v1/project_sync_audit.json
- 输入：04-solve/v1/project_sync_audit.json  sha256=6d0334e35e9d6fc1  bytes=57169
- 上游：无
- 产物：04-solve/v1/project_sync_audit.json  sha256=6d0334e35e9d6fc1a67d845d3007b4bae1bad80ab3418568b9a36252957c2d38
- 判据：project_without_run=0、run_not_registered=0、layout_mismatch=0、无重名、网格一致（C-007 双向同步）
- 结论：PASS

## 2026-09-18T23:06:12+08:00 | G5 求解 | INFO
- 动作：登记产物 04-solve/v1/v8-optimized_n05000_p101325/v8-optimized_n05000_p101325.std
- 输入：04-solve/v1/v8-optimized_n05000_p101325/v8-optimized_n05000_p101325.std  sha256=349a129c968ea5d4  bytes=45056
- 上游：无
- 产物：04-solve/v1/v8-optimized_n05000_p101325/v8-optimized_n05000_p101325.std  sha256=349a129c968ea5d45ef1ddd88c30bb3e14a0d23a31bb159df51370c421d72270
- 判据：锚点正在迭代中 —— 仅代表 running。未做收敛验收（C-002 判据未执行）
- 结论：INFO
- 备注：其余 56 点未启动；本条目不得被解读为 accepted

## 2026-09-18T23:06:12+08:00 | G5 求解 | INFO
- 动作：登记产物 _external/v8-large-binaries.json
- 输入：_external/v8-large-binaries.json  sha256=f03c9f6d0c70e79f  bytes=3685
- 上游：无
- 产物：_external/v8-large-binaries.json  sha256=f03c9f6d0c70e79f89e692a7856aa90be2145d48a456189fc43f1a6ce2247ef2
- 判据：10 个大二进制（355.5 MB）的外部路径 + sha256 索引：.iec 23.8MB、.cgns x3 (162.8/50.6/94.9MB)、.geom x2、.adf、.res、.mf、.xmf
- 结论：INFO
- 备注：按账本合同「只索引不复制」处理；含 n05000_p101325.cgns 162.84 MB，说明锚点已写出解

## 2026-09-18T23:06:57+08:00 | G3 叶片造型 | WARN
- 动作：v8 归位入案例（361 文件 / 23MB）+ 手工调整溯源声明
- 实测：R1 轮毂 10 点人工调整（P4-P5 = Ø188mm x 83.96mm，对应 EMRAX 188 电机包络）；LEAN_BETA 3 度；13 截面（参数表为 5 截面）；build-par/v8_build_manifest.json 已过期
- 产物：02-geometry/v8/PROVENANCE.md  sha256=f41a2e7f37d9dd700ea1bd4a4a10313f0828fc7fb0856d5e52ce1047c6bb77f5
- 判据：G3-7「几何由参数表导出」不成立；其余自查可判
- 结论：WARN
- 备注：10 个大二进制 (355.5MB) 按只索引不复制登记在 _external/v8-large-binaries.json。根因：电机几何包络未进 requirements.yaml，G2 无法表达该约束，只能在 G3 手工满足。已把该字段补进 requirements-interview.md Q5。

## 2026-09-18T23:54:08+08:00 | G0 需求 | INFO
- 动作：界面写操作能力自检
- 操作者：human(web-ui)
- 判据：操作者字段可写入且可被解析
- 结论：INFO

## 2026-09-18T23:55:29+08:00 | G0 需求 | PASS
- 动作：界面执行动作：校验案例产物与哈希
- 操作者：human(web-ui)
- 实测：exit=0  用时 0.1s
- 判据：命令退出码为 0
- 结论：PASS
- 备注：校验 26 个产物：全部通过 /   ! 8 个产物缺 provenance（建议补 --from）

## 2026-09-19T00:10:23+08:00 | G0 需求 | PASS
- 动作：界面执行动作：校验案例产物与哈希
- 操作者：human(web-ui)
- 实测：exit=0  用时 0.1s
- 判据：命令退出码为 0
- 结论：PASS
- 备注：校验 26 个产物：全部通过 /   ! 8 个产物缺 provenance（建议补 --from）

## 2026-09-19T00:10:27+08:00 | G0 需求 | PASS
- 动作：界面执行动作：校验案例产物与哈希
- 操作者：human(web-ui)
- 实测：exit=0  用时 0.1s
- 判据：命令退出码为 0
- 结论：PASS
- 备注：校验 26 个产物：全部通过 /   ! 8 个产物缺 provenance（建议补 --from）

## 2026-09-19T00:10:32+08:00 | G0 需求 | PASS
- 动作：界面执行动作：校验案例产物与哈希
- 操作者：human(web-ui)
- 实测：exit=0  用时 0.1s
- 判据：命令退出码为 0
- 结论：PASS
- 备注：校验 26 个产物：全部通过 /   ! 8 个产物缺 provenance（建议补 --from）

## 2026-09-19T00:10:43+08:00 | G0 需求 | PASS
- 动作：界面执行动作：环境预检
- 操作者：human(web-ui)
- 实测：exit=0  用时 0.4s
- 判据：命令退出码为 0
- 结论：PASS
- 备注：环境预检：通过 /   v P-1 projectRoot === cwd  [cwd=D:\Project\Research\turtbo-agent  projectRoot=D:\Project\Research\turtbo-agent] /   v P-2 工作路径纯 ASCII  [D:\Project\Research\turtbo-agent]

## 2026-09-19T00:20:07+08:00 | G1 设计大纲 | INFO
- 动作：界面编辑文件 cases/DF90-001/00-brief/open_questions.md
- 操作者：human(web-ui)
- 实测：sha256 7ea71c6697bcc94f -> eea2984d1e7ba8b8；2076 -> 2043 bytes
- 判据：内容变更已确认；写回前 sha256 与读取时一致（乐观锁通过）
- 结论：INFO
- 备注：操作者通过实时工作台直接编辑

## 2026-09-19T00:20:50+08:00 | G1 设计大纲 | INFO
- 动作：界面编辑文件 cases/DF90-001/00-brief/open_questions.md
- 操作者：human(web-ui)
- 实测：sha256 eea2984d1e7ba8b8 -> 5dfcb6684188ccf2；2043 -> 2037 bytes
- 判据：内容变更已确认；写回前 sha256 与读取时一致（乐观锁通过）
- 结论：INFO
- 备注：操作者通过实时工作台直接编辑

## 2026-09-19T01:10:51+08:00 | G4 网格 | WARN
- 动作：闸门判定 G4
- 命令：python tools/gate_check.py G4 --case cases/DF90-001
- 实测：G4-1=PASS; G4-2=PASS; G4-3=PASS; G4-4=PASS; G4-5=WARN
- 判据：.qualityReport 必须存在且非空 | .trb/.igg/.cgns/.qualityReport 必须齐全；大二进制可在 _external 索引中 | 网格不得有负体积单元 | 至少一套同名的网格文件 | 见合同 C-007「一个唯一网格 ↔ 一个独立 `.iec`」
- 结论：WARN

## 2026-09-19T01:11:01+08:00 | G0 需求 | PASS
- 动作：闸门判定 G0
- 命令：python tools/gate_check.py G0 --case cases/DF90-001
- 实测：G0-1=PASS; G0-2=PASS; G0-3=PASS; G0-4=PASS; G0-5=PASS
- 判据：requirements.yaml 必须存在 | source=open/assumed 的字段必须在 open_questions.md 有对应条目 | thrust.unit 必须是 kgf/N/kN/lbf 之一 | 推力目标 / 环境条件 / 桨盘直径 / 转速上限 必须齐全且带单位 | 见合同 C-004「整机静推力只认控制体口径」　允许 control_volume/wall_axial_force
- 结论：PASS

## 2026-09-19T01:11:01+08:00 | G1 设计大纲 | PASS
- 动作：闸门判定 G1
- 命令：python tools/gate_check.py G1 --case cases/DF90-001
- 实测：G1-1=PASS; G1-2=PASS; G1-3=PASS; G1-4=PASS
- 判据：00-brief/design_brief.md 必须存在 | 大纲中不得出现「保证/一定/必然达到」等断言 | 大纲必须包含 物理链 / 变量与约束 / 自检 三部分 | 盘载荷 0.5-20 kPa 且诱导速度 5-120 m/s
- 结论：PASS

## 2026-09-19T01:11:01+08:00 | G4 网格 | WARN
- 动作：闸门判定 G4
- 命令：python tools/gate_check.py G4 --case cases/DF90-001
- 实测：G4-1=PASS; G4-2=PASS; G4-3=PASS; G4-4=PASS; G4-5=WARN
- 判据：.qualityReport 必须存在且非空 | .trb/.igg/.cgns/.qualityReport 必须齐全；大二进制可在 _external 索引中 | 网格不得有负体积单元 | 至少一套同名的网格文件 | 见合同 C-007「一个唯一网格 ↔ 一个独立 `.iec`」
- 结论：WARN

## 2026-09-19T01:11:01+08:00 | G5 求解 | INFO
- 动作：闸门判定 G5
- 命令：python tools/gate_check.py G5 --case cases/DF90-001
- 实测：G5-1=SKIP
- 判据：sweep_summary.csv 必须存在（或用 --summary 指定）
- 结论：INFO

## 2026-09-19T01:11:01+08:00 | G6 后处理与交付 | PASS
- 动作：闸门判定 G6
- 命令：python tools/gate_check.py G6 --case cases/DF90-001
- 实测：G6-1=PASS; G6-2=PASS; G6-3=SKIP
- 判据：static_thrust = momentum_thrust + pressure_thrust，容差 1e-6 相对 | 交付目录必须有表格/说明文件 | 见合同 C-003「交付参数表是工程表，不是审计日志」　禁用 4 个字段 + 磁盘路径
- 结论：PASS

## 2026-09-19T01:41:44+08:00 | G0 需求 | PASS
- 动作：闸门判定 G0
- 命令：python tools/gate_check.py G0 --case cases/DF90-001
- 实测：G0-1=PASS; G0-2=PASS; G0-3=PASS; G0-4=PASS; G0-5=PASS
- 判据：requirements.yaml 必须存在 | source=open/assumed 的字段必须在 open_questions.md 有对应条目 | thrust.unit 必须是 kgf/N/kN/lbf 之一 | 推力目标 / 环境条件 / 桨盘直径 / 转速上限 必须齐全且带单位 | 见合同 C-004「整机静推力只认控制体口径」　允许 control_volume/wall_axial_force
- 结论：PASS

## 2026-09-19T01:41:44+08:00 | G1 设计大纲 | PASS
- 动作：闸门判定 G1
- 命令：python tools/gate_check.py G1 --case cases/DF90-001
- 实测：G1-1=PASS; G1-2=PASS; G1-3=PASS; G1-4=PASS
- 判据：00-brief/design_brief.md 必须存在 | 大纲中不得出现「保证/一定/必然达到」等断言 | 大纲必须包含 物理链 / 变量与约束 / 自检 三部分 | 盘载荷 0.5-20 kPa 且诱导速度 5-120 m/s
- 结论：PASS

## 2026-09-19T01:41:44+08:00 | G4 网格 | WARN
- 动作：闸门判定 G4
- 命令：python tools/gate_check.py G4 --case cases/DF90-001
- 实测：G4-1=PASS; G4-2=PASS; G4-3=PASS; G4-4=PASS; G4-5=WARN
- 判据：.qualityReport 必须存在且非空 | .trb/.igg/.cgns/.qualityReport 必须齐全；大二进制可在 _external 索引中 | 网格不得有负体积单元 | 至少一套同名的网格文件 | 见合同 C-007「一个唯一网格 ↔ 一个独立 `.iec`」
- 结论：WARN

## 2026-09-19T01:41:44+08:00 | G5 求解 | FAIL
- 动作：闸门判定 G5
- 命令：python tools/gate_check.py G5 --case cases/DF90-001
- 实测：G5-1=FAIL
- 判据：sweep_summary.csv 必须存在（或用 --summary 指定）
- 结论：FAIL

## 2026-09-19T01:41:44+08:00 | G6 后处理与交付 | FAIL
- 动作：闸门判定 G6
- 命令：python tools/gate_check.py G6 --case cases/DF90-001
- 实测：G6-1=FAIL; G6-2=FAIL; G6-3=FAIL
- 判据：交付目录必须有 CSV/XLSX 交付表（三表是硬要求） | 见合同 C-003「交付参数表是工程表，不是审计日志」　禁用 4 个字段 + 磁盘路径（覆盖 1 个交付文件，不限后缀） | 见合同 C-004「整机静推力只认控制体口径」
- 结论：FAIL

## 2026-09-19T01:45:14+08:00 | G5 求解 | WARN
- 动作：闸门判定 G5
- 命令：python tools/gate_check.py G5 --case cases/DF90-001
- 实测：G5-1=PASS; G5-2=PASS; G5-3=PASS; G5-4=PASS; G5-5=WARN
- 判据：sweep_summary.csv 必须存在 | 必须含 case/rpm/state/mass_error_pct | 振荡侧边界的 state 必须被记录；rejected（策略）与 stopped（人为）语义不同，不得混为一谈 | 每个 stopped/rejected 点必须记录 reason | 见合同 C-002「出口静压扫点：末段质量流量稳定性是主判据」　阈值 1.0%
- 结论：WARN

## 2026-09-19T01:46:57+08:00 | G4 网格 | PASS
- 动作：闸门判定 G4
- 命令：python tools/gate_check.py G4 --case cases/DF90-001
- 实测：G4-1=PASS; G4-2=PASS; G4-3=PASS; G4-4=PASS; G4-5=PASS
- 判据：.qualityReport 必须存在且非空 | .trb/.igg/.cgns/.qualityReport 必须齐全；大二进制可在 _external 索引中 | 网格不得有负体积单元 | 至少一套同名的网格文件 | 见合同 C-007「一个唯一网格 ↔ 一个独立 `.iec`」
- 结论：PASS

## 2026-09-19T02:46:31+08:00 | G3 叶片造型 | FAIL
- 动作：设计参数表与几何实测逐项对照
- 操作者：agent
- 命令：python tools/geom_check.py --case cases/DF90-001
- 实测：items=16 PASS=8 WARN=2 FAIL=6；R1 beta2 中径差 5.25deg；S1 beta2 中径差 15.15deg（转向 1.48 倍）；R1 tip_gap 0.002 vs 设计 0.0005；S1 几何 z 0.1714-0.2607 整落在设计出口平面 z=0.180135 下游
- 判据：设计值对照 16 项：一致 8 / 偏离 2 / 对不上 6。对不上的是：R1 出口金属角（设计 -61.39 vs 中径 -56.14）、R1 叶尖间隙（设计 0.5mm vs 几何 2.0mm）、R1 轴向站位（设计 0.1376 vs 几何 0.0205-0.0936）、S1 出口金属角（设计 -2.19 vs 中径 -17.34）、S1 叶尖间隙（几何无间隙块）、S1 轴向站位（设计 0.1376 vs 几何 0.1714-0.2607）。结论：本案例 02-geometry/v8 的几何不是从 01-scheme/v1 这两张表导出的，两者血缘不同。
- 结论：FAIL
- 备注：工具 tools/geom_check.py。这不是说几何做错了，是说这两份东西不是同一套血缘 —— 接手的人必须知道。v8 几何由 v7 五截面 PCHIP 插值而来（见 _automation/v8/build-par/v8_build_manifest.json），不是从本案例的 G2 表导出的。

