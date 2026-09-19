#!/usr/bin/env python3
"""scheme_view.py - 把 G2 的「方案」画出来：对标闸门 + 三表摘要 + 溯源。

为什么要有这个
--------------
界面上原来只有几何 / 网格 / CFD 三组图，全是 G3/G4/G5 的产物。
**第 3 步（一维通流方案）一张图都没有** —— 而三表 + 对标闸门恰恰是
整条链上唯一能回答「这个方案对不对」的证据。

画什么
------
  benchmark.svg   对标闸门 B-1..B-7：目标 / 实测 / 偏差 / 容差 / 结论
  scheme.svg      三表摘要（流道站位、叶排、性能关键值）+ 溯源行

溯源行回答的是 G2-7 那条判据：**这三张表到底是哪一次求解生成的？**
目录里同时躺着多份 result.json 时，没有任何记录说明用的是哪一份，
而它们给出的是完全不同的方案。这里按效率/功率/扭矩三项认，认不出就如实说。

用法
----
  python tools/scheme_view.py --case cases/DF90-001
  python tools/scheme_view.py --scheme cases/DF90-001/01-scheme/v1 --out <dir>
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

VERDICT_COLOR = {"PASS": OK, "WARN": WARN, "FAIL": BAD, "SKIP": DIM}
VERDICT_CN = {"PASS": "通过", "WARN": "注意", "FAIL": "没通过", "SKIP": "还查不了"}


def esc(t):
    """SVG/HTML 转义。引号也必须转 —— 只转 & < > 的话，
    属性位置里一个引号就能破边界。"""
    return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace(chr(34), "&quot;").replace(chr(39), "&#39;"))


def num(v):
    try:
        return float(v)
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


def read_csv(path):
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return [{k.strip(): (v or "").strip() for k, v in r.items() if k}
                for r in csv.DictReader(fh)]


def table(s, x, y, w, headers, rows, colw, rowh=27, fs=12):
    """一张表。rows 是 [{cells, color}]；color 只给最后一列上色。"""
    head_h = 30
    s.append('<rect x="%d" y="%d" width="%d" height="%d" fill="%s" rx="6"/>'
             % (x, y, w, head_h, PANEL))
    cx = x + 12
    for i, htxt in enumerate(headers):
        s.append('<text x="%d" y="%d" fill="%s" font-size="11" font-weight="700">%s</text>'
                 % (cx, y + 20, DIM, esc(htxt)))
        cx += colw[i]
    yy = y + head_h
    for k, row in enumerate(rows):
        if k % 2 == 0:
            s.append('<rect x="%d" y="%d" width="%d" height="%d" fill="%s" opacity="0.5"/>'
                     % (x, yy, w, rowh, PANEL))
        color = row.get("color") or FG
        cx = x + 12
        cells = row["cells"]
        for i, cell in enumerate(cells):
            s.append('<text x="%d" y="%d" fill="%s" font-size="%d">%s</text>'
                     % (cx, yy + 18, color if i == len(cells) - 1 else FG, fs, esc(cell)))
            cx += colw[i]
        yy += rowh
    return yy


def kv_block(s, x, y, w, title, pairs):
    """左标题右数值的一小块。"""
    s.append('<rect x="%d" y="%d" width="%d" height="%d" fill="%s" stroke="%s" rx="8"/>'
             % (x, y, w, 34 + 22 * len(pairs), PANEL, GRID))
    s.append('<text x="%d" y="%d" fill="%s" font-size="12" font-weight="700">%s</text>'
             % (x + 14, y + 22, ACC, esc(title)))
    yy = y + 42
    for k, v in pairs:
        s.append('<text x="%d" y="%d" fill="%s" font-size="12">%s</text>'
                 % (x + 14, yy, DIM, esc(k)))
        # text-anchor="end" 是必须的：没有它，x 是文字的**起点**，
        # 右对齐的坐标反而把长数值（58503.99、False）推出面板右边界裁掉。
        s.append('<text x="%d" y="%d" fill="%s" font-size="12" text-anchor="end">%s</text>'
                 % (x + w - 14, yy, FG, esc(v)))
        yy += 22
    return y + 34 + 22 * len(pairs)


def fmt(v, nd=4):
    f = num(v)
    if f is None:
        return "-" if v in (None, "") else str(v)
    if f != 0 and (abs(f) < 1e-3 or abs(f) >= 1e6):
        return "%.3e" % f
    return ("%%.%df" % nd) % f


def find_scheme_dirs(case: Path):
    """按**版本号数值**排序返回可用方案目录。

    以前这里用 sorted() 按字符串排 —— ["v1","v2","v10"] 会选出 v2，
    而闸门（gate_check.latest_version）选的是 v10。
    同一个提交里两套口径：界面画的方案和闸门判的方案不是同一版，且都不告警。
    """
    d = case / "01-scheme"
    if not d.is_dir():
        return []
    out = []
    for p in d.iterdir():
        if p.is_dir() and re.fullmatch(r"v\d+", p.name):
            if (p / "通流计算结果表.csv").is_file() or (p / "benchmark_gate.json").is_file():
                out.append(p)
    return sorted(out, key=lambda p: int(p.name[1:]))


def build_benchmark(scheme: Path, out: Path):
    bg = scheme / "benchmark_gate.json"
    if not bg.is_file():
        return None
    try:
        blob = json.loads(bg.read_text(encoding="utf-8"))
    except Exception:
        return None
    items = blob.get("items") or []
    targets = blob.get("targets") or {}
    verdict = str(blob.get("verdict") or "?").upper()
    summary = blob.get("summary") or {}

    w = 1180
    colw = [70, 250, 150, 170, 120, 90, 100]
    rows = []
    for i in items:
        v = str(i.get("verdict") or "?").upper()
        rows.append({
            "cells": [str(i.get("id") or ""), str(i.get("title") or ""),
                      fmt(i.get("target")), fmt(i.get("actual")),
                      str(i.get("delta_shown") or "-"), str(i.get("tol")),
                      VERDICT_CN.get(v, v)],
            "color": VERDICT_COLOR.get(v, FG),
        })
    h = 108 + 30 + 27 * len(rows) + 100
    s = svg_open(w, h, "这版方案和基准对上了吗",
                 "基准数字来自：" + str(targets.get("source") or "（没写来源 —— 不允许）"))
    s.append('<text x="18" y="76" fill="%s" font-size="13">结论：</text>' % DIM)
    s.append('<text x="70" y="76" fill="%s" font-size="15" font-weight="700">%s</text>'
             % (VERDICT_COLOR.get(verdict, FG), esc(VERDICT_CN.get(verdict, verdict))))
    s.append('<text x="180" y="76" fill="%s" font-size="12">通过 %s / 注意 %s / 没通过 %s / 还查不了 %s</text>'
             % (DIM, summary.get("pass", "?"), summary.get("warn", "?"),
                summary.get("fail", "?"), summary.get("skip", "?")))
    table(s, 18, 92, w - 36,
          ["id", "项目", "目标", "实测", "偏差", "容差", "结论"], rows, colw)
    y = 92 + 30 + 27 * len(rows) + 18
    notes = [
        "总压比和目标一致不算证据 —— 它是反推出来的目标值。真正的证据是效率、功率、扭矩。",
        "B-7 是软性的一条：它不通过通常说明输入时的算法口径写错了，不是求解器坏了。",
        "「容差」列空着 = 这一条没写允许多大偏差，那就没法判对错。",
    ]
    for i, t in enumerate(notes):
        s.append('<text x="18" y="%d" fill="%s" font-size="11">· %s</text>'
                 % (y + 18 * i, DIM, esc(t)))
    s.append("</svg>")
    (out / "benchmark.svg").write_text(chr(10).join(s), encoding="utf-8")
    return {"verdict": verdict, "items": len(items), "source": targets.get("source") or ""}


def trace_result(scheme: Path, perf):
    """G2-7：这三张表是哪一次求解生成的？按效率/功率/扭矩三项认。"""
    cands = sorted(p for p in scheme.rglob("result.json") if p.is_file())
    hit, lines = [], []
    for p in cands:
        try:
            blob = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        sm = blob.get("summary") or {}
        got = 0
        for label, key in (("总总效率", "efficiency_tt"), ("轴功率", "power_w"),
                           ("扭矩", "torque_nm")):
            want = num(perf.get(label))
            actual = sm.get(key)
            if want is None or actual is None:
                continue
            if abs(float(actual) - want) / max(abs(float(actual)), abs(want), 1e-300) <= 1e-9:
                got += 1
        rel = p.relative_to(scheme).as_posix()
        lines.append((rel, got, sm.get("efficiency_tt"), sm.get("power_w")))
        if got == 3:
            hit.append(rel)
    return cands, hit, lines


def build_scheme(scheme: Path, out: Path):
    ann = read_csv(scheme / "流道尺寸表.csv")
    blades = read_csv(scheme / "叶片几何参数表.csv")
    perf_rows = read_csv(scheme / "通流计算结果表.csv")
    if not (ann or blades or perf_rows):
        return None
    perf = {}
    for r in perf_rows:
        k = (r.get("参数名称") or "").strip()
        if k:
            perf[k] = (r.get("数值") or "").strip()

    cands, hit, lines = trace_result(scheme, perf)

    w = 1180
    cw = (w - 36 - 24) // 3
    top = 92
    body_h = max(34 + 27 * (len(ann) + 1) + 20,
                 34 + 27 * (len(blades) + 1) + 20,
                 34 + 22 * 10 + 20)
    h = top + body_h + 60 + 30 + 27 * max(1, len(lines)) + 40
    try:
        sub = scheme.relative_to(ROOT).as_posix()
    except ValueError:
        sub = str(scheme)
    s = svg_open(w, h, "方案三表 · 这版方案长什么样", sub)

    table(s, 18, top, cw, ["站位", "z(m)", "hub r", "机匣 r"],
          [{"cells": [str(a.get("站位") or ""), fmt(a.get("轴向坐标(m)"), 4),
                      fmt(a.get("轮毂半径(m)"), 4), fmt(a.get("机匣半径(m)"), 4)]}
           for a in ann], [96, 88, 88, 88])

    x2 = 18 + cw + 12
    # 列宽合计必须 <= cw - 12，否则最后几列被面板右边界裁掉（实测踩过：
    # 原列宽合计 426 > 373，β2 列只剩 "-61" 这种半截数字）。
    table(s, x2, top, cw, ["叶排", "叶片数", "弦长 m", "稠度", "β1°", "β2°"],
          [{"cells": [str(b.get("叶排") or ""), str(b.get("叶片数") or ""),
                      fmt(b.get("弦长(m)"), 4), fmt(b.get("稠度"), 3),
                      fmt(b.get("进口金属角(deg,相对轴向)"), 1),
                      fmt(b.get("出口金属角(deg,相对轴向)"), 1)]}
           for b in blades], [50, 58, 66, 50, 56, 56])

    x3 = x2 + cw + 12
    pairs = [("求解器", str(perf.get("求解器") or "-")),
             ("状态", str(perf.get("状态") or "-")),
             ("转速 rpm", str(perf.get("转速") or "-")),
             ("进口流量 kg/s", str(perf.get("进口质量流量") or "-")),
             ("出口流量 kg/s", str(perf.get("出口质量流量") or "-")),
             ("总总效率", fmt(perf.get("总总效率"), 4)),
             ("轴功率 W", fmt(perf.get("轴功率"), 1)),
             ("扭矩 N·m", fmt(perf.get("扭矩"), 2)),
             ("机匣半径 m", fmt(perf.get("机匣半径"), 4)),
             ("工程可行", str(perf.get("工程可行") or "-")),
             ("　↑ 为什么是 False", "见下方说明")]
    kv_block(s, x3, top, cw, "性能与约束", pairs)

    # 「工程可行 = False」必须当场解释。判据 G2-8 自己写着
    # 「表里只写 False 会被读成方案不可行」—— 界面不能正好这么干。
    y = top + body_h + 22
    feas = str(perf.get("工程可行") or "").strip().lower()
    if feas == "false":
        why = ("工程可行 = False：这是说**设计目标**没全中（效率/反力度/流量系数三项），"
               "不是工程约束不通过。工程约束全部通过 —— 这两件事在表里都叫「约束」，"
               "很容易看混。")
        s.append('<text x="18" y="%d" fill="%s" font-size="12">%s</text>'
                 % (y, WARN, esc(why)))
        y += 22
    if len(hit) == 1:
        head = "溯源：这三张表来自 %s（候选 %d 份，唯一命中）" % (hit[0], len(cands))
        col = OK if len(cands) == 1 else WARN
    elif not cands:
        head = "溯源：01-scheme 下找不到任何 result.json —— 这三张表追不到来源"
        col = BAD
    else:
        head = ("溯源：候选 %d 份，命中 %d 份 —— 无法确定用的是哪一份"
                % (len(cands), len(hit)))
        col = BAD
    s.append('<text x="18" y="%d" fill="%s" font-size="13" font-weight="700">%s</text>'
             % (y, col, esc(head)))
    for i, (rel, got, eta, pw) in enumerate(lines):
        s.append('<text x="34" y="%d" fill="%s" font-size="11">%s　效率 %s　功率 %s　命中 %d/3</text>'
                 % (y + 22 + 18 * i, DIM, esc(rel), fmt(eta, 4), fmt(pw, 1), got))
    s.append("</svg>")
    (out / "scheme.svg").write_text(chr(10).join(s), encoding="utf-8")
    return {"rows": {"annulus": len(ann), "blades": len(blades), "perf": len(perf_rows)},
            "trace": {"candidates": len(cands), "hit": hit}}


INDEX_TMPL = """<!doctype html><html lang="zh"><meta charset="utf-8">
<title>方案视图</title>
<style>body{background:#0d1117;color:#c9d1d9;font:14px ui-monospace,Consolas,monospace;
margin:0;padding:20px}h2{font-size:15px;margin:14px 0 8px}p{color:#8b949e;font-size:12px;
margin:0 0 16px}img{width:100%;border:1px solid #21262d;border-radius:8px;margin-bottom:18px}
</style><h2>方案</h2><p>__SUB__</p>__BODY__</html>"""


def build(scheme: Path, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    made = {}
    b = build_benchmark(scheme, out)
    if b:
        made["benchmark"] = b
    c = build_scheme(scheme, out)
    if c:
        made["scheme"] = c
    if not made:
        raise ValueError("01-scheme 下没有可画的东西（三表与 benchmark_gate.json 都不在）")
    body = ""
    for f, t in (("benchmark.svg", "对标闸门"), ("scheme.svg", "三表与溯源")):
        if (out / f).is_file():
            body += '<h2>%s</h2><img src="%s" alt="%s">' % (t, f, t)
    (out / "index.html").write_text(
        INDEX_TMPL.replace("__SUB__", esc(str(scheme))).replace("__BODY__", body),
        encoding="utf-8")
    return made


def main(argv=None):
    ap = argparse.ArgumentParser(prog="scheme_view.py", description="G2 方案可视化")
    ap.add_argument("--case")
    ap.add_argument("--scheme")
    ap.add_argument("--out")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.scheme:
        scheme = Path(args.scheme).resolve()
        if not scheme.is_dir():
            print("PRECONDITION: 目录不存在 " + str(scheme), file=sys.stderr)
            return 3
    elif args.case:
        dirs = find_scheme_dirs(Path(args.case).resolve())
        if not dirs:
            print("PRECONDITION: 找不到 01-scheme/vN", file=sys.stderr)
            return 3
        scheme = dirs[-1]
    else:
        ap.error("需要 --case 或 --scheme")
        return 2

    out = Path(args.out).resolve() if args.out else scheme.parent.parent / "_view" / "scheme"
    made = build(scheme, out)
    if args.json:
        print(json.dumps({"ok": True, "scheme": str(scheme), "out": str(out),
                          "made": made}, ensure_ascii=False, indent=2))
    else:
        print("已生成方案视图：" + str(out))
        for k, v in made.items():
            print("  " + k + " " + json.dumps(v, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())