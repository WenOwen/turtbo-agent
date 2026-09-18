#!/usr/bin/env python3
"""geom_view.py - 把叶轮机械几何画出来，零第三方依赖，输出纯 SVG。

为什么要有这个
--------------
在此之前，"看见设计"这件事全靠 NUMECA 的图形界面：agent 改完文件，
人得自己打开 AutoBlade/IGG 才知道发生了什么。这个工具让**任何一方**
（人、agent、界面）都能在不启动商业软件的前提下，直接把几何画出来。

三个视角，对应工程师真正会看的三种图：

  子午面 meridional   x(轴向) vs r(半径) —— 流道长什么样、叶片在哪个半径
  叶栅展开 cascade    把每个截面按弧长展开 —— 叶片剖面长什么样
  轴测 blade3d        绕轴旋转后投影 —— 叶片立体长什么样

用法
----
  python tools/geom_view.py --case cases/DF90-001
  python tools/geom_view.py --geom <path.geomTurbo> --out <dir>
  python tools/geom_view.py --case cases/DF90-001 --json
"""

from __future__ import annotations

import argparse
import json
import math
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
HUB = "#58a6ff"
SHROUD = "#3fb950"
BLADE = ["#f778ba", "#d2a8ff", "#ffa657", "#79c0ff", "#7ee787", "#ff7b72"]


# ── 解析 ───────────────────────────────────────────────────────────────────
def _points(body, cols=3):
    out = []
    for line in body.strip().splitlines():
        parts = line.split()
        if len(parts) >= cols:
            try:
                out.append(tuple(float(v) for v in parts[:cols]))
            except ValueError:
                pass
    return out


def parse_geomturbo(path: Path):
    """读 .geomTurbo。

    关键结构（实测确认）：
      CHANNEL 里是 hub / shroud 两条 (z, r) 曲线 —— 注意是 **z 在前 r 在后**，
      而叶片截面是 (x, y, z) 直角坐标，x 就是机器轴。
      NIBLADEGEOMETRY 里叶片分 suction / pressure 两侧，**每侧各有一套完整截面**，
      两侧都从 LE 走到 TE。一个截面的真实形状 = suction + reversed(pressure)。
    """
    text = path.read_text(encoding="utf-8", errors="replace")

    # 版本差异（实测）：
    #   AutoBlade 5.5：点数写 "+100"，缩进用 tab
    #   AutoGrid  5.9：点数写 "100"（没有加号），缩进用空格
    # 硬要求 "+" 会让 5.9 的文件静默解析成空 —— 之前就踩了这个坑。
    curves = {}
    for m in re.finditer(r"NAME\s+(\S+)\s*\r?\n\s*DISCRETISATION.*?"
                         r"NI_BEGIN\s+zrcurve\s*\r?\n\s*ZR\s*\r?\n\s*\+?(\d+)\s*\r?\n"
                         r"(.*?)NI_END\s+zrcurve", text, re.S | re.I):
        pts = _points(m.group(3), cols=2)
        if pts:
            curves[m.group(1)] = pts

    channel = {}
    for m in re.finditer(r"NI_BEGIN\s+channel_curve\s+(\S+)(.*?)NI_END\s+channel_curve",
                         text, re.S | re.I):
        which, body = m.group(1).lower(), m.group(2)
        ref = re.search(r"VERTEX\s+CURVE_P\s+(\S+)", body)
        if ref and ref.group(1) in curves:
            channel[which] = curves[ref.group(1)]

    rows = []
    for rm in re.finditer(r"NI_BEGIN\s+NIROW(.*?)NI_END\s+NIROW", text, re.S | re.I):
        body = rm.group(1)

        def grab(pat, cast=str, default=None):
            mm = re.search(pat, body)
            return cast(mm.group(1)) if mm else default

        sides = {}
        for side in ("suction", "pressure"):
            sm = re.search(r"\b" + side + r"\s*\r?\n\s*SECTIONAL\s*\r?\n(.*?)"
                           r"(?=\b(?:suction|pressure)\s*\r?\n\s*SECTIONAL|\Z)",
                           body, re.S | re.I)
            if not sm:
                continue
            got = {}
            for cm in re.finditer(r"#\s*section\s+(\d+)\s*\r?\n\s*XYZ\s*\r?\n\s*\+?(\d+)\s*\r?\n"
                                  r"(.*?)(?=\r?\n\s*#\s*section|\Z)",
                                  sm.group(1), re.S | re.I):
                pts = _points(cm.group(3))
                if len(pts) >= 3:
                    got[int(cm.group(1))] = pts
            sides[side] = got

        sections = []
        for idx in sorted(set(sides.get("suction", {})) | set(sides.get("pressure", {}))):
            suc = sides.get("suction", {}).get(idx)
            prs = sides.get("pressure", {}).get(idx)
            if suc and prs:
                # 两侧都从 LE 走到 TE，所以闭合剖面 = suction + 反向的 pressure
                profile = list(suc) + list(reversed(prs))
                kind = "closed"
            else:
                profile = list(suc or prs)
                kind = "suction-only" if suc else "pressure-only"
            sections.append({"index": idx, "suction": suc, "pressure": prs,
                             "profile": profile, "kind": kind})

        rows.append({
            "name": grab(r"NAME\s+(.+)", str, "row").strip(),
            "periodicity": grab(r"PERIODICITY\s+(\d+)", int, 0),
            "blades": grab(r"number_of_blades\s+(\d+)", int, 0),
            "sections": sections,
            "tip_gap_m": grab(r"WIDTH_AT_LEADING_EDGE\s+([\d.eE+-]+)", float, None),
        })
    # 剖面完整性自检：suction 与 pressure 必须成对。
    # 只有一侧时照样能画出开口折线，看着"像那么回事"—— 所以要显式报出来。
    warnings = []
    for row in rows:
        bad = [s["index"] for s in row["sections"] if s["kind"] != "closed"]
        if bad:
            warnings.append("%s 有 %d 个截面只解析出一侧（%s），画出来是开口曲线"
                            % (row["name"], len(bad), bad[:6]))
    return {"channel": channel, "rows": rows, "source": str(path), "warnings": warnings}


# ── 几何派生 ───────────────────────────────────────────────────────────────
def cyl(p):
    """(x, y, z) -> (轴向 z, 半径 r, 周向角 θ)。

    **旋转轴是第三个分量 z，不是 x。** 这一条是实测确认的，不是猜的：
      · 截面 13（叶尖）的 hypot(x, y) ∈ [0.2958, 0.3041]，而 shroud 的 r = 0.3；
      · 截面 1（叶根）的 hypot(x, y) ∈ [0.0826, 0.0884]，而 hub 的 r ≈ 0.082–0.086。
    按 x 当轴算出来的半径是 0.039–0.099，和流道完全对不上 —— 那样画出来的
    叶片会散在轮毂里面，是错的。
    """
    x, y, z = p
    return z, math.hypot(x, y), math.atan2(y, x)


def unwrap(thetas):
    """把跨 ±pi 的角度解开，避免曲线在图上来回跳。"""
    if not thetas:
        return []
    out = [thetas[0]]
    for t in thetas[1:]:
        d = t - out[-1]
        while d > math.pi:
            d -= 2 * math.pi
        while d < -math.pi:
            d += 2 * math.pi
        out.append(out[-1] + d)
    return out


def section_metrics(sec):
    """算一个截面的展开坐标与特征量。

    弦长/安装角用 **suction 侧**（LE→TE）算 —— 闭合剖面首尾重合，
    拿它算弦长会得到 0（这个坑踩过）。
    """
    ref = sec.get("suction") or sec.get("pressure") or sec["profile"]
    cs = [cyl(p) for p in ref]
    zs = [c[0] for c in cs]                   # 轴向
    rs = [c[1] for c in cs]                   # 半径
    ths = unwrap([c[2] for c in cs])
    rmid = sum(rs) / len(rs)
    ss = [rmid * t for t in ths]              # 周向弧长
    chord = math.hypot(zs[-1] - zs[0], ss[-1] - ss[0])
    stagger = math.degrees(math.atan2(ss[-1] - ss[0], zs[-1] - zs[0]))

    prof = [cyl(p) for p in sec["profile"]]
    pth = unwrap([c[2] for c in prof])
    return {
        "index": sec["index"], "kind": sec["kind"],
        "n": len(sec["profile"]),
        "z": zs, "r": rs, "s": ss, "rmid": rmid,
        "pz": [c[0] for c in prof],
        "ps": [rmid * t for t in pth],
        "r_range": (min(rs), max(rs)),
        "chord_m": chord, "stagger_deg": stagger,
    }


def make_map(xs, ys, w, h, pad):
    """数据坐标 -> SVG 像素坐标（y 轴已经翻好，调用方不用再管正负）。"""
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    dx, dy = (x1 - x0) or 1e-12, (y1 - y0) or 1e-12
    k = min((w - 2 * pad) / dx, (h - 2 * pad) / dy)
    ox = pad + ((w - 2 * pad) - dx * k) / 2 - x0 * k
    oy = pad + ((h - 2 * pad) - dy * k) / 2 - y0 * k

    def f(px, py):
        return px * k + ox, h - (py * k + oy)      # SVG 的 y 向下，翻过来
    return f, k


def pts_attr(seq):
    return " ".join("%.2f,%.2f" % (a, b) for a, b in seq)


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


def axes(s, mp, x0, x1, y0, y1, w, h, pad, nx=6, ny=5, xfmt="%.3f", yfmt="%.3f"):
    for i in range(nx):
        xv = x0 + (x1 - x0) * i / (nx - 1)
        a, b = mp(xv, y0), mp(xv, y1)
        s.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s"/>'
                 % (a[0], a[1], b[0], b[1], GRID))
        s.append('<text x="%.1f" y="%.1f" fill="%s" font-size="10" text-anchor="middle">%s</text>'
                 % (a[0], h - pad + 18, DIM, xfmt % xv))
    for i in range(ny):
        yv = y0 + (y1 - y0) * i / (ny - 1)
        a, b = mp(x0, yv), mp(x1, yv)
        s.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s"/>'
                 % (a[0], a[1], b[0], b[1], GRID))
        s.append('<text x="%.1f" y="%.1f" fill="%s" font-size="10" text-anchor="end">%s</text>'
                 % (pad - 8, a[1] + 3, DIM, yfmt % yv))


# ── 图 1：子午面 ───────────────────────────────────────────────────────────
def view_meridional(geom, w=1160, h=560, pad=70):
    ch = geom["channel"]
    ms_by_row = [[section_metrics(s) for s in row["sections"]] for row in geom["rows"]]

    xs, ys = [], []
    for key in ("hub", "shroud"):
        for z, r in ch.get(key, []):
            xs.append(z)
            ys.append(r)
    for ms in ms_by_row:
        for m in ms:
            xs += m["z"]
            ys += m["r"]
    if not xs:
        return "\n".join(svg_open(w, h, "子午面", "无数据") + ["</svg>"])

    mp, _ = make_map(xs, ys, w, h, pad)
    s = svg_open(w, h, "子午面（流道 + 叶片）",
                 "横轴 = 轴向 z (m)　纵轴 = 半径 r (m)　" + Path(geom["source"]).name)

    if "hub" in ch and "shroud" in ch:
        band = [(z, r) for z, r in ch["hub"]] + [(z, r) for z, r in reversed(ch["shroud"])]
        s.append('<polygon fill="%s" fill-opacity="0.10" points="%s"/>'
                 % (HUB, pts_attr([mp(a, b) for a, b in band])))

    axes(s, mp, min(xs), max(xs), min(ys), max(ys), w, h, pad)

    for key, color in (("hub", HUB), ("shroud", SHROUD)):
        if key in ch:
            s.append('<polyline fill="none" stroke="%s" stroke-width="2.2" points="%s"/>'
                     % (color, pts_attr([mp(z, r) for z, r in ch[key]])))

    for ri, ms in enumerate(ms_by_row):
        color = BLADE[ri % len(BLADE)]
        for m in ms:
            a, b = mp(m["z"][0], m["r"][0]), mp(m["z"][-1], m["r"][-1])
            s.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" '
                     'stroke-width="1.6" stroke-opacity="0.85"/>' % (a[0], a[1], b[0], b[1], color))
        env = [(m["z"][0], m["r"][0]) for m in ms] + \
              [(m["z"][-1], m["r"][-1]) for m in reversed(ms)]
        s.append('<polyline fill="none" stroke="%s" stroke-width="1.2" stroke-dasharray="3 3" '
                 'stroke-opacity="0.5" points="%s"/>' % (color, pts_attr([mp(a, b) for a, b in env])))

    for ri, row in enumerate(geom["rows"]):
        color = BLADE[ri % len(BLADE)]
        s.append('<text x="%d" y="%d" fill="%s" font-size="12" font-weight="700">%s'
                 '（%d 叶 / %d 截面）</text>'
                 % (pad + 6, 80 + ri * 18, color, esc(row["name"]),
                    row["periodicity"], len(row["sections"])))
    lx = w - 180
    for i, (name, color) in enumerate((("hub 轮毂", HUB), ("shroud 涵道", SHROUD))):
        s.append('<rect x="%d" y="%d" width="12" height="3" fill="%s"/>' % (lx, 74 + i * 20, color))
        s.append('<text x="%d" y="%d" fill="%s" font-size="12">%s</text>'
                 % (lx + 20, 79 + i * 20, DIM, name))
    s.append("</svg>")
    return "\n".join(s)


# ── 图 2：叶栅展开 ─────────────────────────────────────────────────────────
def view_cascade(geom, w=1160, h=None, pad=56):
    """每个截面一张，**共用同一比例尺**。

    早先每张面板各自等比缩放 —— 面板之间就不能比大小了（实测两截面弦长
    只差 1.6%，画出来却差 5.4%）。共用比例尺是这张图有意义的前提。
    另外每张只画一个截面，所以叫"截面形状"而不是"叶栅展开"（没有栅距、
    没有相邻叶片，叫叶栅是误导）。
    """
    panels = []
    for ri, row in enumerate(geom["rows"]):
        for m in [section_metrics(s) for s in row["sections"]]:
            panels.append((ri, row, m))
    ncol = min(7, max(1, len(panels)))
    nrow = math.ceil(len(panels) / ncol) if panels else 1
    chh = 178
    h = h or (100 + nrow * chh)
    s = svg_open(w, h, "叶片各截面形状",
                 "横轴 = 轴向 z (m)　纵轴 = 周向弧长 s = r·θ (m)　"
                 "共 %d 个截面，**所有面板同一比例尺**" % len(panels))
    if not panels:
        s.append("</svg>")
        return "\n".join(s)

    cw = (w - 2 * pad) / ncol
    sw, sh = cw - 16, chh - 56
    # 全局比例尺：所有面板共用
    allz = [v for _, _, m in panels for v in m["pz"]]
    alls = [v for _, _, m in panels for v in m["ps"]]
    z0, z1 = min(allz), max(allz)
    s0, s1 = min(alls), max(alls)
    dz, ds = (z1 - z0) or 1e-9, (s1 - s0) or 1e-9
    # 保持纵横比：取较紧的那个方向
    k = min((sw - 24) / dz, (sh - 24) / ds)

    for i, (ri, row, m) in enumerate(panels):
        cx = pad + (i % ncol) * cw
        cy = 92 + (i // ncol) * chh
        ox = cx + (sw - dz * k) / 2 - z0 * k
        oy = cy + (sh - ds * k) / 2 - s0 * k
        shifted = [(ox + z * k, cy + sh - ((s * k + oy) - cy)) for z, s_ in
                   zip(m["pz"], m["ps"]) for s in [s_]]
        color = BLADE[ri % len(BLADE)]
        s.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" '
                 'stroke="%s" rx="4"/>' % (cx, cy, sw, sh, PANEL, GRID))
        s.append('<polygon points="%s" fill="%s" fill-opacity="0.18" stroke="%s" '
                 'stroke-width="1.6"/>' % (pts_attr(shifted), color, color))
        le = shifted[0]
        s.append('<circle cx="%.1f" cy="%.1f" r="2.6" fill="%s"/>' % (le[0], le[1], FG))
        # 标签分两行，避免横向压字（早先一行 30+ 字符，面板间距只有 150 px）
        s.append('<text x="%.1f" y="%.1f" fill="%s" font-size="10">%s #%d</text>'
                 % (cx + 5, cy + sh + 14, DIM, esc(row["name"]), m["index"]))
        s.append('<text x="%.1f" y="%.1f" fill="%s" font-size="10">弦 %.1f mm　'
                 '安装角 %.1f°</text>'
                 % (cx + 5, cy + sh + 26, DIM, m["chord_m"] * 1000, m["stagger_deg"]))
    s.append("</svg>")
    return "\n".join(s)


# ── 图 3：轴测 ─────────────────────────────────────────────────────────────
def view_blade3d(geom, w=1000, h=620, pad=60, az_deg=35.0, el_deg=38.0, copies=0):
    az, el = math.radians(az_deg), math.radians(el_deg)
    items = []

    # 相机：把机器轴 z 当作"世界上方"，方位角 θ 绕它转，仰角 φ 抬高。
    #     screen_x = -X·sinθ + Y·cosθ
    #     screen_y = -(X·cosθ + Y·sinθ)·sinφ + z·cosφ
    # 第一版把 screen_x 直接取成轴向 z、screen_y 只依赖 X/Y —— 那样**圆环会退化成
    # 竖直线**（固定 z 的点横向坐标全相同），画出来是个方盒子。实测踩过。
    # 返回 (屏幕横向, 屏幕纵向, 深度)，深度用于远近排序。
    def project(ax_z, r, th):
        X = r * math.cos(th)
        Y = r * math.sin(th)
        sx = -X * math.sin(az) + Y * math.cos(az)
        sy = -(X * math.cos(az) + Y * math.sin(az)) * math.sin(el) + ax_z * math.cos(el)
        depth = (X * math.cos(az) + Y * math.sin(az)) * math.cos(el) + ax_z * math.sin(el)
        return sx, sy, depth

    # 轮毂/涵道画成"几条子午线 + 进出口两个圆环"，而不是整张圆柱网格 ——
    # 满屏网格线会盖住叶片，反而看不清。这是可读性问题，不是几何问题。
    # items: (名字, 颜色, 点列, 线宽, 不透明度, 是不是叶片)
    # 用显式布尔量而不是"角度==0"当哨兵 —— 后者在 copies=1 时恒真，是死代码。
    for key, color in (("hub", HUB), ("shroud", SHROUD)):
        if key not in geom["channel"]:
            continue
        curve = geom["channel"][key]
        for t_deg in (0, 90, 180, 270):
            th = math.radians(t_deg)
            items.append((key, color, [project(z, r, th) for z, r in curve],
                          1.3, 0.40, False))
        for z, r in (curve[0], curve[-1]):
            items.append((key, color, [project(z, r, math.radians(t))
                                       for t in range(0, 361, 6)],
                          1.2, 0.50, False))

    for ri, row in enumerate(geom["rows"]):
        color = BLADE[ri % len(BLADE)]
        per = max(1, row["periodicity"])
        metrics = [section_metrics(s) for s in row["sections"]]
        ncopy = per if copies <= 0 else copies   # 默认画满一圈
        for c in range(ncopy):
            base = 2 * math.pi * c / per
            # 每个截面的三维点（用展开坐标重建：轴向 z 取真实值，周向由弧长 s 换算）
            rings = []
            for m in metrics:
                rings.append([project(z, m["rmid"], s_ / m["rmid"] + base)
                              for z, s_ in zip(m["z"], m["s"])])
            for ring in rings:
                items.append((row["name"], color, ring, 1.4, 0.85, True))
            # 展向连线：只画截面轮廓会散成一堆弧，看不出"这是个叶片面"。
            # 把相邻截面同序号的点连起来，才有实体感。
            if len(rings) >= 2:
                npts = min(len(r) for r in rings)
                step = max(1, npts // 22)
                for i in range(0, npts, step):
                    span = [rings[k][i] for k in range(len(rings))]
                    items.append((row["name"], color, span, 0.6, 0.26, True))

    if not items:
        return "\n".join(svg_open(w, h, "轴测", "无几何数据") + ["</svg>"])

    xs = [p[0] for _, _, ring, _, _, _ in items for p in ring]
    ys = [p[1] for _, _, ring, _, _, _ in items for p in ring]
    mp, _ = make_map(xs, ys, w, h, pad)

    s = svg_open(w, h, "轴测（叶片 + 涵道）",
                 "方位角 %.0f°　仰角 %.0f°　每排按周期数画满，看得出叶片数"
                 % (az_deg, el_deg))

    # 排序：先把涵道/轮毂（base==0）铺底，再按深度从远到近画叶片。
    # 只按深度排会让半透明的涵道大圆环压住叶片 —— 那是遮挡关系错了，不是审美问题。
    def order(it):
        return (0 if not it[5] else 1,          # 涵道/轮毂铺底，叶片画在上面
                sum(p[2] for p in it[2]) / len(it[2]))

    for name, color, ring, sw_, op, is_blade in sorted(items, key=order):
        pts = pts_attr([mp(a, b) for a, b, _ in ring])
        if is_blade:
            # 叶片截面：填充一点颜色，立体感来自重叠而不是线宽
            s.append('<polygon fill="%s" fill-opacity="0.30" stroke="%s" '
                     'stroke-width="%.1f" stroke-opacity="%.2f" points="%s"/>'
                     % (color, color, sw_, op, pts))
        else:
            s.append('<polyline fill="none" stroke="%s" stroke-width="%.1f" '
                     'stroke-opacity="%.2f" points="%s"/>' % (color, sw_, op, pts))

    # 排序说明放在图注里，免得下一个人又"优化"回去

    ly = 74
    for ri, row in enumerate(geom["rows"]):
        color = BLADE[ri % len(BLADE)]
        s.append('<rect x="%d" y="%d" width="12" height="3" fill="%s"/>' % (w - 230, ly, color))
        s.append('<text x="%d" y="%d" fill="%s" font-size="12">%s（%d 叶，画满一圈）</text>'
                 % (w - 210, ly + 5, DIM, esc(row["name"]), row["periodicity"]))
        ly += 20
    for name, color in (("轮毂 hub", HUB), ("涵道 shroud", SHROUD)):
        s.append('<rect x="%d" y="%d" width="12" height="3" fill="%s"/>' % (w - 230, ly, color))
        s.append('<text x="%d" y="%d" fill="%s" font-size="12">%s（子午线 + 进出口环）</text>'
                 % (w - 210, ly + 5, DIM, name))
        ly += 20
    s.append("</svg>")
    return "\n".join(s)


# ── 组装 ───────────────────────────────────────────────────────────────────
INDEX_TMPL = """<!doctype html><html lang="zh"><meta charset="utf-8">
<title>%(title)s · 几何视图</title>
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


def build(geom_path: Path, out_dir: Path):
    geom = parse_geomturbo(geom_path)
    # 解析出空结果时必须显式失败 —— 出三张"无数据"的图还报 ok，
    # 比报错更糟：人以为看过了。（实测踩过：5.9 版的文件被静默解析成空。）
    if not geom["rows"] and not geom["channel"]:
        raise ValueError("没能从 %s 解析出任何几何（通道与叶排都是空的）。"
                         "可能是文件版本差异，请检查格式。" % geom_path.name)
    out_dir.mkdir(parents=True, exist_ok=True)
    written, cards = [], []
    for fname, title, note, fn in (
            ("meridional.svg", "子午面", "流道轮廓 + 叶片径向位置", view_meridional),
            ("cascade.svg", "叶栅展开", "每个截面的剖面形状（前缘点标白）", view_cascade),
            ("blade3d.svg", "轴测", "叶片与涵道的立体关系", view_blade3d)):
        svg = fn(geom)
        (out_dir / fname).write_text(svg, encoding="utf-8", newline="")
        written.append(str(out_dir / fname))
        cards.append('<div class="card"><h2>%s · %s</h2><img src="%s" alt="%s"></div>'
                     % (esc(title), esc(note), fname, esc(title)))

    kv = ['<div class="card"><h2>几何摘要</h2><dl class="kv">',
          "<dt>来源</dt><dd>%s</dd>" % esc(geom_path.name),
          "<dt>叶排数</dt><dd>%d</dd>" % len(geom["rows"])]
    for row in geom["rows"]:
        ms = [section_metrics(s) for s in row["sections"]]
        if ms:
            kv.append("<dt>%s</dt><dd>%d 叶　%d 截面　弦长 %.1f–%.1f mm　安装角 %.1f–%.1f°</dd>"
                      % (esc(row["name"]), row["periodicity"], len(ms),
                         min(m["chord_m"] for m in ms) * 1000,
                         max(m["chord_m"] for m in ms) * 1000,
                         min(m["stagger_deg"] for m in ms),
                         max(m["stagger_deg"] for m in ms)))
    for which in ("hub", "shroud"):
        if which in geom["channel"]:
            c = geom["channel"][which]
            kv.append("<dt>%s</dt><dd>%d 点　z %.4f–%.4f m　r %.4f–%.4f m</dd>"
                      % (which, len(c), min(p[0] for p in c), max(p[0] for p in c),
                         min(p[1] for p in c), max(p[1] for p in c)))
    kv.append("</dl></div>")

    (out_dir / "index.html").write_text(INDEX_TMPL % {
        "title": geom_path.stem, "bg": BG, "fg": FG, "dim": DIM, "grid": GRID, "panel": PANEL,
        "sub": "由 tools/geom_view.py 生成　·　零依赖纯 SVG，断网可看　·　源文件 " + esc(str(geom_path)),
        "cards": "".join(kv) + "".join(cards),
    }, encoding="utf-8", newline="")
    written.append(str(out_dir / "index.html"))
    return {"ok": True, "source": str(geom_path), "out_dir": str(out_dir), "files": written,
            "warnings": geom.get("warnings", []),
            "rows": [{"name": r["name"], "periodicity": r["periodicity"],
                      "blades": r["blades"], "sections": len(r["sections"])} for r in geom["rows"]],
            "channel": {k: len(v) for k, v in geom["channel"].items()}}


def find_geomturbo(case: Path):
    """找案例里的叶片几何文件。

    **只认 02-geometry/ 下的**，理由：
      · 03-mesh/ 里也有同名 .geomTurbo，但那是 AutoGrid 回写的网格侧面几何，
        不是设计几何；混进来会多出几个标签页，还容易被误读成"设计改了"。
      · .bak 是备份，不是产物。
    """
    hits = [p for p in sorted((case / "02-geometry").glob("**/*.geomTurbo"))
            if p.is_file() and ".bak" not in p.name.lower()]
    return hits


def main(argv=None):
    ap = argparse.ArgumentParser(description="叶轮机械几何可视化（零依赖，输出 SVG）")
    ap.add_argument("--case", default=None)
    ap.add_argument("--geom", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.geom:
        targets = [Path(args.geom)]
        case = targets[0].parent
    else:
        case = Path(args.case).resolve() if args.case else ROOT / "cases" / "DF90-001"
        targets = find_geomturbo(case)
        if not targets:
            print("找不到 .geomTurbo：" + str(case), file=sys.stderr)
            return 3
    out_root = Path(args.out) if args.out else case / "_view"
    results = [build(g, out_root / g.stem) for g in targets]
    if args.json:
        print(json.dumps({"ok": True, "views": results}, ensure_ascii=False, indent=2))
    else:
        print("几何可视化完成：%d 套几何" % len(results))
        for r in results:
            print("  " + Path(r["source"]).name)
            for row in r["rows"]:
                print("    %-10s %2d 叶  %2d 截面" % (row["name"], row["periodicity"], row["sections"]))
            print("    -> " + str(Path(r["out_dir"]) / "index.html"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
