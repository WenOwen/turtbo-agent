#!/usr/bin/env python3
"""v8 / export: refresh GeomTurbo + Parasolid(XMT) for both rows and force the
R2 flowpath to be identical to the manually adjusted R1 flowpath.

Source of truth for the flowpath is the hand-edited R1.par.  Only the hub and
shroud control points are copied to R2; blade sections, lean/sweep and all other
parameters of R2 are left untouched.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v8_ab_lib as ab  # noqa: E402

V8 = Path(r"D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v8")
AB = V8 / "autoblade"
XMT = AB / "xmt"
REPORT = V8 / "automation" / "export_report.json"

AB_SCRIPT = """import os
par_path = r"{par}"
abp_path = r"{abp}"
geom_path = r"{geom}"
xmt_path = r"{xmt}"
print("SCRIPT_BEGIN v8_export")
if not ab_project_open(abp_path):
    raise RuntimeError("ab_project_open failed: %s" % abp_path)
if not ab_project_load_model(par_path):
    raise RuntimeError("ab_project_load_model failed: %s" % par_path)
if not ab_model_update_all():
    raise RuntimeError("ab_model_update_all failed")
if not ab_project_save_as(abp_path):
    raise RuntimeError("ab_project_save_as failed")
r = ab_model_export_geomturbo(geom_path)
print("GEOMTURBO_EXPORT_RESULT %s" % r)
if (not r) and (not os.path.exists(geom_path)):
    raise RuntimeError("ab_model_export_geomturbo failed")
p = ab_model_export_parasolid(xmt_path)
print("PARASOLID_EXPORT_RESULT %s" % p)
if (not p) and (not os.path.exists(xmt_path)):
    raise RuntimeError("ab_model_export_parasolid failed")
print("SCRIPT_RETURN_VALUE 1")
"""


def read_curve_points(text: str, curve_name: str, prefix: str) -> list[tuple[float, float]]:
    m = re.search(
        rf"NI_BEGIN\s+PARAM_CURVE_2D\b.*?NAME\s+{re.escape(curve_name)}\s*$.*?NI_BEGIN\s+PARAMETERS\s*\n(.*?)^\s*NI_END\s+PARAMETERS",
        text, re.M | re.S,
    )
    if not m:
        raise RuntimeError(f"{curve_name} block not found")
    points = []
    index = 1
    while True:
        z = re.search(rf"NAME\s+{prefix}_Z{index}\s*\n(?:.*?\n)*?\s*VALUE\s+(\S+)\s*$", m.group(1), re.M)
        if not z:
            break
        r = re.search(rf"NAME\s+{prefix}_R{index}\s*\n(?:.*?\n)*?\s*VALUE\s+(\S+)\s*$", m.group(1), re.M)
        points.append((float(z.group(1)), float(r.group(1))))
        index += 1
    if not points:
        raise RuntimeError(f"{curve_name} has no control points")
    return points


def main() -> int:
    r1_par = AB / "R1_13span" / "R1.par"
    r2_par = AB / "R2_13span" / "R2.par"
    r1_text = r1_par.read_text(encoding="utf-8")

    hub = read_curve_points(r1_text, "HUB_CURVE", "HUB")
    shroud = read_curve_points(r1_text, "TIP_CURVE", "SHROUD")
    print(f"R1 flowpath (source of truth): hub {len(hub)} points, shroud {len(shroud)} points")
    for i, (z, r) in enumerate(hub, 1):
        print(f"   HUB P{i:<2d} z={z:.9f}  r={r:.9f}  D={2*r*1000:.4f} mm")

    r2_text = r2_par.read_text(encoding="utf-8")
    r2_text = ab.replace_curve_parameters(r2_text, "HUB_CURVE", "HUB", hub)
    r2_text = ab.replace_curve_parameters(r2_text, "TIP_CURVE", "SHROUD", shroud)
    # AutoBlade writes the endwall counts through the same PARAMETERS container
    r2_par.write_text(r2_text, encoding="utf-8")
    print("R2 flowpath replaced by the R1 flowpath")

    XMT.mkdir(parents=True, exist_ok=True)
    report: dict = {"hub": hub, "shroud": shroud, "rows": {}}
    for row in ("R1", "R2"):
        work = AB / f"{row}_13span"
        par = work / f"{row}.par"
        abp = work / f"{row}.abp"
        geom = work / f"{row}.geomTurbo"
        xmt = XMT / f"{row}-model.xmt_txt"
        script_path = V8 / "automation" / f"_export_{row}.py"
        script_path.write_text(
            AB_SCRIPT.format(par=par.as_posix(), abp=abp.as_posix(),
                             geom=geom.as_posix(), xmt=xmt.as_posix()),
            encoding="utf-8",
        )
        import subprocess
        completed = subprocess.run(
            [str(ab.AUTOBLADE_EXE), "-batch", "-script", str(script_path), "-print"],
            cwd=str(work), text=True, capture_output=True,
        )
        log = (completed.stdout or "") + (completed.stderr or "")
        (V8 / "automation" / f"export_{row}.log").write_text(log, encoding="utf-8")
        script_path.unlink()
        ok = (completed.returncode == 0 and "SCRIPT_RETURN_VALUE 1" in log
              and "[error]" not in log.lower())
        report["rows"][row] = {"ok": ok, "geomTurbo": str(geom), "xmt": str(xmt),
                               "geom_bytes": geom.stat().st_size if geom.exists() else 0,
                               "xmt_bytes": xmt.stat().st_size if xmt.exists() else 0}
        print(f"  {row}: ok={ok} geom={report['rows'][row]['geom_bytes']} B "
              f"xmt={report['rows'][row]['xmt_bytes']} B")
        if not ok:
            print("\n".join(log.splitlines()[-25:]))

    # reopen gate on the two delivered projects
    report["reopen_ok"] = ab.reopen_projects(V8 / "automation", [AB / "R1_13span" / "R1.abp",
                                                                AB / "R2_13span" / "R2.abp"])
    print("reopen gate:", report["reopen_ok"])
    REPORT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
