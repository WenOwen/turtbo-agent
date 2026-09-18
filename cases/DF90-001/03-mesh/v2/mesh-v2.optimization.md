# mesh-v2 网格优化记录

- 来源：`D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v8\mesh\mesh-v1\mesh-v1.trb`
- 单因素：row 1 `streamwise_blade_upper_points` = `97`
- 物理合同：`sibling_expected_json`（可信度：`independent`）
- 叶尖间隙策略：`preserve_baseline`，保留基线值

| 指标 | 基线 | 最终 |
| --- | ---: | ---: |
| 点数 | 1686584 | 1779880 |
| 最小偏斜角 | 9.4508° | 16.406° |
| 最大长宽比 | 1078.7 | 1078.7 |
| 最大膨胀率 | 2.0682 | 2.5335 |

仅证明网格质量与合同通过；不证明 CFD 收敛、实际 y+ 或网格无关性。
