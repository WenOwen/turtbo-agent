#!/usr/bin/env python3
"""v8 / chirality read-back on the published GeomTurbo pair."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v8_audit2 as A  # noqa: E402

R7 = Path(r"D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v7\autoblade")
R8 = Path(r"D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v8\autoblade")
for label, path in (
    ("v7 R1", R7 / "R1_5span" / "R1.geomTurbo"),
    ("v8 R1", R8 / "R1_13span" / "R1.geomTurbo"),
    ("v7 R2", R7 / "R2_5span" / "R2.geomTurbo"),
    ("v8 R2", R8 / "R2_13span" / "R2.geomTurbo"),
):
    secs = A.parse_sections(path)
    w = [A.metrics(secs["suction"][i], secs["pressure"][i])["stagger_deg"] for i in sorted(secs["suction"])]
    print("%-7s sections=%2d  winding: %s" % (label, len(w), " ".join("%+.3f" % v for v in w)))
