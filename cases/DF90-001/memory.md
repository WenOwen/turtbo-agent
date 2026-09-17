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
- 晋升状态：待晋升 -> ducted-fan-kickoff-design/references/gates.md#G5
