#!/usr/bin/env python3
"""geom_check.py - 把设计参数表与几何实测值并排比，逐项标出偏离。

为什么要有这个
--------------
前面三个视图画的是"几何长什么样"。但小白真正要回答的问题是
**"这样对不对"** —— 那需要拿实测值和设计值比。

这张图不画形状，只做一件事：把 01-scheme/叶片几何参数表.csv 的设计值，
和从 .par / .geomTurbo 实测出来的值并排放，逐项给结论。

术语必须分清（否则会误判）
--------------------------
  金属角 (metal angle)  = 叶片中弧线在前/尾缘的切线角，来自 .par 的 CAMBER_BETA
  弦线角 (stagger)      = 前缘到尾缘的连线角，从几何点算出来
两者**不是一回事**。参数表里写的是金属角，早先的图把它标成"安装角"，会误导。

用法
----
  python tools/geom_check.py --case cases/DF90-001
  python tools/geom_check.py --case cases/DF90-001 --json
"""

from __future__ import annotations

import argparse
import csv
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

sys.path.insert(0, str(HERE))

BG = "#0d1117"
FG = "#c9d1d9"
DIM = "#8b949e"
GRID = "#21262d"
PANEL = "#161b22"
OK = "#3fb950"
WARN = "#d29922"
BAD = "#f85149"


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


# ── 读设计表 ───────────────────────────────────────────────────────────────
def read_table(path: Path):
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return [{k.strip(): (v or "").strip() for k, v in r.items() if k}
                for r in csv.DictReader(fh)]


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ── 读 .par 的截面金属角 ───────────────────────────────────────────────────
def par_sections(par: Path):
    """从 .par 抽每个截面的 CAMBER_BETA1/2。"""
    if not par.is_file():
        return {}
    text = par.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    out = {}
    for i, line in enumerate(lines):
        m = re.search(r"NAME\s+(S(\d+))_CAMBER_BETA([12])\s*$", line.strip())
        if not m:
            continue
        val = None
        for j in range(i + 1, min(i + 8, len(lines))):
            vm = re.match(r"\s*VALUE\s+([-\d.eE+]+)\s*$", lines[j])
            if vm:
                val = fnum(vm.group(1))
                break
        if val is not None:
            out.setdefault(int(m.group(2)), {})[m.group(3)] = val
    return out


# ── 从几何实测金属角 ───────────────────────────────────────────────────────
def geom_metal_angles(geomturbo: Path):
    """用截面几何点估中弧线前后缘切线角。

    做法：中弧线 = suction 与 pressure 同序号点的中点；
    前缘角 = 中弧线首端几点的切线方向，尾缘角 = 末端几点。
    这是**估计值**（真值在 .par 里），用来交叉验证。
    """
    import geom_view
    g = geom_view.parse_geomturbo(geomturbo)
    out = []
    for row in g["rows"]:
        for sec in row["sections"]:
            suc, prs = sec.get("suction"), sec.get("pressure")
            if not suc or not prs or len(suc) != len(prs):
                continue
            mid = []
            for a, b in zip(suc, prs):
                mid.append(((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0, (a[2] + b[2]) / 2.0))
            cs = [geom_view.cyl(p) for p in mid]
            zs = [c[0] for c in cs]
            rs = [c[1] for c in cs]
            ths = geom_view.unwrap([c[2] for c in cs])
            rmid = sum(rs) / len(rs)
            ss = [rmid * t for t in ths]

            def ang(i, j):
                dz = zs[j] - zs[i]
                ds = ss[j] - ss[i]
                return math.degrees(math.atan2(ds, dz))

            n = len(zs)
            k = max(3, n // 12)
            out.append({
                "row": row["name"], "index": sec["index"],
                "beta1_geom": ang(0, k), "beta2_geom": ang(n - 1 - k, n - 1),
                "r_mid": rmid, "z_mid": sum(zs) / n,
                "chord": math.hypot(zs[-1] - zs[0], ss[-1] - ss[0]),
            })
    return out


# ── 对照表 ─────────────────────────────────────────────────────────────────
def build_rows(case: Path):
    """产出逐项对照。每项：名称 / 设计值 / 实测值 / 偏离 / 结论。"""
    tbl = read_table(case / "01-scheme" / "v1" / "叶片几何参数表.csv")
    geoms = {}
    for p in sorted((case / "02-geometry").glob("**/*.geomTurbo")):
        if ".bak" not in p.name.lower():
            geoms[p.stem] = p

    # 叶排名对齐 —— **这是本工具最容易骗人的地方**：
    # 参数表写 "S1"，几何文件却叫 "R2"。按同名匹配会静默跳过整行，
    # 结果报"全部一致"，而实际上那一行根本没比过。
    # 实测踩过：第一版就是 6 项全 PASS，假的。
    # 正确做法：按顺序配对（都是按流向排列），并把配对关系显式打出来。
    # 配对必须**用叶片数校验**，不能只靠顺序。
    # 审核实测：临时案例里只放 R2.geomTurbo 时，按顺序会把 R1（9 叶）
    # 配到 R2 几何（11 叶）上，输出 3 条 FAIL —— 读起来像几何做坏了。
    # 手里就有"叶片数"这个强判据，必须用。
    def geom_blade_count(p):
        try:
            import geom_view
            g = geom_view.parse_geomturbo(p)
            return g["rows"][0]["periodicity"] if g["rows"] else None
        except Exception:
            return None

    order = sorted(geoms)
    counts = {k: geom_blade_count(v) for k, v in geoms.items()}
    pairing = []
    used = set()
    for i, r in enumerate(tbl):
        name = r.get("叶排", "")
        want = fnum(r.get("叶片数"))
        gt, how = None, "没找到"
        if name in geoms and name not in used:
            gt, how = geoms[name], "同名"
        else:
            for cand in order:
                if cand in used:
                    continue
                if want is not None and counts.get(cand) is not None \
                        and int(counts[cand]) == int(want):
                    gt, how = geoms[cand], "按叶片数配对"
                    break
            if gt is None and i < len(order) and order[i] not in used:
                gt, how = geoms[order[i]], "按顺序（叶片数没对上，存疑）"
        if gt is not None:
            used.add(gt.stem)
            # 同名但叶片数不符也要标出来
            if want is not None and counts.get(gt.stem) is not None \
                    and int(counts[gt.stem]) != int(want):
                how += "　⚠ 叶片数不符（设计 %.0f / 几何 %s）" % (want, counts[gt.stem])
        pairing.append({"table": name, "geom": gt.stem if gt else None,
                        "matched_by": how,
                        "blades_design": want,
                        "blades_geom": counts.get(gt.stem) if gt else None})
        r["_geom"] = gt

    out = {"items": [], "notes": [], "rows": [], "pairing": pairing}
    for r in tbl:
        name = r.get("叶排", "")
        blades_design = fnum(r.get("叶片数"))
        chord_design = fnum(r.get("弦长(m)"))
        b1d = fnum(r.get("进口金属角(deg,相对轴向)"))
        b2d = fnum(r.get("出口金属角(deg,相对轴向)"))
        solidity_design = fnum(r.get("稠度"))

        gt = r.get("_geom")
        rec = {"name": name, "type": r.get("类型", ""),
               "geom_name": gt.stem if gt else None,
               "blades_design": blades_design, "chord_design": chord_design,
               "beta1_design": b1d, "beta2_design": b2d,
               "solidity_design": solidity_design,
               "blades_geom": None, "chord_geom": None,
               "beta1_geom": None, "beta2_geom": None,
               "beta1_par": None, "beta2_par": None,
               "beta1_par_root": None, "beta2_par_root": None,
               "beta1_par_tip": None, "beta2_par_tip": None,
               "solidity_geom": None, "geom_file": gt.name if gt else None}

        if gt:
            import geom_view
            g = geom_view.parse_geomturbo(gt)
            if g["rows"]:
                row = g["rows"][0]
                rec["blades_geom"] = row["periodicity"]
                rec["tip_gap_geom"] = row.get("tip_gap_m")
                ms = [geom_view.section_metrics(s) for s in row["sections"]]
                if ms:
                    rec["z_min"] = min(min(m["z"]) for m in ms)
                    rec["z_max"] = max(max(m["z"]) for m in ms)
                if ms:
                    rec["chord_geom"] = sum(m["chord_m"] for m in ms) / len(ms)
                    rec["chord_min"] = min(m["chord_m"] for m in ms)
                    rec["chord_max"] = max(m["chord_m"] for m in ms)
                    rec["r_mid"] = sum(m["rmid"] for m in ms) / len(ms)
                    if rec["r_mid"] and rec["chord_geom"]:
                        rec["solidity_geom"] = rec["chord_geom"] / (
                            2 * math.pi * rec["r_mid"] / max(row["periodicity"], 1))
            # 真值：.par 的 CAMBER_BETA
            par = gt.with_suffix(".par")
            secs = par_sections(par)
            if secs:
                idxs = sorted(secs)
                rec["beta1_par_root"] = secs[idxs[0]].get("1")
                rec["beta2_par_root"] = secs[idxs[0]].get("2")
                rec["beta1_par_tip"] = secs[idxs[-1]].get("1")
                rec["beta2_par_tip"] = secs[idxs[-1]].get("2")
                b1 = [secs[i]["1"] for i in idxs if "1" in secs[i]]
                b2 = [secs[i]["2"] for i in idxs if "2" in secs[i]]
                rec["beta1_par"] = sum(b1) / len(b1) if b1 else None
                rec["beta2_par"] = sum(b2) / len(b2) if b2 else None
                # 中径截面 = 中间那个（截面按展向排）
                mid_i = idxs[len(idxs) // 2]
                rec["beta1_par_mid"] = secs[mid_i].get("1")
                rec["beta2_par_mid"] = secs[mid_i].get("2")
                rec["mid_section"] = mid_i
                rec["par_file"] = par.name
            # 几何估计（交叉验证 .par 是否与画出来的形状一致）
            ga = geom_metal_angles(gt)
            if ga:
                rec["beta1_geom"] = sum(x["beta1_geom"] for x in ga) / len(ga)
                rec["beta2_geom"] = sum(x["beta2_geom"] for x in ga) / len(ga)
        out["rows"].append(rec)

    for pr in pairing:
        if pr["geom"] is None:
            out["notes"].append("参数表里的 %s 在 02-geometry 下找不到对应几何 —— "
                                "这一行没有比过，不代表一致。" % pr["table"])
        elif pr["matched_by"] == "按顺序":
            out["notes"].append("参数表叫 %s，几何文件叫 %s —— 名字不同，"
                                "按流向顺序配对。这种血缘差异必须让接手的人知道。"
                                % (pr["table"], pr["geom"]))

    # 结论
    for rec in out["rows"]:
        n = rec["name"]
        if rec["blades_design"] is not None and rec["blades_geom"] is not None:
            ok = int(rec["blades_design"]) == int(rec["blades_geom"])
            out["items"].append({
                "row": n, "what": "叶片数",
                "design": "%.0f" % rec["blades_design"],
                "actual": "%.0f" % rec["blades_geom"],
                "verdict": "PASS" if ok else "FAIL",
                "note": "" if ok else "几何里的叶片数与设计表不一致",
            })
        if rec["chord_design"] and rec["chord_geom"]:
            dev = (rec["chord_geom"] - rec["chord_design"]) / rec["chord_design"]
            v = "PASS" if abs(dev) <= 0.05 else ("WARN" if abs(dev) <= 0.15 else "FAIL")
            out["items"].append({
                "row": n, "what": "平均弦长 (m)",
                "design": "%.4f" % rec["chord_design"],
                "actual": "%.4f" % rec["chord_geom"],
                "verdict": v, "dev_pct": dev * 100,
                "note": "几何实测 %.1f–%.1f mm" % (rec.get("chord_min", 0) * 1000,
                                                    rec.get("chord_max", 0) * 1000),
            })
        if rec["solidity_design"] and rec.get("solidity_geom"):
            dev = (rec["solidity_geom"] - rec["solidity_design"]) / rec["solidity_design"]
            v = "PASS" if abs(dev) <= 0.10 else ("WARN" if abs(dev) <= 0.25 else "FAIL")
            out["items"].append({
                "row": n, "what": "中径稠度",
                "design": "%.3f" % rec["solidity_design"],
                "actual": "%.3f" % rec["solidity_geom"],
                "verdict": v, "dev_pct": dev * 100, "note": "由几何弦长与中径回算",
            })
        # 金属角：**必须拿中径截面比**，不能拿 [root, tip] 区间比。
        # 审核实测：R1 跨度 22°、S1 跨度 25°，"落在区间内 ±1°" 任何中间值都 PASS，
        # 判据形同虚设。用中径（S7 附近）±2° 才是工程上说得通的比法。
        for which, key_d, key_mid, label in (
                ("1", "beta1_design", "beta1_par_mid", "进口金属角 (°)"),
                ("2", "beta2_design", "beta2_par_mid", "出口金属角 (°)")):
            d = rec.get(key_d)
            mid = rec.get(key_mid)
            if d is None or mid is None:
                continue
            delta = mid - d
            ok = abs(delta) <= 2.0
            out["items"].append({
                "row": n, "what": label,
                "design": "%.2f" % d,
                "actual": "%.2f（中径）" % mid,
                "verdict": "PASS" if ok else ("WARN" if abs(delta) <= 5.0 else "FAIL"),
                "dev_abs": delta,
                "note": "中径比对，容差 ±2°。几何全展向 %.2f…%.2f。"
                        % (rec["beta%s_par_root" % which], rec["beta%s_par_tip" % which])
                        + ("" if ok else "差 %.2f° —— 两者血缘不同" % delta),
            })
        # 叶尖间隙：设计表写了，几何里也有，必须比 —— 这是审核点名的漏项
        tg_d = fnum(r.get("叶尖间隙(m)"))
        tg_g = rec.get("tip_gap_geom")
        if tg_d is not None:
            if tg_g is None:
                out["items"].append({
                    "row": n, "what": "叶尖间隙 (m)",
                    "design": "%.4f" % tg_d, "actual": "几何里没有间隙块",
                    "verdict": "FAIL",
                    "note": "设计表要求有间隙，几何里没有 —— 转子没间隙会刮蹭",
                })
            else:
                dev = (tg_g - tg_d) / tg_d if tg_d else 0
                v = "PASS" if abs(dev) <= 0.10 else ("WARN" if abs(dev) <= 0.5 else "FAIL")
                out["items"].append({
                    "row": n, "what": "叶尖间隙 (m)",
                    "design": "%.4f" % tg_d, "actual": "%.4f" % tg_g,
                    "verdict": v, "dev_pct": dev * 100,
                    "note": "" if v == "PASS" else "差 %.1f 倍" % (tg_g / tg_d if tg_d else 0),
                })

        # 轴向位置：设计表给了站位，几何有实际 z 范围 —— 对不上说明不是同一台机器
        z_d = fnum(r.get("轴向坐标(m)"))
        if z_d is not None and rec.get("z_min") is not None:
            inside = rec["z_min"] - 0.005 <= z_d <= rec["z_max"] + 0.005
            out["items"].append({
                "row": n, "what": "轴向位置 (m)",
                "design": "%.4f" % z_d,
                "actual": "%.4f … %.4f" % (rec["z_min"], rec["z_max"]),
                "verdict": "PASS" if inside else "FAIL",
                "note": "" if inside else "设计站位落在几何 z 范围之外 —— 两排不是同一台机器",
            })

        # 几何估计 vs .par 真值：验证"画出来的形状"与"参数文件"一致
        if rec["beta1_par"] is not None and rec["beta1_geom"] is not None:
            d = abs(rec["beta1_par"] - rec["beta1_geom"])
            out["items"].append({
                "row": n, "what": "几何 vs .par 自洽 (进口)",
                "design": "%.2f (.par 均值)" % rec["beta1_par"],
                "actual": "%.2f (几何估)" % rec["beta1_geom"],
                "verdict": "PASS" if d <= 3.0 else "WARN",
                "note": "差 %.2f°；几何估计用中弧线切线，含端点效应" % d,
            })
    return out


def view_report(data, w=1160, h=None):
    items = data["items"]
    rowh = 30
    h = h or (130 + len(items) * rowh + 150)
    s = svg_open(w, h, "设计值 vs 几何实测",
                 "左边是 01-scheme 参数表写的，右边是从几何文件实测的　"
                 "结论：PASS 一致 / WARN 有偏离 / FAIL 对不上")
    colx = [24, 150, 330, 520, 720]
    heads = ["叶排", "项目", "设计值（参数表）", "实测值（几何）", "结论"]
    y = 92
    for i, hd in enumerate(heads):
        s.append('<text x="%d" y="%d" fill="%s" font-size="11.5" font-weight="700">%s</text>'
                 % (colx[i], y, DIM, hd))
    y += 10
    s.append('<line x1="20" y1="%d" x2="%d" y2="%d" stroke="%s"/>' % (y, w - 20, y, GRID))
    y += 22
    for it in items:
        c = {"PASS": OK, "WARN": WARN, "FAIL": BAD}.get(it["verdict"], DIM)
        if it["verdict"] == "FAIL":
            s.append('<rect x="16" y="%d" width="%d" height="%d" fill="%s" fill-opacity="0.10" '
                     'rx="4"/>' % (y - 17, w - 32, rowh - 2, BAD))
        s.append('<text x="%d" y="%d" fill="%s" font-size="12">%s</text>'
                 % (colx[0], y, FG, esc(it["row"])))
        s.append('<text x="%d" y="%d" fill="%s" font-size="12">%s</text>'
                 % (colx[1], y, FG, esc(it["what"])))
        s.append('<text x="%d" y="%d" fill="%s" font-size="12">%s</text>'
                 % (colx[2], y, DIM, esc(it["design"])))
        s.append('<text x="%d" y="%d" fill="%s" font-size="12">%s</text>'
                 % (colx[3], y, FG, esc(it["actual"])))
        s.append('<text x="%d" y="%d" fill="%s" font-size="12" font-weight="700">%s</text>'
                 % (colx[4], y, c, it["verdict"]))
        if it.get("dev_pct") is not None:
            s.append('<text x="%d" y="%d" fill="%s" font-size="11">%+.1f%%</text>'
                     % (colx[4] + 52, y, c, it["dev_pct"]))
        if it.get("note"):
            y += 16
            s.append('<text x="%d" y="%d" fill="%s" font-size="10.5">%s</text>'
                     % (colx[1], y, DIM, esc(it["note"])[:120]))
        y += rowh
    s.append("</svg>")
    return "\n".join(s)


INDEX_TMPL = """<!doctype html><html lang="zh"><meta charset="utf-8">
<title>%(title)s · 设计值对照</title>
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
 .fail{color:#f85149}.warn{color:#d29922}.ok{color:#3fb950}
</style>
<h1>%(title)s</h1>
<div class="sub">%(sub)s</div>
%(cards)s
"""


def build(case: Path, out_dir: Path):
    data = build_rows(case)
    out_dir.mkdir(parents=True, exist_ok=True)
    svg = view_report(data)
    (out_dir / "design-vs-geom.svg").write_text(svg, encoding="utf-8", newline="")

    n = {"PASS": 0, "WARN": 0, "FAIL": 0}
    for it in data["items"]:
        n[it["verdict"]] = n.get(it["verdict"], 0) + 1
    fails = [it for it in data["items"] if it["verdict"] == "FAIL"]

    kv = ['<div class="card"><h2>逐项对照</h2><dl class="kv">',
          "<dt>对照项</dt><dd>%d 项　<span class='ok'>一致 %d</span>　"
          "<span class='warn'>偏离 %d</span>　<span class='fail'>对不上 %d</span></dd>"
          % (len(data["items"]), n["PASS"], n["WARN"], n["FAIL"])]
    for it in fails:
        kv.append("<dt class='fail'>%s %s</dt><dd class='fail'>设计 %s　实测 %s　%s</dd>"
                  % (esc(it["row"]), esc(it["what"]), esc(it["design"]),
                     esc(it["actual"]), esc(it.get("note", ""))))
    kv.append("</dl></div>")
    kv.append('<div class="card"><h2>结论</h2><p>%s</p></div>'
              % ("<br>".join(esc(x) for x in data["notes"]) or
                 "参数表与几何逐项比过。上面标红的是对不上的项 —— "
                 "它们不代表几何做错了，而代表<b>这两份东西不是同一套血缘</b>，"
                 "接手的人必须知道这件事。"))

    (out_dir / "index.html").write_text(INDEX_TMPL % {
        "title": case.name + " 设计值对照", "bg": BG, "fg": FG, "dim": DIM,
        "grid": GRID, "panel": PANEL,
        "sub": "由 tools/geom_check.py 生成　·　源：01-scheme 参数表 + 02-geometry 几何文件",
        "cards": "".join(kv) + '<div class="card"><h2>对照图</h2>'
                 '<img src="design-vs-geom.svg" alt="设计值对照"></div>',
    }, encoding="utf-8", newline="")
    return {"ok": True, "case": str(case), "out_dir": str(out_dir),
            "counts": n, "items": data["items"], "rows": data["rows"]}


def main(argv=None):
    ap = argparse.ArgumentParser(description="设计参数表 vs 几何实测值对照")
    ap.add_argument("--case", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    case = Path(args.case).resolve() if args.case else ROOT / "cases" / "DF90-001"
    out = Path(args.out) if args.out else case / "_view" / "check"
    r = build(case, out)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print("设计值对照：%d 项　一致 %d / 偏离 %d / 对不上 %d"
              % (len(r["items"]), r["counts"]["PASS"], r["counts"]["WARN"], r["counts"]["FAIL"]))
        for it in r["items"]:
            if it["verdict"] != "PASS":
                print("  [%s] %s %s：设计 %s　实测 %s"
                      % (it["verdict"], it["row"], it["what"], it["design"], it["actual"]))
        print("  -> " + str(Path(r["out_dir"]) / "index.html"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
