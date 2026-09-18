#!/usr/bin/env python3
"""v8 / rebuild the v7 characteristic-scan plan against the v8 case root.

Keeps the v7 contract (speed lines, outlet static-pressure ladder, the same
cold-start anchor, the same restart topology) and only re-points the restart
paths at the v8 project tree.

The previous version replaced the bare token "v7-optimized" everywhere, which
also rewrote the *case directory* component but left the run root pointing into
the v7 tree.  Here the restart path is recomposed from the case name instead.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

V7_ROOT = Path(r"D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v7\fine\v7-optimized")
V8_ROOT = Path(r"D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v8\fine\v8-optimized")
SRC = V7_ROOT / "scan_plan.csv"
OUT = Path(r"D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v8\automation\scan_plan.csv")
STEM_OLD, STEM_NEW = "v7-optimized", "v8-optimized"


def main() -> int:
    rows = list(csv.DictReader(SRC.open(encoding="utf-8")))
    out_rows = []
    for r in rows:
        restart = r["restart_from"].strip()
        new_restart = ""
        if restart:
            src = Path(restart)
            case_dir = src.parent.name
            if not case_dir.startswith(STEM_OLD + "_"):
                raise SystemExit(f"unexpected v7 case directory: {case_dir}")
            case = case_dir[len(STEM_OLD) + 1:]
            if src.stem != f"{STEM_OLD}_{case}":
                raise SystemExit(f"restart file stem mismatch: {src.name}")
            new_restart = str((V8_ROOT / f"{STEM_NEW}_{case}" / f"{STEM_NEW}_{case}.cgns").as_posix())
        out_rows.append({"case": r["case"], "rpm": r["rpm"],
                         "target_pressure_pa_abs": r["target_pressure_pa_abs"],
                         "restart_from": new_restart})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["case", "rpm", "target_pressure_pa_abs", "restart_from"])
        writer.writeheader()
        writer.writerows(out_rows)
    print(f"written {OUT} ({len(out_rows)} rows)")
    anchors = [r for r in out_rows if not r["restart_from"]]
    print(f"cold-start anchors: {[r['case'] for r in anchors]}")
    for r in out_rows[1:3]:
        print(f"  restart sample {r['case']}: {r['restart_from']}")
    bad = [r["restart_from"] for r in out_rows if r["restart_from"] and "90kg-duct-fan-v7" in r["restart_from"]]
    print(f"rows still pointing at the v7 tree: {len(bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
