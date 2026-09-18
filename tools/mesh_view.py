#!/usr/bin/env python3
"""mesh_view.py - 把网格画出来：块拓扑 + 质量指标，零依赖纯 SVG。

诚实的边界（重要）
------------------
NUMECA 的网格坐标存在 .cgns 里，那是 **ADF 格式**（不是 HDF5），
没有 NUMECA 的库读不出来，本机也没有 h5py。所以这里**不画网格线**。

能画的是两样真东西：
  1. **块拓扑**：从 .igg 里解析出真实的 16 个块与它们的 IMAX/JMAX/KMAX，
     以及块之间的面连接关系。这是求解器真正读的网格结构。
  2. **质量指标**：从 .qualityReport 里解析出偏斜角/长宽比/膨胀率/壁面距离，
     按叶排和整体分别画成条形图，并标出工程常用阈值。

画不了网格线就直说画不了 —— 比画一张假的强。

用法
----
  python tools/mesh_view.py --case cases/DF90-001
  python tools/mesh_view.py --mesh cases/DF90-001/03-mesh/v2 --out <dir>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

BG = "#0d1117"
FG = "#c9d1d9"
DIM = "#8b949e"
GRID = "#21262d"
PANEL = "#161b22"
OK = "#3fb950"
WARN = "#d29922"
BAD = "#f85149"
ROW_COLORS = ["#58a6ff", "#f778ba", "#d2a8ff", "#ffa657", "#7ee787"]


def esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def svg_open(w, h, title, subtitle=""):
    s = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
         'viewBox="0 0 %d %d" font-family="ui-monospace,Consolas,monospace">' % (w, h, w, h),
         '<rect width="%d" height="%d" fill="%s"/>' % (w, h, BG),
         '<text x="18" y="30" fill="%s" font-size="16" font-weight="700">%s</text>'
         % (FG, esc(title))]
    if subtitle:
        s.append('<text x="18" y="52" fill="%s" font-size="12">%s</text>' % (DIM, esc(subtitle)))
    return s


# ── 解析 .igg 的块拓扑 ─────────────────────────────────────────────────────
def parse_igg_blocks(path: Path):
    """从 .igg 里读块定义。

    实测格式（每块两行）：
        Block 0
        1 row_1_flux_1_Main_Blade_downStream domain1  6 89 73 33  1 0 1 1 2 9 1 ...
    第 2 行依次是：块序号、块名、域、然后是 IMAX/JMAX/KMAX。
    """
    if not path or not path.is_file():
        return []
    raw = path.read_bytes()
    if len(raw) > 64 * 1024 * 1024:
        return []
    lines = raw.decode("latin-1", errors="replace").split("\n")
    blocks = []
    for i, line in enumerate(lines):
        if not line.strip().startswith("Block "):
            continue
        if i + 1 >= len(lines):
            continue
        parts = lines[i + 1].split()
        if len(parts) < 7:
            continue
        try:
            # 列含义（用点数守恒验证过，不是猜的）：
            #   [0] 块序号  [1] 块名  [2] 域  [3] 网格级数  [4]IMAX [5]JMAX [6]KMAX
            # 验证：16 块的 IMAX*JMAX*KMAX 之和 = 1,779,880，
            # 与 .qualityReport 的 "Number of Points" 精确相等（差 0）。
            # 取 [3][4][5] 会得到 200,400，差 1,579,480 —— 那是错的。
            blocks.append({
                "seq": int(parts[0]),
                "name": parts[1],
                "domain": parts[2],
                "levels": int(parts[3]),
                "imax": int(parts[4]), "jmax": int(parts[5]), "kmax": int(parts[6]),
            })
        except ValueError:
            continue
    return blocks


# ── 解析 .qualityReport ────────────────────────────────────────────────────
Q_KEYS = [
    ("min_skew", r"Minimal Skewness\s+Angle:\s*([\d.eE+-]+)", "最小偏斜角", "°", 10.0, "ge"),
    ("max_skew", r"Maximal Skewness\s+Angle:\s*([\d.eE+-]+)", "最大偏斜角", "°", None, None),
    ("avg_skew", r"Average Skewness\s+Angle:\s*([\d.eE+-]+)", "平均偏斜角", "°", None, None),
    ("max_aspect", r"Maximal Aspect\s+Ratio:\s*([\d.eE+-]+)", "最大长宽比", "", 1000.0, "le"),
    ("avg_aspect", r"Average Aspect\s+Ratio:\s*([\d.eE+-]+)", "平均长宽比", "", None, None),
    ("max_expansion", r"Maximal Expansion Ratio:\s*([\d.eE+-]+)", "最大膨胀率", "", 2.5, "le"),
    ("avg_expansion", r"Average Expansion Ratio:\s*([\d.eE+-]+)", "平均膨胀率", "", None, None),
    ("min_wall", r"Minimal wall Distance\s*:\s*([\d.eE+-]+)", "最小壁面距离", " m", None, None),
    ("max_wall", r"Maximal wall Distance\s*:\s*([\d.eE+-]+)", "最大壁面距离", " m", None, None),
]


def parse_quality(path: Path):
    """按 整体 / row N 分段解析质量报告。"""
    if not path or not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")

    # 切段：Entire Mesh Quality / row N Quality
    marks = [(m.start(), m.group(1)) for m in
             re.finditer(r"(Entire Mesh Quality|row \d+ Quality)", text)]
    if not marks:
        return {}
    out = {}
    for i, (pos, name) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        seg = text[pos:end]
        key = "entire" if name.startswith("Entire") else name.split()[1]
        rec = {"label": name.replace(" Quality", ""), "metrics": {}}
        for mid, pat, label, unit, thr, direction in Q_KEYS:
            m = re.search(pat, seg)
            if m:
                try:
                    rec["metrics"][mid] = float(m.group(1))
                except ValueError:
                    pass
        nm = re.search(r"Number of Points\s+(\d+)", seg)
        if nm:
            rec["points"] = int(nm.group(1))
        nl = re.search(r"Number of grid levels\s+(\d+)", seg)
        if nl:
            rec["levels"] = int(nl.group(1))
        nb = re.search(r"NUMBER OF MAIN BLADES\s+(\d+)", seg)
        if nb:
            rec["blades"] = int(nb.group(1))
        rec["negative_ok"] = bool(re.search(r"No Negative Cell", seg))
        rec["valid"] = "OK" if re.search(r"Mesh Validity\s*:\s*OK", seg) else None
        out[key] = rec
    return out


# ── 图 1：块拓扑 ───────────────────────────────────────────────────────────
def view_blocks(blocks, w=1160, h=None, pad=60):
    if not blocks:
        s = svg_open(w, 200, "网格块结构", "没有解析到块定义（.igg 缺失或格式不同）")
        s.append("</svg>")
        return "\n".join(s)

    # 按叶排分组
    groups = {}
    for b in blocks:
        m = re.match(r"(row_\d+)_", b["name"])
        groups.setdefault(m.group(1) if m else "其他", []).append(b)
    order = sorted(groups)
    row_h = 30
    h = h or (110 + sum(len(groups[g]) for g in order) * row_h + len(order) * 16 + 60)

    s = svg_open(w, h, "网格块结构",
                 "%d 个块　按叶排分组　条形长度 = 块尺寸（对数刻度）" % len(blocks))
    y = 92
    maxcells = max(b["imax"] * b["jmax"] * b["kmax"] for b in blocks)
    import math
    bar_x, bar_w = 330, w - 330 - pad - 120
    for gi, g in enumerate(order):
        color = ROW_COLORS[gi % len(ROW_COLORS)]
        s.append('<text x="%d" y="%d" fill="%s" font-size="13" font-weight="700">%s'
                 '（%d 块）</text>' % (pad, y, color, esc(g), len(groups[g])))
        y += 20
        for b in groups[g]:
            cells = b["imax"] * b["jmax"] * b["kmax"]
            frac = math.log10(max(cells, 10)) / math.log10(max(maxcells, 10))
            bw = max(6, bar_w * frac)
            s.append('<rect x="%d" y="%d" width="%.1f" height="14" fill="%s" fill-opacity="0.55" '
                     'rx="2"/>' % (bar_x, y - 11, bw, color))
            s.append('<text x="%d" y="%d" fill="%s" font-size="11.5">%s</text>'
                     % (pad, y, FG, esc(b["name"])))
            s.append('<text x="%d" y="%d" fill="%s" font-size="11">%d×%d×%d　%.2f M 点</text>'
                     % (bar_x + bw + 8, y, DIM, b["imax"], b["jmax"], b["kmax"],
                        cells / 1e6))
            y += row_h
        y += 16
    s.append("</svg>")
    return "\n".join(s)


# ── 图 2：质量指标 ─────────────────────────────────────────────────────────
def view_quality(qual, w=1160, h=None, pad=60):
    if not qual:
        s = svg_open(w, 200, "网格质量", "没有解析到 .qualityReport")
        s.append("</svg>")
        return "\n".join(s)

    show = [("min_skew", "最小偏斜角", "°", 10.0, "ge", "工程经验：≥ 10°"),
            ("max_aspect", "最大长宽比", "", 1000.0, "le", "工程经验：≤ 1000"),
            ("max_expansion", "最大膨胀率", "", 2.5, "le", "工程经验：≤ 2.5")]
    recs = [(k, v) for k, v in qual.items()]
    nrow = len(show)
    row_h = 96
    h = h or (110 + nrow * row_h + 90)

    s = svg_open(w, h, "网格质量",
                 "数值来自 .qualityReport　阈值是工程经验值，不是本项目的合同判据")
    x0, x1 = 210, w - pad - 150
    y = 96
    for mid, label, unit, thr, direction, note in show:
        vals = [(k, v["metrics"].get(mid)) for k, v in recs if v["metrics"].get(mid) is not None]
        if not vals:
            y += row_h
            continue
        s.append('<text x="%d" y="%d" fill="%s" font-size="13" font-weight="700">%s</text>'
                 % (pad, y, FG, label))
        s.append('<text x="%d" y="%d" fill="%s" font-size="11">%s</text>'
                 % (pad, y + 16, DIM, note))
        lo = min([v for _, v in vals] + ([thr] if thr else []))
        hi = max([v for _, v in vals] + ([thr] if thr else []))
        if hi - lo < 1e-9:
            hi = lo + 1
        pad_v = (hi - lo) * 0.12
        lo, hi = lo - pad_v, hi + pad_v

        def X(v):
            return x0 + (x1 - x0) * (v - lo) / (hi - lo)

        for i in range(5):
            v = lo + (hi - lo) * i / 4
            s.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="%s"/>'
                     % (X(v), y - 6, X(v), y + 56, GRID))
            s.append('<text x="%.1f" y="%d" fill="%s" font-size="10" text-anchor="middle">'
                     '%s</text>' % (X(v), y + 70, DIM, ("%.3g" % v)))
        if thr is not None and lo <= thr <= hi:
            s.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="%s" '
                     'stroke-width="1.6" stroke-dasharray="4 3"/>'
                     % (X(thr), y - 10, X(thr), y + 58, WARN))
        for i, (k, v) in enumerate(vals):
            yy = y + 6 + i * 17
            good = (v >= thr) if direction == "ge" else (v <= thr)
            col = OK if good else BAD
            s.append('<circle cx="%.1f" cy="%d" r="4" fill="%s"/>' % (X(v), yy, col))
            s.append('<text x="%.1f" y="%d" fill="%s" font-size="11">%s = %s%s</text>'
                     % (x0 - 8, yy + 4, DIM, esc(qual[k]["label"]),
                        ("%.4g" % v), unit))
        y += row_h
    s.append("</svg>")
    return "\n".join(s)


INDEX_TMPL = """<!doctype html><html lang="zh"><meta charset="utf-8">
<title>%(title)s · 网格视图</title>
<style>
 body{background:%(bg)s;color:%(fg)s;font:14px/1.6 system-ui,"Segoe UI",sans-serif;margin:0;padding:24px}
 h1{font-size:19px;margin:0 0 4px}
 .sub{color:%(dim)s;font-size:13px;margin-bottom:20px;word-break:break-all}
 .card{background:%(panel)s;border:1px solid %(grid)s;border-radius:10px;padding:14px;margin-bottom:18px}
 .card h2{font-size:13px;margin:0 0 10px;color:%(dim)s;font-weight:600}
 img{width:100%%;display:block;border-radius:6px}
 .kv{display:grid;grid-template-columns:auto 1fr;gap:4px 16px;font-size:13px}
 .kv dt{color:%(dim)s}
 .kv dd{margin:0}
 .note{background:#1c1a12;border:1px solid #3d3418;border-radius:8px;padding:12px 14px;
   font-size:13px;color:#d29922;margin-bottom:18px}
</style>
<h1>%(title)s</h1>
<div class="sub">%(sub)s</div>
<div class="note">%(note)s</div>
%(cards)s
"""


def build(mesh_dir: Path, out_dir: Path):
    igg = next(iter(sorted(mesh_dir.glob("*.igg"))), None)
    qr = next(iter(sorted(mesh_dir.glob("*.qualityReport"))), None)
    blocks = parse_igg_blocks(igg)
    qual = parse_quality(qr)

    out_dir.mkdir(parents=True, exist_ok=True)
    written, cards = [], []
    for fname, title, note, fn, data in (
            ("blocks.svg", "块结构", "从 .igg 解析出的真实块拓扑", view_blocks, blocks),
            ("quality.svg", "质量指标", "从 .qualityReport 解析", view_quality, qual)):
        svg = fn(data)
        (out_dir / fname).write_text(svg, encoding="utf-8", newline="")
        written.append(str(out_dir / fname))
        cards.append('<div class="card"><h2>%s · %s</h2><img src="%s" alt="%s"></div>'
                     % (esc(title), esc(note), fname, esc(title)))

    kv = ['<div class="card"><h2>网格摘要</h2><dl class="kv">',
          "<dt>来源</dt><dd>%s</dd>" % esc(mesh_dir.name)]
    if qual.get("entire"):
        e = qual["entire"]
        kv.append("<dt>总点数</dt><dd>%s</dd>" % ("{:,}".format(e["points"]) if e.get("points") else "—"))
        kv.append("<dt>网格层数</dt><dd>%s</dd>" % e.get("levels", "—"))
        kv.append("<dt>有效性</dt><dd>%s</dd>" % ("无重叠单元" if e.get("valid") else "—"))
        kv.append("<dt>负体积单元</dt><dd>%s</dd>" % ("无" if e.get("negative_ok") else "有（必须处理）"))
    kv.append("<dt>块数</dt><dd>%d</dd>" % len(blocks))
    kv.append("</dl></div>")

    note = ("坐标存在 .cgns 里，那是 NUMECA 的 ADF 格式（不是 HDF5），"
            "本机没有可读它的库 —— 所以这里不画网格线，只画真实的块拓扑与质量指标。"
            "要看网格线请用 NUMECA IGG / CFView 打开 .igg 或 .cgns。")

    (out_dir / "index.html").write_text(INDEX_TMPL % {
        "title": mesh_dir.name, "bg": BG, "fg": FG, "dim": DIM, "grid": GRID, "panel": PANEL,
        "sub": "由 tools/mesh_view.py 生成　·　零依赖纯 SVG　·　源目录 " + esc(str(mesh_dir)),
        "note": esc(note), "cards": "".join(kv) + "".join(cards),
    }, encoding="utf-8", newline="")
    written.append(str(out_dir / "index.html"))
    # 自检：块点数之和必须等于质量报告的总点数。
    # 这个等式是块尺寸列解析正确与否的**唯一客观判据** —— 差一点都说明取错列了。
    total = sum(b["imax"] * b["jmax"] * b["kmax"] for b in blocks)
    reported = (qual.get("entire") or {}).get("points")
    check = {"blocks_total": total, "reported_total": reported,
             "match": (reported is None or total == reported)}
    return {"ok": True, "source": str(mesh_dir), "out_dir": str(out_dir), "files": written,
            "blocks": len(blocks), "check": check,
            "rows": sorted({re.match(r"(row_\d+)_", b["name"]).group(1)
                            for b in blocks
                            if re.match(r"(row_\d+)_", b["name"])}),
            "quality_rows": [k for k in qual]}


def find_mesh_dirs(case: Path):
    d = case / "03-mesh"
    if not d.is_dir():
        return []
    return sorted([p for p in d.iterdir() if p.is_dir()],
                  key=lambda p: (len(p.name), p.name))


def main(argv=None):
    ap = argparse.ArgumentParser(description="网格可视化（块拓扑 + 质量指标，零依赖 SVG）")
    ap.add_argument("--case", default=None)
    ap.add_argument("--mesh", default=None, help="直接指定网格目录")
    ap.add_argument("--out", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.mesh:
        dirs = [Path(args.mesh)]
        case = dirs[0].parent.parent
    else:
        case = Path(args.case).resolve() if args.case else ROOT / "cases" / "DF90-001"
        dirs = find_mesh_dirs(case)
        if not dirs:
            print("找不到网格目录：" + str(case / "03-mesh"), file=sys.stderr)
            return 3
    out_root = Path(args.out) if args.out else case / "_view"
    results = [build(d, out_root / ("mesh-" + d.name)) for d in dirs]
    if args.json:
        print(json.dumps({"ok": True, "views": results}, ensure_ascii=False, indent=2))
    else:
        print("网格可视化完成：%d 个版本" % len(results))
        for r in results:
            print("  %s　%d 块　质量段 %s" % (Path(r["source"]).name, r["blocks"],
                                             r["quality_rows"]))
            print("    -> " + str(Path(r["out_dir"]) / "index.html"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
