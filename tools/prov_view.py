#!/usr/bin/env python3
"""prov_view.py - 把「造型溯源」画出来：参数表 → 几何 这条链哪一环断了。

为什么要有这个
--------------
`cascade-forge-geometry-handoff/SKILL.md` 的失败出口写着「不手工编辑几何文件」，
但这条规则长期没有检查 id —— 于是人工调过轮毂、人工选过弯掠的几何在工具眼里完全合法。
DF90-001 的 v8 就是这么过去的：它是设计决策的载体，不是参数表的推导结果。

这个视图把那条链摊开，逐环标出证据状态：

    参数表 ──→ SectionSchedule ──→ .geomTurbo ──→ *.manifest.json
     原生          _automation/g3      造型产物        机器可读溯源

任何一环缺证据，链就断在那里 —— 断点就是「这套几何能不能从参数表复现」的答案。

用法
----
  python tools/prov_view.py --case cases/DF90-001
  python tools/prov_view.py --case cases/DF90-001 --out <dir>
"""

from __future__ import annotations

import argparse
import csv
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
ACC = "#58a6ff"
OK = "#3fb950"
WARN = "#d29922"
BAD = "#f85149"


def esc(t):
    return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace(chr(34), "&quot;").replace(chr(39), "&#39;"))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def read_csv(path):
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return [{k.strip(): (v or "").strip() for k, v in r.items() if k}
                for r in csv.DictReader(fh)]


# 「当前版本是哪个」只能有一份定义。以前 gate_check / prov_view / liveview 各抄一份，
# scheme_view 还抄错成字符串排序。统一从 gate_check 取。
sys.path.insert(0, str(HERE))
from gate_check import latest_version  # noqa: E402


def _rel(p, base):
    """相对路径。**别用相对案例根**：02-geometry/v8/autoblade/R1_13span/R1.geomTurbo
    有 47 个字符，11px 字号下约 282px，比盒子还宽 —— 会直接画出框外。"""
    try:
        return p.relative_to(base).as_posix()
    except ValueError:
        return p.name


def box(s, x, y, w, h, title, lines, color):
    s.append('<rect x="%d" y="%d" width="%d" height="%d" fill="%s" stroke="%s" rx="8"/>'
             % (x, y, w, h, PANEL, color))
    s.append('<text x="%d" y="%d" fill="%s" font-size="12" font-weight="700">%s</text>'
             % (x + 12, y + 22, color, esc(title)))
    for i, t in enumerate(lines):
        s.append('<text x="%d" y="%d" fill="%s" font-size="11">%s</text>'
                 % (x + 12, y + 42 + 16 * i, DIM, esc(t)))


def arrow(s, x0, x1, y):
    s.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-width="1.5"/>'
             % (x0, y, x1, y, GRID))
    s.append('<polygon points="%d,%d %d,%d %d,%d" fill="%s"/>'
             % (x1 - 7, y - 4, x1, y, x1 - 7, y + 4, GRID))


def collect(case: Path):
    sv = latest_version(case / "01-scheme")
    gv = latest_version(case / "02-geometry")
    scheme = case / "01-scheme" / sv
    groot = case / "02-geometry" / gv
    tbl = read_csv(scheme / "叶片几何参数表.csv")

    geoms = [p for p in sorted(groot.rglob("*.geomTurbo"))
             if ".bak" not in p.name.lower()] if groot.is_dir() else []
    counts = {}
    for p in geoms:
        try:
            import geom_view
            g = geom_view.parse_geomturbo(p)
            rows = g.get("rows") or []
            counts[p] = {"periodicity": (rows[0].get("periodicity") if rows else None),
                         "sections": len(rows[0].get("sections") or []) if rows else 0,
                         "name": (rows[0].get("name") if rows else None)}
        except Exception as exc:
            counts[p] = {"error": repr(exc)}

    sched = {}
    sd = case / "_automation" / "g3"
    if sd.is_dir():
        for f in sorted(sd.glob("schedule-*.json")):
            try:
                blob = json.loads(f.read_text(encoding="utf-8"))
                sched[f.stem.replace("schedule-", "")] = (
                    blob.get("output_section_count") or len(blob.get("sections") or []))
            except Exception:
                sched[f.stem.replace("schedule-", "")] = None

    manifests = [p for p in groot.rglob("*.manifest.json")] if groot.is_dir() else []
    provdocs = [p for p in groot.rglob("*PROVENANCE*.md")] if groot.is_dir() else []

    # 配对：同名 → 按叶片数 → 按顺序（与 gate_check / geom_check 同规则）
    by_name = {}
    for x in tbl:
        by_name.setdefault((x.get("叶排") or "").strip(), x)
    used, pairs = set(), []
    for p in geoms:
        info = counts.get(p) or {}
        nb = info.get("periodicity")
        trow, how = None, "没找到"
        for key, cand in by_name.items():
            if key in used:
                continue
            w = num(cand.get("叶片数"))
            if w is not None and nb and int(w) == int(nb):
                trow, how = cand, "按叶片数"
                break
        if trow is None:
            for key, cand in by_name.items():
                if key not in used:
                    trow, how = cand, "按顺序（叶片数没对上，存疑）"
                    break
        if trow is not None:
            used.add((trow.get("叶排") or "").strip())
        pairs.append({"geom": p, "info": info, "table": trow, "how": how})

    return {"scheme": scheme, "groot": groot, "tbl": tbl, "pairs": pairs,
            "sched": sched, "manifests": manifests, "provdocs": provdocs,
            "geoms": geoms}


def build(case: Path, out: Path):
    d = collect(case)
    if not d["geoms"]:
        raise ValueError("02-geometry 下没有 .geomTurbo，没有可画的溯源链")

    w = 1180
    bw, gap = 268, 22
    row_h = 122
    top = 96
    n = len(d["pairs"])
    h = top + row_h * n + 150
    s = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
         'viewBox="0 0 %d %d" font-family="ui-monospace,Consolas,monospace">' % (w, h, w, h),
         '<rect width="%d" height="%d" fill="%s"/>' % (w, h, BG),
         '<text x="18" y="30" fill="%s" font-size="16" font-weight="700">%s</text>'
         % (FG, esc("这套几何能从参数表算出来吗")),
         '<text x="18" y="52" fill="%s" font-size="12">%s</text>'
         % (DIM, esc("参数表 → 截面表 → 几何文件 → 来源记录；哪一环没有证据，链就断在那里")),
         ]

    for i, pr in enumerate(d["pairs"]):
        y = top + row_h * i
        trow = pr["table"] or {}
        name = (trow.get("叶排") or "?")
        info = pr["info"]
        key = name
        x = 18
        # 1 参数表
        box(s, x, y, bw, 88, "① 参数表（原生）",
            ["01-scheme/%s/叶片几何参数表.csv" % latest_version(case / "01-scheme"),
             "叶排 %s　叶片数 %s　弦长 %s m" % (name, trow.get("叶片数") or "-",
                                              trow.get("弦长(m)") or "-"),
             "稠度 %s　β1 %s°　β2 %s°" % (trow.get("稠度") or "-",
                                        trow.get("进口金属角(deg,相对轴向)") or "-",
                                        trow.get("出口金属角(deg,相对轴向)") or "-")],
            OK if trow else BAD)
        arrow(s, x + bw, x + bw + gap, y + 44)
        x += bw + gap
        # 2 SectionSchedule
        nsc = d["sched"].get(name)
        box(s, x, y, bw, 88, "② 截面表（交接）",
            ["_automation/g3/schedule-%s.json" % name,
             ("截面数 %s" % nsc) if nsc else "文件不在 —— 交接这一步没有留痕",
             "由 tools/g3_schedule.py 生成" if nsc else "参数表到造型之间没有留痕"],
            OK if nsc else WARN)
        arrow(s, x + bw, x + bw + gap, y + 44)
        x += bw + gap
        # 3 geomTurbo
        gname = pr["geom"].name
        secs = info.get("sections")
        box(s, x, y, bw, 88, "③ 几何文件",
            ["%s" % _rel(pr["geom"], d["groot"]),
             "内部名 %s　周期 %s　截面 %s" % (info.get("name") or "-",
                                            info.get("periodicity") or "-", secs),
             "配对依据：%s" % pr["how"]],
            OK if not info.get("error") else BAD)
        arrow(s, x + bw, x + bw + gap, y + 44)
        x += bw + gap
        # 4 manifest
        have = [m for m in d["manifests"] if m.parent == pr["geom"].parent]
        box(s, x, y, bw, 88, "④ 来源记录",
            ["有来源记录（*.manifest.json）" if have else "没有来源记录",
             ("找到 %d 份" % len(have)) if have else "无法证明它由参数表导出",
             ("人工说明 %d 份（不是机器可读）" % len(d["provdocs"])) if d["provdocs"]
             else "也没有人工说明"],
            OK if have else BAD)

    y = top + row_h * n + 20
    ok_rows = [p for p in d["pairs"] if p["table"]]
    concl = []
    concl.append(("参数表里有 %d 个叶排，几何里 %d 个文件，配上 %d 对"
                  % (len(d["tbl"]), len(d["geoms"]), len(ok_rows)),
                  OK if len(ok_rows) == len(d["tbl"]) == len(d["geoms"]) else WARN))
    concl.append(("截面表有 %d 份（%s）"
                  % (len(d["sched"]), "、".join(sorted(d["sched"])) or "无"),
                  OK if d["sched"] else WARN))
    concl.append(("机器可读的来源记录 %d 份" % len(d["manifests"]),
                  OK if d["manifests"] else BAD))
    if not d["manifests"]:
        concl.append(("结论：这套几何证明不了它是从参数表算出来的", BAD))
    for i, (t, c) in enumerate(concl):
        s.append('<text x="18" y="%d" fill="%s" font-size="12">%s</text>'
                 % (y + 20 * i, c, esc(t)))
    s.append("</svg>")
    out.mkdir(parents=True, exist_ok=True)
    (out / "provenance.svg").write_text(chr(10).join(s), encoding="utf-8")
    body = '<h2>参数表 → 几何</h2><img src="provenance.svg" alt="provenance">'
    (out / "index.html").write_text(
        '<!doctype html><html lang="zh"><meta charset="utf-8"><title>造型溯源</title>'
        '<style>body{background:#0d1117;color:#c9d1d9;font:14px ui-monospace,Consolas,monospace;'
        'margin:0;padding:20px}h2{font-size:15px;margin:14px 0 8px}img{width:100%%;'
        'border:1px solid #21262d;border-radius:8px}</style>' + body + "</html>",
        encoding="utf-8")
    return {"rows": len(d["pairs"]), "manifests": len(d["manifests"]),
            "schedules": sorted(d["sched"]), "provenance_docs": len(d["provdocs"])}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="prov_view.py", description="造型溯源可视化")
    ap.add_argument("--case", required=True)
    ap.add_argument("--out")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    case = Path(args.case).resolve()
    if not case.is_dir():
        print("PRECONDITION: 案例目录不存在 " + str(case), file=sys.stderr)
        return 3
    out = Path(args.out).resolve() if args.out else case / "_view" / "provenance"
    made = build(case, out)
    if args.json:
        print(json.dumps({"ok": True, "out": str(out), "made": made},
                         ensure_ascii=False, indent=2))
    else:
        print("已生成溯源图：" + str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())