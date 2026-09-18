#!/usr/bin/env python3
"""v8 / quantify the "simple Bezier" 弯(lean) + 掠(sweep) adjustment.

Runs the same 13-section / 10-point-hub model three times, changing only the two
BEZIER_BETA stacking angles, and compares the exported blade geometry:

  ref : LEAN_BETA = 0.3707 deg (v7 value), SWEEP_BETA = 0.0 deg (v7 value)
  new : LEAN_BETA = 1.5 deg,               SWEEP_BETA = 1.0 deg   (v8 delivery)
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v8_ab_lib as ab  # noqa: E402
import v8_audit2 as A  # noqa: E402

BUILD = Path(r"D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v8\automation\build-par")
WORK = Path(r"D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v8\automation\leansweep")


def main() -> int:
    base = (BUILD / "R1.par").read_text(encoding="utf-8")
    ref = ab.set_parameter_block(ab.set_parameter_block(base, "LEAN_BETA", 0.370700005692461), "SWEEP_BETA", 0.0)
    new = base
    results = {}
    for tag, text in (("ref", ref), ("new", new)):
        res = ab.run_batch(WORK / tag, "R1", text)
        if not res["ok"]:
            print(f"{tag}: FAILED")
            return 1
        results[tag] = A.parse_sections(res["geom"])
        print(f"{tag}: ok")
    print(f"{'span':>7} {'r':>9} {'z_LE ref':>10} {'z_LE new':>10} {'dz (sweep) mm':>14} "
          f"{'t_LE ref':>10} {'t_LE new':>10} {'r*dt (lean) mm':>15}")
    out = []
    ref_sec, new_sec = results["ref"], results["new"]
    for i in sorted(ref_sec["suction"]):
        r_pts = ref_sec["suction"][i] + ref_sec["pressure"][i]
        n_pts = new_sec["suction"][i] + new_sec["pressure"][i]
        r_rm = sum(p[0] for p in r_pts) / len(r_pts)
        span = (r_rm - 0.094) / (0.3 - 0.094)
        zmin_r = min(p[2] for p in r_pts)
        zmin_n = min(p[2] for p in n_pts)
        le_r = [p for p in r_pts if p[2] <= zmin_r + 0.0005]
        le_n = [p for p in n_pts if p[2] <= zmin_n + 0.0005]
        t_r = sum(p[1] for p in le_r) / len(le_r)
        t_n = sum(p[1] for p in le_n) / len(le_n)
        dz = (zmin_n - zmin_r) * 1000
        dt = (t_n - t_r) * r_rm * 1000
        out.append({"section": i, "span": span, "dz_mm": dz, "d_tangential_mm": dt})
        print(f"{span:7.4f} {r_rm*1000:9.3f} {zmin_r*1000:10.4f} {zmin_n*1000:10.4f} {dz:14.4f} "
              f"{t_r:10.6f} {t_n:10.6f} {dt:15.4f}")
    (WORK / "leansweep_delta.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
