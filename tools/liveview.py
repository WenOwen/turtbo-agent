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
import hashlib
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import case_watch as watch  # noqa: E402  文件看守 + 交接简报（同一份实现，避免漂移）

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

# 规矩文件：人话解释直接从它解析，保证与正式文件同源、不会漂移
CONTRACTS = ROOT / ".agents" / "skills" / "ducted-fan-aero-design" / "references" / "ducted-fan-contracts.md"


def parse_contracts(path=None):
    """从规矩文件里抽出每条的 标题 / 人话 / 当初为什么加 / 来源。"""
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


# 白话对照表：内部术语 → 给人看的话。
# 界面与 skill 共用同一份，改词只改它 —— 否则又多一个"同一条规则写在两处"的漂移点。
PLAIN = ROOT / ".agents" / "skills" / "ducted-fan-aero-design" / "references" / "plain-language.json"


def plain_language(path=None):
    """读白话对照表，供界面把 G0-G6 / 闸门 / 规矩 翻译成人话。"""
    path = Path(path) if path else PLAIN
    if not path.is_file():
        return {}
    try:
        return json.loads(read_text_safe(path))
    except Exception:
        return {}


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
STAGE_ORDER = [("G0", "需求"), ("G1", "设计大纲"), ("G2", "1D/通流方案"), ("G3", "叶片造型"),
               ("G4", "网格"), ("G5", "求解"), ("G6", "后处理与交付")]

_scan_cache = {"ts": 0.0, "key": None, "value": None}
_scan_lock = threading.Lock()


def scan_recent_cached(roots, limit=8, max_age=2.0):
    """scan_recent 要遍历上万个文件，多个客户端轮询时加个短缓存。"""
    key = tuple(str(r) for r in roots) + (limit,)
    with _scan_lock:
        if _scan_cache["key"] == key and time.time() - _scan_cache["ts"] < max_age:
            return _scan_cache["value"]
    value = scan_recent(roots, limit=limit)
    with _scan_lock:
        _scan_cache.update({"ts": time.time(), "key": key, "value": value})
    return value


def list_cases():
    """列出工作区 cases/ 下所有登记过的案例（有新到旧）。"""
    cases_dir = ROOT / "cases"
    out = []
    if not cases_dir.is_dir():
        return out
    for d in cases_dir.iterdir():
        mp = d / "manifest.json"
        if not d.is_dir() or not mp.is_file():
            continue
        man = read_json_safe(mp) or {}
        sp = d / "STATE.json"
        try:
            mtime = mp.stat().st_mtime
        except Exception:
            mtime = 0
        out.append({
            "id": man.get("case_id") or d.name,
            "dir": str(d),
            "current_stage": man.get("current_stage"),
            "revision": man.get("revision"),
            "artifact_count": len(man.get("artifacts", []) or []),
            "mtime": mtime,
            "has_state": sp.is_file(),
        })
    out.sort(key=lambda x: x["mtime"], reverse=True)
    return out


def parse_log(text):
    """日志解析统一走 case_watch，避免两处实现漂移。"""
    return watch.parse_log(text)


def _parse_log_local(text):
    entries = []
    cur = None
    for line in text.splitlines():
        m = re.match(r"^##\s+(\S+)\s+\|\s+(.+?)\s+\|\s+(\S+)\s*$", line)
        if m:
            if cur:
                entries.append(cur)
            label = m.group(2).strip()
            g = re.match(r"^(G\d)\s*(.*)$", label)
            cur = {
                "ts": m.group(1),
                "stage": g.group(1) if g else "",
                "stage_name": (g.group(2) if g else label),
                "verdict": m.group(3),
                "fields": [],
            }
            continue
        if cur is None:
            continue
        m2 = re.match(r"^-\s*([^：:]+)[：:]\s*(.*)$", line)
        if m2:
            cur["fields"].append({"k": m2.group(1).strip(), "v": m2.group(2).strip()})
    if cur:
        entries.append(cur)
    return entries


def trim_artifact(a):
    prov = a.get("provenance") or {}
    return {
        "kind": a.get("kind"), "path": a.get("path"), "version": a.get("version"),
        "verdict": a.get("verdict", "INFO"), "bytes": a.get("bytes"),
        "sha256": (a.get("sha256") or "")[:16], "ts": a.get("ts"),
        "note": a.get("note") or "", "from": prov.get("from") or "",
    }


def build_stage_detail(state, manifest, log_entries):
    """每个阶段一个包：状态 + 产物 + 过程记录。点时间线就能看。"""
    arts = manifest.get("artifacts", []) or []
    detail = {}
    for sid, default_name in STAGE_ORDER:
        st = (state.get("stages") or {}).get(sid) or {}
        detail[sid] = {
            "id": sid,
            "name": st.get("name") or default_name,
            "status": st.get("status", "pending"),
            "updated": st.get("updated"),
            "artifacts": [trim_artifact(a) for a in arts if a.get("stage") == sid],
            "log": [e for e in log_entries if e.get("stage") == sid],
        }
    return detail


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
        recent, newest = scan_recent_cached(self.roots)
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
            "plain": plain_language(),
            "cases": list_cases(),
            "watch": watch.status(self.case_dir),
            "watch_changes": watch.read_changes(self.case_dir, limit=12)[::-1],
            "stage_detail": build_stage_detail(state, manifest, parse_log(read_text_safe(log_path))),
        }


# ── 写能力（人工操控） ─────────────────────────────────────────────────────
# 原则：界面上的任何写操作，都走与 agent 完全相同的工具路径，
#       只在日志里多记一个 - 操作者：human(web-ui)。
#       这样审计链不会因为"是人点的"而断掉。

MAX_EDIT_BYTES = 2 * 1024 * 1024

# 界面能写哪里 —— **用白名单，不用黑名单**。
#
# 为什么改：原来是黑名单（.git/_memfix/...），结果是 tools/ 和
# cases/*/_automation/ 都能通过界面写。那些是**可执行代码** ——
# 改掉 tools/case_ledger.py 或 _automation/v8/*.py，下一次跑就被 hijack。
# 黑名单永远漏一条，白名单默认拒绝。
WRITE_ALLOW_PATTERNS = [
    r"^cases/[^/]+/(00-brief|01-scheme|02-geometry|03-mesh|04-solve|05-post|06-delivery)/",
    r"^cases/[^/]+/(LOG\.md|STATE\.json|memory\.md|manifest\.json|requirements\.yaml)$",
    r"^cases/[^/]+/_automation/.*\.(json|csv|md|txt|log)$",   # 数据可以，脚本不行
    r"^cases/[^/]+/_external/.*\.json$",
]
WRITE_DENY_PARTS = {".git", "_memfix", "node_modules", "__pycache__", ".venv", "_watch"}
WRITE_DENY_SUFFIX = (".py", ".ps1", ".cmd", ".bat", ".exe", ".dll", ".sh")


def _write_allowed(rel_posix):
    """这个路径允许通过界面写吗？返回 (bool, 原因)。"""
    for part in rel_posix.split("/"):
        if part in WRITE_DENY_PARTS:
            return False, "该目录不允许通过界面修改：" + part
    if rel_posix.endswith(WRITE_DENY_SUFFIX):
        return False, ("可执行文件不允许通过界面修改（"
                       + rel_posix.rsplit("/", 1)[-1] + "）—— 改了它等于改了工具本身")
    for pat in WRITE_ALLOW_PATTERNS:
        if re.match(pat, rel_posix):
            return True, ""
    return False, ("只允许改案例的工程内容；" + rel_posix + " 不在允许范围内。"
                   "工具与 skill 请用编辑器直接改。")

TEXT_SUFFIXES = {".md", ".json", ".yaml", ".yml", ".csv", ".txt", ".py", ".ps1", ".cmd", ".html",
                 ".trb", ".bcs", ".config", ".info", ".qualityReport", ".geomTurbo", ".log", ".std"}


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def resolve_in_root(rel):
    """把相对路径解析成 ROOT 内的绝对路径。**只做越界检查，不管能不能写。**

    读和写的边界不一样：读只需要"在工作区内"（界面要能看 _view/ 下自己生成的
    SVG、能看 tools/ 下的脚本）；写才需要白名单。早先把两者混在一个函数里，
    结果是把读也一起锁死了 —— 所以拆成两个。
    """
    if not rel or not isinstance(rel, str):
        raise ApiError("缺少路径")
    candidate = (ROOT / rel.replace("\\", "/")).resolve()
    try:
        candidate.relative_to(ROOT)
    except ValueError:
        raise ApiError("路径越界，只允许工作区内的文件", 403)
    for part in candidate.relative_to(ROOT).parts:
        if part in (".git", "node_modules", "__pycache__", ".venv"):
            raise ApiError("该目录不提供访问：" + part, 403)
    return candidate


def resolve_writable(rel):
    """写专用：在 resolve_in_root 之上再加白名单。"""
    candidate = resolve_in_root(rel)
    ok, why = _write_allowed(candidate.relative_to(ROOT).as_posix())
    if not ok:
        raise ApiError(why, 403)
    return candidate


# ── 几何可视化 ─────────────────────────────────────────────────────────────
# 原则：**每次请求都重新生成**，不缓存。
# 理由：agent 改完几何，人切回页面就该看到新的 —— 这正是"一边操作一边看得见"。
# 生成一套 SVG 大约 0.2 秒，比缓存失效的复杂度便宜得多。
_VIEW_LOCK = threading.Lock()


def _stamp_ok(sub, sig, force):
    """源文件没改就跳过重算。几何/网格文件都几百 KB，比 mtime 很便宜。"""
    if force:
        return False
    stamp = sub / ".source.json"
    if not stamp.is_file():
        return False
    try:
        return json.loads(stamp.read_text(encoding="utf-8")) == sig
    except Exception:
        return False


def _sig_of(path):
    st = path.stat()
    return {"path": str(path), "mtime": st.st_mtime, "size": st.st_size}


# 「当前版本是哪个」只能有一份定义 —— 直接从闸门取，不在这里另抄一份。
from gate_check import latest_version  # noqa: E402


def build_views(case_id, force=False):
    """生成（或复用）该案例的几何与网格视图。

    原则：**按需生成、源变才重算**。agent 改完几何/网格，人切回页面就该看到新的。
    """
    case = case_dir_of(case_id)
    out_root = case / "_view"
    groups = []

    try:
        import geom_view
        geoms = geom_view.find_geomturbo(case)
        views = []
        with _VIEW_LOCK:
            for g in geoms:
                sub = out_root / g.stem
                if not _stamp_ok(sub, _sig_of(g), force):
                    geom_view.build(g, sub)
                    (sub / ".source.json").write_text(json.dumps(_sig_of(g)), encoding="utf-8")
                rel = sub.relative_to(ROOT).as_posix()
                views.append({
                    "name": g.stem, "dir": rel,
                    "images": [{"title": t, "note": n, "path": rel + "/" + f}
                               for f, t, n in (
                                   ("meridional.svg", "子午面", "流道轮廓 + 叶片径向位置"),
                                   ("cascade.svg", "各截面形状", "13 个截面的剖面，同一比例尺"),
                                   ("blade3d.svg", "轴测", "叶片与涵道的立体关系"))],
                })
        if views:
            groups.append({"kind": "geom", "title": "几何", "hint": "叶片与流道", "views": views})
    except Exception as exc:
        groups.append({"kind": "geom", "title": "几何", "error": repr(exc), "views": []})

    try:
        import mesh_view
        dirs = mesh_view.find_mesh_dirs(case)
        views = []
        with _VIEW_LOCK:
            for d in dirs:
                sub = out_root / ("mesh-" + d.name)
                srcs = sorted(d.glob("*.igg")) + sorted(d.glob("*.qualityReport"))
                sig = {"dir": str(d), "files": [_sig_of(p) for p in srcs]}
                if not _stamp_ok(sub, sig, force):
                    mesh_view.build(d, sub)
                    (sub / ".source.json").write_text(json.dumps(sig), encoding="utf-8")
                rel = sub.relative_to(ROOT).as_posix()
                views.append({
                    "name": d.name, "dir": rel,
                    "images": [{"title": t, "note": n, "path": rel + "/" + f}
                               for f, t, n in (
                                   ("blocks.svg", "块结构", "从 .igg 解析的真实块拓扑"),
                                   ("quality.svg", "质量指标", "从 .qualityReport 解析"))],
                })
        if views:
            groups.append({"kind": "mesh", "title": "网格", "hint": "块拓扑与质量", "views": views})
    except Exception as exc:
        groups.append({"kind": "mesh", "title": "网格", "error": repr(exc), "views": []})

    try:
        import cfd_view
        sums = cfd_view.find_summaries(case)
        views = []
        with _VIEW_LOCK:
            for t in sums:
                sub = out_root / ("cfd-" + t.parent.name)
                if not _stamp_ok(sub, _sig_of(t), force):
                    cfd_view.build(t, sub)
                    (sub / ".source.json").write_text(json.dumps(_sig_of(t)), encoding="utf-8")
                rel = sub.relative_to(ROOT).as_posix()
                views.append({
                    "name": t.parent.name, "dir": rel,
                    "images": [{"title": t_, "note": n_, "path": rel + "/" + f_}
                               for f_, t_, n_ in (
                                   ("map.svg", "性能曲线", "只连已验收点，未验收画 ×"),
                                   ("sweep.svg", "扫点状态", "每格一个工况"),
                                   ("convergence.svg", "收敛情况", "步数 vs 质量不平衡"))],
                })
        if views:
            groups.append({"kind": "cfd", "title": "CFD 结果", "hint": "性能曲线与扫点", "views": views})
    except Exception as exc:
        groups.append({"kind": "cfd", "title": "CFD 结果", "error": repr(exc), "views": []})

    # ── 方案（G2）：三表 + 对标闸门 ─────────────────────────────────────────
    # 界面上原来只有几何 / 网格 / CFD 三组图，全是 G3/G4/G5 的产物 ——
    # **第 3 步一张图都没有**。而三表 + 对标闸门恰恰是整条链上唯一能
    # 回答"这个方案对不对"的证据。
    try:
        import scheme_view
        dirs = scheme_view.find_scheme_dirs(case)
        if dirs:
            src = dirs[-1]
            sub = out_root / "scheme"
            srcs = [src / n for n in ("流道尺寸表.csv", "叶片几何参数表.csv",
                                      "通流计算结果表.csv", "benchmark_gate.json")]
            srcs += sorted(src.rglob("result.json"))
            srcs = [p for p in srcs if p.is_file()]
            sig = {"files": [_sig_of(p) for p in srcs]}
            if srcs and not _stamp_ok(sub, sig, force):
                scheme_view.build(src, sub)
                (sub / ".source.json").write_text(json.dumps(sig), encoding="utf-8")
            rel = sub.relative_to(ROOT).as_posix()
            imgs = []
            for f, t, n in (("benchmark.svg", "和基准对一对",
                             "和基准对上了吗：目标 / 实测 / 偏差 / 结论"),
                            ("scheme.svg", "三表与溯源",
                             "流道、叶排、性能，以及这三表是哪一次求解生成的")):
                if (sub / f).is_file():
                    imgs.append({"title": t, "note": n, "path": rel + "/" + f})
            if imgs:
                groups.append({"kind": "scheme", "title": "方案",
                               "hint": "三表与基准对照",
                               "views": [{"name": "方案", "dir": rel, "images": imgs}]})
    except Exception as exc:
        groups.append({"kind": "scheme", "title": "方案", "error": repr(exc),
                       "views": []})

    # ── 设计值对照（G3）：设计表 vs 几何实测 + 溯源链 ──────────────────────
    # 溯源图放在这里，不另开一组：它和对照表回答的是同一个问题 ——
    # "这套几何站不站得住"。断点和偏差并排看，才知道该信哪个。
    try:
        import geom_check
        sub = out_root / "check"
        scheme_dir = case / "01-scheme" / latest_version(case / "01-scheme")
        srcs = [scheme_dir / "叶片几何参数表.csv"]
        srcs += sorted((case / "02-geometry").glob("**/*.par"))
        srcs += sorted((case / "02-geometry").glob("**/*.geomTurbo"))
        srcs = [p for p in srcs if p.is_file()]
        sig = {"files": [_sig_of(p) for p in srcs]}
        if srcs and not _stamp_ok(sub, sig, force):
            geom_check.build(case, sub)
            (sub / ".source.json").write_text(json.dumps(sig), encoding="utf-8")
        rel = sub.relative_to(ROOT).as_posix()
        imgs = []
        if (sub / "design-vs-geom.svg").is_file():
            imgs.append({"title": "设计值 vs 几何实测",
                         "note": "逐项结论，红框是对不上的",
                         "path": rel + "/design-vs-geom.svg"})
        if imgs:
            groups.append({"kind": "check", "title": "设计值对照",
                           "hint": "参数表 vs 几何实测",
                           "views": [{"name": "对照", "dir": rel, "images": imgs}]})
    except Exception as exc:
        groups.append({"kind": "check", "title": "设计值对照",
                       "error": repr(exc), "views": []})

    # ── 造型溯源（G3）：参数表 → 几何 这条链哪一环断了 ─────────────────────
    try:
        import prov_view
        sub = out_root / "provenance"
        srcs = sorted((case / "02-geometry").glob("**/*.geomTurbo"))
        srcs += sorted((case / "_automation").glob("g3/schedule-*.json"))
        srcs = [p for p in srcs if p.is_file()]
        sig = {"files": [_sig_of(p) for p in srcs]}
        if srcs and not _stamp_ok(sub, sig, force):
            prov_view.build(case, sub)
            (sub / ".source.json").write_text(json.dumps(sig), encoding="utf-8")
        rel = sub.relative_to(ROOT).as_posix()
        if (sub / "provenance.svg").is_file():
            groups.append({"kind": "check", "title": "设计值对照",
                           "hint": "参数表 vs 几何实测", "views": [],
                           "_merge": {"name": "溯源", "dir": rel, "images": [
                               {"title": "造型溯源",
                                "note": "参数表 → 几何，哪一环没有证据",
                                "path": rel + "/provenance.svg"}]}})
    except Exception as exc:
        groups.append({"kind": "check", "title": "设计值对照",
                       "error": repr(exc), "views": []})

    # 把溯源图并进「设计值对照」那一组 —— 不另开一组。
    # 审核反复说过：组数本身就是负担。这两张图回答同一个问题，
    # 拆成两组只是让页面更长。
    by_kind = {}
    for g in groups:
        if g["kind"] == "check":
            by_kind.setdefault("check", []).append(g)
    if len(by_kind.get("check") or []) > 1:
        merged, extra = [], []
        for g in groups:
            if g["kind"] != "check":
                merged.append(g)
                continue
            if g.get("_merge"):
                extra.append(g.pop("_merge"))
            elif g["views"]:
                merged.append(g)
        for g in merged:
            if g["kind"] == "check" and extra:
                g["views"] = (g.get("views") or []) + extra
                extra = []
        groups = merged

    # 显示顺序 = 人该看的顺序：先"方案对不对"，再"几何对不对"，最后"长什么样"。
    # 以前这里注释写着"设计值对照放最前面"，代码却把它 append 在最后 ——
    # 注释和实际显示的顺序是反的。现在按这张表排，注释不再说谎。
    ORDER = ["scheme", "check", "geom", "mesh", "cfd"]
    groups.sort(key=lambda g: ORDER.index(g["kind"]) if g["kind"] in ORDER else 99)

    live = [g for g in groups if g["views"]]
    if not live:
        return {"ok": True, "available": False, "groups": groups,
                "reason": "本案例还没有方案、几何、网格或求解产物"}
    return {"ok": True, "available": True, "groups": groups}


def read_file_payload(rel):
    p = resolve_in_root(rel)
    if not p.is_file():
        raise ApiError("文件不存在：" + rel, 404)
    size = p.stat().st_size
    if size > MAX_EDIT_BYTES:
        raise ApiError("文件过大，界面不提供查看（%.1f MB）" % (size / 1048576), 413)
    raw = p.read_bytes()
    try:
        text = raw.decode("utf-8")
        editable = True
    except UnicodeDecodeError:
        raise ApiError("二进制文件，界面不提供查看", 415)
    if p.suffix.lower() not in TEXT_SUFFIXES and p.suffix:
        editable = True   # 仍允许编辑，但下面会提示
    return {"path": rel.replace("\\", "/"), "bytes": size,
            "sha256": hashlib.sha256(raw).hexdigest(), "content": text,
            "editable": editable, "mtime": p.stat().st_mtime}


def write_file_payload(rel, content, expected_sha256, case=None):
    """乐观锁：调用方必须带回它读到的 sha256。不一致就拒绝，防止覆盖别人的改动。"""
    p = resolve_writable(rel)
    if not p.is_file():
        raise ApiError("文件不存在：" + rel, 404)
    old_raw = p.read_bytes()
    old_sha = hashlib.sha256(old_raw).hexdigest()
    if expected_sha256 and expected_sha256 != old_sha:
        raise ApiError("文件已被其他操作改动（可能是 agent 或另一个窗口）。"
                       "请重新载入后再改。当前 sha256=" + old_sha[:16], 409)
    if content is None:
        raise ApiError("缺少 content")
    data = content.encode("utf-8")
    if len(data) > MAX_EDIT_BYTES:
        raise ApiError("内容过大", 413)
    if data == old_raw:
        return {"ok": True, "unchanged": True, "sha256": old_sha, "bytes": len(data)}

    tmp = p.with_name(p.name + ".ui-tmp")
    tmp.write_bytes(data)
    os.replace(tmp, p)
    new_sha = hashlib.sha256(data).hexdigest()

    if case:
        # 注意：这里收到的是案例 **id**（如 DF90-001），不是路径，必须先解析。
        # 之前直接拼 ROOT/id 导致目录不存在、日志静默写不出来，归因因此全丢。
        real = case_dir_of(case)
        if real is not None:
            proc = log_via_ledger(real, stage=guess_stage(rel), action="界面编辑文件 " + rel,
                                  verdict="INFO",
                                  criteria="内容变更已确认；写回前 sha256 与读取时一致（乐观锁通过）",
                                  measured="sha256 " + old_sha[:16] + " -> " + new_sha[:16]
                                           + "；%d -> %d bytes" % (len(old_raw), len(data)),
                                  note="操作者通过实时工作台直接编辑")
            if proc.returncode != 0:
                # 日志写失败不能静默 —— 否则这次改动会永远归因不到人
                raise ApiError("文件已写入，但审计日志写入失败："
                               + ((proc.stderr or proc.stdout or "").strip()[:200]), 500)
            # 立刻跑一轮看守：确保这次改动在日志已经存在之后才被检测到，归因必然命中
            try:
                watch.tick(real)
            except Exception:
                pass
    return {"ok": True, "sha256": new_sha, "bytes": len(data), "old_sha256": old_sha}


def guess_stage(rel):
    """从路径猜阶段，用于把界面写操作记到正确的阶段下。"""
    rel = rel.replace("\\", "/")
    for prefix, stage in STAGE_DIR.items():
        if rel.startswith(prefix + "/") or rel.startswith("cases/") and ("/" + prefix + "/") in rel:
            return stage
    for prefix, stage in STAGE_DIR.items():
        if ("/" + prefix + "/") in ("/" + rel):
            return stage
    return "G0"


def log_via_ledger(case, stage, action, verdict, criteria, measured=None, note=None):
    """通过 case_ledger 写日志 —— 界面与 agent 共用同一套审计格式。"""
    case_dir = Path(case) if Path(case).is_absolute() else (ROOT / case)
    args = [sys.executable, str(HERE / "case_ledger.py"), "log",
            "--case", str(case_dir), "--stage", stage, "--action", action,
            "--verdict", verdict, "--criteria", criteria, "--actor", "human(web-ui)"]
    if measured:
        args += ["--measured", measured]
    if note:
        args += ["--note", note]
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                          timeout=60, cwd=str(ROOT))


def case_dir_of(case_id):
    for c in list_cases():
        if c["id"] == case_id:
            return Path(c["dir"])
    return None


# 界面可触发的动作白名单。名字 -> (说明, 参数说明)
ACTIONS = {
    "gate":       ("跑这一步的检查", "gate=G0..G6 对应的子命令名"),
    "verify":     ("校验案例产物与哈希", ""),
    "preflight":  ("环境预检", ""),
    "replay":     ("回放审计 v7 黄金基准", ""),
    "audit":      ("规矩自检（规矩文件 ↔ 代码是否对得上）", ""),
}


def run_action(case_id, action, params):
    if action not in ACTIONS:
        raise ApiError("未授权的动作：" + str(action), 403)
    case_dir = case_dir_of(case_id)
    if action != "preflight" and case_dir is None:
        raise ApiError("案例不存在：" + str(case_id), 404)

    if action == "gate":
        gate = (params or {}).get("gate")
        GATE_MAP = {"G0": "requirements", "G1": "brief", "G2": "scheme", "G3": "geometry",
                    "G4": "mesh", "G5": "solve", "G6": "post"}
        if gate not in GATE_MAP:
            raise ApiError("检查参数必须是 G0..G6", 400)
        cmd = [sys.executable, str(HERE / "gate_check.py"), GATE_MAP[gate],
               "--case", str(case_dir), "--no-log"]
    elif action == "verify":
        cmd = [sys.executable, str(HERE / "case_ledger.py"), "verify", "--case", str(case_dir)]
    elif action == "preflight":
        cmd = [sys.executable, str(HERE / "preflight.py"), "all"]
    elif action == "audit":
        cmd = [sys.executable, str(HERE / "gate_check.py"), "audit", "--case", str(case_dir)]
    elif action == "replay":
        baseline = ROOT.parent / "Ducted-Fan" / "run" / "90kg-duct-fan-v7" / "fine" / "v7-optimized"
        if not baseline.is_dir():
            raise ApiError("找不到基准目录：" + str(baseline), 404)
        cmd = [sys.executable, str(HERE / "replay_audit.py"), "--baseline", str(baseline),
               "--case", str(case_dir), "--label", "v7"]

    started = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=900, cwd=str(ROOT))
        out, err, code = proc.stdout or "", proc.stderr or "", proc.returncode
    except subprocess.TimeoutExpired:
        out, err, code = "", "命令超时（900 秒）", -1
    elapsed = time.time() - started

    # 这里**不写日志**：跑检查/校验/预检只是看结果，没有改变任何工程内容。
    # 看守只记录四类实质变更（设计参数/几何/网格/算例参数），
    # "谁点了哪个按钮"不属于其中 —— 界面控制台里有实时输出就够了。
    return {"ok": code == 0, "exit": code, "elapsed": round(elapsed, 1),
            "stdout": out[-20000:], "stderr": err[-8000:],
            "command": " ".join(cmd[1:])}


# ── HTTP ───────────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    ui_bytes = b""
    extra_roots = []
    default_case = None
    _agg_cache = {}
    _agg_lock = threading.Lock()

    @classmethod
    def aggregator_for(cls, case_id):
        """按案例 id 取聚合器。找不到就退回默认案例。"""
        cases = {c["id"]: c for c in list_cases()}
        target = None
        if case_id and case_id in cases:
            target = Path(cases[case_id]["dir"])
        if target is None:
            target = cls.default_case
        key = str(target)
        with cls._agg_lock:
            agg = cls._agg_cache.get(key)
            if agg is None:
                agg = Aggregator(target, cls.extra_roots)
                cls._agg_cache[key] = agg
        return agg

    def log_message(self, fmt, *args):
        pass

    # ── 本地写接口的三道门 ──────────────────────────────────────────────
    # 背景：服务绑在 127.0.0.1 是对的，但"本机"不等于"本服务的页面"。
    # 任何在浏览器里打开的网页都能对本机端口发简单请求（text/plain 不触发预检），
    # 而写接口能改整个工作区 —— 包括闸门阈值的唯一真源和校验器本身。
    # 三道门：Host 必须是本机、跨站请求一律拒绝、写操作要带会话令牌。
    ALLOWED_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
    token = ""          # main() 启动时随机生成并注入页面

    def _host_ok(self):
        host = (self.headers.get("Host") or "").strip().lower()
        if not host:
            return False
        name = host.rsplit(":", 1)[0] if not host.startswith("[") else host.split("]")[0] + "]"
        return name in self.ALLOWED_HOSTS

    def _cross_site(self):
        """浏览器主动告诉我们的跨站信号 —— 有就拒，不看别的。"""
        site = (self.headers.get("Sec-Fetch-Site") or "").strip().lower()
        if site and site not in ("same-origin", "same-site", "none"):
            return True
        origin = (self.headers.get("Origin") or "").strip()
        if origin and origin != "null":
            from urllib.parse import urlparse as _up
            o = _up(origin)
            if (o.hostname or "") not in ("127.0.0.1", "localhost", "::1"):
                return True
            if o.port and self.server.server_address[1] and o.port != self.server.server_address[1]:
                return True
        return False

    def _guard(self, need_token):
        if not self._host_ok():
            raise ApiError("Host 不是本机地址", 403)
        if self._cross_site():
            raise ApiError("拒绝跨站请求", 403)
        if need_token and self.token:
            got = (self.headers.get("X-DSH-Token") or "").strip()
            if got != self.token:
                raise ApiError("缺少或错误的会话令牌（页面刷新即可）", 403)

    def _send(self, code, body, ctype, extra_headers=None):
        extra_headers = extra_headers or {}
        headers = {
            "Content-Type": ctype,
            "Content-Length": str(len(body)),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy":
                "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                "connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'",
        }
        # extra 是**覆盖**不是追加 —— 同名头发两遍浏览器会取交集，
        # 结果是两边都不生效（实测踩过：sandbox 那条被拼在默认策略后面）。
        headers.update(extra_headers)
        self.send_response(code)
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    # UI 文件的基线哈希。token 是注入到 UI 里的，所以 UI 一旦被改，
    # 改的人就能让页面把 token 发给别人。启动时记一份哈希，页面被改就重置 token。
    ui_sha = ""
    token_reset_at = 0.0

    def _ui_fresh(self):
        """读 UI 文件；如果哈希和启动时不一致，重置 token 并记时间。"""
        try:
            raw = UI.read_bytes()
        except Exception:
            return self.ui_bytes, False
        sha = hashlib.sha256(raw).hexdigest()
        if self.ui_sha and sha != self.ui_sha:
            # 文件被改过 —— 旧 token 可能已经被读走了，换一个
            self.token = secrets.token_urlsafe(24)
            self.ui_sha = sha
            self.token_reset_at = time.time()
            return raw, True
        if not self.ui_sha:
            self.ui_sha = sha
        return raw, False

    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        case_id = (qs.get("case") or [None])[0]

        try:
            self._guard(need_token=False)
        except ApiError as exc:
            self._send(exc.status, json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")
            return

        if path in ("/", "/index.html"):
            # 令牌随页面下发：页面拿得到，别的站的页面拿不到（读不到响应体）。
            # 每次都读盘 —— 改了界面不该要求重启服务，否则调试时永远在看旧页面。
            raw, rotated = self._ui_fresh()
            html = raw.replace(b"__DSH_TOKEN__", self.token.encode("ascii") or b"")
            extra = {}
            if rotated:
                # 让页面知道发生了什么，而不是默默换掉令牌导致写操作 403
                extra["X-DSH-Notice"] = "ui-changed-token-rotated"
            self._send(200, html, "text/html; charset=utf-8", extra)
        elif path == "/api/cases":
            try:
                payload = json.dumps({"cases": list_cases()}, ensure_ascii=False).encode("utf-8")
                self._send(200, payload, "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"error": repr(exc)}).encode("utf-8"),
                           "application/json; charset=utf-8")
        elif path == "/api/state":
            try:
                agg = self.aggregator_for(case_id)
                payload = json.dumps(agg.build(), ensure_ascii=False).encode("utf-8")
                self._send(200, payload, "application/json; charset=utf-8")
            except Exception as exc:
                err = json.dumps({"error": repr(exc)}, ensure_ascii=False).encode("utf-8")
                self._send(500, err, "application/json; charset=utf-8")
        elif path == "/api/file":
            try:
                payload = json.dumps(read_file_payload((qs.get("path") or [""])[0]),
                                     ensure_ascii=False).encode("utf-8")
                self._send(200, payload, "application/json; charset=utf-8")
            except ApiError as exc:
                self._send(exc.status, json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8"),
                           "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"error": repr(exc)}).encode("utf-8"),
                           "application/json; charset=utf-8")
        elif path == "/api/views":
            try:
                force = (qs.get("force") or ["0"])[0] not in ("0", "", "false")
                payload = json.dumps(build_views(case_id or self.default_case.name, force=force),
                                     ensure_ascii=False).encode("utf-8")
                self._send(200, payload, "application/json; charset=utf-8")
            except ApiError as exc:
                self._send(exc.status, json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8"),
                           "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"error": repr(exc)}, ensure_ascii=False).encode("utf-8"),
                           "application/json; charset=utf-8")
        elif path == "/api/asset":
            # 只送工作区内的图片类文件，且只读 —— 页面用 <img src> 直接引用
            try:
                rel = (qs.get("path") or [""])[0]
                p = resolve_in_root(rel)
                if not p.is_file() or p.suffix.lower() not in (".svg", ".png", ".jpg", ".jpeg"):
                    raise ApiError("不是可展示的图片：" + rel, 404)
                suffix = p.suffix.lower()
                ctype = {".svg": "image/svg+xml", ".png": "image/png",
                         ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}[suffix]
                extra = {}
                if suffix == ".svg":
                    # SVG 里可以带 <script>。用 <img> 加载不会执行，但**直接导航**
                    # 就会在同源里跑起来 —— 那样它能 fetch("/") 读到会话令牌，
                    # 再用令牌调写接口。加 CSP sandbox 把它关进笼子。
                    extra["Content-Security-Policy"] = "sandbox; default-src 'none'; style-src 'unsafe-inline'"
                self._send(200, p.read_bytes(), ctype + "; charset=utf-8", extra)
            except ApiError as exc:
                self._send(exc.status, json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8"),
                           "application/json; charset=utf-8")
        elif path == "/api/actions":
            payload = json.dumps({"actions": [{"id": k, "label": v[0], "params": v[1]}
                                              for k, v in ACTIONS.items()]},
                                 ensure_ascii=False).encode("utf-8")
            self._send(200, payload, "application/json; charset=utf-8")
        elif path == "/api/ping":
            self._send(200, b"ok", "text/plain; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain; charset=utf-8")

    def _read_json_body(self):
        # 强制 application/json：跨站简单请求只能用 text/plain / form-urlencoded，
        # 要求 json 就等于强制预检 —— 而预检会被上面的 Origin 检查拦掉。
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            raise ApiError("Content-Type 必须是 application/json", 415)
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_EDIT_BYTES + 65536:
            raise ApiError("请求体缺失或过大", 413)
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            raise ApiError("请求体不是合法 JSON", 400)

    def do_POST(self):
        from urllib.parse import urlparse
        path = urlparse(self.path).path
        try:
            self._guard(need_token=True)
            body = self._read_json_body()
            if path == "/api/file":
                result = write_file_payload(body.get("path"), body.get("content"),
                                            body.get("expected_sha256"), body.get("case"))
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"),
                           "application/json; charset=utf-8")
            elif path == "/api/run":
                result = run_action(body.get("case"), body.get("action"), body.get("params") or {})
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"),
                           "application/json; charset=utf-8")
            else:
                self._send(404, json.dumps({"error": "unknown endpoint"}).encode("utf-8"),
                           "application/json; charset=utf-8")
        except ApiError as exc:
            self._send(exc.status, json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")
        except Exception as exc:
            self._send(500, json.dumps({"error": repr(exc)}, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")


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

    Handler.default_case = case_dir
    Handler.extra_roots = extra
    # 会话令牌：每次启动重新生成。写接口要求带上它，页面从自己那份 HTML 里读。
    Handler.token = secrets.token_urlsafe(24)
    Handler.ui_bytes = UI.read_bytes()

    # 单实例锁：两个 liveview 会跑两套看守线程，双倍扫盘（审核实测过）。
    # 端口探测只是"找个空位"，不是"独占" —— 所以需要单独的锁文件。
    lock = ROOT / ".liveview.lock"
    try:
        if lock.is_file():
            old = lock.read_text(encoding="utf-8").strip()
            pid_txt = old.split()[0] if old else ""
            alive = False
            if pid_txt.isdigit():
                import subprocess as _sp
                out = _sp.run(["tasklist", "/FI", "PID eq " + pid_txt, "/NH"],
                              capture_output=True, text=True,
                              creationflags=getattr(_sp, "CREATE_NO_WINDOW", 0))
                alive = pid_txt in (out.stdout or "")
            if alive:
                print("  已经有一个 liveview 在跑（pid %s）。" % pid_txt)
                print("  同时开两个会跑两套看守线程、双倍扫盘。")
                print("  要强制再开一个，先删掉 " + str(lock))
                return 3
        lock.write_text("%d %s\n" % (os.getpid(), now_iso()), encoding="utf-8")
    except SystemExit:
        raise
    except Exception as exc:
        print("  单实例锁写不了（不影响使用）：" + repr(exc))

    # 看守后台线程：不依赖有没有人开页面，服务在跑就在看守。
    def _watch_loop():
        interval = 3.0
        while True:
            try:
                for c in list_cases():
                    watch.tick(Path(c["dir"]))
            except Exception:
                pass
            time.sleep(interval)

    threading.Thread(target=_watch_loop, daemon=True).start()
    print("  案例数  : " + str(len(list_cases())) + "（可用 ?case=<id> 切换）")

    port = pick_port(args.port)
    url = "http://127.0.0.1:" + str(port) + "/"

    print("=" * 62)
    print("  叶轮机械设计工作台 · 实时窗口")
    print("=" * 62)
    print("  案例    : " + str(case_dir))
    print("  监视    : " + "；".join([str(case_dir)] + extra))
    print("  地址    : " + url)
    print("  规矩    : " + str(len(parse_contracts())) + " 条（含人话解释）")
    print("  白话对照: " + str(len(plain_language().get("terms", []))) + " 个词 / "
          + str(len(plain_language().get("stages", []))) + " 个步骤")
    print("  可写    : 是（人工操作走 case_ledger，日志记 操作者=human(web-ui)）")
    print("  停止    : 按 Ctrl+C")
    print("=" * 62)

    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    import atexit

    def _drop_lock():
        try:
            if lock.is_file() and lock.read_text(encoding="utf-8").startswith(str(os.getpid())):
                lock.unlink()
        except Exception:
            pass
    atexit.register(_drop_lock)
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
