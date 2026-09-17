#!/usr/bin/env python3
"""turboflow_adapter.py - turbo-flow result.json 转三表 + 对标闸门报告。

背景（2026-09-17 实测，三组 A/B）
--------------------------------
涵道风扇工况下用 turbo-flow 的默认配置会得到误导性结果：

  attempt-1  annulus.strategy=constant_mean, rows=[]（自动生成）
             工具按"总状态定尺寸"重算流道，机匣半径被放大到 0.3486 m，
             违反锁定的 D=0.600 m 需求；并自动生成 IGV+R1+OGV 三排
             （默认弦长/稠度/叶片数），OGV 扩散因子 0.978 超限。
             eta_tt=0.7597（目标 0.8931），power=67.7 kW（目标 57.7 kW）。

  attempt-2  annulus.strategy=custom（锁死机匣 r=0.300），rows=[]（仍自动生成）
             流道正确了，但三排默认几何仍在；eta_tt=0.7976，power=64.5 kW。

  attempt-3  annulus.strategy=custom + 显式 rows=[R1 转子 9 叶, S1 静子 11 叶]
             eta_tt=0.8794（目标 0.8931，差 1.37 个百分点）
             power=58.504 kW（目标 57.696 kW，+1.40%）
             torque=91.59 N*m（目标 90.32 N*m，+1.41%）
             机匣半径 0.3000（严格满足），8 条工程约束全 PASS，0 条警告。

因此适配器有两条硬要求：
  A. annulus.strategy 必须是 custom，并显式给出 hub_curve / shroud_curve。
     默认的 constant_mean 会静默改掉被需求锁死的直径。
  B. rows 必须显式给出。留空会触发按级数自动生成（并额外加 IGV/OGV）。

另有两个口径陷阱：
  C. design.flow_coefficient 在 turbo-flow 中按中径定义，不是桨尖。
     实测 attempt-3：桨尖口径 0.2581 对应工具中径口径 0.3864。
     换算：phi_mean = phi_tip * (r_tip / r_mean)。
  D. target_efficiency_tt 只作初始功估算与可行性约束，不是强制结果
     （见 result.metadata.target_efficiency_role）。

用法
----
  python tools/turboflow_adapter.py --result result.json --targets targets.json --out 01-scheme/v1
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_PRECONDITION = 3
EXIT_VERIFY = 4

LF = chr(10)


def now_iso():
    return _dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def write_csv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for row in rows:
            w.writerow(row)


def build_flowpath_table(result):
    rows = []
    for st in result.get("stations", []):
        rows.append([
            st.get("id"), st.get("row_type"), st.get("index"),
            "%.6f" % (st.get("x_m") or 0.0),
            "%.6f" % (st.get("hub_radius_m") or 0.0),
            "%.6f" % (st.get("tip_radius_m") or 0.0),
            "%.6f" % (st.get("mean_radius_m") or 0.0),
            "%.6f" % (st.get("area_m2") or 0.0),
        ])
    return (["站位", "类型", "序号", "轴向坐标(m)", "轮毂半径(m)", "机匣半径(m)",
             "中径半径(m)", "通流面积(m2)"], rows)


def build_blade_table(result):
    rows = []
    for row in result.get("metadata", {}).get("generated_rows", []):
        rows.append([
            row.get("id"), row.get("row_type"), row.get("stage"),
            "%.6f" % (row.get("x_m") or 0.0),
            row.get("blade_count"),
            "%.6f" % (row.get("chord_m") or 0.0),
            "%.6f" % (row.get("solidity") or 0.0),
            "%.6f" % (row.get("aspect_ratio") or 0.0),
            "%.3f" % (row.get("metal_angle_in_deg") or 0.0),
            "%.3f" % (row.get("metal_angle_out_deg") or 0.0),
            "%.6f" % (row.get("tip_clearance_m") or 0.0),
            "%.6f" % (row.get("blockage") or 0.0),
        ])
    return (["叶排", "类型", "级", "轴向坐标(m)", "叶片数", "弦长(m)", "稠度",
             "展弦比", "进口金属角(deg,相对轴向)", "出口金属角(deg,相对轴向)",
             "叶尖间隙(m)", "堵塞"], rows)


def build_performance_table(result, targets):
    s = result.get("summary", {})
    stages = result.get("stage_results") or [{}]
    st1 = stages[0] if stages else {}
    stations = result.get("stations") or []
    tip_radius = max([(st.get("tip_radius_m") or 0.0) for st in stations] or [0.0])
    outlet_total = stations[-1].get("total_pressure_pa") if stations else None
    rows = [
        ["基本信息", "求解器", "-", result.get("solver")],
        ["基本信息", "状态", "-", result.get("status")],
        ["基本信息", "迭代数", "-", result.get("iterations")],
        ["基本信息", "级数", "-", s.get("stage_count")],
        ["基本信息", "叶排数", "-", s.get("generated_row_count")],
        ["工况", "转速", "rpm", s.get("rpm")],
        ["工况", "进口质量流量", "kg/s", s.get("mass_flow_kg_s")],
        ["工况", "出口质量流量", "kg/s", s.get("outlet_mass_flow_kg_s")],
        ["工况", "修正转速分数", "-", s.get("corrected_speed_fraction")],
        ["压力", "进口总压", "Pa", targets.get("inlet_total_pressure_pa")],
        ["压力", "出口总压", "Pa", outlet_total],
        ["压力", "出口静压", "Pa", s.get("outlet_static_pressure_pa")],
        ["压力", "总压比", "-", s.get("total_pressure_ratio")],
        ["温度", "进口总温", "K", targets.get("inlet_total_temperature_k")],
        ["效率", "总总效率", "-", s.get("efficiency_tt")],
        ["载荷", "轴功率", "W", s.get("power_w")],
        ["载荷", "扭矩", "N*m", s.get("torque_nm")],
        ["载荷", "级单位功", "J/kg", st1.get("work_j_kg")],
        ["气动", "最大扩散因子", "-", s.get("max_diffusion_factor")],
        ["气动", "最大相对马赫数", "-", s.get("max_relative_mach")],
        ["气动", "机匣半径", "m", tip_radius],
        ["约束", "堵塞叶排数", "-", len(s.get("choked_rows") or [])],
        ["约束", "工程可行", "-", s.get("engineering_feasible")],
    ]
    return (["参数类别", "参数名称", "单位", "数值"], rows)


def benchmark(result, targets):
    s = result.get("summary", {})
    items = []

    def add(cid, title, target, actual, tol, mode, source):
        if actual is None or target is None:
            items.append({"id": cid, "title": title, "target": target, "actual": actual,
                          "delta": None, "delta_shown": "-", "tol": tol,
                          "verdict": "SKIP", "source": source})
            return
        delta = actual - target
        if mode == "abs":
            ok = abs(delta) <= tol
            shown = "%.4g" % delta
        else:
            rel = delta / target if target else float("inf")
            ok = abs(rel) <= tol
            shown = "%+.2f%%" % (rel * 100.0)
        items.append({"id": cid, "title": title, "target": target, "actual": actual,
                      "delta": delta, "delta_shown": shown, "tol": tol,
                      "verdict": "PASS" if ok else "FAIL", "source": source})

    add("B-1", "总总效率（绝对偏差）", targets.get("efficiency_tt"), s.get("efficiency_tt"),
        targets.get("tol_efficiency_abs", 0.02), "abs", targets.get("source", ""))
    add("B-2", "轴功率（相对偏差）", targets.get("power_w"), s.get("power_w"),
        targets.get("tol_power_rel", 0.05), "rel", targets.get("source", ""))
    add("B-3", "扭矩（相对偏差）", targets.get("torque_nm"), s.get("torque_nm"),
        targets.get("tol_torque_rel", 0.05), "rel", targets.get("source", ""))

    tip = max([(st.get("tip_radius_m") or 0.0) for st in result.get("stations", [])] or [None])
    add("B-4", "机匣半径（绝对偏差, m）", targets.get("tip_radius_m"), tip, 1e-4, "abs",
        "requirements.yaml#geometry.tip_radius_m（锁定）")
    add("B-5", "叶排数", targets.get("row_count"), s.get("generated_row_count"), 0, "abs",
        "requirements.yaml#rows.count（转子+静子）")

    eng_fail = [c for c in result.get("constraints", [])
                if c.get("kind") == "engineering" and not c.get("passed")]
    items.append({"id": "B-6", "title": "工程约束全部通过",
                  "target": "0 条不通过", "actual": "%d 条不通过" % len(eng_fail),
                  "delta": None, "delta_shown": "-", "tol": 0,
                  "verdict": "PASS" if not eng_fail else "FAIL",
                  "source": "result.json#constraints(kind=engineering)",
                  "detail": eng_fail})

    design_fail = [c for c in result.get("constraints", [])
                   if c.get("kind") == "design" and not c.get("passed")]
    items.append({"id": "B-7", "title": "输入的设计目标自洽",
                  "target": "0 条不通过", "actual": "%d 条不通过" % len(design_fail),
                  "delta": None, "delta_shown": "-", "tol": 0,
                  "verdict": "PASS" if not design_fail else "WARN",
                  "source": "result.json#constraints(kind=design)",
                  "detail": design_fail,
                  "note": "design 类约束不通过通常源于输入口径定义错误"
                          "（如 flow_coefficient 按桨尖还是中径定义），不是求解器缺陷。"})

    failed = [i for i in items if i["verdict"] == "FAIL"]
    return {"time": now_iso(), "targets": targets, "items": items,
            "verdict": "PASS" if not failed else "FAIL",
            "summary": {"total": len(items),
                        "pass": len([i for i in items if i["verdict"] == "PASS"]),
                        "warn": len([i for i in items if i["verdict"] == "WARN"]),
                        "fail": len(failed),
                        "skip": len([i for i in items if i["verdict"] == "SKIP"])}}


def render_md(bm, result, targets):
    lines = [
        "# G2 对标闸门报告",
        "",
        "- 时间：" + bm["time"],
        "- 结论：**" + bm["verdict"] + "**（PASS %d / WARN %d / FAIL %d / SKIP %d）" % (
            bm["summary"]["pass"], bm["summary"]["warn"],
            bm["summary"]["fail"], bm["summary"]["skip"]),
        "- 基准来源：" + str(targets.get("source", "")),
        "",
        "| id | 项目 | 目标 | 实测 | 偏差 | 容差 | 结论 |",
        "|---|---|---|---|---|---|---|",
    ]
    for i in bm["items"]:
        lines.append("| " + i["id"] + " | " + i["title"] + " | " + str(i["target"])
                     + " | " + str(i["actual"]) + " | " + str(i.get("delta_shown", "-"))
                     + " | " + str(i["tol"]) + " | **" + i["verdict"] + "** |")
    lines += [
        "",
        "## 求解器自述",
        "",
        "- 状态：" + str(result.get("status")) + "，迭代 " + str(result.get("iterations")) + " 次",
        "- 效率目标角色：" + str(result.get("metadata", {}).get("target_efficiency_role")),
        "- 流道方法：" + str(result.get("metadata", {}).get("annulus_method")),
        "- 设计方法：" + str(result.get("metadata", {}).get("design_method")),
        "- 警告：" + str(result.get("warnings")),
        "",
        "## 口径说明（必读）",
        "",
        "1. 总压比是反设计的射击目标，与目标一致不构成证据；真正的证据是效率、功率、扭矩。",
        "2. flow_coefficient 按中径定义。桨尖口径需换算：phi_mean = phi_tip * r_tip / r_mean。",
        "3. target_efficiency_tt 只作初始功估算与可行性约束，不是强制结果。",
        "4. 机匣半径必须由 custom annulus 锁死；默认 constant_mean 会静默改掉被需求锁定的直径。",
        "",
    ]
    return LF.join(lines) + LF


def main(argv=None):
    p = argparse.ArgumentParser(prog="turboflow_adapter.py")
    p.add_argument("--result", required=True)
    p.add_argument("--targets", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    rp = Path(args.result).resolve()
    tp = Path(args.targets).resolve()
    if not rp.is_file() or not tp.is_file():
        print("PRECONDITION: 缺少 --result 或 --targets 文件", file=sys.stderr)
        return EXIT_PRECONDITION
    try:
        result = json.loads(rp.read_text(encoding="utf-8"))
        targets = json.loads(tp.read_text(encoding="utf-8"))
    except Exception as exc:
        print("PRECONDITION: 输入不是合法 JSON：" + repr(exc), file=sys.stderr)
        return EXIT_PRECONDITION

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    h, rows = build_flowpath_table(result)
    write_csv(out / "流道尺寸表.csv", h, rows)
    h, rows = build_blade_table(result)
    write_csv(out / "叶片几何参数表.csv", h, rows)
    h, rows = build_performance_table(result, targets)
    write_csv(out / "通流计算结果表.csv", h, rows)

    bm = benchmark(result, targets)
    (out / "benchmark_gate.json").write_text(
        json.dumps(bm, ensure_ascii=False, indent=2) + LF, encoding="utf-8", newline="")
    (out / "benchmark_gate.md").write_text(
        render_md(bm, result, targets), encoding="utf-8", newline="")

    if args.json:
        print(json.dumps({"ok": bm["verdict"] == "PASS", "verdict": bm["verdict"],
                          "summary": bm["summary"], "out": str(out)},
                         ensure_ascii=False, indent=2))
    else:
        print("对标闸门：" + bm["verdict"] + "  (PASS %d / WARN %d / FAIL %d / SKIP %d)" % (
            bm["summary"]["pass"], bm["summary"]["warn"],
            bm["summary"]["fail"], bm["summary"]["skip"]))
        for i in bm["items"]:
            print("  " + i["verdict"].ljust(4) + " " + i["id"] + " " + i["title"]
                  + "  目标=" + str(i["target"]) + "  实测=" + str(i["actual"])
                  + "  " + str(i.get("delta_shown", "")))
        print("  三表 + 报告已写入 " + str(out))

    return EXIT_OK if bm["verdict"] == "PASS" else EXIT_VERIFY


if __name__ == "__main__":
    raise SystemExit(main())
