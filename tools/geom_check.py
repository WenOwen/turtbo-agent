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

# 「当前版本是哪个」只从闸门取一份定义，不在这里另抄。
sys.path.insert(0, str(HERE))
from gate_check import latest_version  # noqa: E402

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
    """SVG/HTML 转义。**必须转义引号** —— 只转 & < > 的话，
    属性位置（title="..."、x="..."）里一个引号就能破边界，
    把后面的内容变成新属性甚至新元素（审核实测过）。"""
    return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;"))
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
def build_rows(case: Path, scheme_version=None, geom_version=None):
    """产出逐项对照。每项：名称 / 设计值 / 实测值 / 偏离 / 结论。

    scheme_version / geom_version：闸门带 --version 检查时，这里必须看同一版。
    以前这里写死 `01-scheme/v1`，几何又是**全版本** glob —— 于是同一份报告里
    「截面数 / 展向」查的是 v9 的副本，「几何 vs 参数表」查的却是 v8 的真交付物，
    而 `--version` 对它逐字无影响（审核实测）。
    """
    sv = scheme_version or latest_version(case / "01-scheme")
    gv = geom_version or latest_version(case / "02-geometry")
    tbl = read_table(case / "01-scheme" / sv / "叶片几何参数表.csv")
    annulus_rows = read_table(case / "01-scheme" / sv / "流道尺寸表.csv")
    geoms = {}
    for p in sorted((case / "02-geometry" / gv).glob("**/*.geomTurbo")):
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
               # 设计表的整行也存进来。**不要靠外层循环变量 r** ——
               # 结论循环是 for rec in out["rows"]，r 是建表循环遗留的最后一行（S1），
               # 用它会让每一行都拿 S1 的设计值去比（实测踩过，R1 轴向位置报成 0.1376）。
               "design_row": dict(r),
               "blades_geom": None, "chord_geom": None,
               "beta1_geom": None, "beta2_geom": None,
               "beta1_par": None, "beta2_par": None,
               "beta1_par_root": None, "beta2_par_root": None,
               "beta1_par_tip": None, "beta2_par_tip": None,
               "solidity_geom": None, "geom_file": gt.name if gt else None}

        # 设计流道站位（z, hub, shroud），来自流道尺寸表
        rec["r_design_mid"] = None
        z_sel = fnum(r.get("轴向坐标(m)"))
        if z_sel is not None:
            best = min(annulus_rows,
                       key=lambda a: abs((fnum(a.get("轴向坐标(m)")) or 1e9) - z_sel),
                       default=None)
            if best is not None:
                rec["r_design_mid"] = fnum(best.get("中径半径(m)"))
                rec["r_design_station"] = best.get("站位")

        rec["annulus_design"] = []
        for a in annulus_rows:
            z_ = fnum(a.get("轴向坐标(m)"))
            h_ = fnum(a.get("轮毂半径(m)"))
            s_ = fnum(a.get("机匣半径(m)"))
            if z_ is not None and h_ is not None and s_ is not None:
                rec["annulus_design"].append((z_, h_, s_))

        if gt:
            import geom_view
            g = geom_view.parse_geomturbo(gt)
            # 几何流道曲线（geomTurbo 里本来就有，之前根本没读）
            ch = g.get("channel") or {}
            if ch.get("hub") and ch.get("shroud"):
                hp, sp = ch["hub"], ch["shroud"]

                def annulus_at(zq, hp=hp, sp=sp):
                    """在几何流道曲线上按 z 线性插值出 hub / shroud 半径。"""
                    def interp(pts):
                        pts = sorted(pts)
                        if zq <= pts[0][0]:
                            return pts[0][1]
                        if zq >= pts[-1][0]:
                            return pts[-1][1]
                        for i in range(len(pts) - 1):
                            z0, r0 = pts[i]
                            z1, r1 = pts[i + 1]
                            if z0 <= zq <= z1 and z1 > z0:
                                return r0 + (r1 - r0) * (zq - z0) / (z1 - z0)
                        return pts[-1][1]
                    return interp(hp), interp(sp)

                rec["annulus_geom"] = {"hub_pts": len(hp), "shroud_pts": len(sp)}
                rec["annulus_at"] = annulus_at
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
        elif pr["matched_by"].startswith("按顺序") or pr["matched_by"].startswith("按叶片数"):
            out["notes"].append("参数表叫 %s，几何文件叫 %s —— **名字不同**，按「%s」配对。"
                                "这种血缘差异必须让接手的人知道。"
                                % (pr["table"], pr["geom"], pr["matched_by"]))

    # 参数表自洽检查 —— **比"设计 vs 几何"更靠前的一步**。
    # 表自己就矛盾的话，拿它当基准去判几何是错的。
    # 实测：S1 行 弦长 0.0900 与 稠度 0.700 在 v1 流道 S1_EXIT 中径 0.210276 处
    # 自相矛盾 6.6%；而几何实测弦长 0.08379 代进去恰好自洽到 0.3%。
    # 也就是说那条"S1 弦长 -6.9%"的 WARN 很可能是**参数表抄错了**，不是几何错。
    for rec in out["rows"]:
        n = rec["name"]
        if rec.get("chord_design") and rec.get("solidity_design") and rec.get("r_design_mid"):
            blades = rec["blades_design"]
            if blades:
                implied = rec["chord_design"] * blades / (2 * math.pi * rec["r_design_mid"])
                dev = (implied - rec["solidity_design"]) / rec["solidity_design"]
                if abs(dev) > 0.02:
                    out["items"].append({
                        "row": n, "what": "参数表自洽（σ=chord·Z/2πr）",
                        "design": "稠度列写 %.3f" % rec["solidity_design"],
                        "actual": "由弦长列算得 %.3f" % implied,
                        "verdict": "FAIL" if abs(dev) > 0.05 else "WARN",
                        "dev_pct": dev * 100,
                        "note": "参数表自己这一行对不上（差 %.1f%%）。"
                                "拿它当基准判几何之前，先确认是弦长抄错还是稠度抄错。"
                                % (dev * 100),
                    })
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
        # 稠度：σ = chord/(2πr/Z) ∝ 1/r —— **两边必须用同一半径**。
        # 之前几何侧用各截面平均半径（R1 0.19435），设计侧定义在流道中径（0.20173），
        # 半径差 3.8% 直接变成 +3.6% 的假偏差；同半径算只有 -0.15%。
        # 这条合同我自己刚写进 memory.md，工具却没做（审核指出）。
        if rec["solidity_design"] and rec.get("chord_geom") and rec.get("r_design_mid"):
            blades = rec["blades_design"] or rec["blades_geom"]
            sigma_same_r = rec["chord_geom"] * blades / (2 * math.pi * rec["r_design_mid"])
            dev = (sigma_same_r - rec["solidity_design"]) / rec["solidity_design"]
            v = "PASS" if abs(dev) <= 0.10 else ("WARN" if abs(dev) <= 0.25 else "FAIL")
            out["items"].append({
                "row": n, "what": "稠度（同半径）",
                "design": "%.3f" % rec["solidity_design"],
                "actual": "%.3f" % sigma_same_r,
                "verdict": v, "dev_pct": dev * 100,
                "note": "两边都用设计中径 r=%.5f m 算（σ∝1/r，不同半径不能直接比）"
                        % rec["r_design_mid"],
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
        # 叶尖间隙。
        # **静子不该有叶尖间隙块** —— 它不转，没有叶尖泄漏。参数表却给 S1 也写了
        # 0.0005 m。第一版见到"几何里没有间隙块"就判 FAIL，那是**假警报**：
        # 报不该报的 FAIL 比漏报更伤信任。判据要按类型分：
        #   转子：必须有间隙块，且与设计值比
        #   静子：几何没有间隙块是对的；参数表写间隙是表自己的定义问题
        drow = rec.get("design_row") or {}
        tg_d = fnum(drow.get("叶尖间隙(m)"))
        tg_g = rec.get("tip_gap_geom")
        is_rotor = (rec.get("type", "").strip().lower() == "rotor")
        if tg_d is not None:
            if tg_g is None and not is_rotor:
                out["items"].append({
                    "row": n, "what": "叶尖间隙 (m)",
                    "design": "%.4f（参数表）" % tg_d,
                    "actual": "几何无间隙块",
                    "verdict": "PASS",
                    "note": "静子不转、没有叶尖泄漏，几何没有间隙块是对的。"
                            "参数表给静子写间隙值属于表本身的定义不清。",
                })
            elif tg_g is None:
                out["items"].append({
                    "row": n, "what": "叶尖间隙 (m)",
                    "design": "%.4f" % tg_d, "actual": "几何里没有间隙块",
                    "verdict": "FAIL",
                    "note": "转子必须有叶尖间隙，几何里没有 —— 会刮蹭",
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

        # 流道半径比对 —— 这才是"两套流道能不能比"的实质判据。
        #
        # 为什么不用"设计站位落在几何 z 范围内"：设计站位来自 v1 流道（全长 0.180 m），
        # 几何来自 v8 流道（全长 0.300 m，1.67 倍）。拿某一个站位去比叶片 z 跨度，
        # 恰好落进去就 PASS —— 没有判别力（审核实测：同 z 处 v8 hub 比 v1 低 22%）。
        # 直接比 hub/shroud 曲线，才能看出"是不是同一个流道"。
        ann = rec.get("annulus_geom")
        if ann:
            worst_hub = worst_shroud = None
            for z_d, h_d, s_d in rec.get("annulus_design", []):
                h_g, s_g = rec.get("annulus_at", lambda z: (None, None))(z_d) \
                    if callable(rec.get("annulus_at")) else (None, None)
                if h_g is None:
                    continue
                dh = (h_g - h_d) / h_d if h_d else 0
                ds = (s_g - s_d) / s_d if s_d else 0
                if worst_hub is None or abs(dh) > abs(worst_hub):
                    worst_hub = dh
                if worst_shroud is None or abs(ds) > abs(worst_shroud):
                    worst_shroud = ds
            if worst_hub is not None:
                w = max(abs(worst_hub), abs(worst_shroud or 0))
                v = "PASS" if w <= 0.02 else ("WARN" if w <= 0.10 else "FAIL")
                out["items"].append({
                    "row": n, "what": "流道半径（同 z 处）",
                    "design": "见流道尺寸表", "actual": "几何 hub/shroud 曲线",
                    "verdict": v,
                    "dev_pct": (worst_hub or 0) * 100,
                    "note": "最大偏差 hub %+.1f%%、shroud %+.1f%%。"
                            % ((worst_hub or 0) * 100, (worst_shroud or 0) * 100)
                            + ("" if v == "PASS" else
                               "两套流道不是同一条曲线 —— 这解释了几何与参数表为何对不上。"),
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
    colx = [24, 132, 300, 470, 660]
    heads = ["叶排", "项目", "设计值（参数表）", "实测值（几何）", "结论"]
    # 配对关系必须显示出来 —— 否则"参数表 S1 其实比的是 R2.geomTurbo"
    # 这件事在界面上完全看不到（审核指出）。
    pmap = {p["table"]: p for p in (data.get("pairing") or [])}
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
        pr = pmap.get(it["row"]) or {}
        gname = pr.get("geom") or "—"
        s.append('<text x="%d" y="%d" fill="%s" font-size="12">%s</text>'
                 % (colx[0], y, FG, esc(it["row"])))
        s.append('<text x="%d" y="%d" fill="%s" font-size="10.5">↔ %s</text>'
                 % (colx[0], y + 13, DIM, esc(gname)))
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
            "counts": n, "items": data["items"], "rows": data["rows"],
            # pairing 与 notes 必须进返回值 —— 否则"参数表 S1 其实比的是 R2.geomTurbo"
            # 这件事在 JSON 和界面上都看不到（审核指出）。
            "pairing": data.get("pairing", []), "notes": data.get("notes", [])}


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
