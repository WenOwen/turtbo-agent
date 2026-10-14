"""agent_reply.py - 聊天输入的最小应答回路。

不是真 agent，只是把"自然语言 → 已可执行命令"的口径接住，再回填一句工程上下文。

沿用项目既有约定：
- 不写任何案例目录，只读。
- 不引第三方依赖。
- 输出结构稳定：每条消息都有 case / stage / source / kind，便于 UI 着色。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent

# 命令前缀 → (动作, 参数解析)
COMMANDS = {
    "help":      "help",
    "case":      "switch",
    "open":      "open",
    "show":      "open",
    "ls":        "list",
    "list":      "list",
    "run":       "run",
    "refresh":   "refresh",
    "where":     "where",
    "status":    "status",
    "verify":    "run",
    "preflight": "run",
    "audit":     "run",
    "replay":    "run",
    "gate":      "run",
}


def _read_json_safe(p: Path) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def parse_command(text: str) -> Tuple[str, List[str]]:
    """把 'open x/y.csv' 切成 ('open', ['x/y.csv'])。无前缀视为 'status'。"""
    text = (text or "").strip()
    if not text:
        return "status", []
    parts = re.split(r"\s+", text, maxsplit=1)
    head = parts[0].lower()
    rest = parts[1].strip() if len(parts) > 1 else ""
    args = re.split(r"\s+", rest) if rest else []
    cmd = COMMANDS.get(head, "status")
    return cmd, args


def _latest_state(case_dir: Path) -> Dict[str, Any]:
    state = _read_json_safe(case_dir / "STATE.json") or {}
    manifest = _read_json_safe(case_dir / "manifest.json") or {}
    return {
        "current_stage": manifest.get("current_stage") or state.get("current_stage"),
        "revision": manifest.get("revision"),
        "artifact_count": len(manifest.get("artifacts", []) or []),
        "blockers": state.get("blockers") or [],
    }


def cmd_status(case_dir: Path, _args: List[str]) -> Dict[str, Any]:
    s = _latest_state(case_dir)
    line = "当前阶段 " + (s.get("current_stage") or "—") + "　·　产物 " + str(s.get("artifact_count", 0)) + " 件"
    if s.get("blockers"):
        line += "　·　阻塞 " + "; ".join((b.get("reason") or "") for b in s["blockers"])
    return {"kind": "info", "text": line, "state": s}


def cmd_help(_case_dir: Path, _args: List[str]) -> Dict[str, Any]:
    lines = [
        "可用命令：",
        "  case <id>                切换左侧案例",
        "  open <path>              读文件并回灌首 200 字",
        "  list                     列出当前案例最近改动的 5 个文件",
        "  run preflight            跑环境预检",
        "  run gate G0..G6          跑对应闸门检查",
        "  run verify               校验产物与哈希",
        "  run audit                规矩自检",
        "  run replay               v7 黄金基准回放",
        "  status                   看当前案例阶段、产物、阻塞",
        "  refresh                  强制刷新中间面板",
        "  help                     显示本帮助",
        "无前缀或未知命令 → 视为 status。",
    ]
    return {"kind": "info", "text": "\n".join(lines)}


def cmd_switch(case_dir: Path, args: List[str]) -> Dict[str, Any]:
    if not args:
        return {"kind": "info", "text": "用法：case <id>", "switch_to": None}
    return {"kind": "switch", "text": "已切换到 " + args[0], "switch_to": args[0]}


def cmd_open(case_dir: Path, args: List[str]) -> Dict[str, Any]:
    if not args:
        return {"kind": "info", "text": "用法：open <path>"}
    rel = args[0]
    p = (case_dir / rel).resolve()
    try:
        p.relative_to(case_dir)
    except ValueError:
        return {"kind": "error", "text": "路径越界：open 必须留在当前案例目录内"}
    if not p.is_file():
        return {"kind": "error", "text": "文件不存在：" + rel}
    if p.stat().st_size > 256 * 1024:
        return {"kind": "info", "text": "文件过大（>" + str(p.stat().st_size // 1024) + " KB），用编辑器查看"}
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return {"kind": "error", "text": "读失败：" + repr(exc)}
    head = text[:200].rstrip()
    more = "（…剩余 " + str(max(0, len(text) - 200)) + " 字节）" if len(text) > 200 else ""
    return {"kind": "open", "text": "—— " + rel + " ——\n" + head + more,
            "path": rel, "bytes": p.stat().st_size}


def cmd_list(case_dir: Path, _args: List[str]) -> Dict[str, Any]:
    found = []
    skip = {"__pycache__", ".git", "node_modules", ".venv", ".pytest_cache",
            ".ruff_cache", ".playwright-cli", ".turbo-flow", "_watch"}
    for dirpath, dirnames, filenames in os.walk(case_dir):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for fn in filenames:
            p = Path(dirpath) / fn
            try:
                st = p.stat()
            except Exception:
                continue
            found.append((p, st.st_mtime))
    found.sort(key=lambda x: x[1], reverse=True)
    lines = ["最近改动（最多 5 条）："]
    for p, _ in found[:5]:
        try:
            rel = p.relative_to(case_dir).as_posix()
        except ValueError:
            rel = str(p)
        lines.append("  " + rel)
    return {"kind": "info", "text": "\n".join(lines)}


def cmd_refresh(_case_dir: Path, _args: List[str]) -> Dict[str, Any]:
    return {"kind": "refresh", "text": "已触发刷新，中间面板会重新拉数据。"}


def cmd_where(case_dir: Path, _args: List[str]) -> Dict[str, Any]:
    return {"kind": "info", "text": "案例目录：" + str(case_dir.relative_to(ROOT))}


def cmd_run(case_dir: Path, args: List[str]) -> Dict[str, Any]:
    if not args:
        return {"kind": "info", "text": "用法：run preflight|gate G3|verify|audit|replay"}
    head = args[0].lower()
    if head == "preflight":
        cmd = [str(Path(__file__).resolve().parent / "preflight.py"), "all"]
        return _run_subprocess(cmd, ROOT, "环境预检")
    if head == "gate":
        gate = (args[1] if len(args) > 1 else "G2").upper()
        GATE_MAP = {"G0": "requirements", "G1": "brief", "G2": "scheme", "G3": "geometry",
                    "G4": "mesh", "G5": "solve", "G6": "post"}
        if gate not in GATE_MAP:
            return {"kind": "error", "text": "gate 必须是 G0..G6"}
        cmd = [str(Path(__file__).resolve().parent / "gate_check.py"),
               GATE_MAP[gate], "--case", str(case_dir), "--no-log"]
        return _run_subprocess(cmd, ROOT, "G" + GATE_MAP[gate][0] + " 闸门检查")
    if head == "verify":
        cmd = [str(Path(__file__).resolve().parent / "case_ledger.py"), "verify",
               "--case", str(case_dir)]
        return _run_subprocess(cmd, ROOT, "产物与哈希校验")
    if head == "audit":
        cmd = [str(Path(__file__).resolve().parent / "gate_check.py"), "audit",
               "--case", str(case_dir)]
        return _run_subprocess(cmd, ROOT, "规矩自检")
    if head == "replay":
        baseline = ROOT.parent / "Ducted-Fan" / "run" / "90kg-duct-fan-v7" / "fine" / "v7-optimized"
        if not baseline.is_dir():
            return {"kind": "error", "text": "找不到基准目录：" + str(baseline)}
        cmd = [str(Path(__file__).resolve().parent / "replay_audit.py"),
               "--baseline", str(baseline), "--case", str(case_dir), "--label", "v7"]
        return _run_subprocess(cmd, ROOT, "v7 黄金基准回放")
    return {"kind": "info", "text": "未知 run 子命令：" + head + "。可用：preflight / gate G3 / verify / audit / replay"}


def _run_subprocess(cmd: List[str], cwd: Path, label: str) -> Dict[str, Any]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=600, cwd=str(cwd))
        out = (proc.stdout or "")[-1500:]
        err = (proc.stderr or "")[-800:]
        ok = proc.returncode == 0
        text = ("✓ " if ok else "✗ ") + label
        if out.strip():
            text += "\n── stdout ──\n" + out.rstrip()
        if err.strip():
            text += "\n── stderr ──\n" + err.rstrip()
        return {"kind": "run", "text": text, "ok": ok, "exit": proc.returncode,
                "command": " ".join(cmd[1:])}
    except subprocess.TimeoutExpired:
        return {"kind": "error", "text": label + "：超时（600 秒）"}
    except Exception as exc:
        return {"kind": "error", "text": label + "：失败 " + repr(exc)}


def reply(case_dir: Path, text: str) -> Dict[str, Any]:
    """主入口：返回一条 agent 消息（含 kind / switch / open / info / error / run / refresh）。"""
    cmd, args = parse_command(text)
    handler = {
        "status":  cmd_status,
        "help":    cmd_help,
        "switch":  cmd_switch,
        "open":    cmd_open,
        "list":    cmd_list,
        "where":   cmd_where,
        "refresh": cmd_refresh,
        "run":     cmd_run,
    }.get(cmd, cmd_status)
    return handler(case_dir, args)