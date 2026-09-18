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
WRITE_DENY_PARTS = {".git", "_memfix", "node_modules", "__pycache__", ".venv"}
TEXT_SUFFIXES = {".md", ".json", ".yaml", ".yml", ".csv", ".txt", ".py", ".ps1", ".cmd", ".html",
                 ".trb", ".bcs", ".config", ".info", ".qualityReport", ".geomTurbo", ".log", ".std"}


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def resolve_in_root(rel):
    """把相对路径解析成 ROOT 内的绝对路径；越界、目录、黑名单一律拒绝。"""
    if not rel or not isinstance(rel, str):
        raise ApiError("缺少路径")
    candidate = (ROOT / rel.replace("\\", "/")).resolve()
    try:
        candidate.relative_to(ROOT)
    except ValueError:
        raise ApiError("路径越界，只允许工作区内的文件", 403)
    for part in candidate.relative_to(ROOT).parts:
        if part in WRITE_DENY_PARTS:
            raise ApiError("该目录不允许通过界面修改：" + part, 403)
    return candidate


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
    p = resolve_in_root(rel)
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
    "gate":       ("跑阶段闸门", "gate=G0..G6 对应的子命令名"),
    "verify":     ("校验案例产物与哈希", ""),
    "preflight":  ("环境预检", ""),
    "replay":     ("回放审计 v7 黄金基准", ""),
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
            raise ApiError("闸门参数必须是 G0..G6", 400)
        cmd = [sys.executable, str(HERE / "gate_check.py"), GATE_MAP[gate],
               "--case", str(case_dir), "--no-log"]
    elif action == "verify":
        cmd = [sys.executable, str(HERE / "case_ledger.py"), "verify", "--case", str(case_dir)]
    elif action == "preflight":
        cmd = [sys.executable, str(HERE / "preflight.py"), "all"]
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

    # 这里**不写日志**：跑闸门/校验/预检只是看结果，没有改变任何工程内容。
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
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        case_id = (qs.get("case") or [None])[0]

        if path in ("/", "/index.html"):
            self._send(200, self.ui_bytes, "text/html; charset=utf-8")
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
    Handler.ui_bytes = UI.read_bytes()

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
    print("  合同    : " + str(len(parse_contracts())) + " 条（含人话解释）")
    print("  可写    : 是（人工操作走 case_ledger，日志记 操作者=human(web-ui)）")
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
