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
from datetime import datetime
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
    "ls":        "ls",
    "dir":       "ls",
    "list":      "list",
    "recent":    "list",
    "run":       "run",
    "refresh":   "refresh",
    "where":     "where",
    "status":    "status",
    "verify":    "run",
    "preflight": "run",
    "audit":     "run",
    "replay":    "run",
    "gate":      "run",
    "design":    "design",
    "manifest":  "manifest",
    "log":       "log",
    "summary":   "summary",
    "pending":   "pending",
    "get":       "get",
    "find":      "find",
    "note":      "note",
    "tree":      "tree",
    "next":      "next",
    "plan":      "plan",
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


def cmd_design(case_dir: Path, _args: List[str]) -> Dict[str, Any]:
    """调 design_summary.py 读 方案/设计值对照；优先用它的结果（与中间面板同源）。"""
    try:
        import design_summary  # type: ignore
    except Exception as exc:
        return {"kind": "error", "text": "design_summary 加载失败：" + repr(exc)}
    try:
        ds = design_summary.build_design_summary(case_dir)
        lines = ["设计摘要（来自 design_summary）："]
        target = ds.get("target_kgf")
        peak = ds.get("peak") or {}
        peak_kgf = peak.get("thrust_kgf") if peak else None
        gap = (peak_kgf - target) if (target and peak_kgf) else None
        lines.append("  目标推力  " + (f"{target:.2f} kgf" if target else "—") + "（" + (f"{ds.get('target_n'):.0f} N" if ds.get("target_n") else "—") + "）")
        lines.append("  实测最大  " + (f"{peak_kgf:.2f} kgf" if peak_kgf else "—") + "（" + (f"{peak.get('thrust_n'):.0f} N" if peak and peak.get("thrust_n") else "—") + "）")
        if gap is not None:
            lines.append("  差距      " + f"{gap:+.3f} kgf")
        lines.append("  实测点数  " + str(sum(1 for r in (ds.get("results") or []) if r.get("state") in ("analyzed", "converged", "accepted"))))
        latest = ds.get("latest_scheme") or {}
        if latest:
            lines.append("  最近方案  " + str(latest.get("version")) + "　·　status=" + str(latest.get("status", "—")))
        return {"kind": "info", "text": "\n".join(lines), "summary": ds}
    except Exception as exc:
        return {"kind": "error", "text": "design_summary 计算失败：" + repr(exc)}


def cmd_manifest(case_dir: Path, _args: List[str]) -> Dict[str, Any]:
    m = _read_json_safe(case_dir / "manifest.json") or {}
    if not m:
        return {"kind": "info", "text": "（无 manifest.json）"}
    keys = ("id", "title", "current_stage", "revision", "requirement",
            "engine_model", "duct_inner_mm", "rpm_peak")
    lines = ["manifest.json："]
    for k in keys:
        if k in m:
            v = m[k]
            if isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False)[:120]
            lines.append("  " + k + ": " + str(v))
    return {"kind": "info", "text": "\n".join(lines)}


def cmd_log(case_dir: Path, args: List[str]) -> Dict[str, Any]:
    n = 20
    if args and args[0].isdigit():
        n = max(1, min(200, int(args[0])))
    log = case_dir / "LOG.md"
    if not log.is_file():
        return {"kind": "info", "text": "（无 LOG.md）"}
    text = log.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    tail = lines[-n:] if len(lines) > n else lines
    return {"kind": "info", "text": "LOG.md 尾 " + str(len(tail)) + " 行：\n" + "\n".join(tail)}


def cmd_summary(case_dir: Path, _args: List[str]) -> Dict[str, Any]:
    """一句话：把 status + 目标差距 + 最近文件合并到一条信息。"""
    parts = [cmd_status(case_dir, []), cmd_design(case_dir, []), cmd_list(case_dir, [])]
    return {"kind": "info", "text": "\n\n".join(p["text"] for p in parts)}


def cmd_pending(case_dir: Path, _args: List[str]) -> Dict[str, Any]:
    """展示：当前阶段 + LOG.md 末尾最近 5 段结论中带 FAIL/WARN 的条目（若没有则说明）。"""
    log = case_dir / "LOG.md"
    if not log.is_file():
        return {"kind": "info", "text": "（无 LOG.md）"}
    text = log.read_text(encoding="utf-8", errors="replace")
    # LOG.md 的每段以 "## " 开头
    sections = re.split(r"(?m)^## ", text)
    headers = [s for s in sections if s.strip() and re.match(r"\d{4}-", s)]
    if not headers:
        return {"kind": "info", "text": "（LOG.md 无条目）"}
    recent = headers[-5:]
    lines = ["最近 5 段 LOG（含 WARN/FAIL 标记）："]
    bad = []
    for h in recent:
        first = h.splitlines()[0] if h.splitlines() else ""
        verdict = re.search(r"\b(PASS|WARN|FAIL|SKIP)\b", h)
        v = verdict.group(0) if verdict else "—"
        lines.append("  [" + v + "] " + first.strip())
        if v in ("WARN", "FAIL"):
            # 抓 FAIL/WARN 那行的实测摘要
            m = re.search(r"实测：([^\n]+)", h)
            if m:
                bad.append("    " + first.strip() + " → " + m.group(1).strip()[:120])
    if bad:
        lines.append("")
        lines.append("未通过的实测摘要：")
        lines.extend(bad)
    return {"kind": "info", "text": "\n".join(lines)}


def cmd_get(case_dir: Path, args: List[str]) -> Dict[str, Any]:
    """按点路径读 manifest.json 字段（例：get requirement.thrust.target_n / get id）。"""
    if not args:
        return {"kind": "info", "text": "用法：get <key[.subkey]>\n例：get id / get requirement.thrust.target_n"}
    path = args[0]
    m = _read_json_safe(case_dir / "manifest.json") or {}
    cur: Any = m
    for piece in path.split("."):
        if isinstance(cur, dict) and piece in cur:
            cur = cur[piece]
        else:
            return {"kind": "info", "text": "（无该字段）"}
    if isinstance(cur, (dict, list)):
        return {"kind": "info", "text": path + " =\n" + json.dumps(cur, ensure_ascii=False, indent=2)}
    return {"kind": "info", "text": path + " = " + str(cur)}


def cmd_find(case_dir: Path, args: List[str]) -> Dict[str, Any]:
    """在当前案例目录（除大目录外）下按文本片段搜，返回最多 12 条命中位置。"""
    if not args:
        return {"kind": "info", "text": "用法：find <pattern>\n例：find R1.abp"}
    needle = " ".join(args)
    skip_dirs = {"__pycache__", ".git", "node_modules", ".venv", ".pytest_cache",
                 ".ruff_cache", ".playwright-cli", ".turbo-flow", "_watch",
                 "figures", "xmt", "abm"}
    hits: List[Tuple[str, int, str]] = []
    for dirpath, dirnames, filenames in os.walk(case_dir):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for fn in filenames:
            p = Path(dirpath) / fn
            if p.stat().st_size > 512 * 1024:
                continue  # 跳过 >512K 的二进制
            try:
                with p.open("r", encoding="utf-8", errors="replace") as fp:
                    for ln, line in enumerate(fp, 1):
                        if needle in line:
                            try:
                                rel = p.relative_to(case_dir).as_posix()
                            except ValueError:
                                rel = str(p)
                            hits.append((rel, ln, line.rstrip()[:160]))
                            if len(hits) >= 12:
                                break
            except Exception:
                continue
            if len(hits) >= 12:
                break
        if len(hits) >= 12:
            break
    if not hits:
        return {"kind": "info", "text": "（无命中）"}
    lines = ["命中 " + needle + "（最多 12 条）："]
    for rel, ln, line in hits:
        lines.append("  " + rel + ":" + str(ln) + "  " + line)
    return {"kind": "info", "text": "\n".join(lines)}


def cmd_note(case_dir: Path, args: List[str]) -> Dict[str, Any]:
    """把一行注释追加到 LOG.md，标注来源 agent 聊天。这是写命令，会动 case 目录。"""
    if not args:
        return {"kind": "info", "text": "用法：note <text>"}
    log = case_dir / "LOG.md"
    text = " ".join(args)
    now = datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
    block = "\n## " + now + " | 笔记 | INFO\n- 动作：agent 聊天手记\n- 内容：" + text + "\n- 来源：tools/agent_reply.cmd_note\n"
    try:
        with log.open("a", encoding="utf-8") as fp:
            fp.write(block)
    except Exception as exc:
        return {"kind": "error", "text": "写 LOG.md 失败：" + repr(exc)}
    return {"kind": "info", "text": "已写入 LOG.md（" + now + "）"}


def cmd_help(_case_dir: Path, _args: List[str]) -> Dict[str, Any]:
    lines = [
        "可用命令：",
        "  case <id>                切换左侧案例",
        "  open <path>              读文件并回灌首 200 字",
        "  list                     列出当前案例最近改动的 5 个文件",
        "  ls [stage]               列某阶段目录文件（无参 → 列所有阶段摘要）",
        "  tree [depth]             目录树（默认深度 2）",
        "  run preflight            跑环境预检",
        "  run gate G0..G6          跑对应闸门检查",
        "  run verify               校验产物与哈希",
        "  run audit                规矩自检",
        "  run replay               v7 黄金基准回放",
        "  status                   看当前案例阶段、产物、阻塞",
        "  design                   目标推力 / 实测最大 / 差距（design_summary 同源）",
        "  manifest                 关键字段（id/要求/电机/包络/转速）",
        "  get <key>                按点路径读 manifest 字段",
        "  log [N]                  LOG.md 尾 N 行（默认 20，最多 200）",
        "  pending                  最近 5 段 LOG 里的 WARN/FAIL 摘要",
        "  next                     基于当前阶段给「下一动作」建议",
        "  plan                     现状+下一步+待办的三段叙事",
        "  find <pattern>           在当前案例目录搜文本（最多 12 条）",
        "  note <text>              把一行手记追加到 LOG.md",
        "  summary                  status+design+list 的合并视图",
        "  refresh                  强制刷新中间面板",
        "  where                    报当前案例目录",
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


def cmd_tree(case_dir: Path, args: List[str]) -> Dict[str, Any]:
    """列目录树（按 stage 排序，深度 2，跳过 noise）。"""
    max_depth = 2
    if args and args[0].isdigit():
        max_depth = max(1, min(4, int(args[0])))
    skip = {"__pycache__", ".git", "node_modules", ".venv", ".pytest_cache",
            ".ruff_cache", ".playwright-cli", ".turbo-flow", "_watch",
            "xmt", "abm", "figures", "history"}
    lines = ["目录树（深度 " + str(max_depth) + "）："]
    root_depth = len(case_dir.parts)
    for dirpath, dirnames, filenames in os.walk(case_dir):
        rel = Path(dirpath).relative_to(case_dir)
        depth = len(rel.parts)
        if depth > max_depth:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in skip]
        # 排序：阶段目录优先
        dirnames.sort()
        prefix = "  " * depth
        if depth == 0:
            lines.append(case_dir.name + "/")
        else:
            lines.append(prefix + rel.parts[-1] + "/")
        sub = "  " * (depth + 1)
        for fn in sorted(filenames):
            lines.append(sub + fn)
    return {"kind": "info", "text": "\n".join(lines[:200])}


def cmd_ls(case_dir: Path, args: List[str]) -> Dict[str, Any]:
    """ls <stage> —— 列某阶段目录的文件（不带参数 → 列所有阶段目录的 size 摘要）。"""
    if not args:
        # 列所有 0X-xxx 阶段目录
        lines = ["阶段目录："]
        for d in sorted(case_dir.iterdir()):
            if not d.is_dir() or not re.match(r"^\d{2}-", d.name):
                continue
            size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
            count = sum(1 for _ in d.rglob("*") if _.is_file())
            lines.append("  " + d.name + "　·　" + str(count) + " 文件　·　"
                         + str(size // 1024) + " KB")
        return {"kind": "info", "text": "\n".join(lines)}
    stage = args[0]
    target = case_dir / stage
    if not target.is_dir():
        # 容错：允许只给 '01' 这种前两位
        cand = [d for d in case_dir.iterdir() if d.is_dir() and d.name.startswith(stage)]
        if not cand:
            return {"kind": "info", "text": "未找到阶段目录：" + stage}
        target = cand[0]
    lines = [target.name + "："]
    for f in sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name)):
        if f.is_dir():
            lines.append("  " + f.name + "/")
        else:
            lines.append("  " + f.name + "　" + str(f.stat().st_size // 1024) + " KB")
    return {"kind": "info", "text": "\n".join(lines)}


def cmd_next(case_dir: Path, _args: List[str]) -> Dict[str, Any]:
    """next —— 读 STATE.json + manifest.json 给出"下一动作"建议。"""
    state = _read_json_safe(case_dir / "STATE.json") or {}
    manifest = _read_json_safe(case_dir / "manifest.json") or {}
    cur = manifest.get("current_stage") or state.get("current_stage") or "00-brief"
    blockers = state.get("blockers") or []
    lines = ["当前 " + cur + " →"]
    STAGE_FLOW = ["00-brief", "01-scheme", "02-geometry", "03-mesh",
                  "04-solve", "05-post", "06-delivery"]
    try:
        idx = STAGE_FLOW.index(cur)
    except ValueError:
        idx = 0
    if idx >= len(STAGE_FLOW) - 1:
        next_stage = "06-delivery"
        next_act = "汇总交付三表（推力/扭矩/包络）"
    else:
        next_stage = STAGE_FLOW[idx + 1]
        NEXT_ACT = {
            "00-brief": "梳理需求 → 生成 6 张需求 yaml 卡片",
            "01-scheme": "跑一维通流（turbo-flow）→ 出 3 张方案表",
            "02-geometry": "AutoBlade 造型 → 出 geomTurbo + 3 截面",
            "03-mesh": "AutoGrid 出网格 → 1k-50w 的 .cggr",
            "04-solve": "FINE/Turbo 求解 → 收残差曲线",
            "05-post": "CFView 后处理 → 推力/扭矩/包络",
            "06-delivery": "写交付报告 + manifest 收尾",
        }
        next_act = NEXT_ACT.get(next_stage, "—")
    lines.append("  下一阶段  " + next_stage + "：" + next_act)
    if blockers:
        lines.append("  当前阻塞  " + "; ".join(b.get("reason", "") for b in blockers))
    # 试出 stage 目录是否存在 / 是否空
    sd = case_dir / next_stage
    if sd.is_dir():
        n = sum(1 for _ in sd.rglob("*") if _.is_file())
        lines.append("  现状      " + str(n) + " 个文件已落地")
    return {"kind": "info", "text": "\n".join(lines), "next_stage": next_stage}


def cmd_plan(case_dir: Path, _args: List[str]) -> Dict[str, Any]:
    """plan —— 把'现状 → 下一步 → 收尾'做成三段叙事。"""
    s = cmd_status(case_dir, [])
    n = cmd_next(case_dir, [])
    p = cmd_pending(case_dir, [])
    text = "【现状】\n" + s["text"] + "\n\n【下一步】\n" + n["text"] + "\n\n【待办】\n" + p["text"]
    return {"kind": "info", "text": text}


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
        "status":   cmd_status,
        "help":     cmd_help,
        "switch":   cmd_switch,
        "open":     cmd_open,
        "list":     cmd_list,
        "ls":       cmd_ls,
        "where":    cmd_where,
        "refresh":  cmd_refresh,
        "run":      cmd_run,
        "design":   cmd_design,
        "manifest": cmd_manifest,
        "log":      cmd_log,
        "summary":  cmd_summary,
        "pending":  cmd_pending,
        "get":      cmd_get,
        "find":     cmd_find,
        "note":     cmd_note,
        "tree":     cmd_tree,
        "next":     cmd_next,
        "plan":     cmd_plan,
    }.get(cmd, cmd_status)
    return handler(case_dir, args)