#!/usr/bin/env python3
"""build_dashboard.py - 生成单文件自包含 HTML 看板。

约束
----
- **零外部依赖**：不引 CDN、不引字体、不引 JS 库。断网双击可看。
- **只读**：不改任何案例文件；只写 06-delivery/<version>/dashboard.html。
- **数据来自磁盘**：manifest.json / STATE.json / LOG.md / _replay/*/replay_audit.json
  / sweep_summary.csv。不臆造。

用法
----
  python tools/build_dashboard.py --case cases/DF90-001 --version v1
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import html
import json
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_PRECONDITION = 3
EXIT_INTERNAL = 5

LF = chr(10)

STAGES = [
    ("G0", "需求"), ("G1", "设计大纲"), ("G2", "1D/通流方案"), ("G3", "叶片造型"),
    ("G4", "网格"), ("G5", "求解"), ("G6", "后处理与交付"),
]

CSS = """
*{box-sizing:border-box}
body{margin:0;font:14px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;
     background:#f6f7f9;color:#1a1d21}
.wrap{max-width:1180px;margin:0 auto;padding:28px 20px 80px}
h1{font-size:22px;margin:0 0 4px}
h2{font-size:16px;margin:32px 0 12px;padding-bottom:6px;border-bottom:1px solid #e3e6ea}
.sub{color:#6b7280;font-size:13px;margin-bottom:20px}
.card{background:#fff;border:1px solid #e3e6ea;border-radius:8px;padding:16px 18px;margin-bottom:14px}
.kv{display:grid;grid-template-columns:150px 1fr;gap:6px 14px;font-size:13px}
.kv dt{color:#6b7280}
.kv dd{margin:0;font-family:ui-monospace,Consolas,monospace;word-break:break-all}
.tl{display:flex;gap:6px;flex-wrap:wrap}
.st{flex:1 1 130px;border:1px solid #e3e6ea;border-radius:6px;padding:10px 12px;background:#fff}
.st .id{font-weight:700;font-size:12px;color:#6b7280}
.st .nm{font-size:13px;margin-top:2px}
.st .bd{display:inline-block;margin-top:8px;font-size:11px;padding:2px 8px;border-radius:99px}
.s-done{background:#e7f6ec;color:#17703a;border-color:#bfe6cd}
.s-in_progress{background:#e8f0fe;color:#1a56b8;border-color:#c3d7fb}
.s-blocked{background:#fdecec;color:#a32020;border-color:#f6c9c9}
.s-pending{background:#f3f4f6;color:#6b7280}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th,td{text-align:left;padding:7px 9px;border-bottom:1px solid #eef0f3;vertical-align:top}
th{background:#fafbfc;color:#6b7280;font-weight:600;font-size:12px}
td.mono,th.mono{font-family:ui-monospace,Consolas,monospace;font-size:11.5px}
.v{font-weight:700;font-size:11px;padding:1px 7px;border-radius:99px;white-space:nowrap}
.v-PASS{background:#e7f6ec;color:#17703a}
.v-WARN{background:#fff6e5;color:#8a5a00}
.v-FAIL{background:#fdecec;color:#a32020}
.v-SKIP{background:#f3f4f6;color:#6b7280}
.v-INFO{background:#eef2ff;color:#3730a3}
.v-BLOCKED{background:#fdecec;color:#a32020}
pre{background:#0f1115;color:#d7dce2;padding:14px;border-radius:6px;overflow-x:auto;
    font:12px/1.6 ui-monospace,Consolas,monospace;max-height:460px}
.note{font-size:12.5px;color:#6b7280;margin:8px 0 0}
.bar{height:8px;background:#eef0f3;border-radius:99px;overflow:hidden;margin-top:6px}
.bar>i{display:block;height:100%;background:#17703a}
.warnbox{background:#fff8e6;border:1px solid #f0dca8;border-radius:6px;padding:12px 14px;font-size:13px}
svg{max-width:100%;height:auto}
.legend{font-size:12px;color:#6b7280;margin-top:6px}
"""


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def read_json(path: Path, default=None):
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def verdict_span(v: str) -> str:
    return '<span class="v v-' + esc(v) + '">' + esc(v) + "</span>"


def scatter_svg(points, width=1040, height=340, xlabel="", ylabel="", title="") -> str:
    """points: [(x, y, label, accepted_bool)]"""
    if not points:
        return ""
    pad_l, pad_r, pad_t, pad_b = 62, 22, 26, 46
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    if x1 - x0 < 1e-9:
        x1 = x0 + 1.0
    if y1 - y0 < 1e-9:
        y1 = y0 + 1.0
    mx, my = (x1 - x0) * 0.06, (y1 - y0) * 0.08
    x0, x1 = x0 - mx, x1 + mx
    y0, y1 = y0 - my, y1 + my

    def sx(v):
        return pad_l + (v - x0) / (x1 - x0) * (width - pad_l - pad_r)

    def sy(v):
        return height - pad_b - (v - y0) / (y1 - y0) * (height - pad_t - pad_b)

    parts = ['<svg viewBox="0 0 %d %d" xmlns="http://www.w3.org/2000/svg">' % (width, height)]
    parts.append('<rect width="%d" height="%d" fill="#fff"/>' % (width, height))
    for i in range(6):
        gy = pad_t + i * (height - pad_t - pad_b) / 5.0
        val = y1 - i * (y1 - y0) / 5.0
        parts.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#eef0f3"/>'
                     % (pad_l, gy, width - pad_r, gy))
        parts.append('<text x="%d" y="%.1f" font-size="10" fill="#9aa1ab" text-anchor="end">%.4g</text>'
                     % (pad_l - 8, gy + 3, val))
    for i in range(6):
        gx = pad_l + i * (width - pad_l - pad_r) / 5.0
        val = x0 + i * (x1 - x0) / 5.0
        parts.append('<text x="%.1f" y="%d" font-size="10" fill="#9aa1ab" text-anchor="middle">%.4g</text>'
                     % (gx, height - pad_b + 16, val))
    parts.append('<text x="%.1f" y="%d" font-size="11" fill="#6b7280" text-anchor="middle">%s</text>'
                 % ((pad_l + width - pad_r) / 2.0, height - 8, esc(xlabel)))
    parts.append('<text x="14" y="%.1f" font-size="11" fill="#6b7280" transform="rotate(-90 14 %.1f)" '
                 'text-anchor="middle">%s</text>' % (height / 2.0, height / 2.0, esc(ylabel)))
    parts.append('<text x="%d" y="17" font-size="12" fill="#1a1d21" font-weight="600">%s</text>'
                 % (pad_l, esc(title)))
    for x, y, label, acc in points:
        color = "#1a56b8" if acc else "#c0c4cc"
        parts.append('<circle cx="%.1f" cy="%.1f" r="3.2" fill="%s"><title>%s</title></circle>'
                     % (sx(x), sy(y), color, esc(label)))
    parts.append("</svg>")
    return "".join(parts)


def build(case: Path, version: str) -> str:
    manifest = read_json(case / "manifest.json", {}) or {}
    state = read_json(case / "STATE.json", {}) or {}

    stage_html = []
    for sid, name in STAGES:
        st = (state.get("stages") or {}).get(sid, {})
        status = st.get("status", "pending")
        stage_html.append(
            '<div class="st"><div class="id">' + esc(sid) + '</div>'
            '<div class="nm">' + esc(name) + '</div>'
            '<span class="bd s-' + esc(status) + '">' + esc(status) + "</span></div>"
        )

    art_rows = []
    for a in sorted(manifest.get("artifacts", []), key=lambda x: (x.get("stage", ""), x.get("ts", ""))):
        prov = a.get("provenance") or {}
        art_rows.append(
            "<tr>"
            "<td class='mono'>" + esc(a.get("stage")) + "</td>"
            "<td>" + esc(a.get("kind")) + "</td>"
            "<td class='mono'>" + esc(a.get("path")) + "</td>"
            "<td class='mono'>" + esc(a.get("version")) + "</td>"
            "<td>" + verdict_span(a.get("verdict", "INFO")) + "</td>"
            "<td class='mono'>" + esc((a.get("sha256") or "")[:16]) + "</td>"
            "<td class='mono'>" + esc(prov.get("from") or "—") + "</td>"
            "<td class='mono'>" + esc(a.get("ts")) + "</td>"
            "</tr>"
        )

    # 回放审计
    replay_blocks = []
    replay_dir = case / "_replay"
    if replay_dir.is_dir():
        for sub in sorted(p for p in replay_dir.iterdir() if p.is_dir()):
            rep = read_json(sub / "replay_audit.json")
            if not rep:
                continue
            rows = []
            for item in rep.get("checks", []):
                rows.append(
                    "<tr><td class='mono'>" + esc(item["id"]) + "</td>"
                    "<td>" + esc(item["title"]) + "</td>"
                    "<td>" + esc(item["criteria"]) + "</td>"
                    "<td class='mono'>" + esc(item["measured"]) + "</td>"
                    "<td>" + verdict_span(item["verdict"]) + "</td>"
                    "<td class='mono'>" + esc(item["source"]) + "</td></tr>"
                )
            s = rep.get("summary", {})
            replay_blocks.append(
                '<div class="card"><h2 style="margin-top:0">回放审计：' + esc(rep.get("label")) + "</h2>"
                "<p class='note'>基准：<span class='mono'>" + esc(rep.get("baseline")) + "</span>　"
                "时间：" + esc(rep.get("time")) + "　结论："
                + verdict_span(rep.get("verdict")) + "　"
                "(PASS " + esc(s.get("pass")) + " / WARN " + esc(s.get("warn"))
                + " / FAIL " + esc(s.get("fail")) + ")</p>"
                "<table><thead><tr><th>id</th><th>检查</th><th>判据</th><th>实测</th><th>结论</th><th>来源</th></tr></thead>"
                "<tbody>" + "".join(rows) + "</tbody></table></div>"
            )

    # 性能曲线
    chart = ""
    summary_paths = []
    for base in ("04-solve", "05-post", "_replay"):
        d = case / base
        if d.is_dir():
            summary_paths += list(d.glob("**/sweep_summary.csv"))
    if summary_paths:
        src = summary_paths[0]
        try:
            with src.open("r", encoding="utf-8-sig", newline="") as fh:
                rows = list(csv.DictReader(fh))
            pts = []
            for row in rows:
                try:
                    mf = float(row["mf_in"])
                    pr = float(row["pressure_ratio"])
                except (KeyError, TypeError, ValueError):
                    continue
                acc = row.get("state") == "accepted"
                pts.append((mf, pr, row.get("case", "") + " | " + row.get("state", ""), acc))
            if pts:
                chart = ('<div class="card"><h2 style="margin-top:0">总压比 – 进口质量流量</h2>'
                         + scatter_svg(pts, xlabel="mdot_in (kg/s)", ylabel="pressure ratio",
                                       title="accepted = 蓝；其余 = 灰（悬停查看工况名）")
                         + '<p class="legend">数据源：<span class="mono">' + esc(src) + "</span>　"
                         + "蓝点 " + str(len([p for p in pts if p[3]])) + " / 总 " + str(len(pts))
                         + "</p></div>")
        except Exception:
            chart = ""

    log_text = ""
    log_path = case / "LOG.md"
    if log_path.is_file():
        text = log_path.read_text(encoding="utf-8")
        log_text = text[-14000:]

    mem_text = ""
    mem_path = case / "memory.md"
    if mem_path.is_file():
        mem_text = mem_path.read_text(encoding="utf-8")

    ref = manifest.get("requirement_ref") or {}
    built = _dt.datetime.now().astimezone().replace(microsecond=0).isoformat()

    return ("<!DOCTYPE html>" + LF + '<html lang="zh-CN"><head><meta charset="utf-8">'
            + '<meta name="viewport" content="width=device-width,initial-scale=1">'
            + "<title>" + esc(manifest.get("case_id")) + " · 设计案例看板</title>"
            + "<style>" + CSS + "</style></head><body><div class='wrap'>"
            + "<h1>" + esc(manifest.get("case_id")) + " · 涵道风扇气动设计案例看板</h1>"
            + "<div class='sub'>生成于 " + esc(built) + "　·　单文件自包含，无外部依赖</div>"
            + "<div class='card'><dl class='kv'>"
            + "<dt>当前阶段</dt><dd>" + esc(manifest.get("current_stage")) + "</dd>"
            + "<dt>manifest revision</dt><dd>" + esc(manifest.get("revision")) + "</dd>"
            + "<dt>产物数</dt><dd>" + esc(len(manifest.get("artifacts", []))) + "</dd>"
            + "<dt>需求基线</dt><dd>" + esc(ref.get("file") or "（未建立）") + "</dd>"
            + "<dt>需求 sha256</dt><dd>" + esc((ref.get("sha256") or "")[:32]) + "</dd>"
            + "<dt>阻塞项</dt><dd>" + esc(len(state.get("blockers", []))) + "</dd>"
            + "</dl></div>"
            + "<h2>阶段时间线</h2><div class='tl'>" + "".join(stage_html) + "</div>"
            + "<h2>产物与溯源链</h2><div class='card'><table><thead><tr>"
            + "<th>阶段</th><th>类型</th><th>路径</th><th>版本</th><th>结论</th>"
            + "<th>sha256</th><th>上游</th><th>时间</th></tr></thead><tbody>"
            + ("".join(art_rows) or "<tr><td colspan='8'>暂无产物</td></tr>")
            + "</tbody></table></div>"
            + chart
            + "".join(replay_blocks)
            + "<h2>案例经验（memory.md）</h2><pre>" + esc(mem_text) + "</pre>"
            + "<h2>工程日志（LOG.md 末尾）</h2><pre>" + esc(log_text) + "</pre>"
            + "<p class='note'>本页由 <span class='mono'>tools/build_dashboard.py</span> 生成，"
            + "数据全部来自案例目录磁盘文件。</p>"
            + "</div></body></html>" + LF)


def main(argv=None):
    p = argparse.ArgumentParser(prog="build_dashboard.py")
    p.add_argument("--case", required=True)
    p.add_argument("--version", default="v1")
    p.add_argument("--out", default=None)
    args = p.parse_args(argv)

    case = Path(args.case).resolve()
    if not (case / "manifest.json").is_file():
        print("PRECONDITION: 未找到 manifest.json：" + str(case), file=sys.stderr)
        return EXIT_PRECONDITION

    try:
        page = build(case, args.version)
    except Exception as exc:
        print("INTERNAL ERROR: " + repr(exc), file=sys.stderr)
        return EXIT_INTERNAL

    out = Path(args.out) if args.out else (case / "06-delivery" / args.version / "dashboard.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8", newline=LF)
    print("看板已生成：" + str(out) + "  (" + str(len(page.encode("utf-8"))) + " bytes)")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
