#!/usr/bin/env python3
"""v8 / pre-launch audit of a materialised .run (mesh binding, boundary, loads)."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

MESH = Path(r"D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v8\mesh\mesh-v2\mesh-v2.igg")
WHITELIST = Path(r"D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v7\automation\rotor_surfaces.txt")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    run = args.run
    text = run.read_text(encoding="utf-8", errors="replace")
    out = args.out or run.with_name("boundary_audit.json")

    want = {l.strip() for l in WHITELIST.read_text(encoding="utf-8").splitlines() if l.strip()}
    selected = set()
    for m in re.finditer(r"NI_BEGIN\s+boundary_condition(.*?)NI_END\s+boundary_condition", text, re.S):
        block = m.group(1)
        if not re.search(r"(?m)^\s*TYPE\s+SOL\s*$", block):
            continue
        name = re.search(r"(?m)^\s*NAME\s+(\S+)\s*$", block)
        ctrl = re.findall(r"CONTROL_SURFACE_NAME\s+(\S+)", block)
        if name and "Force_and_Torque" in ctrl:
            selected.add(name.group(1))

    grid = re.findall(r"(?m)^\s*GRID_FILE\s+(.+?)\s*$", text)
    static_p = re.findall(r"(?m)^\s*REAL_ENTRY\s+Static_Pressure\s+([-+0-9.eE]+)\s*$", text)
    start_from = re.findall(r"(?m)^\s*START_FROM_INITIAL_SOLUTION_FILE[ \t]+(\S+)[ \t]*$", text)
    init_file = re.findall(r"(?m)^\s*INITIAL_SOLUTION_FILE[ \t]+(\S+)[ \t]*$", text)
    speeds = sorted({float(v) for v in re.findall(
        r"(?m)^\s*REAL_ENTRY\s+(?:Block_Rotation_Speed|Rotational Speed 1)\s+([-+0-9.eE]+)\s*$", text)})

    mesh_norm = str(MESH).replace("/", "\\").lower()
    grid_norm = [g.replace("/", "\\").lower() for g in grid]
    result = {
        "run": str(run),
        "run_bytes": run.stat().st_size,
        "grid_file": grid,
        "grid_binds_v8_mesh": all(g == mesh_norm for g in grid_norm) and bool(grid),
        "static_pressure_entries": static_p,
        "start_from_initial_solution_file": start_from,
        "initial_solution_file": init_file,
        "rotation_speeds_rpm": speeds,
        "force_surfaces_selected": sorted(selected),
        "force_surfaces_expected": sorted(want),
        "force_surfaces_exact_match": selected == want,
    }
    # .run stores angular velocity in rad/s; 5000 rpm = 523.5988 rad/s
    expected_speed = 5000.0 * 2.0 * 3.141592653589793 / 60.0
    result["expected_nonzero_speed_rad_s"] = expected_speed
    result["passed"] = (
        result["grid_binds_v8_mesh"]
        and len(static_p) == 1
        and result["force_surfaces_exact_match"]
        and start_from == ["no"]
        and all(abs(s - expected_speed) < 1e-6 for s in speeds if s != 0.0)
        and any(abs(s - expected_speed) < 1e-6 for s in speeds)
    )
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    for k, v in result.items():
        print(f"  {k}: {v}")
    print("PASSED" if result["passed"] else "FAILED")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
