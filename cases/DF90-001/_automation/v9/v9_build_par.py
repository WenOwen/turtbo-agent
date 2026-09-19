#!/usr/bin/env python3
"""v9 / 由 01-scheme/v3 的流道造一版新几何（走 AutoBlade）。

这一版做了什么、没做什么
------------------------
**做了**：轮毂型线换成 v3 的（进口 Ø160 -> 电机段 Ø188 -> 出口 Ø226.4），
机匣按 v3 的流道表锁定 0.300。叶片截面沿用 v8 那套（经过三维网格与 CFD 验证的）。

**没做**：叶片金属角没有换成 v3 的值。原因见 OBSERVATIONS 一节 ——
v8 的金属角逐截面是**变化**的（R1 的 BETA1 -56.07..-59.15、BETA2 -28.52..-34.58），
而 v3 的表**每排只给一个值**（R1 的 beta1 -68.276、beta2 -60.531），差 12 度与 32 度。
直接把单值铺到 13 个截面会**把扭转抹平**，那是另一台机器，不是"把方案落到几何上"。
而且 turbo-flow 的金属角与 AutoBlade 的 CAMBER_BETA 是否同一约定（相对轴向 vs 相对切向、
符号坐标系）**没有查证**。猜一个约定去改叶片，比不改更坏。

所以 v9 的定位是：**同一个叶片，一条改正过的流道**。
它能把"流道改动"这一个变量单独隔离出来，划网格、跑 CFD 都是干净的对照。
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASE = HERE.parents[1]
ROOT = CASE.parents[1]

sys.path.insert(0, str(CASE / "_automation" / "v8"))
import v8_ab_lib as ab  # noqa: E402

V8_AB = CASE / "02-geometry" / "v8" / "autoblade"
OUT = CASE / "02-geometry" / "v9" / "autoblade"

# 01-scheme/v3/NOTES.md 的轮毂型线（6 个控制点）
HUB_V3 = [
    (0.000, 0.080000),
    (0.050, 0.086000),
    (0.095, 0.094500),
    (0.185, 0.095800),
    (0.230, 0.098500),
    (0.300, 0.113200),
]
# 01-scheme/v3/流道尺寸表.csv 的机匣半径：四个站位全是 0.300000
SHROUD_V3 = [(0.000, 0.300000), (0.300, 0.300000)]

ROWS = (("R1", "R1_13span/R1.par"), ("R2", "R2_13span/R2.par"))


def build_row(label: str, source: Path) -> str:
    text = source.read_text(encoding="utf-8")
    text = ab.replace_curve_parameters(text, "HUB_CURVE", "HUB", HUB_V3)
    text = ab.replace_curve_parameters(text, "TIP_CURVE", "SHROUD", SHROUD_V3)
    n_hub = len(re.findall(r"NAME\s+HUB_[ZR]\d+", text))
    n_shr = len(re.findall(r"NAME\s+SHROUD_[ZR]\d+", text))
    print(f"  {label}: hub {n_hub // 2} 点, shroud {n_shr // 2} 点")
    return text


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print("v3 轮毂控制点:")
    for i, (z, r) in enumerate(HUB_V3, 1):
        print(f"  P{i} z={z:.6f}  r={r:.6f}  D={2 * r * 1000:.2f} mm")
    report = {"hub_points": HUB_V3, "shroud_points": SHROUD_V3,
              "source": "01-scheme/v3", "rows": {}}
    for label, rel in ROWS:
        print(f"building {label}")
        text = build_row(label, V8_AB / rel.replace("/", "\\"))
        work = OUT / f"{label}_13span"
        result = ab.run_batch(work, label, text)
        report["rows"][label] = {
            "ok": result["ok"],
            "returncode": result["returncode"],
            "par": str(result["par"]),
            "abp": str(result["abp"]),
            "geomTurbo": str(result["geom"]),
            "geom_bytes": result["geom"].stat().st_size if result["geom"].is_file() else 0,
            "abm": result["abm"],
        }
        print(f"  ok={result['ok']} geom={report['rows'][label]['geom_bytes']} B")
        if not result["ok"]:
            print("\n".join(result["log"].splitlines()[-30:]))
    (OUT.parent / "v9_build_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("written to", OUT)
    return 0 if all(r["ok"] for r in report["rows"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())