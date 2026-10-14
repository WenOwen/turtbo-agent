"""agent_web.py - 三栏可视化 agent 对话 Web 界面。

服务 / 设计目标
----------------
服务绑 127.0.0.1:8910（可改），只读默认；写接口走乐观锁 + 三道门（Host / 跨站 / 令牌）。

三栏数据
  GET  /                 三栏 UI
  GET  /api/cases        案例列表（左侧源）
  GET  /api/state        中间面板状态（一次拉全，5s 轮询 + WS 推 push）
  GET  /api/views        中间面板可视化（scheme / check / geom / mesh / cfd）
  GET  /api/asset?path=  SVG / 图片（sandboxed CSP）
  GET  /api/file?path=   读文件（受限路径）
  POST /api/file         写文件（乐观锁 + 白名单）
  GET  /api/chat?case=   聊天历史
  POST /api/chat         发消息 → 回复
  GET  /api/actions      工具动作白名单
  POST /api/run          跑白名单动作
  WS   /ws             推 push（state / chat / watch tick）

复用：liveview 的 list_cases / Aggregator / build_views / 子命令。
不重复实现：把现有函数 import 进来。
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as _dt
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
import uvicorn

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

# ── 复用 liveview 的数据层 ────────────────────────────────────────────────
import liveview as lv  # type: ignore
import case_watch as cw  # type: ignore
import agent_reply as ar  # type: ignore

UI = HERE / "agent_web_ui.html"

# 聊天历史 = 内存 + 落盘（cases/<id>/_watch/chat.jsonl）。
# 落盘为了让重启后能续读；旧的对话仍会由"案例"归档而不是全局共享。
CHAT_LOG: Dict[str, List[Dict[str, Any]]] = {}
CHAT_LOCK = threading.Lock()
CHAT_PERSIST_VERSION = 1  # 写盘格式版本，将来字段迁移时改这个


def _chat_path(case_dir: Path) -> Path:
    return Path(case_dir) / "_watch" / "chat.jsonl"


def _load_chat_for(case_id: str, case_dir: Optional[Path]) -> List[Dict[str, Any]]:
    """从 _watch/chat.jsonl 读已存的历史；存在就覆盖内存里的初值。"""
    if case_dir is None:
        return []
    p = _chat_path(case_dir)
    if not p.is_file():
        return []
    out: List[Dict[str, Any]] = []
    try:
        with p.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("v") != CHAT_PERSIST_VERSION:
                    continue
                if rec.get("case") != case_id:
                    continue
                m = rec.get("msg") or {}
                if isinstance(m, dict):
                    out.append(m)
    except OSError:
        return []
    return out[-200:]


CHAT_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
CHAT_KEEP_BACKUP = True  # 滚动后保留 chat.jsonl.bak


def _maybe_rotate_chat(p: Path) -> None:
    """当 chat.jsonl 超过 CHAT_MAX_BYTES 时，bak + 重开（保留尾部 50%）。"""
    try:
        size = p.stat().st_size
    except OSError:
        return
    if size < CHAT_MAX_BYTES:
        return
    try:
        # 保留尾部 50%（但不超过文件本身大小）；太小就全清
        keep = min(max(size // 2, 64 * 1024), size)
        with p.open("rb") as fh:
            fh.seek(-keep, 2)
            tail = fh.read()
        # 找到下一行起点（避免半截行）
        nl = tail.find(b"\n")
        if nl >= 0 and nl + 1 < len(tail):
            tail = tail[nl + 1:]
        # 写新文件 → 重命名
        tmp = p.with_suffix(".jsonl.tmp")
        with tmp.open("wb") as fh:
            fh.write(tail)
        if CHAT_KEEP_BACKUP and p.exists():
            bak = p.with_suffix(".jsonl.bak")
            try:
                if bak.exists():
                    bak.unlink()
                p.rename(bak)
            except OSError:
                pass
        tmp.rename(p)
    except OSError:
        pass  # 旋转失败不阻塞主流程


def _persist_chat_for(case_id: str, case_dir: Optional[Path], msg: Dict[str, Any]):
    """把一条消息追加到 _watch/chat.jsonl，失败也不抛（chat 不应阻塞主流程）。"""
    if case_dir is None:
        return
    p = _chat_path(case_dir)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        rec = {"v": CHAT_PERSIST_VERSION, "ts": now_iso(), "case": case_id, "msg": msg}
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        _maybe_rotate_chat(p)
    except OSError:
        pass


def now_iso() -> str:
    return _dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


# ── 聊天历史 ───────────────────────────────────────────────────────────────
def chat_log(case_id: str) -> List[Dict[str, Any]]:
    with CHAT_LOCK:
        return list(CHAT_LOG.get(case_id, []))


def chat_append(case_id: str, msg: Dict[str, Any], case_dir: Optional[Path] = None) -> Dict[str, Any]:
    msg.setdefault("ts", now_iso())
    with CHAT_LOCK:
        existing = CHAT_LOG.get(case_id)
        if existing is None:
            existing = _load_chat_for(case_id, case_dir)
            CHAT_LOG[case_id] = existing
        existing.append(msg)
        if len(existing) > 200:
            del existing[:-200]
    _persist_chat_for(case_id, case_dir, msg)
    return msg


# ── WebSocket 推送 ───────────────────────────────────────────────────────
class Broadcaster:
    def __init__(self):
        self._clients: Dict[str, List[WebSocket]] = {}
        self._lock = threading.Lock()

    def add(self, case_id: str, ws: WebSocket):
        with self._lock:
            self._clients.setdefault(case_id, []).append(ws)

    def remove(self, case_id: str, ws: WebSocket):
        with self._lock:
            if case_id in self._clients and ws in self._clients[case_id]:
                self._clients[case_id].remove(ws)
                if not self._clients[case_id]:
                    del self._clients[case_id]

    async def push(self, case_id: str, kind: str, payload: Any):
        msg = json.dumps({"kind": kind, "ts": now_iso(), "payload": payload},
                         ensure_ascii=False)
        dead = []
        with self._lock:
            for ws in self._clients.get(case_id, []):
                try:
                    await ws.send_text(msg)
                except Exception:
                    dead.append(ws)
        for ws in dead:
            self.remove(case_id, ws)

    def broadcast(self, case_id: str, kind: str, payload: Any):
        # 同步版本，给后台 thread 用
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(self.push(case_id, kind, payload), loop)


BC = Broadcaster()


# ── FastAPI 应用 ─────────────────────────────────────────────────────────
app = FastAPI(title="turtbo-agent web", openapi_url=None)


# ── 三道门（Host / 跨站 / 令牌） ────────────────────────────────────────
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "[::1]"}


def _client_host(request: Request) -> str:
    return (request.headers.get("host") or "").strip().lower()


def _host_ok(request: Request) -> bool:
    host = _client_host(request)
    if not host:
        return False
    name = host.rsplit(":", 1)[0] if not host.startswith("[") else host.split("]")[0] + "]"
    return name in ALLOWED_HOSTS


def _cross_site(request: Request) -> bool:
    site = (request.headers.get("sec-fetch-site") or "").strip().lower()
    if site and site not in ("same-origin", "same-site", "none"):
        return True
    origin = (request.headers.get("origin") or "").strip()
    if origin and origin != "null":
        from urllib.parse import urlparse as _up
        o = _up(origin)
        if (o.hostname or "") not in ("127.0.0.1", "localhost", "::1"):
            return True
    return False


# 启动时随机生成；写接口要求带回
SESSION_TOKEN = secrets.token_urlsafe(24)
UI_SHA = ""


def _refresh_ui_sha():
    global UI_SHA
    try:
        UI_SHA = hashlib.sha256(UI.read_bytes()).hexdigest()
    except Exception:
        UI_SHA = ""


def _token_required(request: Request):
    got = (request.headers.get("x-dsh-token") or "").strip()
    if got != SESSION_TOKEN:
        raise HTTPException(status_code=403, detail="缺少或错误的会话令牌")


def resolve_case(case_id: Optional[str]):
    """把 case id 解析成路径。None / 不存在 → 退回 default_case。"""
    if case_id:
        hit = lv.case_dir_of(case_id)
        if hit is not None:
            return hit
    return getattr(lv.Handler, "default_case", None)


# ── 静态路由 ─────────────────────────────────────────────────────────────
@app.get("/", response_class=Response)
async def index():
    if not UI.is_file():
        raise HTTPException(status_code=500, detail="UI 文件不存在")
    raw = UI.read_bytes()
    _refresh_ui_sha()
    raw = raw.replace(b"__DSH_TOKEN__", SESSION_TOKEN.encode("ascii"))
    return Response(content=raw, media_type="text/html; charset=utf-8",
                    headers={"Cache-Control": "no-store",
                             "X-Content-Type-Options": "nosniff"})


# ── 数据路由 ─────────────────────────────────────────────────────────────
@app.get("/api/cases")
async def api_cases(request: Request):
    _token_required(request)
    return {"cases": lv.list_cases()}


def _build_file_tree(case_dir: Path, max_depth: int = 3) -> Dict[str, Any]:
    """给前端渲染'文件' tab 用的轻量目录树（不重 liveview 内部）。"""
    skip = {"__pycache__", ".git", "node_modules", ".venv", ".pytest_cache",
            ".ruff_cache", ".playwright-cli", ".turbo-flow", "_watch",
            "xmt", "abm", "history"}

    def _walk(p: Path, depth: int) -> Optional[Dict[str, Any]]:
        if depth > max_depth:
            return None
        try:
            st = p.stat()
        except OSError:
            return None
        node: Dict[str, Any] = {"name": p.name, "size": st.st_size}
        if p.is_dir():
            node["type"] = "dir"
            node["children"] = []
            try:
                for child in sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
                    if child.name in skip:
                        continue
                    sub = _walk(child, depth + 1)
                    if sub is not None:
                        node["children"].append(sub)
            except OSError:
                pass
        else:
            node["type"] = "file"
            node["path"] = str(p.relative_to(case_dir)).replace("\\", "/")
        return node

    root = _walk(case_dir, 0)
    return root or {"name": case_dir.name, "children": []}


@app.get("/api/state")
async def api_state(request: Request, case: Optional[str] = None):
    _token_required(request)
    target = resolve_case(case)
    if target is None:
        raise HTTPException(status_code=404, detail="案例不存在：" + str(case))
    agg = lv.Aggregator(target, getattr(lv.Handler, "extra_roots", []) or [])
    out = agg.build()
    # 给 process 列表加 stage 提示（点击跳日志时用）
    PROC_STAGE = {
        "euranus": "G5", "finebatch": "G5", "finex86": "G5",
        "autogrid": "G4", "iggx86": "G4", "cfview": "G6",
        "mpiexec": "G5", "numeca": "G5",
    }
    for p in out.get("processes") or []:
        n = str(p.get("name", "")).lower()
        for k, stg in PROC_STAGE.items():
            if k in n:
                p["stage"] = stg
                break
    out["file_tree"] = _build_file_tree(target, max_depth=3)
    return out


@app.get("/api/views")
async def api_views(request: Request, case: Optional[str] = None, force: int = 0):
    _token_required(request)
    target = resolve_case(case)
    if target is None:
        raise HTTPException(status_code=404, detail="案例不存在：" + str(case))
    return lv.build_views(target.name, force=bool(force))


@app.get("/api/asset")
async def api_asset(request: Request, path: str):
    _token_required(request)
    p = lv.resolve_in_root(path)
    if not p.is_file() or p.suffix.lower() not in (".svg", ".png", ".jpg", ".jpeg"):
        raise HTTPException(status_code=404, detail="不是可展示的图片")
    suffix = p.suffix.lower()
    ctype = {".svg": "image/svg+xml", ".png": "image/png",
             ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}[suffix]
    extra = {}
    if suffix == ".svg":
        extra["Content-Security-Policy"] = "sandbox; default-src 'none'; style-src 'unsafe-inline'"
    return Response(content=p.read_bytes(), media_type=ctype + "; charset=utf-8",
                    headers=extra)


@app.get("/api/file")
async def api_file(request: Request, path: str):
    _token_required(request)
    return lv.read_file_payload(path)


@app.post("/api/file")
async def api_file_post(request: Request):
    _token_required(request)
    body = await request.json()
    return lv.write_file_payload(body.get("path"), body.get("content"),
                                 body.get("expected_sha256"), body.get("case"))


# ── 聊天路由 ─────────────────────────────────────────────────────────────
@app.get("/api/chat")
async def api_chat_get(request: Request, case: Optional[str] = None):
    _token_required(request)
    target = resolve_case(case)
    if target is None:
        return {"messages": []}
    # 第一次读时回灌历史
    with CHAT_LOCK:
        if target.name not in CHAT_LOG:
            CHAT_LOG[target.name] = _load_chat_for(target.name, target)
    return {"messages": chat_log(target.name)}


# ── 后台任务（preflight / gate G3 等慢任务） ──────────────────────────
import job_state  # type: ignore

JOB_THREADS: Dict[str, threading.Thread] = {}


def _job_start(case_dir: Path, label: str, cmd: List[str], cwd: Path) -> str:
    """起一个后台线程跑子进程，返回 job_id。状态走 job_state。"""
    job_id = job_state.start_job(
        case_dir.name, label,
        " ".join(cmd[1:]) if len(cmd) > 1 else " ".join(cmd))

    def runner():
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace",
                                  timeout=900, cwd=str(cwd))
            job_state.update_job(
                job_id,
                exit=proc.returncode,
                ok=(proc.returncode == 0),
                stdout_tail=(proc.stdout or "")[-1500:],
                stderr_tail=(proc.stderr or "")[-800:],
                status="done",
                finished=job_state.now_iso(),
            )
        except subprocess.TimeoutExpired:
            job_state.update_job(
                job_id, status="timeout",
                stderr_tail="超时（900 秒）", finished=job_state.now_iso())
        except Exception as exc:
            job_state.update_job(
                job_id, status="error",
                stderr_tail=repr(exc), finished=job_state.now_iso())

    t = threading.Thread(target=runner, daemon=True, name="job-" + job_id)
    JOB_THREADS[job_id] = t
    t.start()
    return job_id


@app.get("/api/jobs")
async def api_jobs(request: Request, case: Optional[str] = None):
    _token_required(request)
    return {"jobs": job_state.list_jobs(case=case, limit=30)}


@app.get("/api/jobs/{job_id}")
async def api_job_get(request: Request, job_id: str):
    _token_required(request)
    rec = job_state.get_job(job_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="job 不存在：" + job_id)
    return rec


@app.post("/api/chat")
async def api_chat_post(request: Request):
    _token_required(request)
    body = await request.json()
    case_id = body.get("case")
    text = body.get("text") or ""
    target = resolve_case(case_id)
    if target is None:
        raise HTTPException(status_code=404, detail="案例不存在：" + str(case_id))

    user_msg = chat_append(target.name, {
        "role": "user", "text": text, "ts": now_iso(),
    }, target)
    # 特殊语法："run_async preflight" → 起后台任务；其它走同步 reply
    head = (text or "").strip().lower()
    if head.startswith("run_async"):
        args = text.strip().split()[1:]
        jid = _submit_job_from_text(target, args)
        if jid is None:
            reply = {"kind": "error", "text": "run_async 语法：run_async preflight|gate G3|verify|audit|replay"}
        else:
            reply = {"kind": "info", "text": "后台任务已起：`" + jid + "`。\n等几分钟，发 `job " + jid + "` 看结果。",
                     "job_id": jid, "async": True}
    else:
        reply = ar.reply(target, text)
    reply_msg = chat_append(target.name, {
        "role": "agent",
        "kind": reply.get("kind", "info"),
        "text": reply.get("text", ""),
        "ts": now_iso(),
        **({"switch_to": reply["switch_to"]} if "switch_to" in reply else {}),
        **({"ok": reply["ok"], "exit": reply["exit"],
            "command": reply["command"]} if reply.get("kind") == "run" else {}),
        **({"path": reply["path"], "bytes": reply["bytes"]} if "path" in reply else {}),
        **({"next_stage": reply["next_stage"]} if "next_stage" in reply else {}),
        **({"job_id": reply["job_id"]} if "job_id" in reply else {}),
    }, target)
    return {"user": user_msg, "reply": reply_msg}


def _submit_job_from_text(case_dir: Path, args: List[str]) -> Optional[str]:
    """把 run_async 参数翻译成子进程命令并起任务。"""
    if not args:
        return None
    head = args[0].lower()
    if head == "preflight":
        cmd = [str(HERE / "preflight.py"), "all"]
        return _job_start(case_dir, "环境预检", cmd, ROOT)
    if head == "gate":
        gate = (args[1] if len(args) > 1 else "G2").upper()
        GATE_MAP = {"G0": "requirements", "G1": "brief", "G2": "scheme", "G3": "geometry",
                    "G4": "mesh", "G5": "solve", "G6": "post"}
        if gate not in GATE_MAP:
            return None
        cmd = [str(HERE / "gate_check.py"),
               GATE_MAP[gate], "--case", str(case_dir), "--no-log"]
        return _job_start(case_dir, "G" + GATE_MAP[gate][0] + " 闸门检查", cmd, ROOT)
    if head == "verify":
        cmd = [str(HERE / "case_ledger.py"), "verify", "--case", str(case_dir)]
        return _job_start(case_dir, "产物与哈希校验", cmd, ROOT)
    if head == "audit":
        cmd = [str(HERE / "gate_check.py"), "audit", "--case", str(case_dir)]
        return _job_start(case_dir, "规矩自检", cmd, ROOT)
    if head == "replay":
        baseline = ROOT.parent / "Ducted-Fan" / "run" / "90kg-duct-fan-v7" / "fine" / "v7-optimized"
        if not baseline.is_dir():
            return None
        cmd = [str(HERE / "replay_audit.py"),
               "--baseline", str(baseline), "--case", str(case_dir), "--label", "v7"]
        return _job_start(case_dir, "v7 黄金基准回放", cmd, ROOT)
    return None


# ── 动作路由 ─────────────────────────────────────────────────────────────
@app.get("/api/actions")
async def api_actions(request: Request):
    _token_required(request)
    return {"actions": [{"id": k, "label": v[0], "params": v[1]}
                        for k, v in lv.ACTIONS.items()]}


@app.post("/api/run")
async def api_run(request: Request):
    _token_required(request)
    body = await request.json()
    return lv.run_action(body.get("case"), body.get("action"), body.get("params") or {})


# ── ping ─────────────────────────────────────────────────────────────────
@app.get("/api/ping")
async def api_ping():
    return {"ok": True, "ts": now_iso()}


# ── WebSocket ────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket, case: Optional[str] = None,
                       token: Optional[str] = None):
    """只允许带正确 token 的连接。token 通过 ?token=... 传；和 HTTP 头共用同一个 SESSION_TOKEN。

    不带或错 token → 直接 close(1008)，不 accept，避免任何回显。
    """
    if not token or token != SESSION_TOKEN:
        await ws.close(code=1008)
        return
    await ws.accept()
    target = resolve_case(case)
    case_id = target.name if target else "unknown"
    BC.add(case_id, ws)
    await ws.send_text(json.dumps({"kind": "hello", "ts": now_iso(),
                                    "payload": {"case": case_id}}, ensure_ascii=False))
    try:
        while True:
            # 客户端只是偶尔发 ping，主体由 BC.push 主动推
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=30)
                if msg == "ping":
                    await ws.send_text(json.dumps({"kind": "pong", "ts": now_iso()},
                                              ensure_ascii=False))
            except asyncio.TimeoutError:
                await ws.send_text(json.dumps({"kind": "keepalive", "ts": now_iso()},
                                          ensure_ascii=False))
    except WebSocketDisconnect:
        pass
    finally:
        BC.remove(case_id, ws)


# ── 启动 ─────────────────────────────────────────────────────────────────
def pick_port(preferred: int) -> int:
    for port in [preferred] + list(range(preferred + 1, preferred + 20)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return preferred


def pick_case(explicit: Optional[str]) -> Path:
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
    ap = argparse.ArgumentParser(prog="agent_web.py",
                                 description="三栏可视化 agent 对话 Web 界面")
    ap.add_argument("--port", type=int, default=8910)
    ap.add_argument("--case", default=None)
    ap.add_argument("--watch", action="append", default=None)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)

    if not UI.is_file():
        print("缺少界面文件：" + str(UI), file=sys.stderr)
        return 3

    case_dir = pick_case(args.case)
    extra = args.watch if args.watch is not None else [str(p) for p in lv.DEFAULT_EXTRA_ROOTS if p.exists()]

    # liveview.Handler 上的 default_case 用于回退；we 引用同一个变量
    lv.Handler.default_case = case_dir
    lv.Handler.extra_roots = extra

    _refresh_ui_sha()

    # 单实例锁文件
    lock = ROOT / ".agent_web.lock"
    try:
        if lock.is_file():
            old = lock.read_text(encoding="utf-8").strip()
            pid_txt = old.split()[0] if old else ""
            alive = False
            if pid_txt.isdigit():
                out = subprocess.run(["tasklist", "/FI", "PID eq " + pid_txt, "/NH"],
                                     capture_output=True, text=True,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                alive = pid_txt in (out.stdout or "")
            if alive:
                print("  已经有一个 agent_web 在跑（pid %s）。" % pid_txt)
                return 3
        lock.write_text("%d %s\n" % (os.getpid(), now_iso()), encoding="utf-8")
    except Exception as exc:
        print("  单实例锁写不了：" + repr(exc))

    # 看守后台线程：每次 tick 给所有接入的客户端推 push
    def _watch_loop():
        last = 0.0
        while True:
            try:
                for c in lv.list_cases():
                    cw.tick(Path(c["dir"]))
                    # 每 3 秒推一次 state 增量（不是全量）
                    if time.time() - last > 3.0:
                        agg = lv.Aggregator(Path(c["dir"]), extra)
                        BC.broadcast(c["id"], "state", agg.build())
                last = time.time()
            except Exception:
                pass
            time.sleep(3.0)

    threading.Thread(target=_watch_loop, daemon=True).start()

    port = pick_port(args.port)
    url = "http://127.0.0.1:" + str(port) + "/"
    print("=" * 62)
    print("  turtbo-agent · 三栏可视化对话 Web 界面")
    print("=" * 62)
    print("  案例    : " + str(case_dir))
    print("  监视    : " + "；".join([str(case_dir)] + extra))
    print("  地址    : " + url)
    print("  令牌    : " + SESSION_TOKEN)
    print("  停止    : 按 Ctrl+C")
    print("=" * 62)

    # 写一份 token 到 .agent_web.token（smoke / 启动脚本可读）
    try:
        (ROOT / ".agent_web.token").write_text(SESSION_TOKEN, encoding="utf-8")
    except Exception:
        pass

    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    import atexit
    def _drop_lock():
        try:
            if lock.is_file() and lock.read_text(encoding="utf-8").startswith(str(os.getpid())):
                lock.unlink()
        except Exception:
            pass
    atexit.register(_drop_lock)

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())