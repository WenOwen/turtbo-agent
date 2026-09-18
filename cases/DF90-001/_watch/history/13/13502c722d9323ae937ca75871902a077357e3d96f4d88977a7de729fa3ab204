# 回放审计报告 | v7

- 审计时间：2026-09-17T15:03:58+08:00
- 基准目录：`D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v7\fine\v7-optimized`
- 结论：**PASS**（PASS 10 / WARN 0 / FAIL 0，共 10 项）

> 本报告由 `tools/replay_audit.py` 只读生成，未修改基准目录任何文件。

## 判读复现

| 状态 | 重算 | 基准审计 |
|---|---:|---:|
| accepted | 45 | 45 |
| rejected | 2 | 2 |
| stopped | 10 | 10 |

## 逐转速验收范围 vs 交付文档

| 转速 rpm | 验收点数 | 背压区间 Pa(abs) | 流量区间 kg/s |
|---:|---:|---|---|
| 4500 | 15 | 97884–103052 | 9.0345–15.9910 |
| 5000 | 15 | 97075–103458 | 10.0500–17.6720 |
| 5500 | 15 | 96183–103906 | 10.0630–19.3090 |

## 逐项检查

| id | 检查 | 判据 | 实测 | 结论 | 来源 |
|---|---|---|---|---|---|
| R-1 | 登记点与状态记录一一对应 | scan_plan 的每个登记点都必须在 sweep_summary 里有状态；不得有未记录的算例 | plan=57 summary=57 missing=0 extra=0 | **PASS** | D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v7\fine\v7-optimized\scan_plan.csv |
| R-2 | 状态计数与基准审计一致 | 从 sweep_summary.csv 重新统计的 state 计数必须等于 final_delivery_audit.json 的 counts | recomputed={'accepted': 45, 'stopped': 10, 'rejected': 2} golden={'accepted': 45, 'stopped': 10, 'rejected': 2} | **PASS** | D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v7\fine\v7-optimized\final_delivery_audit.json |
| R-2b | 验收总数与交付文档声明一致 | CFD-DELIVERY.md 声明各转速各 15 个验收点，合计 45 | recomputed accepted=45 published=45 | **PASS** | Ducted-Fan/run/90kg-duct-fan-v7/CFD-DELIVERY.md#各转速验收范围 |
| R-3 | accepted 点满足质量不平衡判据 | 100*|mdot_in-mdot_out|/|mdot_in| <= 1.0% | checked=45 violations=0 | **PASS** | C-002 |
| R-4 | 非 accepted 点都有拒绝/停止原因 | 每个 stopped/rejected 点必须有 reason 字段，不得静默丢弃 | non_accepted=12 without_reason=0 | **PASS** | D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v7\fine\v7-optimized\sweep_summary.csv |
| R-5 | 上游源文件哈希未变 | final_delivery_audit.json 的 source_hashes_unchanged 必须为 true | True | **PASS** | final_delivery_audit.json#source_hashes_unchanged |
| R-6 | ICE 原生历史可重开 | final_delivery_audit.json 的 native_history_reopen 必须为 true | True | **PASS** | final_delivery_audit.json#native_history_reopen |
| R-7 | 逐转速验收范围与交付文档一致 | 各转速的验收点数、背压区间、流量区间必须与 CFD-DELIVERY.md 的表格相符 | rpm_lines=3 mismatched=0 | **PASS** | Ducted-Fan/run/90kg-duct-fan-v7/CFD-DELIVERY.md#各转速验收范围 |
| R-8 | 失速侧边界区间与文档一致 | 每转速的「已验收最高背压」与「首个未验收背压」（rejected 或 stopped，容差 1 Pa）必须落在文档声明值上 | rpm_lines=3 mismatched=0 | **PASS** | Ducted-Fan/run/90kg-duct-fan-v7/CFD-DELIVERY.md#各转速验收范围 |
| R-9 | 基准自身审计通过 | final_delivery_audit.json 的 passed 必须为 true 且 failures 为空 | passed=True failures=0 | **PASS** | final_delivery_audit.json |

