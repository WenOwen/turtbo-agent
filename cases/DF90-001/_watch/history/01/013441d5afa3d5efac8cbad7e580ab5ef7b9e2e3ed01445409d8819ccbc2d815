#!/usr/bin/env python3
"""v8 / final acceptance audit - the numbers quoted in the delivery README."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v8_ab_lib as ab  # noqa: E402
import v8_audit2 as A  # noqa: E402
import v8_build_par as B  # noqa: E402

ROOT = Path(r"D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v8")
FINAL = ROOT / "autoblade"
V7 = Path(r"D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v7\autoblade")
OUT = ROOT / "automation" / "final_audit.json"


def main() -> int:
    report: dict = {"hub_points": B.HUB_POINTS, "spans13": B.cosine_spans(13),
                    "lean_beta_deg": B.LEAN_BETA_NEW, "sweep_beta_deg": B.SWEEP_BETA_NEW,
                    "rows": {}}
    p = B.HUB_POINTS
    report["p4_p5_distance_mm"] = math.hypot(p[4][0] - p[3][0], p[4][1] - p[3][1]) * 1000
    report["p4_p5_diameter_mm"] = 2 * p[3][1] * 1000

    for row in ("R1", "R2"):
        geom = FINAL / f"{row}_13span" / f"{row}.geomTurbo"
        curves = ab.read_zr_curves(geom)
        hub, shroud = curves["hub_crv_1"], curves["shroud_crv_1"]
        inside = [r for z, r in hub if p[3][0] <= z <= p[4][0]]
        # annulus area along the passage
        area = [math.pi * (s[1] ** 2 - h[1] ** 2) for h, s in zip(hub, shroud)]
        # spanwise section report
        secs = A.parse_sections(geom)
        v7secs = A.parse_sections(V7 / f"{row}_5span" / f"{row}.geomTurbo")
        shared = {1: 1, 5: 2, 7: 3, 9: 4, 13: 5}
        table = []
        for i8, i7 in shared.items():
            a = A.metrics(v7secs["suction"][i7], v7secs["pressure"][i7])
            b = A.metrics(secs["suction"][i8], secs["pressure"][i8])
            table.append({
                "span": B.cosine_spans(13)[i8 - 1],
                "v7_stagger_deg": a["stagger_deg"], "v8_stagger_deg": b["stagger_deg"],
                "v7_axial_chord_mm": (a["z_te"] - a["z_le"]) * 1000,
                "v8_axial_chord_mm": (b["z_te"] - b["z_le"]) * 1000,
            })
        entry = {
            "sections": len(A.parse_sections(geom)["suction"]),
            "hub_points": len(hub),
            "motor_window_r_min_mm": min(inside) * 1000,
            "motor_window_r_max_mm": max(inside) * 1000,
            "motor_window_diameter_min_mm": 2 * min(inside) * 1000,
            "hub_monotone": all(hub[i + 1][1] >= hub[i][1] - 1e-9 for i in range(len(hub) - 1)),
            "hub_worst_backstep_um": min((hub[i + 1][1] - hub[i][1]) for i in range(len(hub) - 1)) * 1e6,
            "min_shroud_clearance_mm": min(s[1] - h[1] for h, s in zip(hub, shroud)) * 1000,
            "area_inlet_m2": area[0], "area_outlet_m2": area[-1],
            "area_ratio_out_in": area[-1] / area[0],
            "area_monotone_decreasing": all(area[i + 1] <= area[i] + 1e-12 for i in range(len(area) - 1)),
            "area_max_increase_m2": max(area[i + 1] - area[i] for i in range(len(area) - 1)),
            "hub_tip_ratio_inlet": hub[0][1] / shroud[0][1],
            "hub_tip_ratio_outlet": hub[-1][1] / shroud[-1][1],
            "v7_area_ratio_out_in": None,
            "section_table": table,
        }
        v7c = ab.read_zr_curves(V7 / f"{row}_5span" / f"{row}.geomTurbo")
        a7 = [math.pi * (s[1] ** 2 - h[1] ** 2) for h, s in zip(v7c["hub_crv_1"], v7c["shroud_crv_1"])]
        entry["v7_area_ratio_out_in"] = a7[-1] / a7[0]
        report["rows"][row] = entry

    report["reopen_ok"] = json.loads((ROOT / "automation" / "publish_report.json").read_text(encoding="utf-8"))["reopen_ok"]
    report["files"] = sorted(str(f.relative_to(ROOT)) for f in FINAL.rglob("*") if f.is_file())
    OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")

    print("hub control points:")
    for i, (z, r) in enumerate(p, 1):
        print(f"  P{i:<2d} z={z:.6f} m  r={r:.6f} m  D={2*r*1000:.3f} mm")
    print(f"  |P5-P4| = {report['p4_p5_distance_mm']:.4f} mm   nominal diameter = {report['p4_p5_diameter_mm']:.3f} mm")
    for row, e in report["rows"].items():
        print(f"--- {row} ---")
        print(f"  sections exported        : {e['sections']}   hub control points: {e['hub_points']}")
        print(f"  motor window radius      : {e['motor_window_r_min_mm']:.6f} .. {e['motor_window_r_max_mm']:.6f} mm")
        print(f"  motor window diameter    : {e['motor_window_diameter_min_mm']:.4f} mm (min)")
        print(f"  hub monotone             : {e['hub_monotone']} (worst backstep {e['hub_worst_backstep_um']:+.4f} um)")
        print(f"  min hub-shroud clearance : {e['min_shroud_clearance_mm']:.3f} mm")
        print(f"  passage area ratio out/in: v8 {e['area_ratio_out_in']:.4f}  (v7 {e['v7_area_ratio_out_in']:.4f})"
              f"   monotone decreasing: {e['area_monotone_decreasing']} (max step up {e['area_max_increase_m2']:.3e} m2)")
        print(f"  hub/tip ratio            : inlet {e['hub_tip_ratio_inlet']:.4f} -> outlet {e['hub_tip_ratio_outlet']:.4f}")
        print(f"  {'span':>7} {'v7 stagger':>11} {'v8 stagger':>11} {'v7 Cax':>9} {'v8 Cax':>9}")
        for t in e["section_table"]:
            print(f"  {t['span']:7.4f} {t['v7_stagger_deg']:11.4f} {t['v8_stagger_deg']:11.4f} "
                  f"{t['v7_axial_chord_mm']:9.4f} {t['v8_axial_chord_mm']:9.4f}")
    print(f"reopen gate (.abp re-open with AutoBlade): {report['reopen_ok']}")
    print("delivered files:")
    for f in report["files"]:
        print("   " + f)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
