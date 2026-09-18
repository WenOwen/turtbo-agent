#!/usr/bin/env python3
"""liveview.py - 叶轮机械设计案例的实时可视化窗口。

你为什么需要它
--------------
case_ledger / gate_check / manifest / LOG.md 记下了"发生了什么"，
但它们是文件，你只能翻。这个东西把它们变成一扇会自己更新的窗口。

它读什么（全部只读，不改任何案例文件）
------------------------------------
  cases/<ID>/STATE.json      阶段时间线
  cases/<ID>/manifest.json   版本、产物数、当前阶段
  cases/<ID>/requirements.yaml  需求摘要
  cases/<ID>/LOG.md          工程日志尾部
  <watch roots>/**           最近改动的文件（用来推断"现在在做什么"）
  Get-Process                正在跑的 NUMECA / 求解进程

用法
----
  python tools/liveview.py                      # 默认 127.0.0.1:8899
  python tools/liveview.py --port 8900
  python tools/liveview.py --case cases/DF90-001
  python tools/liveview.py --no-browser         # 不自动开浏览器

不需要任何第三方依赖，不需要提权，不写工作区以外的任何文件。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                      # 工作区根
UI = HERE / "liveview_ui.html"

# 输出被重定向到文件时默认是块缓冲，启动信息会看不见
try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass

DEFAULT_EXTRA_ROOTS = [Path("D:/Project/Research/Ducted-Fan/run")]

# 工程合同文件：人话解释直接从它解析，保证与正式合同同源、不会漂移
CONTRACTS = ROOT / ".agents" / "skills" / "ducted-fan-aero-design" / "references" / "ducted-fan-contracts.md"


def parse_contracts(path=None):
    """从合同文件里抽出每条的 标题 / 人话 / 当初为什么加 / 来源。"""
    path = Path(path) if path else CONTRACTS
    if not path.is_file():
        return []
    text = read_text_safe(path)
    parts = re.split(r"\n## (C-\d+)\s+([^\n]*)\n", text)
    rules = []
    for i in range(1, len(parts) - 2, 3):
        cid, title, body = parts[i], parts[i + 1], parts[i + 2]

        def grab(label):
            m = re.search(r"\*\*" + label + r"\*\*：(.+?)(?:\n\s*\n|\n\*\*)", body, re.S)
            if not m:
                return ""
            return re.sub(r"\s+", " ", m.group(1)).strip()

        src = re.search(r"\*\*来源\*\*：(.+?)(?:\n|$)", body)
        rules.append({
            "id": cid,
            "title": title.strip(),
            "plain": grab("人话"),
            "why": grab("当初为什么加"),
            "source": re.sub(r"\s+", " ", src.group(1)).strip()[:150] if src else "",
        })
    return rules


STAGE_DIR = {
    "00-brief": "G1", "01-scheme": "G2", "02-geometry": "G3",
    "03-mesh": "G4", "04-solve": "G5", "05-post": "G6", "06-delivery": "G6",
}

PROC_PATTERNS = re.compile(
    r"euranus|finebatch|finex86|autogrid|iggx86|cfview|mpiexec|numeca|python|node",
    re.I,
)
PROC_INTERESTING = re.compile(
    r"euranus|finebatch|finex86|autogrid|iggx86|cfview|mpiexec|numeca",
    re.I,
)

_proc_cache = {"ts": 0.0, "data": []}
_proc_lock = threading.Lock()


def now_iso():
    return _dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def read_json_safe(path):
    try:
        with Path(path).open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def read_text_safe(path, limit=None):
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        return text[-limit:] if limit else text
    except Exception:
        return ""


# ── 进程 ───────────────────────────────────────────────────────────────────
def sample_processes(max_age=4.0):
    with _proc_lock:
        if time.time() - _proc_cache["ts"] < max_age:
            return _proc_cache["data"]
    data = []
    try:
        cmd = ("Get-Process | Where-Object { $_.ProcessName -match '" +
               PROC_PATTERNS.pattern + "' } | "
               "Select-Object ProcessName,Id | ConvertTo-Json -Compress")
        out = subprocess.run(["pwsh", "-NoProfile", "-Command", cmd],
                             capture_output=True, text=True, timeout=20).stdout.strip()
        if out:
            parsed = json.loads(out)
            if isinstance(parsed, dict):
                parsed = [parsed]
            for item in parsed:
                name = str(item.get("ProcessName", ""))
                if PROC_INTERESTING.search(name):
                    data.append({"name": name, "pid": item.get("Id")})
    except Exception:
        pass
    with _proc_lock:
        _proc_cache["ts"] = time.time()
        _proc_cache["data"] = data
    return data


# ── 目录扫描 ───────────────────────────────────────────────────────────────
SKIP_DIRS = {"__pycache__", ".git", "node_modules", ".venv", ".pytest_cache",
             ".ruff_cache", ".playwright-cli", ".turbo-flow"}


def scan_recent(roots, limit=8, max_files=20000):
    """返回最近改动的文件。限制遍历规模，避免大目录拖慢轮询。"""
    found = []
    scanned = 0
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in filenames:
                scanned += 1
                if scanned > max_files:
                    break
                p = Path(dirpath) / fn
                try:
                    st = p.stat()
                except Exception:
                    continue
                found.append({"path": p, "mtime": st.st_mtime, "bytes": st.st_size})
            if scanned > max_files:
                break
        if scanned > max_files:
            break
    found.sort(key=lambda x: x["mtime"], reverse=True)
    now = time.time()

    def relpath(p):
        try:
            return p.relative_to(ROOT).as_posix()
        except ValueError:
            return str(p)

    out = []
    for f in found[:limit]:
        out.append({"path": relpath(f["path"]), "age_sec": now - f["mtime"], "bytes": f["bytes"]})

    newest = None
    if found:
        top = found[0]
        newest = {"path": relpath(top["path"]), "age_sec": now - top["mtime"],
                  "mtime": top["mtime"], "bytes": top["bytes"]}
    return out, newest


# ── 推断"现在在做什么" ─────────────────────────────────────────────────────
# 进程分类：只有求解器才算"正在算"；GUI 打开着不等于在计算。
PROC_SOLVER = re.compile(r"euranus|finex86|mpiexec", re.I)
PROC_BATCH = re.compile(r"finebatch", re.I)
PROC_GUI = re.compile(r"iggx86|autogrid|cfview", re.I)

# 从路径里认出"正在处理的工况名"，例如 v8-optimized_n05000_p101325
CASE_NAME = re.compile(r"([A-Za-z0-9_\-]+_n\d+_p\d+)")


def infer_activity(state, manifest, newest, procs, log_age):
    stages = (state or {}).get("stages", {}) or {}
    order = ("G0", "G1", "G2", "G3", "G4", "G5", "G6")
    running = [g for g in order if (stages.get(g) or {}).get("status") == "in_progress"]
    blocked = [g for g in order if (stages.get(g) or {}).get("status") == "blocked"]

    solvers = [p for p in procs if PROC_SOLVER.search(p["name"])]
    batches = [p for p in procs if PROC_BATCH.search(p["name"])]
    guis = [p for p in procs if PROC_GUI.search(p["name"])]

    case_hint = ""
    if newest:
        m = CASE_NAME.search(newest["path"])
        if m:
            case_hint = m.group(1)
    age = newest["age_sec"] if newest else None

    # 1) 真有求解器进程
    if solvers:
        names = "、".join(sorted({p["name"] for p in solvers}))
        detail = "求解进程 " + names
        if case_hint:
            detail += "　·　工况 " + case_hint
        if age is not None:
            detail += "　·　最近写入 %d 秒前" % int(age)
        return "求解器正在算", detail

    # 2) finebatch 在物化
    if batches:
        detail = "finebatch 正在生成/物化 .run"
        if case_hint:
            detail += "　·　工况 " + case_hint
        return "正在物化工况", detail

    # 3) 没求解器，但文件刚动过 —— 说明 agent 正在写东西
    if age is not None and age < 90:
        tail = newest["path"].rsplit("/", 1)[-1]
        return "刚刚有文件写入", tail + "（%d 秒前）" % int(age)

    # 4) 只有 GUI 开着 —— 不许说"正在算"
    if guis:
        names = "、".join(sorted({p["name"] for p in guis}))
        detail = names + " 打开着，但没有求解进程"
        if age is not None:
            detail += "　·　最近写入 %d 分钟前" % int(age / 60)
        return "NUMECA 界面打开着（未在计算）", detail

    # 5) 只有阶段标记
    if running:
        g = running[0]
        detail = "阶段标记为进行中"
        if case_hint:
            detail = "涉及工况 " + case_hint
        if age is not None and age < 1800:
            detail += "　·　最近写入 %d 分钟前" % int(age / 60)
        return "%s 进行中（无活动进程）" % g, detail

    if blocked:
        blockers = (state or {}).get("blockers", []) or []
        reason = blockers[0].get("reason") if blockers else ""
        return "%s 阻塞" % blocked[0], str(reason)

    if log_age is not None and log_age < 300:
        return "有日志活动", "LOG.md 在 %d 秒前更新" % int(log_age)

    return "空闲", "没有检测到正在进行的操作"



# ── 组装状态 ───────────────────────────────────────────────────────────────
class Aggregator:
    def __init__(self, case_dir, extra_roots):
        self.case_dir = Path(case_dir)
        self.roots = [self.case_dir] + [Path(r) for r in extra_roots]

    def requirement_line(self):
        text = read_text_safe(self.case_dir / "requirements.yaml")
        thrust = re.search(r"^\s*value:\s*([\d.]+)", text, re.M)
        unit = re.search(r"^\s*unit:\s*(\S+)", text, re.M)
        dia = re.search(r"^\s*tip_diameter_m:\s*([\d.]+)", text, re.M)
        motor = re.search(r"^\s*model:\s*(\S.*)$", text, re.M)
        bits = []
        if thrust and unit:
            bits.append("推力 " + thrust.group(1) + " " + unit.group(1))
        if dia:
            bits.append("桨盘直径 " + dia.group(1) + " m")
        if motor:
            bits.append("电机 " + motor.group(1).strip())
        return "　·　".join(bits)

    def build(self):
        state = read_json_safe(self.case_dir / "STATE.json") or {}
        manifest = read_json_safe(self.case_dir / "manifest.json") or {}
        recent, newest = scan_recent(self.roots)
        procs = sample_processes()

        log_path = self.case_dir / "LOG.md"
        log_age = None
        if log_path.exists():
            try:
                log_age = time.time() - log_path.stat().st_mtime
            except Exception:
                pass
        log_tail = read_text_safe(log_path, 6000)

        activity, detail = infer_activity(state, manifest, newest, procs, log_age)

        return {
            "server_time": now_iso(),
            "case_id": manifest.get("case_id") or state.get("case_id") or self.case_dir.name,
            "case_dir": str(self.case_dir),
            "requirement_line": self.requirement_line(),
            "current_stage": manifest.get("current_stage") or state.get("current_stage"),
            "revision": manifest.get("revision"),
            "artifact_count": len(manifest.get("artifacts", []) or []),
            "stages": state.get("stages") or {},
            "blockers": state.get("blockers") or [],
            "activity": activity,
            "activity_detail": detail,
            "processes": procs,
            "recent_files": recent,
            "newest": newest and {"path": newest["path"], "age_sec": newest["age_sec"],
                                  "bytes": newest.get("bytes")},
            "log_age_sec": log_age,
            "log_tail": log_tail,
            "rules": parse_contracts(),
        }


# ── HTTP ───────────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    aggregator = None
    ui_bytes = b""

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self._send(200, self.ui_bytes, "text/html; charset=utf-8")
        elif path == "/api/state":
            try:
                payload = json.dumps(self.aggregator.build(), ensure_ascii=False).encode("utf-8")
                self._send(200, payload, "application/json; charset=utf-8")
            except Exception as exc:
                err = json.dumps({"error": repr(exc)}, ensure_ascii=False).encode("utf-8")
                self._send(500, err, "application/json; charset=utf-8")
        elif path == "/api/ping":
            self._send(200, b"ok", "text/plain; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain; charset=utf-8")


def pick_port(preferred):
    for port in [preferred] + list(range(preferred + 1, preferred + 20)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return preferred


def pick_case(explicit):
    if explicit:
        p = Path(explicit)
        return p if p.is_absolute() else (ROOT / p).resolve()
    cases_dir = ROOT / "cases"
    if not cases_dir.is_dir():
        return ROOT
    cands = [d for d in cases_dir.iterdir() if (d / "manifest.json").is_file()]
    if not cands:
        return ROOT
    cands.sort(key=lambda d: (d / "manifest.json").stat().st_mtime, reverse=True)
    return cands[0].resolve()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="liveview.py", description="设计案例实时可视化窗口")
    ap.add_argument("--port", type=int, default=8899)
    ap.add_argument("--case", default=None)
    ap.add_argument("--watch", action="append", default=None,
                    help="额外监视的目录（可重复）；默认含 Ducted-Fan/run")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)

    if not UI.is_file():
        print("缺少界面文件：" + str(UI), file=sys.stderr)
        return 3

    case_dir = pick_case(args.case)
    extra = args.watch if args.watch is not None else [str(p) for p in DEFAULT_EXTRA_ROOTS if p.exists()]

    Handler.aggregator = Aggregator(case_dir, extra)
    Handler.ui_bytes = UI.read_bytes()

    port = pick_port(args.port)
    url = "http://127.0.0.1:" + str(port) + "/"

    print("=" * 62)
    print("  叶轮机械设计工作台 · 实时窗口")
    print("=" * 62)
    print("  案例    : " + str(case_dir))
    print("  监视    : " + "；".join([str(case_dir)] + extra))
    print("  地址    : " + url)
    print("  合同    : " + str(len(parse_contracts())) + " 条（含人话解释）")
    print("  停止    : 按 Ctrl+C")
    print("=" * 62)

    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("")
        print("已停止。")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
