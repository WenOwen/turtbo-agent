#!/usr/bin/env python3
"""v8 / audit v2 - corrected GeomTurbo frame handling.

The v8 (and v7) GeomTurbo blade sections are exported as CARTESIAN (x, y, z)
triples, not (r, theta, z): for the v7 R1 hub section, sqrt(x^2+y^2) reproduces
the hub endwall radius at that axial station to 1.4 um, while the first column
alone does not.  This script therefore reconstructs r = sqrt(x^2+y^2) and
theta = atan2(y, x) before measuring anything.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v8_ab_lib as ab  # noqa: E402

V7 = Path(r"D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v7\autoblade")
V8 = Path(r"D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v8\automation\stage")
SPANS13 = [0.5 * (1 - math.cos(i * math.pi / 12)) for i in range(13)]


def parse_sections(path: Path):
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    result = {}
    for side in ("suction", "pressure"):
        idx = next(i for i, line in enumerate(lines) if line.strip() == side)
        while lines[idx].strip() != "SECTIONAL":
            idx += 1
        idx += 1
        count = int(lines[idx].strip().lstrip("+"))
        idx += 1
        sections = {}
        for _ in range(count):
            while not lines[idx].strip().startswith("# section"):
                idx += 1
            section_index = int(lines[idx].strip().split()[-1])
            idx += 1
            assert lines[idx].strip() == "XYZ"
            idx += 1
            npts = int(lines[idx].strip().lstrip("+"))
            idx += 1
            pts = []
            for _ in range(npts):
                x, y, z = (float(v) for v in lines[idx].split()[:3])
                pts.append((math.hypot(x, y), math.atan2(y, x), z))
                idx += 1
            sections[section_index] = pts
        result[side] = sections
    return result


def metrics(suction, pressure):
    pts = suction + pressure
    le = min(suction + pressure, key=lambda p: p[2])
    # LE/TE from the extreme axial points of both sides, averaged over a small band
    zmin = min(p[2] for p in pts)
    zmax = max(p[2] for p in pts)
    band = 0.02 * (zmax - zmin)
    le_pts = [p for p in pts if p[2] <= zmin + band]
    te_pts = [p for p in pts if p[2] >= zmax - band]
    r_le = sum(p[0] for p in le_pts) / len(le_pts)
    t_le = sum(p[1] for p in le_pts) / len(le_pts)
    z_le = sum(p[2] for p in le_pts) / len(le_pts)
    r_te = sum(p[0] for p in te_pts) / len(te_pts)
    t_te = sum(p[1] for p in te_pts) / len(te_pts)
    z_te = sum(p[2] for p in te_pts) / len(te_pts)
    r_mid = 0.5 * (r_le + r_te)
    dt = (t_te - t_le) * r_mid
    dz = z_te - z_le
    chord = math.hypot(dz, dt)
    stagger = math.degrees(math.atan2(dt, dz))
    thick = 0.0
    for a in suction:
        thick = max(thick, min(math.dist(a, b) for b in pressure))
    return {
        "r_le": r_le, "t_le": t_le, "z_le": z_le, "r_te": r_te, "t_te": t_te, "z_te": z_te,
        "chord": chord, "stagger_deg": stagger, "tmax": thick, "r_mid": r_mid,
        "z_min": zmin, "z_max": zmax,
    }


def main() -> int:
    report = {}
    for row in ("R1", "R2"):
        v7p = V7 / f"{row}_5span" / f"{row}.geomTurbo"
        v8p = V8 / f"{row}_13span" / f"{row}.geomTurbo"
        v7 = parse_sections(v7p)
        v8 = parse_sections(v8p)
        hub7 = ab.read_zr_curves(v7p)["hub_crv_1"]
        hub8 = ab.read_zr_curves(v8p)["hub_crv_1"]
        print("=" * 96)
        print(f"{row}:  v7 sections={len(v7['suction'])}   v8 sections={len(v8['suction'])}")
        m7 = {i: metrics(v7["suction"][i], v7["pressure"][i]) for i in sorted(v7["suction"])}
        m8 = {i: metrics(v8["suction"][i], v8["pressure"][i]) for i in sorted(v8["suction"])}
        print("  --- v7 reference sections (span 0/.25/.5/.75/1) ---")
        for i in sorted(m7):
            m = m7[i]
            print(f"    S{i}: z {m['z_min']*1000:8.3f}..{m['z_max']*1000:8.3f} mm  "
                  f"r_LE={m['r_le']*1000:8.3f}  r_TE={m['r_te']*1000:8.3f}  "
                  f"stagger={m['stagger_deg']:8.3f} deg  chord={m['chord']*1000:7.3f} mm  tmax={m['tmax']*1000:6.3f} mm")
        print("  --- v8 sections (13) ---")
        for i in sorted(m8):
            m = m8[i]
            r_hub = ab.interp(hub8, m["z_le"])
            r_sh = 0.3
            pred = r_hub + SPANS13[i - 1] * (r_sh - r_hub)
            print(f"    S{i:<2d} span={SPANS13[i-1]:.4f}  z {m['z_min']*1000:8.3f}..{m['z_max']*1000:8.3f}  "
                  f"r_LE={m['r_le']*1000:8.3f} (pred {pred*1000:8.3f})  "
                  f"stagger={m['stagger_deg']:8.3f}  chord={m['chord']*1000:7.3f}  tmax={m['tmax']*1000:6.3f}")
        print("  --- v7 vs v8 at shared spans ---")
        shared = {1: 1, 4: 2, 7: 3, 10: 4, 13: 5}
        print(f"    {'span':>7} {'stagger v7':>11} {'stagger v8':>11} {'d':>8} "
              f"{'chord v7':>10} {'chord v8':>10} {'d':>8} {'z_LE v7':>9} {'z_LE v8':>9}")
        for i8, i7 in shared.items():
            a, b = m7[i7], m8[i8]
            print(f"    {SPANS13[i8-1]:7.4f} {a['stagger_deg']:11.4f} {b['stagger_deg']:11.4f} "
                  f"{b['stagger_deg']-a['stagger_deg']:8.4f} {a['chord']*1000:10.4f} {b['chord']*1000:10.4f} "
                  f"{(b['chord']-a['chord'])*1000:8.4f} {a['z_le']*1000:9.4f} {b['z_le']*1000:9.4f}")
        report[row] = {"v7": m7, "v8": m8, "spans13": SPANS13}
    (Path(__file__).resolve().parent / "v8_audit2.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
