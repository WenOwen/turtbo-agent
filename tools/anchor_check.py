#!/usr/bin/env python3
"""anchor_check.py - 「同转速 + 同环形几何」锚点对照。

为什么要有这个
--------------
`requirements.yaml` 里有一节 `verification_plan.first_point`，写着这个案例的核实点：

    rpm: 5000.0
    outlet_static_pressure_pa_abs: 101325.0
    reason: "v7 已验收锚点，可直接逐项对照：mdot ~13.499 kg/s, PR 1.0139,
             eta_tt 0.85193, rotor torque 34.507 N*m"
    source: user

**但在这之前，没有任何工具会去读它。**

于是 5000 rpm 的算例被拿去比 6100 rpm 的设计目标（90 kgf），得出
「差 -29.7%、达不到要求」—— 而那是两个不同工况的数直接相减。
这跟 G2-7（三表是哪一次求解生成的）是同一类错：**口径不同，而没人查。**

还要比环形几何，不能只比转速
--------------------------
本轮就是栽在这：转速对上了（5000 = 5000），几何没对上 ——
v7 锚点入口轮毂 0.103457，本次求解 0.08，**差 22.7%**。
只比转速不比几何，等于换个方式再犯同一个错。

环形几何的锚点从哪来
------------------
`01-scheme/vN/流道尺寸表.csv` 的 INLET / OUTLET 站位。
理由：它与 v7 锚点同源 —— 那张表的 INLET 轮毂 0.103457 与 v7 XMF 里的
0.1034572 到六位有效数字一致，OUTLET 轮毂 0.125500 对 0.125167（0.27%）。
而且它在案例内、可移植。（v7 的 XMF 在另一个工程目录里，不宜当依赖。）

用法
----
  python tools/anchor_check.py --case cases/DF90-001
  python tools/anchor_check.py --case cases/DF90-001 --out <dir> --json
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from gate_check import latest_version  # noqa: E402  「当前版本是哪个」只有一份定义

RAD_S_TO_RPM = 60.0 / (2.0 * math.pi)

# 锚点几何对照的容差。**不是新发明的阈值** ——
# 方案表与 CFD 域的站位位置本来就略有差别（OUTLET 轮毂 0.125500 对 0.125167 = 0.27%），
# 所以给 2% 的观察带：超过它就不再是"站位定义差异"，而是"另一套几何"。
GEOM_WARN_REL = 0.02

# 与 tools/gate_check.py 的退出码语义保持一致。
VERDICT_EXIT = {"PASS": 0, "FAIL": 4, "WARN": 5, "SKIP": 6}

# 期望值藏在 reason 的自由文本里，用显式正则提，不猜。
# 抓不到就是抓不到 —— 记 SKIP，不记 PASS。
ANCHOR_ITEMS = [
    ("mass_flow_kg_s", "mdot", r"mdot\s*~?\s*([\d.]+)", "rel", "tol_mass_flow_rel"),
    ("pressure_ratio", "PR", r"PR\s*~?\s*([\d.]+)", "rel", "tol_pressure_ratio_rel"),
    ("efficiency_tt", "eta_tt", r"eta_tt\s*~?\s*([\d.]+)", "abs", "tol_efficiency_abs"),
    ("torque_nm", "rotor torque", r"rotor\s+torque\s*~?\s*([\d.]+)", "rel", "tol_torque_rel"),
]

# 方案表的站位名 -> XMF 的站位名
STATIONS = [("Inlet", "INLET"), ("Outlet", "OUTLET")]


def q(text):
    """YAML 里去掉行尾注释。requirements.yaml 是极简 YAML，值可能带 # 注释。"""
    return re.sub(r"\s+#.*$", "", str(text)).strip().strip(chr(34)).strip(chr(39))


def read_yaml_block(path, section, key):
    """从极简 YAML 里取 section: -> key: -> 子键。树内够用，不引第三方。"""
    if not path.is_file():
        return {}
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    out, inside, base = {}, False, None
    for raw in lines:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        s = raw.strip()
        m = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", s)
        if m and indent <= 2:
            if m.group(1) == section and not m.group(2).strip():
                inside, base = True, indent
                continue
            if inside and indent <= (base or 0):
                inside = False
            continue
        if inside:
            m2 = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", s)
            if m2:
                out[m2.group(1)] = q(m2.group(2))
    return out


def load_anchor(case: Path):
    """读 requirements.yaml 的核实点定义，以及方案表里的环形几何。"""
    req = case / "requirements.yaml"
    fp = read_yaml_block(req, "verification_plan", "first_point")
    info = {"requirements": str(req), "raw": fp}

    rpm = None
    try:
        rpm = float(fp.get("rpm"))
    except (TypeError, ValueError):
        rpm = None
    info["rpm"] = rpm
    p_abs = None
    try:
        p_abs = float(fp.get("outlet_static_pressure_pa_abs"))
    except (TypeError, ValueError):
        p_abs = None
    info["outlet_static_pressure_pa_abs"] = p_abs
    info["source"] = fp.get("source") or ""
    info["reason"] = fp.get("reason") or ""

    # 期望值：显式正则，抓不到就 None
    expect = {}
    for field, label, pat, kind, tol_key in ANCHOR_ITEMS:
        m = re.search(pat, info["reason"])
        expect[field] = float(m.group(1)) if m else None
    info["expected"] = expect
    info["expected_labels"] = {f: lb for f, lb, _, _, _ in ANCHOR_ITEMS}

    # 容差：只从 benchmark-targets.json 取，取不到就是 None（不自己发明）
    bt_path = case / "01-scheme" / latest_version(case / "01-scheme") / "inputs" / "benchmark-targets.json"
    targets = {}
    if bt_path.is_file():
        try:
            targets = json.loads(bt_path.read_text(encoding="utf-8-sig"))
        except Exception:
            targets = {}
    info["targets_path"] = str(bt_path)
    info["tolerances"] = {f: targets.get(tk) for f, _, _, _, tk in ANCHOR_ITEMS}

    # 环形几何锚点：方案表的 INLET / OUTLET
    scheme = case / "01-scheme" / latest_version(case / "01-scheme")
    csv_path = scheme / "流道尺寸表.csv"
    ann = {}
    if csv_path.is_file():
        import csv as _csv
        with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
            for row in _csv.DictReader(fh):
                r = {k.strip(): (v or "").strip() for k, v in row.items() if k}
                key = r.get("站位", "").strip().upper()
                if key in ("INLET", "OUTLET"):
                    def f(v):
                        try:
                            return float(v)
                        except (TypeError, ValueError):
                            return None
                    ann[key] = {"hub_radius_m": f(r.get("轮毂半径(m)")),
                                "shroud_radius_m": f(r.get("机匣半径(m)")),
                                "z_m": f(r.get("轴向坐标(m)"))}
    info["annulus"] = ann
    info["annulus_source"] = str(csv_path)
    info["annulus_why"] = ("方案表与 v7 锚点同源：INLET 轮毂 0.103457 对 v7 XMF 的 0.1034572，",
                           "OUTLET 轮毂 0.125500 对 0.125167（0.27%）；且它在案例内、可移植。")
    return info


def _named(parent, tag, name):
    if parent is None:
        return None
    for n in parent.iter(tag):
        if n.attrib.get("name") == name and n.text:
            try:
                return float(n.text)
            except ValueError:
                return None
    return None


def load_solve(case: Path):
    """找当前算例的 .xmf，读转速、环形几何与性能。多个候选时取最新修改的那个。"""
    cands = [p for p in (case / "04-solve").rglob("*.xmf") if p.is_file()]
    if not cands:
        return {"found": False, "why": "04-solve 下没有 .xmf"}
    xmf = max(cands, key=lambda p: p.stat().st_mtime)
    try:
        root_el = ET.parse(xmf).getroot()
    except Exception as exc:
        return {"found": False, "why": "%s 解析失败：%r" % (xmf.name, exc)}

    stations = {}
    for st in root_el.iter("Station"):
        name = st.attrib.get("name")
        geo = next((n for n in st if n.tag == "GeometricalData"), None)
        hub = _named(geo, "float", "Hub radius")
        shr = _named(geo, "float", "Shroud radius")
        stations[name] = {
            "hub_radius_m": hub,
            "shroud_radius_m": shr,
            "sector_area_m2": _named(geo, "float", "Area"),
            "periodicity": _named(geo, "integer", "Number of blades"),
            "analytic_annulus_m2": (math.pi * (shr ** 2 - hub ** 2)) if (hub and shr) else None,
        }

    perf = next((n for n in root_el.iter("Performance")), None)
    outlet_el = next((st for st in root_el.iter("Station")
                      if st.attrib.get("name") == "Outlet"), None)
    inlet_el = next((st for st in root_el.iter("Station")
                     if st.attrib.get("name") == "Inlet"), None)
    rpm = None
    for n in root_el.iter("float"):
        if n.attrib.get("name") == "Rotational speed" and n.text:
            try:
                v = float(n.text)
            except ValueError:
                continue
            if v > 0:
                rpm = v * RAD_S_TO_RPM
                break

    return {
        "found": True,
        "xmf": str(xmf),
        "xmf_rel": xmf.relative_to(case).as_posix(),
        "rpm": rpm,
        "stations": stations,
        "performance": {
            # 质量流量在 **Station** 上，不在 Performance 里 —— 读这里读错过一次。
            "mass_flow_kg_s": (_named(outlet_el, "float", "Mass flow")
                               if _named(outlet_el, "float", "Mass flow") is not None
                               else _named(inlet_el, "float", "Mass flow")),
            "pressure_ratio": _named(perf, "float", "Absolute total pressure ratio"),
            "efficiency_tt": _named(perf, "float", "Isentropic efficiency"),
            "torque_nm": _named(perf, "float", "Torque"),
            "power_w": _named(perf, "float", "Power"),
            "wall_axial_thrust_n": _named(perf, "float", "Axial thrust"),
        },
    }


def _rel(a, b):
    if a is None or b is None:
        return None
    return abs(a - b) / max(abs(a), abs(b), 1e-300)


def compare(case: Path, anchor=None, solve=None):
    anchor = anchor or load_anchor(case)
    solve = solve or load_solve(case)

    out = {"case": str(case), "anchor": anchor, "solve": solve,
           "same_rpm": None, "same_annulus": None, "items": [], "reasons": []}

    if not solve.get("found"):
        out["verdict"] = "SKIP"
        out["reasons"].append("没有可对照的求解结果：" + str(solve.get("why")))
        return out
    if anchor.get("rpm") is None:
        out["verdict"] = "SKIP"
        out["reasons"].append("requirements.yaml 没有定义 verification_plan.first_point.rpm")
        return out

    # ---- 转速 ----
    r_a, r_b = anchor.get("rpm"), solve.get("rpm")
    rel_rpm = _rel(r_a, r_b)
    same_rpm = rel_rpm is not None and rel_rpm <= 1e-3   # 0.1%：够容纳读数的浮点尾巴
    out["rpm"] = {"anchor": r_a, "solve": r_b, "rel_diff": rel_rpm, "match": same_rpm}
    if not same_rpm:
        out["same_rpm"] = False
        out["verdict"] = "SKIP"
        out["reasons"].append(
            "转速对不上（锚点 %.4g rpm / 本次 %s rpm）—— **没得比，不是比过了**。"
            "拿不同转速的数直接相减，正是这个工具要防的错。"
            % (r_a, ("%.4g" % r_b) if r_b is not None else "读不到"))
        return out
    out["same_rpm"] = True

    # ---- 环形几何 ----
    geo_rows, geo_bad, geo_max = [], [], 0.0
    for xmf_name, csv_key in STATIONS:
        a = (anchor.get("annulus") or {}).get(csv_key) or {}
        b = (solve.get("stations") or {}).get(xmf_name) or {}
        row = {"station": xmf_name, "scheme_key": csv_key,
               "anchor_hub_m": a.get("hub_radius_m"),
               "solve_hub_m": b.get("hub_radius_m"),
               "anchor_shroud_m": a.get("shroud_radius_m"),
               "solve_shroud_m": b.get("shroud_radius_m"),
               "hub_rel_diff": _rel(a.get("hub_radius_m"), b.get("hub_radius_m")),
               "shroud_rel_diff": _rel(a.get("shroud_radius_m"), b.get("shroud_radius_m"))}
        worst = max([v for v in (row["hub_rel_diff"], row["shroud_rel_diff"]) if v is not None],
                    default=None)
        row["worst_rel_diff"] = worst
        # 每条属性各自判。**不能整行取最差** —— 机匣半径两边都是 0.3（差 0.0000%），
        # 却会因为同站位的轮毂对不上而被印成 FAIL，读起来像机匣也错了。
        for key in ("hub", "shroud"):
            rel = row.get(key + "_rel_diff")
            if rel is None:
                row[key + "_verdict"] = "SKIP"
            elif rel <= GEOM_WARN_REL:
                row[key + "_verdict"] = "PASS"
            else:
                row[key + "_verdict"] = "FAIL"
        row["verdict"] = ("FAIL" if "FAIL" in (row["hub_verdict"], row["shroud_verdict"])
                          else ("SKIP" if worst is None else "PASS"))
        if row["verdict"] == "FAIL":
            geo_bad.append(row)
            geo_max = max(geo_max, worst or 0.0)
        geo_rows.append(row)
    out["annulus_rows"] = geo_rows
    out["same_annulus"] = not geo_bad and any(r["verdict"] == "PASS" for r in geo_rows)

    # ---- 四个期望值 ----
    perf = solve.get("performance") or {}
    for field, label, _pat, kind, _tk in ANCHOR_ITEMS:
        want = (anchor.get("expected") or {}).get(field)
        got = perf.get(field)
        tol = (anchor.get("tolerances") or {}).get(field)
        # 扭矩必须比**绝对值**。实测：同一份 .xmf 里 Power = T x omega 精确成立，
        # 而入口总温 288.15 K -> 出口 289.77 K（流体获得能量），所以报告的是
        # 「流体作用在转子上的」量，风扇吸功时为负；轴端应供给正扭矩。
        # 锚点那个 34.507 是正值（幅值），不做绝对值会得出一个假的 -193%。
        compare_got = abs(got) if (field == "torque_nm" and got is not None) else got
        item = {"field": field, "label": label, "expected": want, "actual": got,
                "tol": tol, "mode": kind}
        if field == "torque_nm" and got is not None:
            item["sign_convention"] = ("求解器报的是流体作用在转子上的扭矩，吸功时为负；"
                                       "这里按绝对值比 —— 轴端应供给 +%.4g N·m。" % abs(got))
        if want is None or got is None:
            item["delta_shown"] = "-"
            item["verdict"] = "SKIP"
            item["note"] = ("锚点的 reason 里没写这一项" if want is None
                            else "求解结果里读不到这一项")
        else:
            delta = compare_got - want
            item["delta_shown"] = ("%+.4g" % delta) if kind == "abs" else ("%+.2f%%" % (delta / want * 100.0))
            if tol is None:
                # 没有声明容差就是"查不了"。按项目原则记 SKIP，不记 PASS —— 也不记 WARN，
                # 因为 WARN 读起来像"看过了、有点问题"，而这里是"根本没标准可比"。
                item["verdict"] = "SKIP"
                item["note"] = ("基准文件里没有声明这一项的容差 —— **不自己发明阈值**，"
                                "所以只报偏差，不给通过/不通过。")
            else:
                ok = (abs(delta) <= float(tol)) if kind == "abs" \
                    else (abs(delta / want) <= float(tol))
                item["verdict"] = "PASS" if ok else "FAIL"
        out["items"].append(item)

    # ---- 总判定 ----
    fail_items = [i for i in out["items"] if i["verdict"] == "FAIL"]
    warn_items = [i for i in out["items"] if i["verdict"] == "WARN"]
    skip_items = [i for i in out["items"] if i["verdict"] == "SKIP"]
    out["summary"] = {"total": len(out["items"]),
                      "pass": len([i for i in out["items"] if i["verdict"] == "PASS"]),
                      "warn": len(warn_items), "fail": len(fail_items),
                      "skip": len(skip_items)}

    if geo_bad:
        out["verdict"] = "WARN"
        out["reasons"].append(
            "**跨血缘对照**：转速对上了，但环形几何对不上（最大 %.1f%%）——"
            % (geo_max * 100.0)
        )
        for row in geo_bad:
            out["reasons"].append(
                "  %s 轮毂：锚点 %.6g m / 本次 %.6g m（差 %.1f%%）"
                % (row["station"], row["anchor_hub_m"] or 0.0, row["solve_hub_m"] or 0.0,
                   (row["hub_rel_diff"] or 0.0) * 100.0))
        out["reasons"].append(
            "  → **不得声称「复现了锚点」**。两套环形几何不是同一台机器，"
            "流量/效率对得上只是巧合或部分相似，不构成继承关系的证据。"
        )
    if fail_items:
        out["verdict"] = "FAIL"
        out["reasons"].append("有 %d 项超出声明的容差：%s"
                              % (len(fail_items), "、".join(i["label"] for i in fail_items)))
        if geo_bad:
            out["reasons"].append(
                "  ⚠ 但环形几何不同源，所以这一条**不能读成「这台机器不达标」**，"
                "只能读成「和 v7 锚点不可比」。"
                "要判达标，得先让方案与几何回到同一台机器上（回 G2 用电机包络重出轮毂型线）。"
            )
    if not geo_bad and not fail_items:
        out["verdict"] = "WARN" if (warn_items or skip_items) else "PASS"
    if out["verdict"] == "PASS":
        out["reasons"].append("转速与环形几何都对得上，各项都在声明容差内 —— 可以声称复现了这个锚点。")
    return out


def headline(c):
    """给闸门用的一句话摘要。详细理由在 detail / md 里，这里只求一眼看懂。"""
    if c.get("verdict") == "SKIP":
        return ";".join(c.get("reasons") or []) or "无可对照"
    rp = c.get("rpm") or {}
    bits = []
    if rp.get("match"):
        bits.append("转速一致 %s rpm" % ("%.6g" % rp["solve"] if rp.get("solve") else "?"))
    else:
        bits.append("转速不一致（锚点 %s / 本次 %s）" % (rp.get("anchor"), rp.get("solve")))
    rows = c.get("annulus_rows") or []
    worst = max([x.get("worst_rel_diff") or 0.0 for x in rows] or [0.0])
    bits.append("环形几何最大差 %.1f%%（%s）" % (
        worst * 100.0, "同源" if c.get("same_annulus") else "**跨血缘**"))
    s = c.get("summary") or {}
    bits.append("期望值：通过 %s / 未声明容差 %s / 超容差 %s"
                % (s.get("pass", 0), s.get("skip", 0), s.get("fail", 0)))
    bad = [i["label"] for i in (c.get("items") or []) if i.get("verdict") == "FAIL"]
    if bad:
        bits.append("超容差项：" + "、".join(bad))
    return "；".join(bits)


def render_md(c):
    a, s = c["anchor"], c["solve"]
    L = ["# 锚点对照：同转速 + 同环形几何", ""]
    L.append("- 对照物：`requirements.yaml#verification_plan.first_point`（来源：%s）" % (a.get("source") or "未声明"))
    L.append("- 锚点说明：%s" % (a.get("reason") or "（空）"))
    L.append("- 本次求解：`%s`" % (s.get("xmf_rel") or "无"))
    L.append("- 结论：**%s**" % c.get("verdict"))
    L.append("")
    for r in c.get("reasons") or []:
        L.append(r)
    L.append("")
    L.append("## 转速")
    L.append("")
    rp = c.get("rpm") or {}
    L.append("| | 锚点 | 本次 | 相对差 | 一致 |")
    L.append("|---|---|---|---|---|")
    L.append("| 转速 rpm | %s | %s | %s | %s |" % (
        rp.get("anchor"),
        ("%.6g" % rp["solve"]) if rp.get("solve") is not None else "-",
        ("%.3e" % rp["rel_diff"]) if rp.get("rel_diff") is not None else "-",
        "是" if rp.get("match") else "否"))
    L.append("")
    L.append("## 环形几何")
    L.append("")
    L.append("锚点几何取自 `%s` —— %s" % (a.get("annulus_source"), "".join(a.get("annulus_why") or [])))
    L.append("")
    L.append("| 站位 | 项 | 锚点 m | 本次 m | 相对差 | 结论 |")
    L.append("|---|---|---|---|---|---|")
    for row in c.get("annulus_rows") or []:
        for key, lab in (("hub", "轮毂半径"), ("shroud", "机匣半径")):
            rel = row.get(key + "_rel_diff")
            L.append("| %s | %s | %s | %s | %s | %s |" % (
                row["station"], lab, row.get("anchor_" + key + "_m"),
                row.get("solve_" + key + "_m"),
                ("%.4f%%" % (rel * 100.0)) if rel is not None else "-",
                row.get(key + "_verdict")))
    L.append("")
    L.append("## 期望值逐项")
    L.append("")
    L.append("| 项 | 锚点 | 本次 | 偏差 | 容差 | 结论 |")
    L.append("|---|---|---|---|---|---|")
    for i in c.get("items") or []:
        L.append("| %s | %s | %s | %s | %s | %s |" % (
            i["label"], i["expected"], i["actual"], i["delta_shown"],
            i["tol"] if i["tol"] is not None else "未声明", i["verdict"]))
    L.append("")
    # 去重：mdot 与 PR 都因为「没声明容差」而 SKIP，提示语一模一样，
    # 不去重就会在报告里连着印两遍。
    notes = list(dict.fromkeys(i.get("note") for i in (c.get("items") or []) if i.get("note")))
    for n in notes:
        L.append("> " + n)
    if notes:
        L.append("")
    return chr(10).join(L) + chr(10)


def write(out_dir: Path, c):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "anchor_comparison.json").write_text(
        json.dumps(c, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8", newline="")
    (out_dir / "anchor_comparison.md").write_text(
        render_md(c), encoding="utf-8", newline="")
    return out_dir / "anchor_comparison.json"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="anchor_check.py", description="同转速 + 同环形几何 锚点对照")
    ap.add_argument("--case", required=True)
    ap.add_argument("--out")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    case = Path(args.case).resolve()
    if not case.is_dir():
        print("PRECONDITION: 案例目录不存在 " + str(case), file=sys.stderr)
        return 3
    c = compare(case)
    out = Path(args.out).resolve() if args.out else None
    if out is not None and c.get("verdict") != "SKIP":
        write(out, c)
    if args.json:
        print(json.dumps(c, ensure_ascii=False, indent=2))
    else:
        print(render_md(c))
    return VERDICT_EXIT.get(c.get("verdict"), 7)


if __name__ == "__main__":
    raise SystemExit(main())