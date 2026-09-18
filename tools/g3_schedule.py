#!/usr/bin/env python3
"""g3_schedule.py - 把 01-scheme 的两张表转成 cascade-forge 要的 SectionSchedule JSON。

为什么要有这个
--------------
cascade-forge-geometry-handoff 这个 skill 里写的是：

    build-blade --schedule <叶片几何参数表.csv>

**但那是错的。** CLI 实际调的是 SectionSchedule.model_validate_json()，
要的是 JSON，字段是 span_fraction / radius_m / chord_m / geometry_id / stagger_deg。
直接喂 CSV 会报 "Invalid JSON: expected value at line 1 column 1"。

实测记录（2026-09-19）：
    ValidationError: 1 validation error for SectionSchedule
      Invalid JSON: expected value at line 1 column 1

这就是 G3 那段"端到端尚未验证"的真正原因 —— 契约对不上，不是工具坏了。

这个脚本负责翻译。它做三件事：
  1. 从流道尺寸表插值出该叶排位置的 hub / shroud 半径
  2. 把叶片几何参数表的单值参数**沿展向展开**成 N 个截面
     （参数表只有一行一个叶排，而 SectionSchedule 至少要 2 个截面）
  3. 按 cascade-forge 的 schema 写出 JSON，并显式声明哪些是推算的

**展开方式是明确的工程假设，不是从数据里读出来的** —— 所以同时写一份
.notes.md，让接手的人知道哪些数是原生的、哪些是这里补的。

用法
----
  python tools/g3_schedule.py --case cases/DF90-001 --row R1
  python tools/g3_schedule.py --case cases/DF90-001 --row S1 --sections 13
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def cosine_spans(n):
    """余弦展向律：叶根叶尖加密、中间稀疏。

    选它是因为案例里 v8 几何用的就是这个分布（与 v8_build_manifest.json 实测吻合）。
    但要说清楚：这是一个**工程选择**，不是从参数表读出来的。
    """
    if n < 2:
        return [0.0]
    return [0.5 * (1 - math.cos(math.pi * i / (n - 1))) for i in range(n)]


def read_csv(path: Path):
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return [{k.strip(): (v or "").strip() for k, v in r.items() if k}
                for r in csv.DictReader(fh)]


def fnum(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def find_scheme_dir(case: Path, version=None):
    d = case / "01-scheme"
    if not d.is_dir():
        return None
    if version:
        return d / version
    vs = sorted([p for p in d.iterdir() if p.is_dir()], key=lambda p: p.name)
    return vs[-1] if vs else None


def build(case: Path, row_name: str, n_sections: int, version=None):
    scheme = find_scheme_dir(case, version)
    if scheme is None:
        raise SystemExit("找不到 01-scheme 目录：" + str(case))

    blades = read_csv(scheme / "叶片几何参数表.csv")
    annulus = read_csv(scheme / "流道尺寸表.csv")
    if not blades:
        raise SystemExit("读不到叶片几何参数表.csv")
    if not annulus:
        raise SystemExit("读不到流道尺寸表.csv")

    row = next((r for r in blades if r.get("叶排") == row_name), None)
    if row is None:
        raise SystemExit("参数表里没有叶排 %s；有的是 %s"
                         % (row_name, [r.get("叶排") for r in blades]))

    blades_n = int(fnum(row.get("叶片数"), 0))
    chord = fnum(row.get("弦长(m)"))
    stagger_deg = fnum(row.get("进口金属角(deg,相对轴向)"))
    axial_z = fnum(row.get("轴向坐标(m)"))
    if not blades_n or chord is None or stagger_deg is None:
        raise SystemExit("参数表这一行缺关键列：叶片数/弦长/进口金属角")

    pts = []
    for a in annulus:
        z = fnum(a.get("轴向坐标(m)"))
        h = fnum(a.get("轮毂半径(m)"))
        s = fnum(a.get("机匣半径(m)"))
        if z is not None and h is not None and s is not None:
            pts.append((z, h, s))
    if len(pts) < 2:
        raise SystemExit("流道尺寸表至少要有 2 个站位才能插值")
    pts.sort()

    def lerp(zq):
        if zq <= pts[0][0]:
            return pts[0][1], pts[0][2]
        if zq >= pts[-1][0]:
            return pts[-1][1], pts[-1][2]
        for i in range(len(pts) - 1):
            z0, h0, s0 = pts[i]
            z1, h1, s1 = pts[i + 1]
            if z0 <= zq <= z1:
                t = (zq - z0) / (z1 - z0) if z1 > z0 else 0.0
                return h0 + (h1 - h0) * t, s0 + (s1 - s0) * t
        return pts[-1][1], pts[-1][2]

    hub_r, shroud_r = lerp(axial_z if axial_z is not None else pts[0][0])

    sections = []
    for sp in cosine_spans(n_sections):
        r = hub_r + (shroud_r - hub_r) * sp
        sections.append({
            "span_fraction": round(sp, 10),
            "radius_m": round(r, 10),
            "chord_m": round(chord, 10),
            "geometry_id": "",
            "stagger_deg": round(stagger_deg, 6),
            "axial_offset_m": 0.0,
            "tangential_offset_m": 0.0,
            "lean_m": 0.0,
            "sweep_m": 0.0,
        })

    schedule = {
        "name": "%s-%s" % (case.name, row_name),
        "blade_count": blades_n,
        "rotation_direction": "ccw",
        "sections": sections,
        "output_section_count": n_sections,
        "units": "m",
    }

    notes = [
        "# %s %s 的 SectionSchedule 来源说明" % (case.name, row_name),
        "",
        "由 tools/g3_schedule.py 从 01-scheme 的两张表生成。**哪些是原生、哪些是推算，必须分清：**",
        "",
        "| 字段 | 来源 |",
        "|---|---|",
        "| blade_count = %d | 原生，来自参数表「叶片数」 |" % blades_n,
        "| chord_m = %.6f | 原生，来自参数表「弦长」；**沿展向取常数** |" % chord,
        "| stagger_deg = %.3f | 参数表给的是**进口金属角**，这里当作安装角用 —— "
        "两者不是一回事（金属角是中弧线切线角，安装角是前后缘连线角）。"
        "这是本转换的**已知近似**，不是等价。 |" % stagger_deg,
        "| radius_m | 推算：由流道尺寸表在 z=%.4f 处插值得 hub=%.6f / shroud=%.6f，"
        "再按余弦展向律分配 |" % (axial_z or 0.0, hub_r, shroud_r),
        "| span_fraction | 推算：余弦展向律，%d 个截面 |" % n_sections,
        "| geometry_id | **空占位**。真实值由 cascade-forge 的 dataset 决定，"
        "需在 build-blade 之后回填 |",
        "| axial_offset_m / lean_m / sweep_m | 参数表里没有，取 0 |",
        "",
        "**为什么截面数不是 1：** 参数表一个叶排只有一行，而 SectionSchedule 要求 >=2 个截面。",
        "沿展向展开是必须的一步，展开律是一个工程选择，不是从数据里读出来的。",
    ]

    return {"schedule": schedule, "notes": "\n".join(notes) + "\n",
            "scheme_dir": str(scheme), "row": row_name,
            "hub_r": hub_r, "shroud_r": shroud_r, "sections": n_sections}


def main(argv=None):
    ap = argparse.ArgumentParser(description="参数表 -> cascade-forge SectionSchedule JSON")
    ap.add_argument("--case", required=True)
    ap.add_argument("--row", required=True, help="叶排名，如 R1 / S1")
    ap.add_argument("--sections", type=int, default=13)
    ap.add_argument("--version", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    case = Path(args.case).resolve()
    r = build(case, args.row, args.sections, args.version)
    out = Path(args.out) if args.out else case / "_automation" / "g3"
    out.mkdir(parents=True, exist_ok=True)
    jp = out / ("schedule-%s.json" % args.row)
    np_ = out / ("schedule-%s.notes.md" % args.row)
    jp.write_text(json.dumps(r["schedule"], ensure_ascii=False, indent=2) + "\n",
                  encoding="utf-8", newline="")
    np_.write_text(r["notes"], encoding="utf-8", newline="")

    if args.json:
        print(json.dumps({"ok": True, "schedule": str(jp), "notes": str(np_),
                          "sections": r["sections"],
                          "blade_count": r["schedule"]["blade_count"],
                          "hub_r": r["hub_r"], "shroud_r": r["shroud_r"]},
                         ensure_ascii=False, indent=2))
    else:
        print("已生成 SectionSchedule：%s" % jp)
        print("  叶排 %s　%d 叶　%d 截面　hub %.4f / shroud %.4f"
              % (args.row, r["schedule"]["blade_count"], r["sections"],
                 r["hub_r"], r["shroud_r"]))
        print("  来源说明：%s" % np_)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
