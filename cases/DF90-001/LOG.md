## 2026-09-19T16:03:33+08:00 | G0 需求 | PASS
- 动作：闸门判定 G0
- 命令：python tools/gate_check.py G0 --case cases/DF90-001
- 实测：G0-1=PASS; G0-2=PASS; G0-3=PASS; G0-4=PASS; G0-6=PASS; G0-5=PASS
- 判据：requirements.yaml 必须存在 | source=open/assumed 的字段必须在 open_questions.md 有对应条目 | thrust.unit 必须是 kgf/N/kN/lbf 之一 | value_n == value × 9.80665（kgf→N），相对误差 <= 0.1% | 推力目标 / 环境条件 / 桨盘直径 / 转速上限 必须齐全且带单位 | 见合同 C-004「整机静推力只认控制体口径」　允许 control_volume/wall_axial_force
- 结论：PASS

## 2026-09-19T16:03:33+08:00 | G1 设计大纲 | PASS
- 动作：闸门判定 G1
- 命令：python tools/gate_check.py G1 --case cases/DF90-001
- 实测：G1-1=PASS; G1-2=PASS; G1-3=PASS; G1-4=PASS
- 判据：00-brief/design_brief.md 必须存在 | 大纲中不得出现「保证/一定/必然达到」等断言 | 大纲必须包含 物理链 / 变量与约束 / 自检 三部分 | 盘载荷 0.5-20 kPa 且诱导速度 5-120 m/s
- 结论：PASS

## 2026-09-19T16:03:33+08:00 | G2 1D通流方案 | WARN
- 动作：闸门判定 G2
- 命令：python tools/gate_check.py G2 --case cases/DF90-001
- 实测：G2-1=PASS; G2-2=PASS; G2-3=PASS; G2-4=PASS; G2-5=PASS; G2-6=PASS; G2-7=WARN; G2-8=WARN
- 判据：benchmark_gate.json 必须存在、逐项带 source、且无 FAIL 项 | |mdot_in - mdot_out| / |mdot_in| <= 1e-6 | 三张表必须能追到生成它们的那一份 result.json（按效率/功率/扭矩三项认） | 叶片几何参数表的行数 == requirements rows.count，且 == 计算表的「叶排数」 | 按 ducted-fan-1d-scheme 输出契约逐列核对（含单位后缀） | 流道尺寸表 / 叶片几何参数表 / 通流计算结果表 必须都存在且非空 | 站位轴向坐标单调递增；轮毂 < 中径 < 机匣；被需求锁定的机匣半径不得被静默改动（容差 1e-04 m） | 计算表里必须有「工程可行」，且结论要能由约束清单解释
- 结论：WARN

## 2026-09-19T16:03:33+08:00 | G3 叶片造型 | FAIL
- 动作：闸门判定 G3
- 命令：python tools/gate_check.py G3 --case cases/DF90-001
- 实测：G3-1=PASS; G3-2=PASS; G3-3=PASS; G3-4=PASS; G3-5=FAIL; G3-6=PASS; G3-7=PASS; G3-8=PASS; G3-9=FAIL
- 判据：_automation/g3/schedule-<叶排>.json 的截面数 == 几何的截面数 | 全链路路径不得含非 ASCII 字符（否则 AutoGrid 会误报格式错误） | 几何必须带机器可读的溯源记录（*.manifest.json），记下它由哪份参数表导出 | 几何目录下必须有可看的预览图（目视是否像叶片由人判断，工具只查在不在） | 各截面相对展向位置单调递增，最小 ≈0、最大 ≈1（容差 0.02） | 周期数 == 叶片数 == 参数表叶片数；REVERSE_THETA / SIDES_EXCHANGE 必须已记录 | 每个截面点序闭合（首尾点重合）、相邻点不重复 | 每个截面的弦长必须为正 | 逐项比对设计表与几何实测（稠度按**同一半径**比、弦长、叶片数）；阈值与 tools/geom_check.py 同源
- 结论：FAIL

## 2026-09-19T16:03:33+08:00 | G4 网格 | PASS
- 动作：闸门判定 G4
- 命令：python tools/gate_check.py G4 --case cases/DF90-001
- 实测：G4-1=PASS; G4-2=PASS; G4-3=PASS; G4-4=PASS; G4-5=PASS
- 判据：.qualityReport 必须存在且非空 | .trb/.igg/.cgns/.qualityReport 必须齐全；大二进制可在 _external 索引中 | 网格不得有负体积单元 | 至少一套同名的网格文件 | 见合同 C-007「一个唯一网格 ↔ 一个独立 `.iec`」
- 结论：PASS

## 2026-09-19T16:03:33+08:00 | G5 求解 | WARN
- 动作：闸门判定 G5
- 命令：python tools/gate_check.py G5 --case cases/DF90-001
- 实测：G5-1=PASS; G5-2=PASS; G5-3=PASS; G5-4=PASS; G5-5=WARN
- 判据：sweep_summary.csv 必须存在 | 必须含 case/rpm/state/mass_error_pct | 振荡侧边界的 state 必须被记录；rejected（策略）与 stopped（人为）语义不同，不得混为一谈 | 每个 stopped/rejected 点必须记录 reason | 见合同 C-002「出口静压扫点：末段质量流量稳定性是主判据」　阈值 1.0%
- 结论：WARN

## 2026-09-19T16:03:33+08:00 | G6 后处理与交付 | FAIL
- 动作：闸门判定 G6
- 命令：python tools/gate_check.py G6 --case cases/DF90-001
- 实测：G6-1=FAIL; G6-2=FAIL; G6-3=FAIL
- 判据：交付目录必须有 CSV/XLSX 交付表（三表是硬要求） | 见合同 C-003「交付参数表是工程表，不是审计日志」　禁用 4 个字段 + 磁盘路径（覆盖 1 个交付文件，不限后缀） | 见合同 C-004「整机静推力只认控制体口径」
- 结论：FAIL

## 2026-09-19T16:37:44+08:00 | G3 叶片造型 | BLOCKED
- 动作：阶段状态 -> blocked
- 操作者：agent
- 判据：gate_check.py geometry: G3-9 FAIL / G3-5 FAIL
- 结论：BLOCKED
- 备注：几何不能证明由参数表导出：v8 的轮毂型线与弯掠是人工调过的，没有机器可读的来源记录（G3-9 判没通过）。要么回第 3 步用参数表重出几何，要么把电机包络约束补进需求后重跑

## 2026-09-19T16:39:50+08:00 | G0 需求 | PASS
- 动作：闸门判定 G0
- 命令：python tools/gate_check.py requirements --case cases/DF90-001
- 实测：G0-1=PASS; G0-2=PASS; G0-3=PASS; G0-4=PASS; G0-6=PASS; G0-5=PASS
- 判据：requirements.yaml 必须存在 | source=open/assumed 的字段必须在 open_questions.md 有对应条目 | thrust.unit 必须是 kgf/N/kN/lbf 之一 | value_n == value × 9.80665（kgf→N），相对误差 <= 0.1% | 推力目标 / 环境条件 / 桨盘直径 / 转速上限 必须齐全且带单位 | 见合同 C-004「整机静推力只认控制体口径」　允许 control_volume/wall_axial_force
- 结论：PASS

## 2026-09-19T16:39:50+08:00 | G1 设计大纲 | PASS
- 动作：闸门判定 G1
- 命令：python tools/gate_check.py brief --case cases/DF90-001
- 实测：G1-1=PASS; G1-2=PASS; G1-3=PASS; G1-4=PASS
- 判据：00-brief/design_brief.md 必须存在 | 大纲中不得出现「保证/一定/必然达到」等断言 | 大纲必须包含 物理链 / 变量与约束 / 自检 三部分 | 盘载荷 0.5-20 kPa 且诱导速度 5-120 m/s
- 结论：PASS

## 2026-09-19T16:39:50+08:00 | G2 1D通流方案 | WARN
- 动作：闸门判定 G2
- 命令：python tools/gate_check.py scheme --case cases/DF90-001
- 实测：G2-1=PASS; G2-2=PASS; G2-3=PASS; G2-4=PASS; G2-5=PASS; G2-6=PASS; G2-7=WARN; G2-8=WARN
- 判据：benchmark_gate.json 必须存在、逐项带 source；对标不通过记 FAIL 但**不阻塞下一步** | |mdot_in - mdot_out| / |mdot_in| <= 1e-6 | 三张表必须能追到生成它们的那一份 result.json（按效率/功率/扭矩三项认） | 叶片几何参数表的行数 == requirements rows.count，且 == 计算表的「叶排数」 | 按 ducted-fan-1d-scheme 输出契约逐列核对（含单位后缀） | 流道尺寸表 / 叶片几何参数表 / 通流计算结果表 必须都存在且非空 | 站位轴向坐标单调递增；轮毂 < 中径 < 机匣；被需求锁定的机匣半径不得被静默改动（容差 1e-04 m） | 计算表里必须有「工程可行」，且结论要能由约束清单解释
- 结论：WARN

## 2026-09-19T16:39:50+08:00 | G3 叶片造型 | FAIL
- 动作：闸门判定 G3
- 命令：python tools/gate_check.py geometry --case cases/DF90-001
- 实测：G3-1=PASS; G3-2=WARN; G3-3=PASS; G3-4=PASS; G3-5=FAIL; G3-6=PASS; G3-7=PASS; G3-8=PASS; G3-9=FAIL
- 判据：_automation/g3/schedule-<叶排>.json 的截面数 == 几何的截面数；缺一份就不算比过 | 全链路路径不得含非 ASCII 字符（否则 AutoGrid 会误报格式错误） | 几何必须带机器可读的溯源记录（*.manifest.json），记下它由哪份参数表导出 | 几何目录下必须有可看的预览图（目视是否像叶片由人判断，工具只查在不在） | 各截面相对展向位置单调递增，最小 ≈0、最大 ≈1（容差 0.02） | 周期数 == 叶片数 == 参数表叶片数；REVERSE_THETA / SIDES_EXCHANGE 必须已记录 | 每个截面点序闭合（首尾点重合）、相邻点不重复 | 每个截面的弦长必须为正 | 逐项比对设计表与几何实测（稠度按**同一半径**比、弦长、叶片数）；阈值与 tools/geom_check.py 同源
- 结论：FAIL

## 2026-09-19T16:39:50+08:00 | G4 网格 | PASS
- 动作：闸门判定 G4
- 命令：python tools/gate_check.py mesh --case cases/DF90-001
- 实测：G4-1=PASS; G4-2=PASS; G4-3=PASS; G4-4=PASS; G4-5=PASS
- 判据：.qualityReport 必须存在且非空 | .trb/.igg/.cgns/.qualityReport 必须齐全；大二进制可在 _external 索引中 | 网格不得有负体积单元 | 至少一套同名的网格文件 | 见合同 C-007「一个唯一网格 ↔ 一个独立 `.iec`」
- 结论：PASS

## 2026-09-19T16:39:50+08:00 | G5 求解 | WARN
- 动作：闸门判定 G5
- 命令：python tools/gate_check.py solve --case cases/DF90-001
- 实测：G5-1=PASS; G5-2=PASS; G5-3=PASS; G5-4=PASS; G5-5=WARN
- 判据：sweep_summary.csv 必须存在 | 必须含 case/rpm/state/mass_error_pct | 振荡侧边界的 state 必须被记录；rejected（策略）与 stopped（人为）语义不同，不得混为一谈 | 每个 stopped/rejected 点必须记录 reason | 见合同 C-002「出口静压扫点：末段质量流量稳定性是主判据」　阈值 1.0%
- 结论：WARN

## 2026-09-19T16:39:50+08:00 | G6 后处理与交付 | FAIL
- 动作：闸门判定 G6
- 命令：python tools/gate_check.py post --case cases/DF90-001
- 实测：G6-1=FAIL; G6-2=FAIL; G6-3=FAIL
- 判据：交付目录必须有 CSV/XLSX 交付表（三表是硬要求） | 见合同 C-003「交付参数表是工程表，不是审计日志」　禁用 4 个字段 + 磁盘路径（覆盖 1 个交付文件，不限后缀） | 见合同 C-004「整机静推力只认控制体口径」
- 结论：FAIL

