#!/usr/bin/env python3
"""cfd_view.py - 把 CFD 结果画出来：性能曲线 + 扫点收敛图，零依赖纯 SVG。

这是"看着它在算"的最后一环：前两个工具画的是"要算什么"（几何、网格），
这个画的是"算出来什么"。

画什么
------
  性能曲线 map.svg     每个转速一条线：出口压力 vs 效率 / 功率 / 扭矩 / 推力
  扫点状态 sweep.svg   每个工况点一个格子，按 state 上色，看边界在哪
  收敛散点 conv.svg    迭代步数 vs 质量不平衡，看哪些点算得干净

数据来源
--------
  sweep_summary.csv（由 tools/turboflow_adapter.py 或求解编排生成）
  字段：case,rpm,pressure_pa_abs,state,iteration,mf_in,mf_out,mass_error_pct,
        pressure_ratio,efficiency,torque_nm,shaft_power_w,reason

**只画 accepted 的点连线**；stopped/rejected 的点单独标出来。
把没收敛的点和收敛的点连成一条光滑曲线，是最容易骗人的做法。

用法
----
  python tools/cfd_view.py --case cases/DF90-001
  python tools/cfd_view.py --summary <sweep_summary.csv> --out <dir>
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

BG = "#0d1117"
FG = "#c9d1d9"
DIM = "#8b949e"
GRID = "#21262d"
PANEL = "#161b22"
ACC = "#58a6ff"
OK = "#3fb950"
WARN = "#d29922"
BAD = "#f85149"
SERIES = ["#58a6ff", "#f778ba", "#7ee787", "#ffa657", "#d2a8ff"]

STATE_COLOR = {"accepted": OK, "stopped": WARN, "rejected": BAD}


def esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def num(v):
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def svg_open(w, h, title, subtitle=""):
    s = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
         'viewBox="0 0 %d %d" font-family="ui-monospace,Consolas,monospace">' % (w, h, w, h),
         '<rect width="%d" height="%d" fill="%s"/>' % (w, h, BG),
         '<text x="18" y="30" fill="%s" font-size="16" font-weight="700">%s</text>'
         % (FG, esc(title))]
    if subtitle:
        s.append('<text x="18" y="52" fill="%s" font-size="12">%s</text>' % (DIM, esc(subtitle)))
    return s


def load_summary(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        rows = []
        for r in csv.DictReader(fh):
            rec = {k.strip(): (v or "").strip() for k, v in r.items() if k}
            rec["_rpm"] = num(rec.get("rpm"))
            rec["_p"] = num(rec.get("pressure_pa_abs"))
            rec["_eta"] = num(rec.get("efficiency"))
            rec["_pw"] = num(rec.get("shaft_power_w"))
            rec["_tq"] = num(rec.get("torque_nm"))
            rec["_it"] = num(rec.get("iteration"))
            rec["_me"] = num(rec.get("mass_error_pct"))
            rec["_pr"] = num(rec.get("pressure_ratio"))
            rec["_mf"] = num(rec.get("mf_in"))
            rows.append(rec)
    return rows


def panel(s, x, y, w, h, title, note=""):
    s.append('<rect x="%d" y="%d" width="%d" height="%d" fill="%s" stroke="%s" rx="8"/>'
             % (x, y, w, h, PANEL, GRID))
    s.append('<text x="%d" y="%d" fill="%s" font-size="13" font-weight="700">%s</text>'
             % (x + 14, y + 22, FG, esc(title)))
    if note:
        s.append('<text x="%d" y="%d" fill="%s" font-size="11">%s</text>'
                 % (x + 14, y + 38, DIM, esc(note)))


def plot(s, rows, x0, y0, w, h, ykey, ylabel, unit, color_of, fmt="%.4g"):
    """画一张 出口压力(x) vs 指标(y) 的图。只连 accepted 点。"""
    pts = [r for r in rows if r["_p"] is not None and r[ykey] is not None]
    if not pts:
        s.append('<text x="%d" y="%d" fill="%s" font-size="12">无数据</text>'
                 % (x0 + 20, y0 + h / 2, DIM))
        return
    # 轴范围按**已验收点**算。用全部行会把未验收的离群点算进来 ——
    # 实测轴功率轴被拉到 -4462 W（已验收点最低只有 275.9 W），有用区间被压成一条线。
    acc_pts = [r for r in pts if r.get("state") == "accepted"]
    span = acc_pts if len(acc_pts) >= 2 else pts
    xs = [r["_p"] for r in span]
    ys = [r[ykey] for r in span]
    xlo, xhi = min(xs), max(xs)
    ylo, yhi = min(ys), max(ys)
    if xhi - xlo < 1e-9:
        xhi = xlo + 1
    if yhi - ylo < 1e-9:
        yhi = ylo + 1
    xpad, ypad = (xhi - xlo) * 0.06, (yhi - ylo) * 0.12
    xlo, xhi = xlo - xpad, xhi + xpad
    ylo, yhi = ylo - ypad, yhi + ypad

    def X(v):
        return x0 + w * (v - xlo) / (xhi - xlo)

    def Y(v):
        return y0 + h - h * (v - ylo) / (yhi - ylo)

    for i in range(5):
        v = ylo + (yhi - ylo) * i / 4
        s.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s"/>'
                 % (x0, Y(v), x0 + w, Y(v), GRID))
        s.append('<text x="%.1f" y="%.1f" fill="%s" font-size="10" text-anchor="end">%s</text>'
                 % (x0 - 6, Y(v) + 3, DIM, fmt % v))
    for i in range(5):
        v = xlo + (xhi - xlo) * i / 4
        s.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s"/>'
                 % (X(v), y0, X(v), y0 + h, GRID))
        s.append('<text x="%.1f" y="%.1f" fill="%s" font-size="10" text-anchor="middle">%.0f</text>'
                 % (X(v), y0 + h + 15, DIM, v))
    s.append('<text x="%.1f" y="%.1f" fill="%s" font-size="11" text-anchor="middle">%s</text>'
             % (x0 + w / 2, y0 + h + 32, DIM, "出口静压 (Pa)"))
    # 轴标题**竖排**画在最左边 —— 横排会和 text-anchor=end 的刻度标签叠在一起
    # （实测重叠 43 px，轴功率/扭矩/效率三张都中招）。
    s.append('<text x="%.1f" y="%.1f" fill="%s" font-size="11" text-anchor="middle" '
             'transform="rotate(-90 %.1f %.1f)">%s</text>'
             % (x0 - 66, y0 + h / 2, DIM, x0 - 66, y0 + h / 2,
                ylabel + (" " + unit if unit else "")))

    # 每个转速一条线（只连 accepted）
    rpms = sorted({r["_rpm"] for r in pts if r["_rpm"] is not None})
    for ri, rpm in enumerate(rpms):
        color = color_of(rpm, ri)
        acc = sorted([r for r in pts if r["_rpm"] == rpm and r["state"] == "accepted"],
                     key=lambda r: r["_p"])
        if len(acc) >= 2:
            s.append('<polyline fill="none" stroke="%s" stroke-width="2" points="%s"/>'
                     % (color, " ".join("%.1f,%.1f" % (X(r["_p"]), Y(r[ykey])) for r in acc)))
        for r in pts:
            if r["_rpm"] != rpm:
                continue
            c = STATE_COLOR.get(r["state"], DIM)
            if r["state"] == "accepted":
                s.append('<circle cx="%.1f" cy="%.1f" r="2.8" fill="%s"/>'
                         % (X(r["_p"]), Y(r[ykey]), color))
            else:
                # 未验收点画成空心叉，绝不参与连线
                s.append('<path d="M %.1f %.1f l 5 5 m -5 0 l 5 -5" stroke="%s" '
                         'stroke-width="1.6" fill="none"/>'
                         % (X(r["_p"]) - 2.5, Y(r[ykey]) - 2.5, c))


def view_map(rows, w=1160, h=None):
    metrics = [("_eta", "等熵效率", ""), ("_pw", "轴功率", "W"),
               ("_tq", "扭矩", "N·m"), ("_pr", "总压比", "")]
    pw, ph = (w - 150) // 2, 250
    h = h or (110 + 2 * (ph + 26) + 70)
    s = svg_open(w, h, "CFD 性能曲线",
                 "横轴 = 出口静压 (Pa)　实线只连已验收的点　× = 未验收（不参与连线）")
    rpms = sorted({r["_rpm"] for r in rows if r["_rpm"] is not None})

    def color_of(rpm, i):
        return SERIES[i % len(SERIES)]

    for i, (key, label, unit) in enumerate(metrics):
        cx = 108 + (i % 2) * (pw + 30)
        cy = 92 + (i // 2) * (ph + 26)
        note = unit and ("单位 " + unit) or ""
        if key == "_eta":
            # 效率图被那几个负值点压扁了 —— 说明清楚，别让人以为是画错了
            note = "注意左下方凹陷：就是那几个效率为负的已验收点"
        panel(s, cx - 96, cy - 62, pw + 112, ph + 74, label, note)
        plot(s, rows, cx, cy, pw - 20, ph - 40, key, label, unit, color_of)
    # 图例
    lx, ly = w - 210, 78
    for i, rpm in enumerate(rpms):
        s.append('<rect x="%d" y="%d" width="12" height="3" fill="%s"/>'
                 % (lx, ly + i * 18, SERIES[i % len(SERIES)]))
        s.append('<text x="%d" y="%d" fill="%s" font-size="11">%.0f rpm</text>'
                 % (lx + 18, ly + 4 + i * 18, DIM, rpm))
    s.append("</svg>")
    return "\n".join(s)


def view_sweep(rows, w=1160, h=None):
    """扫点状态矩阵：每行一个转速，每列一个出口压力，格子按 state 上色。"""
    rpms = sorted({r["_rpm"] for r in rows if r["_rpm"] is not None})
    if not rpms:
        return "\n".join(svg_open(w, 200, "扫点状态", "无数据") + ["</svg>"])
    cell_w, cell_h = 26, 34
    h = h or (120 + len(rpms) * (cell_h + 10) + 90)
    s = svg_open(w, h, "扫点状态",
                 "每格一个工况　按出口压力排序　颜色 = 验收状态")

    y = 100
    for ri, rpm in enumerate(rpms):
        sub = sorted([r for r in rows if r["_rpm"] == rpm], key=lambda r: r["_p"] or 0)
        s.append('<text x="20" y="%d" fill="%s" font-size="12" font-weight="700">%.0f rpm</text>'
                 % (y + 20, FG, rpm))
        for i, r in enumerate(sub):
            cx = 130 + i * (cell_w + 2)
            c = STATE_COLOR.get(r["state"], DIM)
            s.append('<rect x="%d" y="%d" width="%d" height="%d" fill="%s" fill-opacity="0.75" '
                     'rx="3"><title>%s\n%s Pa\n%s%s</title></rect>'
                     % (cx, y, cell_w, cell_h, c, esc(r.get("case", "")),
                        ("%.0f" % r["_p"]) if r["_p"] else "?",
                        esc(r["state"]), ("　" + esc(r.get("reason", ""))) if r.get("reason") else ""))
        s.append('<text x="%d" y="%d" fill="%s" font-size="10">%.0f → %.0f Pa</text>'
                 % (130, y + cell_h + 22, DIM, sub[0]["_p"] or 0, sub[-1]["_p"] or 0))
        y += cell_h + 40

    # 图例
    ly = y + 6
    for name, c in (("accepted 已验收", OK), ("stopped 停止", WARN), ("rejected 拒绝", BAD)):
        s.append('<rect x="130" y="%d" width="14" height="14" fill="%s" fill-opacity="0.75" rx="3"/>'
                 % (ly, c))
        s.append('<text x="152" y="%d" fill="%s" font-size="11.5">%s</text>' % (ly + 12, DIM, name))
        ly += 20
    s.append("</svg>")
    return "\n".join(s)


def view_convergence(rows, w=1160, h=None):
    """迭代步数 vs 质量不平衡：看哪些点算得干净。"""
    pts = [r for r in rows if r["_it"] is not None and r["_me"] is not None]
    h = h or 380
    s = svg_open(w, h, "收敛情况",
                 "横轴 = 迭代步数　纵轴 = 末段质量不平衡 (%)　越靠下越干净")
    if not pts:
        s.append("</svg>")
        return "\n".join(s)
    x0, y0, pw, ph = 90, 96, w - 180, h - 190
    # 迭代步数分布极不均匀（489..7159，绝大多数落在 570-600）——
    # 线性横轴会把所有点挤在左边一条竖线上。两个轴都取对数才看得清。
    xs = [max(r["_it"], 1.0) for r in pts]
    ys = [max(r["_me"], 1e-7) for r in pts]
    xlo, xhi = min(xs) * 0.9, max(xs) * 1.1
    if xhi / xlo < 1.05:
        xhi = xlo * 1.05
    ylo, yhi = min(ys) * 0.5, max(ys) * 3.0

    def X(v):
        v = max(v, 1.0)
        return x0 + pw * (math.log10(v) - math.log10(xlo)) / (math.log10(xhi) - math.log10(xlo))

    def Y(v):
        return y0 + ph - ph * (math.log10(v) - math.log10(ylo)) / (math.log10(yhi) - math.log10(ylo))

    for i in range(5):
        v = math.log10(ylo) + (math.log10(yhi) - math.log10(ylo)) * i / 4
        s.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="%s"/>'
                 % (x0, Y(10 ** v), x0 + pw, Y(10 ** v), GRID))
        s.append('<text x="%d" y="%.1f" fill="%s" font-size="10" text-anchor="end">%.3g</text>'
                 % (x0 - 6, Y(10 ** v) + 3, DIM, 10 ** v))
    for i in range(6):
        v = xlo + (xhi - xlo) * i / 5
        s.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="%s"/>'
                 % (X(v), y0, X(v), y0 + ph, GRID))
        s.append('<text x="%.1f" y="%d" fill="%s" font-size="10" text-anchor="middle">%.0f</text>'
                 % (X(v), y0 + ph + 15, DIM, v))
    s.append('<text x="%.1f" y="%d" fill="%s" font-size="11" text-anchor="middle">'
             '迭代步数（对数轴）</text>' % (x0 + pw / 2, y0 + ph + 32, DIM))
    # 1% 线（C-002 的阈值，从合同机读块来；这里写死一个参考线并注明）
    if ylo <= 1.0 <= yhi:
        s.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="%s" stroke-width="1.4" '
                 'stroke-dasharray="4 3"/>' % (x0, Y(1.0), x0 + pw, Y(1.0), WARN))
        s.append('<text x="%d" y="%.1f" fill="%s" font-size="10.5">1%% 参考线（C-002 阈值）</text>'
                 % (x0 + 6, Y(1.0) - 5, WARN))
    for r in pts:
        c = STATE_COLOR.get(r["state"], DIM)
        s.append('<circle cx="%.1f" cy="%.1f" r="3.4" fill="%s" fill-opacity="0.85">'
                 '<title>%s\n%d 步\n不平衡 %s%%</title></circle>'
                 % (X(r["_it"]), Y(max(r["_me"], 1e-6)), c, esc(r.get("case", "")),
                    int(r["_it"]), ("%.4g" % r["_me"])))
    s.append("</svg>")
    return "\n".join(s)


INDEX_TMPL = """<!doctype html><html lang="zh"><meta charset="utf-8">
<title>%(title)s · CFD 结果</title>
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
</style>
<h1>%(title)s</h1>
<div class="sub">%(sub)s</div>
%(cards)s
"""


def build(summary: Path, out_dir: Path):
    rows = load_summary(summary)
    out_dir.mkdir(parents=True, exist_ok=True)
    written, cards = [], []
    for fname, title, note, fn in (
            ("map.svg", "性能曲线", "只连已验收的点，未验收点画 ×", view_map),
            ("sweep.svg", "扫点状态", "每格一个工况，颜色 = 验收状态", view_sweep),
            ("convergence.svg", "收敛情况", "迭代步数 vs 质量不平衡", view_convergence)):
        svg = fn(rows)
        (out_dir / fname).write_text(svg, encoding="utf-8", newline="")
        written.append(str(out_dir / fname))
        cards.append('<div class="card"><h2>%s · %s</h2><img src="%s" alt="%s"></div>'
                     % (esc(title), esc(note), fname, esc(title)))

    states = {}
    for r in rows:
        states[r.get("state", "?")] = states.get(r.get("state", "?"), 0) + 1

    # 物理上讲不通的已验收点：质量守恒过了，但效率是负的。
    # 这类点最危险 —— 状态是 accepted，看状态列会以为没问题。
    # 单独揪出来，因为"只查一个判据"正是这个项目反复踩的坑。
    odd = [r for r in rows
           if r.get("state") == "accepted" and r["_eta"] is not None and r["_eta"] < 0]
    rpms = sorted({r["_rpm"] for r in rows if r["_rpm"] is not None})
    kv = ['<div class="card"><h2>工况摘要</h2><dl class="kv">',
          "<dt>来源</dt><dd>%s</dd>" % esc(summary.name),
          "<dt>工况总数</dt><dd>%d</dd>" % len(rows),
          "<dt>转速</dt><dd>%s</dd>" % ("、".join("%.0f" % r for r in rpms) + " rpm"),
          "<dt>验收状态</dt><dd>%s</dd>" % "　".join(
              "%s %d" % (k, v) for k, v in sorted(states.items()))]
    acc = [r for r in rows if r.get("state") == "accepted" and r["_eta"] is not None]
    if acc:
        best = max(acc, key=lambda r: r["_eta"])
        kv.append("<dt>最高效率</dt><dd>%.4f　（%s）</dd>"
                  % (best["_eta"], esc(best.get("case", ""))))
    pw = [r for r in rows if r.get("state") == "accepted" and r["_pw"] is not None]
    if pw:
        hi = max(pw, key=lambda r: r["_pw"])
        kv.append("<dt>最大轴功率</dt><dd>%.2f kW　（%s）</dd>"
                  % (hi["_pw"] / 1000.0, esc(hi.get("case", ""))))
    if odd:
        kv.append("<dt>⚠ 物理异常</dt><dd>%d 个已验收点的效率为负：%s"
                  "　—— 质量守恒过了，但能量侧讲不通，需复查</dd>"
                  % (len(odd), "、".join(esc(r.get("case", "")) for r in odd[:5])))
    kv.append("</dl></div>")

    (out_dir / "index.html").write_text(INDEX_TMPL % {
        "title": summary.stem, "bg": BG, "fg": FG, "dim": DIM, "grid": GRID, "panel": PANEL,
        "sub": "由 tools/cfd_view.py 生成　·　零依赖纯 SVG　·　源文件 " + esc(str(summary)),
        "cards": "".join(kv) + "".join(cards),
    }, encoding="utf-8", newline="")
    written.append(str(out_dir / "index.html"))
    return {"ok": True, "source": str(summary), "out_dir": str(out_dir), "files": written,
            "rows": len(rows), "states": states, "rpms": rpms,
            "physically_odd": [r.get("case") for r in odd]}


def find_summaries(case: Path):
    hits = []
    for sub in ("04-solve", "_replay", "05-post"):
        d = case / sub
        if d.is_dir():
            hits += sorted(d.glob("**/sweep_summary.csv"))
    return hits


def main(argv=None):
    ap = argparse.ArgumentParser(description="CFD 结果可视化（性能曲线 + 扫点状态，零依赖 SVG）")
    ap.add_argument("--case", default=None)
    ap.add_argument("--summary", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.summary:
        targets = [Path(args.summary)]
        case = targets[0].parent
    else:
        case = Path(args.case).resolve() if args.case else ROOT / "cases" / "DF90-001"
        targets = find_summaries(case)
        if not targets:
            print("找不到 sweep_summary.csv：" + str(case), file=sys.stderr)
            return 3
    out_root = Path(args.out) if args.out else case / "_view"
    results = [build(t, out_root / ("cfd-" + t.parent.name)) for t in targets]
    if args.json:
        print(json.dumps({"ok": True, "views": results}, ensure_ascii=False, indent=2))
    else:
        print("CFD 结果可视化完成：%d 份汇总" % len(results))
        for r in results:
            print("  %s　%d 个工况　%s" % (Path(r["source"]).parent.name, r["rows"],
                                           r["states"]))
            print("    -> " + str(Path(r["out_dir"]) / "index.html"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
