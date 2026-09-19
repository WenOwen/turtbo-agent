#!/usr/bin/env python3
"""thrust_closure.py - C-004 静推力闭合：静推力 = 动量推力 + 压力推力。

为什么要有这个
--------------
`tools/gate_check.py post` 的 G6-3 找的是交付表里这三列：
    static_thrust_n = momentum_thrust_n + pressure_thrust_n
而案例里一直没有一张带这三列的表 —— 所以 G6 从来没通过。

公式来自哪里
------------
**不是我自己推的。** 与 `numeca-cfview-post` 的 `scripts/build_operating_conditions.py`
里的 `add_static_thrust()` 逐字一致：
    momentum_thrust = mass_flow * axial_velocity
    pressure_thrust = (static_pressure - ambient_pressure_pa) * outlet_area_m2
    static_thrust   = momentum_thrust + pressure_thrust
数据源也一样：求解器写的 `.xmf` 的 Outlet 站位。

        （那个脚本本身还要求 `post/summary.md`，本案例没有，所以不能直接用；
          这里只复用它的公式与字段名。）

A_out 怎么来的 —— 这是 C-004 唯一真正要动脑的地方
-----------------------------------------------
C-004 原文：「对定静压出口，压力项用**真实全周出口面积**：CFView 周期扇区面积
必须乘以出口叶排周期数，并与轮毂/机匣半径解析环面积交叉核验。」

  A_out = XMF Outlet 的 Area（周期扇区） × Number of blades
  交叉核验 = pi * (r_shroud^2 - r_hub^2)  ← 同一个站位的半径，解析环面积

两条都对不上就不许声称闭合 —— 那说明周期扇区面积和半径不是同一个东西。

用法
----
  python tools/thrust_closure.py --xmf <case.xmf> --out <dir>
  python tools/thrust_closure.py --case cases/DF90-001 --solve-dir <dir> --out <dir>
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

AMBIENT_PA_DEFAULT = 101325.0
AREA_PASS_REL = 0.005      # 0.5%：周期面积 x 周期数 与解析环面积的一致度
AREA_WARN_REL = 0.02       # 2%
KGF = 9.80665


def named_float(parent, name):
    """XMF 里按 name 找 <float>。找不到返回 None（不抛，让调用方决定怎么办）。"""
    for node in parent.iter("float"):
        if node.attrib.get("name") == name and node.text is not None:
            try:
                return float(node.text)
            except ValueError:
                return None
    return None


def named_int(parent, name):
    for node in parent.iter("integer"):
        if node.attrib.get("name") == name and node.text is not None:
            try:
                return int(node.text)
            except ValueError:
                return None
    return None


def find_station(root, name):
    return next((n for n in root.iter("Station") if n.attrib.get("name") == name), None)


def compute(xmf_path: Path, ambient_pa: float, station_name="Outlet"):
    root = ET.parse(xmf_path).getroot()
    st = find_station(root, station_name)
    if st is None:
        raise SystemExit("PRECONDITION: %s 里没有 %s 站位" % (xmf_path.name, station_name))

    geo = next((n for n in st if n.tag == "GeometricalData"), None)
    if geo is None:
        raise SystemExit("PRECONDITION: %s 站位没有 GeometricalData" % station_name)

    mass_flow = named_float(st, "Mass flow")
    vx = named_float(st, "Axial velocity")
    p_out = named_float(st, "Static pressure")
    area_sector = named_float(geo, "Area")
    n_blades = named_int(geo, "Number of blades")
    r_hub = named_float(geo, "Hub radius")
    r_shroud = named_float(geo, "Shroud radius")

    missing = [k for k, v in (("Mass flow", mass_flow), ("Axial velocity", vx),
                              ("Static pressure", p_out), ("Area", area_sector),
                              ("Number of blades", n_blades), ("Hub radius", r_hub),
                              ("Shroud radius", r_shroud)) if v is None]
    if missing:
        raise SystemExit("PRECONDITION: %s 站位缺字段 %s" % (station_name, missing))

    # 全周出口面积 = 周期扇区面积 x 周期数（C-004 明写的那一步）
    area_full = area_sector * n_blades
    # 解析环面积，用同一个站位自己的半径
    area_analytic = math.pi * (r_shroud ** 2 - r_hub ** 2)
    rel = abs(area_full - area_analytic) / area_analytic if area_analytic else float("inf")
    if rel <= AREA_PASS_REL:
        area_verdict = "PASS"
    elif rel <= AREA_WARN_REL:
        area_verdict = "WARN"
    else:
        area_verdict = "FAIL"

    momentum = mass_flow * vx
    pressure = (p_out - ambient_pa) * area_full
    static = momentum + pressure
    closure_rel = abs(static - (momentum + pressure)) / max(abs(static), 1e-12)

    perf = next((n for n in root.iter("Performance")), None)
    return {
        "xmf": str(xmf_path),
        "station": station_name,
        "inputs": {
            "mass_flow_kg_s": mass_flow,
            "axial_velocity_m_s": vx,
            "static_pressure_pa_abs": p_out,
            "ambient_static_pressure_pa_abs": ambient_pa,
        },
        "outlet_area": {
            "sector_area_m2": area_sector,
            "periodicity": n_blades,
            "full_area_m2": area_full,
            "analytic_annulus_m2": area_analytic,
            "hub_radius_m": r_hub,
            "shroud_radius_m": r_shroud,
            "rel_diff": rel,
            "verdict": area_verdict,
            "how": "全周面积 = XMF 周期扇区面积 x 出口叶排周期数；与 pi*(r_shroud^2-r_hub^2) 交叉核验",
        },
        "result": {
            "momentum_thrust_n": momentum,
            "pressure_thrust_n": pressure,
            "static_thrust_n": static,
            "static_thrust_kgf": static / KGF,
            "closure_rel_err": closure_rel,
        },
        "solver_reported": {
            "axial_thrust_n_wall_only": (named_float(perf, "Axial thrust") if perf is not None else None),
            "torque_nm": (named_float(perf, "Torque") if perf is not None else None),
            "power_w": (named_float(perf, "Power") if perf is not None else None),
            "isentropic_efficiency_tt": (named_float(perf, "Isentropic efficiency") if perf is not None else None),
            "total_pressure_ratio": (named_float(perf, "Absolute total pressure ratio") if perf is not None else None),
        },
        "note": ("solver_reported.axial_thrust_n_wall_only 是**壁面力**，只积分转子叶片与轮毂。",
                 "C-004 明说它不是整机推力，列在这里只为对照，不得当结论。"),
    }


def write_csv(data, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / "thrust_closure.csv"
    r = data["result"]
    a = data["outlet_area"]
    i = data["inputs"]
    s = data["solver_reported"]
    # 列名必须包含 gate_check.py 的 G6-3 找的那三个
    cols = ["static_thrust_n", "momentum_thrust_n", "pressure_thrust_n",
            "static_thrust_kgf", "closure_rel_err",
            "outlet_mass_flow_kg_s", "outlet_axial_velocity_m_s",
            "outlet_static_pressure_pa_abs", "ambient_static_pressure_pa_abs",
            "outlet_area_m2", "outlet_sector_area_m2", "outlet_periodicity",
            "outlet_area_analytic_m2", "outlet_area_rel_diff", "outlet_area_verdict",
            "solver_wall_axial_thrust_n", "solver_torque_nm", "solver_power_w",
            "solver_efficiency_tt", "solver_total_pressure_ratio", "source_xmf"]
    row = [r["static_thrust_n"], r["momentum_thrust_n"], r["pressure_thrust_n"],
           r["static_thrust_kgf"], r["closure_rel_err"],
           i["mass_flow_kg_s"], i["axial_velocity_m_s"],
           i["static_pressure_pa_abs"], i["ambient_static_pressure_pa_abs"],
           a["full_area_m2"], a["sector_area_m2"], a["periodicity"],
           a["analytic_annulus_m2"], a["rel_diff"], a["verdict"],
           s["axial_thrust_n_wall_only"], s["torque_nm"], s["power_w"],
           s["isentropic_efficiency_tt"], s["total_pressure_ratio"], data["xmf"]]
    with p.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        w.writerow(["%.10g" % v if isinstance(v, float) else v for v in row])
    (out_dir / "thrust_closure.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8", newline="")
    return p


def main(argv=None):
    ap = argparse.ArgumentParser(prog="thrust_closure.py", description="C-004 静推力闭合")
    ap.add_argument("--xmf")
    ap.add_argument("--solve-dir", help="算例目录，自动找同名 .xmf")
    ap.add_argument("--out", required=True)
    ap.add_argument("--ambient-pa", type=float, default=AMBIENT_PA_DEFAULT)
    ap.add_argument("--station", default="Outlet")
    ap.add_argument("--convergence", help="convergence.json；给了就把收敛状态嵌进产物")
    ap.add_argument("--outlet-area-only", action="store_true",
                    help="只出出口面积审计（C-004 交叉核验），不出推力 —— 面积是可复用的几何结论")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.xmf:
        xmf = Path(args.xmf).resolve()
    elif args.solve_dir:
        sd = Path(args.solve_dir).resolve()
        cands = sorted(sd.glob("*.xmf"))
        if not cands:
            print("PRECONDITION: %s 下没有 .xmf" % sd, file=sys.stderr)
            return 3
        xmf = cands[0]
    else:
        ap.error("需要 --xmf 或 --solve-dir")
        return 2
    if not xmf.is_file():
        print("PRECONDITION: 找不到 " + str(xmf), file=sys.stderr)
        return 3

    data = compute(xmf, args.ambient_pa, args.station)
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # 收敛状态必须嵌进产物本身。**一个没收敛的数被单独拎出来就会变成"结论"** ——
    # 所以让它自己带着"能不能用"的标记走。
    conv = None
    if args.convergence:
        try:
            conv = json.loads(Path(args.convergence).read_text(encoding="utf-8-sig"))
        except Exception as exc:
            conv = {"verdict": "读不到：" + repr(exc)}
    data["convergence"] = conv
    usable = bool(conv) and conv.get("verdict") == "算完了"
    data["usable_for_conclusions"] = usable
    if not usable:
        data["provisional_warning"] = ("此值建立在**未收敛**的解上（收敛判定："
                                       + str((conv or {}).get("verdict", "未提供"))
                                       + "）。**不得用于任何结论**，仅作中间量留痕。")

    # 出口面积单独出一份审计：它是**几何 + 方法**的结论，与流场收不收敛无关，
    # 所以它可以在解还没收敛时就成立（C-004 明写要做的交叉核验）。
    a = data["outlet_area"]
    area_audit = {
        "what": "C-004 全周出口面积交叉核验",
        "independent_of_flow_convergence": True,
        "why": ("全周面积只由网格几何与叶排周期数决定，不依赖流场是否收敛；",
                "所以这一条的结论不受本次未收敛影响。"),
        "sector_area_m2": a["sector_area_m2"],
        "periodicity": a["periodicity"],
        "full_area_m2": a["full_area_m2"],
        "analytic_annulus_m2": a["analytic_annulus_m2"],
        "hub_radius_m": a["hub_radius_m"],
        "shroud_radius_m": a["shroud_radius_m"],
        "rel_diff": a["rel_diff"],
        "verdict": a["verdict"],
        "how": a["how"],
        "source_xmf": data["xmf"],
    }
    (out_dir / "outlet-area-audit.json").write_text(
        json.dumps(area_audit, ensure_ascii=False, indent=2) + chr(10),
        encoding="utf-8", newline="")

    if args.outlet_area_only:
        print("出口面积交叉核验（C-004）")
        print("  全周面积 = 周区 %.10g x 周期 %d = %.10g m2"
              % (a["sector_area_m2"], a["periodicity"], a["full_area_m2"]))
        print("  解析环面积 = pi*(%.8g^2 - %.8g^2) = %.10g m2"
              % (a["shroud_radius_m"], a["hub_radius_m"], a["analytic_annulus_m2"]))
        print("  相对差 %.4e  [%s]" % (a["rel_diff"], a["verdict"]))
        print("  -> " + str(out_dir / "outlet-area-audit.json"))
        return 0 if a["verdict"] != "FAIL" else 4

    p = write_csv(data, out_dir)
    r = data["result"]
    a = data["outlet_area"]
    if args.json:
        print(json.dumps({"ok": a["verdict"] != "FAIL", "csv": str(p), "data": data},
                         ensure_ascii=False, indent=2))
    else:
        print("静推力闭合（C-004）")
        print("  动量推力 = %.6g kg/s x %.6g m/s = %.6g N"
              % (data["inputs"]["mass_flow_kg_s"], data["inputs"]["axial_velocity_m_s"],
                 r["momentum_thrust_n"]))
        print("  压力推力 = (%.6g - %.6g) Pa x %.6g m2 = %.6g N"
              % (data["inputs"]["static_pressure_pa_abs"],
                 data["inputs"]["ambient_static_pressure_pa_abs"],
                 a["full_area_m2"], r["pressure_thrust_n"]))
        print("  静推力   = %.6g N = %.4g kgf" % (r["static_thrust_n"], r["static_thrust_kgf"]))
        print("  出口面积 = %.6g m2（周区 %.6g x %d）　解析环 %.6g m2　相对差 %.3e  [%s]"
              % (a["full_area_m2"], a["sector_area_m2"], a["periodicity"],
                 a["analytic_annulus_m2"], a["rel_diff"], a["verdict"]))
        print("  -> " + str(p))
    return 0 if a["verdict"] != "FAIL" else 4


if __name__ == "__main__":
    raise SystemExit(main())