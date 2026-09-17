#!/usr/bin/env python3
"""replay_audit.py - 对既有算例做只读回放验收，复现黄金基准的判读。

用途
----
把"我们新的闸门逻辑"跑在"别人已经验收过的算例"上，看两者结论是否一致。
一致 => 闸门逻辑可信；不一致 => 要么闸门错，要么原判读错，两者都必须查清。

设计原则
--------
1. **只读**：绝不修改基准目录里的任何文件。
2. **不硬编码期望值**：期望值优先从基准自己的审计文件读取；
   只有"文档声明"（如交付报告里的表格）才作为常量并标注来源。
3. 每条检查都有 id、判据、实测、来源，输出机器可读 JSON + 人类可读 Markdown。

用法
----
  python tools/replay_audit.py \
    --baseline "D:/Project/Research/Ducted-Fan/run/90kg-duct-fan-v7/fine/v7-optimized" \
    --case cases/DF90-001 --label v7
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_PRECONDITION = 3
EXIT_VERIFY = 4
EXIT_INTERNAL = 5

LF = chr(10)

# CFD-DELIVERY.md 里公布的三转速验收范围表。
# 这是"文档声明"，不是机器可读真源；回放的价值恰恰在于用它去核机器数据。
PUBLISHED_TABLE = {
    "source": "Ducted-Fan/run/90kg-duct-fan-v7/CFD-DELIVERY.md#各转速验收范围",
    "rows": [
        {"rpm": 4500, "accepted": 15, "pressure_min": 97884, "pressure_max": 103052,
         "mf_min": 9.0345, "mf_max": 15.9910, "max_accepted_p": 103052, "first_rejected_p": 103107},
        {"rpm": 5000, "accepted": 15, "pressure_min": 97075, "pressure_max": 103458,
         "mf_min": 10.0500, "mf_max": 17.6720, "max_accepted_p": 103458, "first_rejected_p": 103525},
        {"rpm": 5500, "accepted": 15, "pressure_min": 96183, "pressure_max": 103906,
         "mf_min": 10.0630, "mf_max": 19.3090, "max_accepted_p": 103906, "first_rejected_p": 103987},
    ],
}

# C-002 的硬判据
MASS_ERROR_LIMIT_PCT = 1.0
RANGE_LIMIT_PCT = 0.2


def now_iso():
    return _dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def read_csv(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def read_json(path):
    with Path(path).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def fnum(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class Checks:
    def __init__(self):
        self.items = []

    def add(self, cid, title, criteria, measured, verdict, source, detail=None):
        self.items.append({
            "id": cid, "title": title, "criteria": criteria,
            "measured": measured, "verdict": verdict, "source": source,
            "detail": detail or {},
        })

    @property
    def failed(self):
        return [i for i in self.items if i["verdict"] == "FAIL"]

    @property
    def warned(self):
        return [i for i in self.items if i["verdict"] == "WARN"]


def run(baseline: Path, case: Path, label: str) -> dict:
    checks = Checks()
    out = {"label": label, "baseline": str(baseline), "time": now_iso()}

    plan_path = baseline / "scan_plan.csv"
    summary_path = baseline / "sweep_summary.csv"
    audit_path = baseline / "final_delivery_audit.json"

    for p in (plan_path, summary_path, audit_path):
        if not p.is_file():
            print("PRECONDITION FAILED: missing " + str(p), file=sys.stderr)
            raise SystemExit(EXIT_PRECONDITION)

    plan = read_csv(plan_path)
    summary = read_csv(summary_path)
    audit = read_json(audit_path)

    out["registered_from_plan"] = len(plan)
    out["registered_from_summary"] = len(summary)
    out["registered_from_audit"] = audit.get("registered")

    # R-1 完整性：登记点与状态记录一一对应
    plan_cases = {r["case"] for r in plan}
    sum_cases = {r["case"] for r in summary}
    missing = sorted(plan_cases - sum_cases)
    extra = sorted(sum_cases - plan_cases)
    checks.add(
        "R-1", "登记点与状态记录一一对应",
        "scan_plan 的每个登记点都必须在 sweep_summary 里有状态；不得有未记录的算例",
        "plan=%d summary=%d missing=%d extra=%d" % (len(plan_cases), len(sum_cases), len(missing), len(extra)),
        "PASS" if (not missing and not extra) else "FAIL",
        str(plan_path),
        {"missing": missing, "extra": extra},
    )

    # R-2 计数一致：重算 vs 基准自己的审计文件
    counts = {}
    for row in summary:
        counts[row["state"]] = counts.get(row["state"], 0) + 1
    golden_counts = audit.get("counts", {})
    same = {k: int(v) for k, v in counts.items()} == {k: int(v) for k, v in golden_counts.items()}
    checks.add(
        "R-2", "状态计数与基准审计一致",
        "从 sweep_summary.csv 重新统计的 state 计数必须等于 final_delivery_audit.json 的 counts",
        "recomputed=%s golden=%s" % (counts, golden_counts),
        "PASS" if same else "FAIL",
        str(audit_path),
    )
    out["counts"] = counts
    out["golden_counts"] = golden_counts

    # R-2b 与交付文档声明一致
    pub_total = sum(r["accepted"] for r in PUBLISHED_TABLE["rows"])
    checks.add(
        "R-2b", "验收总数与交付文档声明一致",
        "CFD-DELIVERY.md 声明各转速各 15 个验收点，合计 45",
        "recomputed accepted=%d published=%d" % (counts.get("accepted", 0), pub_total),
        "PASS" if counts.get("accepted", 0) == pub_total else "FAIL",
        PUBLISHED_TABLE["source"],
    )

    # R-3 accepted 点必须满足质量不平衡判据
    violations = []
    for row in summary:
        if row["state"] != "accepted":
            continue
        me = fnum(row.get("mass_error_pct"))
        if me is None or me > MASS_ERROR_LIMIT_PCT:
            violations.append({"case": row["case"], "mass_error_pct": row.get("mass_error_pct")})
    checks.add(
        "R-3", "accepted 点满足质量不平衡判据",
        "100*|mdot_in-mdot_out|/|mdot_in| <= %.1f%%" % MASS_ERROR_LIMIT_PCT,
        "checked=%d violations=%d" % (counts.get("accepted", 0), len(violations)),
        "PASS" if not violations else "FAIL",
        "C-002",
        {"violations": violations},
    )

    # R-4 非 accepted 点不得被当作有效性能点
    bad_reasons = [r["case"] for r in summary
                   if r["state"] != "accepted" and not r.get("reason")]
    checks.add(
        "R-4", "非 accepted 点都有拒绝/停止原因",
        "每个 stopped/rejected 点必须有 reason 字段，不得静默丢弃",
        "non_accepted=%d without_reason=%d" % (len(summary) - counts.get("accepted", 0), len(bad_reasons)),
        "PASS" if not bad_reasons else "FAIL",
        str(summary_path),
        {"without_reason": bad_reasons},
    )

    # R-5 源哈希未变
    checks.add(
        "R-5", "上游源文件哈希未变",
        "final_delivery_audit.json 的 source_hashes_unchanged 必须为 true",
        str(audit.get("source_hashes_unchanged")),
        "PASS" if audit.get("source_hashes_unchanged") is True else "FAIL",
        "final_delivery_audit.json#source_hashes_unchanged",
    )

    # R-6 原生历史可重开
    checks.add(
        "R-6", "ICE 原生历史可重开",
        "final_delivery_audit.json 的 native_history_reopen 必须为 true",
        str(audit.get("native_history_reopen")),
        "PASS" if audit.get("native_history_reopen") is True else "FAIL",
        "final_delivery_audit.json#native_history_reopen",
    )

    # R-7 逐转速范围与文档声明对照
    per_rpm = {}
    for row in summary:
        if row["state"] != "accepted":
            continue
        rpm = int(float(row["rpm"]))
        per_rpm.setdefault(rpm, []).append(row)

    rpm_compare = []
    for expected in PUBLISHED_TABLE["rows"]:
        rpm = expected["rpm"]
        rows = per_rpm.get(rpm, [])
        pressures = [fnum(r["pressure_pa_abs"]) for r in rows]
        flows = [fnum(r["mf_in"]) for r in rows]
        actual = {
            "rpm": rpm,
            "accepted": len(rows),
            "pressure_min": min(pressures) if pressures else None,
            "pressure_max": max(pressures) if pressures else None,
            "mf_min": min(flows) if flows else None,
            "mf_max": max(flows) if flows else None,
        }
        diffs = {}
        for key in ("accepted",):
            if actual[key] != expected[key]:
                diffs[key] = {"actual": actual[key], "expected": expected[key]}
        for key, tol in (("pressure_min", 1.0), ("pressure_max", 1.0),
                         ("mf_min", 0.0005), ("mf_max", 0.0005)):
            a, e = actual[key], expected[key]
            if a is None or abs(a - e) > tol:
                diffs[key] = {"actual": a, "expected": e, "tol": tol}
        rpm_compare.append({"actual": actual, "expected": expected, "diffs": diffs})

    bad_rpm = [c for c in rpm_compare if c["diffs"]]
    checks.add(
        "R-7", "逐转速验收范围与交付文档一致",
        "各转速的验收点数、背压区间、流量区间必须与 CFD-DELIVERY.md 的表格相符",
        "rpm_lines=%d mismatched=%d" % (len(rpm_compare), len(bad_rpm)),
        "PASS" if not bad_rpm else "FAIL",
        PUBLISHED_TABLE["source"],
        {"rows": rpm_compare},
    )
    out["per_rpm"] = rpm_compare

    # R-8 每转速的"最高验收背压 / 首个振荡背压"边界
    boundary = []
    for expected in PUBLISHED_TABLE["rows"]:
        rpm = expected["rpm"]
        accepted = [fnum(r["pressure_pa_abs"]) for r in summary
                    if int(float(r["rpm"])) == rpm and r["state"] == "accepted"]
        # 注意：交付文档的"首个振荡背压"并不总以 rejected 记录。
        # 实测 v7：4500/5500 rpm 是 rejected/persistent_flow_oscillation，
        # 而 5000 rpm 是 stopped/user_stop（README 记载该点在持续振荡时由用户要求保存停止）。
        # 因此这里取"高于最高验收背压的第一个未验收点"，并保留其 state/reason 以备审计。
        nonaccepted = [(fnum(r["pressure_pa_abs"]), r["state"], r.get("reason", ""))
                       for r in summary
                       if int(float(r["rpm"])) == rpm and r["state"] != "accepted"]
        actual_max = max(accepted) if accepted else None
        above = [x for x in nonaccepted
                 if actual_max is not None and x[0] is not None and x[0] > actual_max]
        first = min(above, key=lambda x: x[0]) if above else None
        actual_first_rej = first[0] if first else None
        ok_max = actual_max is not None and abs(actual_max - expected["max_accepted_p"]) <= 1.0
        ok_rej = actual_first_rej is not None and abs(actual_first_rej - expected["first_rejected_p"]) <= 1.0
        boundary.append({
            "rpm": rpm,
            "max_accepted_p": {"actual": actual_max, "expected": expected["max_accepted_p"], "ok": ok_max},
            "first_rejected_p": {
                "actual": actual_first_rej, "expected": expected["first_rejected_p"], "ok": ok_rej,
                "state": first[1] if first else None, "reason": first[2] if first else None,
            },
        })
    bad_boundary = [b for b in boundary
                    if not (b["max_accepted_p"]["ok"] and b["first_rejected_p"]["ok"])]
    checks.add(
        "R-8", "失速侧边界区间与文档一致",
        "每转速的「已验收最高背压」与「首个未验收背压」（rejected 或 stopped，容差 1 Pa）必须落在文档声明值上",
        "rpm_lines=%d mismatched=%d" % (len(boundary), len(bad_boundary)),
        "PASS" if not bad_boundary else "FAIL",
        PUBLISHED_TABLE["source"],
        {"rows": boundary},
    )
    out["boundary"] = boundary

    # R-9 全案审计总体结论
    checks.add(
        "R-9", "基准自身审计通过",
        "final_delivery_audit.json 的 passed 必须为 true 且 failures 为空",
        "passed=%s failures=%d" % (audit.get("passed"), len(audit.get("failures", []))),
        "PASS" if (audit.get("passed") is True and not audit.get("failures")) else "FAIL",
        "final_delivery_audit.json",
    )

    out["checks"] = checks.items
    out["summary"] = {
        "total": len(checks.items),
        "pass": len([i for i in checks.items if i["verdict"] == "PASS"]),
        "warn": len(checks.warned),
        "fail": len(checks.failed),
    }
    out["verdict"] = "PASS" if not checks.failed else "FAIL"
    return out


def render_markdown(result: dict) -> str:
    s = result["summary"]
    lines = [
        "# 回放审计报告 | " + result["label"],
        "",
        "- 审计时间：" + result["time"],
        "- 基准目录：`" + result["baseline"] + "`",
        "- 结论：**" + result["verdict"] + "**（PASS %d / WARN %d / FAIL %d，共 %d 项）"
        % (s["pass"], s["warn"], s["fail"], s["total"]),
        "",
        "> 本报告由 `tools/replay_audit.py` 只读生成，未修改基准目录任何文件。",
        "",
        "## 判读复现",
        "",
        "| 状态 | 重算 | 基准审计 |",
        "|---|---:|---:|",
    ]
    for key in sorted(set(list(result["counts"].keys()) + list(result["golden_counts"].keys()))):
        lines.append("| " + key + " | " + str(result["counts"].get(key, 0))
                     + " | " + str(result["golden_counts"].get(key, 0)) + " |")
    lines += ["", "## 逐转速验收范围 vs 交付文档", "",
              "| 转速 rpm | 验收点数 | 背压区间 Pa(abs) | 流量区间 kg/s |",
              "|---:|---:|---|---|"]
    for row in result["per_rpm"]:
        a = row["actual"]
        flag = " ⚠" if row["diffs"] else ""
        lines.append("| %d | %d%s | %.0f–%.0f | %.4f–%.4f |" % (
            a["rpm"], a["accepted"], flag,
            a["pressure_min"] or 0, a["pressure_max"] or 0,
            a["mf_min"] or 0, a["mf_max"] or 0))
    lines += ["", "## 逐项检查", "", "| id | 检查 | 判据 | 实测 | 结论 | 来源 |",
              "|---|---|---|---|---|---|"]
    for item in result["checks"]:
        lines.append("| " + item["id"] + " | " + item["title"] + " | " + item["criteria"]
                     + " | " + item["measured"] + " | **" + item["verdict"] + "** | " + item["source"] + " |")
    lines.append("")
    return LF.join(lines) + LF


def main(argv=None):
    p = argparse.ArgumentParser(prog="replay_audit.py",
                                description="对既有算例做只读回放验收")
    p.add_argument("--baseline", required=True, help="基准算例根目录（只读）")
    p.add_argument("--case", required=True, help="本案例目录")
    p.add_argument("--label", default="baseline")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    baseline = Path(args.baseline).resolve()
    case = Path(args.case).resolve()

    try:
        result = run(baseline, case, args.label)
    except SystemExit:
        raise
    except Exception as exc:
        print("INTERNAL ERROR: " + repr(exc), file=sys.stderr)
        return EXIT_INTERNAL

    outdir = case / "_replay" / args.label
    outdir.mkdir(parents=True, exist_ok=True)
    json_path = outdir / "replay_audit.json"
    md_path = outdir / "replay_report.md"
    with json_path.open("w", encoding="utf-8", newline="") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
        fh.write(LF)
    with md_path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(render_markdown(result))

    if args.json:
        print(json.dumps({"ok": result["verdict"] == "PASS", "verdict": result["verdict"],
                          "summary": result["summary"],
                          "json": str(json_path), "md": str(md_path)},
                         ensure_ascii=False, indent=2))
    else:
        s = result["summary"]
        print("回放审计 " + args.label + "：" + result["verdict"]
              + "  (PASS %d / WARN %d / FAIL %d)" % (s["pass"], s["warn"], s["fail"]))
        print("  计数：" + str(result["counts"]) + "  基准：" + str(result["golden_counts"]))
        for item in result["checks"]:
            if item["verdict"] != "PASS":
                print("  [" + item["verdict"] + "] " + item["id"] + " " + item["title"]
                      + " -- " + item["measured"])
        print("  报告：" + str(md_path))

    return EXIT_OK if result["verdict"] == "PASS" else EXIT_VERIFY


if __name__ == "__main__":
    raise SystemExit(main())
