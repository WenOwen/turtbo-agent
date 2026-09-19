#!/usr/bin/env python3
"""v11 / 生成 G3-9 要的机器可读溯源记录（<stem>.geomTurbo.manifest.json）。

字段集对照 cascade-forge 的真实产物：
  D:/Project/Research/cascade-forge/UDF/artifacts/NASA120859-R1/NASA120859-R1.geomTurbo.manifest.json
含 top-level: schema_version / blade_id / geomturbo_path / geomturbo_sha256 / schedule / warnings；
schedule 里: name / blade_count / rotation_direction / sections[]。

**如实记录**：本版几何的流道来自 01-scheme/v3，而叶片截面沿用 v8。
两件事都写进 schedule.source 与 warnings，不掩盖。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASE = HERE.parents[1]
ROOT = CASE.parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import geom_view  # noqa: E402

AB = CASE / "02-geometry" / "v11" / "autoblade"
ROWS = (("R1", "R1_13span/R1.geomTurbo"), ("R2", "R2_13span/R2.geomTurbo"))


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build(row: str, rel: str) -> dict:
    geom = AB / rel.replace("/", "\\")
    g = geom_view.parse_geomturbo(geom)
    r = (g.get("rows") or [{}])[0]
    secs = r.get("sections") or []
    out_sections = []
    for s in secs:
        m = geom_view.section_metrics(s)
        out_sections.append({
            "span_fraction": None,
            "radius_m": round(m["rmid"], 9),
            "chord_m": round(m["chord_m"], 9),
            "stagger_deg": round(m["stagger_deg"], 4),
            "index": s.get("index"),
        })
    # 展向分数用半径线性归一（叶根->叶尖），与 G3-3 的口径一致
    rs = [s["radius_m"] for s in out_sections]
    lo, hi = min(rs), max(rs)
    for s in out_sections:
        s["span_fraction"] = round((s["radius_m"] - lo) / (hi - lo), 9) if hi > lo else 0.0
    blob = {
        "schema_version": "1.0.0",
        "blade_id": "v11-" + row,
        "geomturbo_path": str(geom),
        "geomturbo_sha256": sha256_of(geom),
        "schedule": {
            "name": "DF90-001-" + row,
            "blade_count": r.get("periodicity") or r.get("blades"),
            "rotation_direction": "ccw",
            "sections": out_sections,
            "source": {
                "flowpath": "01-scheme/v3/流道尺寸表.csv（轮毂 6 控制点，机匣锁 0.300）",
                "blade_sections": "02-geometry/v8/autoblade/" + row + "_13span/" + row + ".par",
            },
        },
        "warnings": [
            "叶片截面沿用 v8，**不是**由 01-scheme/v3/叶片几何参数表.csv 导出。"
            "v3 的金属角每排单值（R1 beta1 -68.276 / beta2 -60.531），",
            "而几何的 CAMBER_BETA 逐截面变化（BETA1 -56..-59、BETA2 -28..-34）——",
            "单值铺到 13 个截面会抹平扭转，且两个工具的角度约定未查证，故未改。",
            "弦长同理：v3 表给 0.090，几何实测见 sections[].chord_m。",
        ],
    }
    (geom.with_suffix(".geomTurbo.manifest.json")).write_text(
        json.dumps(blob, ensure_ascii=False, indent=1), encoding="utf-8")
    print("  %s: blade_count=%s sections=%d chord 中位=%.6f sha256=%s"
          % (row, blob["schedule"]["blade_count"], len(out_sections),
             sorted(s["chord_m"] for s in out_sections)[len(out_sections) // 2],
             blob["geomturbo_sha256"][:16]))
    return blob


def main() -> int:
    for row, rel in ROWS:
        build(row, rel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())