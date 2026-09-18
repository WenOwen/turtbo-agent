#!/usr/bin/env python3
"""v8 / materialise the registered computations of the v8 IEC into native
ICE-layout .run files with finebatch, then audit the handoff.

Contract:
  <root>/<project>.iec  +  computation <name>
    -> <root>/<project>_<name>/<project>_<name>.run
       (+ .steering, .run.batch)

finebatch's exit code is NOT trusted: success requires the log line
"Output file(s) successfully written", a non-empty .run and a non-empty .steering.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

FINEBATCH = Path(r"D:\NUMECA_SOFTWARE\fine161\bin64\finebatchx86_64.exe")
PROJECT = Path(r"D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v8\fine\v8-optimized\v8-optimized.iec")
MESH = Path(r"D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v8\mesh\mesh-v2\mesh-v2.igg")
REPORT = PROJECT.parent / "materialize_report.json"


def computation_names(iec: Path) -> list[str]:
    text = iec.read_text(encoding="utf-8", errors="replace")
    names = []
    for block in re.split(r"(?m)^\*+ START COMPUTATION", text)[1:]:
        m = re.search(r"(?m)^\s*NAME\s+(\S+)\s*$", block)
        names.append(m.group(1) if m else "?")
    return names


def grid_signature(run: Path) -> dict:
    """Block name + IMAX/JMAX/KMAX multiset from a .run, for the mesh handoff."""
    text = run.read_text(encoding="utf-8", errors="replace")
    blocks = []
    for m in re.finditer(
        r"NI_BEGIN\s+block(?P<body>.*?)NI_END\s+block", text, re.S
    ):
        body = m.group("body")
        name = re.search(r"(?m)^\s*NAME\s+(\S+)\s*$", body)
        dims = {}
        for key in ("IMAX", "JMAX", "KMAX"):
            d = re.search(rf"(?m)^\s*{key}\s+(\d+)\s*$", body)
            if d:
                dims[key] = int(d.group(1))
        if name and len(dims) == 3:
            blocks.append([name.group(1), dims["IMAX"], dims["JMAX"], dims["KMAX"]])
    return {"block_count": len(blocks), "blocks": sorted(blocks)}


def materialize(name: str) -> dict:
    case_dir = PROJECT.parent / f"{PROJECT.stem}_{name}"
    case_dir.mkdir(parents=True, exist_ok=True)
    run = case_dir / f"{PROJECT.stem}_{name}.run"
    steering = case_dir / f"{PROJECT.stem}_{name}.steering"
    # finebatch -index is ZERO-based: passing the one-based position materialises
    # the NEXT computation while still writing the file name we asked for.
    cmd = [str(FINEBATCH), "-project", str(PROJECT), "-mesh", str(MESH),
           "-index", str(computation_names(PROJECT).index(name)), "-computation", str(run)]
    completed = subprocess.run(cmd, cwd=str(case_dir), text=True, capture_output=True)
    log = (completed.stdout or "") + (completed.stderr or "")
    (case_dir / f"{PROJECT.stem}_{name}.finebatch.log").write_text(log, encoding="utf-8")
    ok = (
        "Output file(s) successfully written" in log
        and run.is_file() and run.stat().st_size > 0
        and steering.is_file() and steering.stat().st_size > 0
    )
    entry = {"case": name, "run": str(run), "ok": ok,
             "run_bytes": run.stat().st_size if run.is_file() else 0,
             "steering_bytes": steering.stat().st_size if steering.is_file() else 0,
             "returncode": completed.returncode,
             "log_tail": "\n".join(log.splitlines()[-3:])}
    if ok:
        entry["grid"] = grid_signature(run)
    return entry


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", nargs="*", default=None)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    names = args.cases or computation_names(PROJECT)
    if args.limit:
        names = names[: args.limit]
    report = {"project": str(PROJECT), "mesh": str(MESH), "cases": []}
    for i, name in enumerate(names, 1):
        entry = materialize(name)
        report["cases"].append(entry)
        print(f"[{i}/{len(names)}] {name}: ok={entry['ok']} run={entry['run_bytes']}B "
              f"steering={entry['steering_bytes']}B rc={entry['returncode']}", flush=True)
        if not entry["ok"]:
            print("   log tail:", entry["log_tail"][:400], flush=True)
    report["ok_count"] = sum(1 for c in report["cases"] if c["ok"])
    REPORT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"materialised {report['ok_count']}/{len(names)}; report -> {REPORT}")
    return 0 if report["ok_count"] == len(names) else 1


if __name__ == "__main__":
    raise SystemExit(main())
