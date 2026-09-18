# 案例经验记录 | DF90-001

> 条目格式见 .agents/skills/turbomachinery-case-ledger/SKILL.md。
> 满足晋升三条件之一时，改写为可执行判据进入 skill 的 references/contracts.md。

## 2026-09-17 | 交付文档的"首个振荡背压"有两种状态口径，审计脚本不能只匹配 rejected

- 来源：实测发现（回放审计 v7 时 R-8 首次报 FAIL）
- 现象：CFD-DELIVERY.md 的「已验收最高背压 / 首个振荡背压」表在 4500、5500 rpm 对应
  rejected/persistent_flow_oscillation，但 5000 rpm 的 103525 Pa 在 sweep_summary.csv 里是
  stopped/user_stop（README-CFD.md 记载该点在持续振荡时由用户要求正常保存停止，
  末 3000 步流量 8.540–8.893 kg/s、各 500 步窗口相对极差约 4.04%、振幅不衰减）。
- 合同：审计「振荡侧边界」时，判据必须是**「高于最高验收背压的第一个未验收点」**，
  而不是只匹配 state == "rejected"；同时必须保留该点的 state 与 reason，以便区分
  「机器按策略自动拒绝」与「人干预停止」。
- 证据：cases/DF90-001/_replay/v7/replay_audit.json#R-8；
  Ducted-Fan/run/90kg-duct-fan-v7/fine/v7-optimized/sweep_summary.csv
- 适用边界：凡交付物用自然语言描述「边界」而非直接给状态码的场合。
  **不得据此认为两个状态等价**——rejected 是策略判定，stopped 是人为干预，审计语义不同。
- 晋升状态：待晋升 -> ducted-fan-aero-design/references/gates.md#G5
## 2026-09-17 | turbo-flow 默认配置会静默改掉被需求锁死的桨盘直径

- 来源：实测发现（G2 对标 A/B 三组）
- 现象：用 turbo-flow 跑涵道风扇工况时，若 annulus.strategy 保持默认的 constant_mean，
  工具按「总状态定尺寸」重算整个流道——输入机匣半径 0.300 m 被改成 0.3486 m，
  轮毂半径 0.103457 被改成 0.0495。这直接违反 requirements.yaml 里锁定的 D=0.600 m。
- 合同：给 turbo-flow 的 annulus 必须显式用 strategy=custom 并给出 hub_curve/shroud_curve
  （两条曲线都须从 x=0 覆盖到 x>=length_m，且 x 单调递增）。
- 证据：cases/DF90-001/01-scheme/v1/benchmark_gate.json；attempt-1 与 attempt-3 的 result.json
- 适用边界：任何「需求锁定了几何尺寸」而一维工具自带尺寸估算逻辑的场合。
  这是一个**通用陷阱**：工具不会报错，只会给出一个看起来合理的错误答案。
- 晋升状态：已晋升 -> ducted-fan-1d-scheme/SKILL.md#两条硬要求A

## 2026-09-17 | turbo-flow 留空 rows 会自动生成三排默认几何

- 来源：实测发现
- 现象：rows: [] + stage_count=1 时，工具自动生成 IGV + R1 + OGV 三排，
  叶片数 36/34/37、弦长 0.04/0.045/0.045、稠度 1.15/1.2/1.3 全是默认值。
  与需求「转子 + 静子两排」不符，且 OGV 扩散因子 0.978（限值 0.6）、de Haller 0.377（限值 0.72）。
- 合同：rows 必须显式给出，不能用自动生成；x_m 必须落在 [0, annulus.length_m] 内。
- 证据：attempt-1/attempt-2 的 metadata.generated_rows 与 constraints
- 适用边界：任何「工具能自动补全缺失拓扑」的场合。**自动补全出的默认值不是设计值。**
- 晋升状态：已晋升 -> ducted-fan-1d-scheme/SKILL.md#两条硬要求B

## 2026-09-17 | flow_coefficient 的桨尖口径与中径口径差 1.49 倍

- 来源：实测发现（B-7 WARN 归因）
- 现象：按桨尖定义算出的 phi_tip = Va/U_tip = 0.2581 输入后，
  工具报告的 flow_coefficient_target 是 0.3864。比值 1.4971 ≈ r_tip/r_mean = 0.300/0.2017 = 1.4871。
- 合同：给 turbo-flow 的 flow_coefficient 必须用中径口径；
  换算 phi_mean = phi_tip * (r_tip / r_mean)。
- 证据：cases/DF90-001/01-scheme/v1/turbo-flow-attempt3/result.json#constraints
- 适用边界：**无量纲系数必须先确认定义半径**（桨尖 / 中径 / 轮毂）。
  这类差异不会被求解器当成错误，只会让可行性判据误报。
- 晋升状态：已晋升 -> ducted-fan-1d-scheme/SKILL.md#口径陷阱C
