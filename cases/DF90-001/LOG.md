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

