#!/usr/bin/env python3
"""v8 / do the v7 rotor force-surface names exist in the v8 .run?"""
from __future__ import annotations

import re
from pathlib import Path

RUN = Path(r"D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v8\fine\v8-optimized\v8-optimized_n05000_p101325\v8-optimized_n05000_p101325.run")
V7RUN = Path(r"D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v7\fine\v7-optimized\v7-optimized_n05000_p101325\v7-optimized_n05000_p101325.run")
WHITE = Path(r"D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v7\automation\rotor_surfaces.txt")


def block_names(run: Path) -> list[str]:
    text = run.read_text(encoding="utf-8", errors="replace")
    # a boundary_condition block that carries a NAME and a CONTROL_SURFACE_NAME
    out = []
    for m in re.finditer(r"NI_BEGIN\s+boundary_condition(.*?)NI_END\s+boundary_condition", text, re.S):
        b = m.group(1)
        n = re.search(r"(?m)^\s*NAME\s+(\S+)\s*$", b)
        c = re.findall(r"CONTROL_SURFACE_NAME\s+(\S+)", b)
        t = re.search(r"(?m)^\s*TYPE\s+(\S+)\s*$", b)
        if n:
            out.append((n.group(1), t.group(1) if t else "?", c))
    return out


def main() -> int:
    want = [l.strip() for l in WHITE.read_text(encoding="utf-8").splitlines() if l.strip()]
    for label, run in (("v8", RUN), ("v7", V7RUN)):
        if not run.is_file():
            print(label, "missing", run)
            continue
        names = block_names(run)
        print(f"=== {label}: {len(names)} boundary_condition blocks")
        for w in want:
            hits = [n for n, t, c in names if n == w]
            if not hits and label == "v8":
                print("   MISSING:", w)
        allnames = {n for n, _, _ in names}
        print(f"   whitelist present: {sum(1 for w in want if w in allnames)}/{len(want)}")
        sol = [(n, c) for n, t, c in names if t.upper() == "SOL"]
        print(f"   TYPE SOL blocks: {len(sol)}")
        ft = [(n, c) for n, c in sol if any(x == "Force_and_Torque" for x in c)]
        print(f"   SOL blocks with Force_and_Torque: {len(ft)}")
        for n, c in ft[:15]:
            print("      ", n, "->", c)
        if label == "v7":
            for n, c in sol[:6]:
                print("      sample SOL:", n, "->", c)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
