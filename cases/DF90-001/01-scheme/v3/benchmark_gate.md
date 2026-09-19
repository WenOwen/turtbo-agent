# G2 对标闸门报告

- 时间：2026-09-20T01:51:28+08:00
- 结论：**PASS**（PASS 6 / WARN 1 / FAIL 0 / SKIP 0）
- 基准来源：Ducted-Fan/PPT/涵道风扇文件创建计算指导-20260904.pptx 第3页（6100 rpm 设计点）+ requirements.yaml

| id | 项目 | 目标 | 实测 | 偏差 | 容差 | 结论 |
|---|---|---|---|---|---|---|
| B-1 | 总总效率（绝对偏差） | 0.8931 | 0.8782235848229542 | -0.01488 | 0.02 | **PASS** |
| B-2 | 轴功率（相对偏差） | 57695.871 | 58579.594378791444 | +1.53% | 0.05 | **PASS** |
| B-3 | 扭矩（相对偏差） | 90.32 | 91.70392140691342 | +1.53% | 0.05 | **PASS** |
| B-4 | 机匣半径（绝对偏差, m） | 0.3 | 0.3 | 0 | 0.0001 | **PASS** |
| B-5 | 叶排数 | 2 | 2 | 0 | 0 | **PASS** |
| B-6 | 工程约束全部通过 | 0 条不通过 | 0 条不通过 | - | 0 | **PASS** |
| B-7 | 输入的设计目标自洽 | 0 条不通过 | 2 条不通过 | - | 0 | **WARN** |

## 求解器自述

- 状态：converged，迭代 2 次
- 效率目标角色：initial work estimate and feasibility constraint, not imposed result
- 流道方法：total-state sizing seed; frozen during aerodynamic inverse solve
- 设计方法：inverse metal angles + entropy losses + pressure-ratio shooting + forward verification
- 警告：[]

## 口径说明（必读）

1. 总压比是反设计的射击目标，与目标一致不构成证据；真正的证据是效率、功率、扭矩。
2. flow_coefficient 按中径定义。桨尖口径需换算：phi_mean = phi_tip * r_tip / r_mean。
3. target_efficiency_tt 只作初始功估算与可行性约束，不是强制结果。
4. 机匣半径必须由 custom annulus 锁死；默认 constant_mean 会静默改掉被需求锁定的直径。

