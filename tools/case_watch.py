#!/usr/bin/env python3
"""case_watch.py - 案例文件看守 + 交接简报生成。

它解决什么问题
--------------
agent 的上下文是文件系统的缓存，缓存会过期。而 LLM 不能被"推送" ——
它只在回合内调用工具的那一刻才知道世界变了。
所以能做的只有两件事：
  1. 让"变了什么、谁改的"成为一个可回答的问题（本文件的 changes.jsonl）
  2. 让新上下文没机会不读（本文件生成的 HANDOFF.md）

它不管是谁写的
--------------
它只看磁盘。AutoBlade 里手改的 .par、agent 用 write 工具改的 md、
人在界面上保存的 csv —— 一视同仁。
日志里有对应条目的，归因给那个操作者；没有的，如实标 unknown。
**unknown 是最有价值的信号：有人说都没说就改了东西。**

成本（实测，389 个文件 22.2 MB）
--------------------------------
  轻量指纹(size+mtime)  4.8 ms     每轮都跑
  全量 sha256           917 ms     只在基线初始化和文件变动时跑
  案例目录里 >1MB 的文件 0 个      所以"只对变动文件算哈希"几乎免费

用法
----
  python tools/case_watch.py --case cases/DF90-001 --once
  python tools/case_watch.py --case cases/DF90-001 --loop --interval 3
  python tools/case_watch.py --case cases/DF90-001 --handoff
  python tools/case_watch.py --case cases/DF90-001 --status
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

LF = chr(10)
ROOT = Path(__file__).resolve().parent.parent

# 看守自己的输出必须排除，否则会自己触发自己，无限循环。
WATCH_DIRNAME = "_watch"
HANDOFF_NAME = "HANDOFF.md"
EXCLUDE_DIRS = {WATCH_DIRNAME, ".git", "__pycache__", "node_modules", ".venv",
                ".pytest_cache", ".ruff_cache", ".playwright-cli", ".turbo-flow"}
# ── 边界：只看工程实质变更 ──────────────────────────────────────────────
# 看守不是行为日志。它只关心四类东西变了没有：
#     设计参数 / 几何 / 网格 / 算例参数
# 其余一律不看 —— 跑了什么检查、生成了什么报告、点了什么按钮，都不进变更流。
#
# 规则是白名单：路径前缀 + 扩展名，两个都对上才看。
CATEGORY_RULES = [
    ("设计参数", ("requirements.yaml",),  {".yaml", ".yml"}),
    ("设计参数", ("01-scheme/",),         {".csv", ".json"}),
    ("几何",     ("02-geometry/",),       {".geomTurbo", ".par", ".abp", ".abm",
                                           ".dat", ".stl", ".xmt_txt"}),
    ("网格",     ("03-mesh/",),           {".trb", ".igg", ".bcs", ".config", ".qualityReport"}),
    ("算例参数", ("04-solve/",),          {".run", ".iec", ".csv"}),
    ("算例参数", ("_automation/",),        {".csv"}),   # 扫描计划等
]

# 账本自身状态与看守自己的产物永远不看
EXCLUDE_FILES = {HANDOFF_NAME, "LOG.md", "STATE.json", "manifest.json"}


def classify(rel):
    """返回该文件属于哪一类工程内容；不属于四类之一就返回 None（不看）。"""
    rel = rel.replace("\\", "/")
    ext = os.path.splitext(rel)[1].lower()
    for cat, prefixes, exts in CATEGORY_RULES:
        if ext not in exts:
            continue
        for pref in prefixes:
            if pref.endswith("/"):
                if rel.startswith(pref):
                    return cat
            elif rel == pref:
                return cat
    return None

HISTORY_MAX_BYTES = 2 * 1024 * 1024
SHA_MAX_BYTES = 64 * 1024 * 1024

# 归因窗口
ATTR_PATH_WINDOW_S = 1800.0     # 日志里直接提到该路径：前后 30 分钟
ATTR_NEARBY_WINDOW_S = 120.0    # 仅时间接近：只记线索，不做归因


def now_iso():
    return _dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def ts_to_epoch(ts):
    try:
        return _dt.datetime.fromisoformat(ts).timestamp()
    except Exception:
        return None


def read_json_safe(path, default=None):
    try:
        with Path(path).open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def read_text_safe(path, limit=None):
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        return text[-limit:] if limit else text
    except Exception:
        return ""


def write_json_atomic(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write(LF)
    os.replace(tmp, path)


def write_json_if_changed(path, payload):
    """序列化后逐字节比对，一样就不写。见 write_text_if_changed 的理由。"""
    text = json.dumps(payload, ensure_ascii=False, indent=2) + LF
    return write_text_if_changed(path, text)


def write_text_if_changed(path, text):
    """内容没变就一个字节都不写。

    为什么要有这个：看守每 tick 都会重建 HANDOFF.md、每 tick 都刷新 state.json，
    里面只有时间戳在动。结果是 —— 光是把工具跑起来，就会把工作区弄脏，
    每天几百次无意义的 mtime 变化，也让 git status 永远不干净。
    内容不变就不落盘，谁都没损失。
    """
    path = Path(path)
    if path.is_file():
        try:
            if path.read_bytes() == text.encode("utf-8"):
                return False
        except Exception:
            pass
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    os.replace(tmp, path)
    return True


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path, cap=SHA_MAX_BYTES):
    """算文件哈希。超过 cap 的返回 None（记 size+mtime 就够定位了）。"""
    p = Path(path)
    try:
        if p.stat().st_size > cap:
            return None
        h = hashlib.sha256()
        with p.open("rb") as fh:
            while True:
                b = fh.read(1 << 20)
                if not b:
                    break
                h.update(b)
        return h.hexdigest()
    except Exception:
        return None


# ── 日志解析（与 liveview 共用） ───────────────────────────────────────────
def parse_log(text):
    """把 LOG.md 解析成结构化条目。格式由 case_ledger._append_log 固定。"""
    entries = []
    cur = None
    for line in text.splitlines():
        m = re.match(r"^##\s+(\S+)\s+\|\s+(.+?)\s+\|\s+(\S+)\s*$", line)
        if m:
            if cur:
                entries.append(cur)
            label = m.group(2).strip()
            g = re.match(r"^(G\d)\s*(.*)$", label)
            cur = {"ts": m.group(1),
                   "stage": g.group(1) if g else "",
                   "stage_name": (g.group(2) if g else label),
                   "verdict": m.group(3), "fields": []}
            continue
        if cur is None:
            continue
        m2 = re.match(r"^-\s*([^：:]+)[：:]\s*(.*)$", line)
        if m2:
            cur["fields"].append({"k": m2.group(1).strip(), "v": m2.group(2).strip()})
    if cur:
        entries.append(cur)
    return entries


# ── 扫描与指纹 ─────────────────────────────────────────────────────────────
def scan(case_dir):
    """遍历案例目录，返回 {相对路径: [size, mtime_ns]}。只看元数据，很便宜。"""
    case_dir = Path(case_dir)
    out = {}
    for dirpath, dirnames, filenames in os.walk(case_dir):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            if fn in EXCLUDE_FILES:
                continue
            p = Path(dirpath) / fn
            try:
                st = p.stat()
            except Exception:
                continue
            rel = p.relative_to(case_dir).as_posix()
            cat = classify(rel)
            if cat is None:
                continue                      # 不是工程实质内容，不看
            out[rel] = [st.st_size, st.st_mtime_ns, cat]
    return out


def watch_paths(case_dir):
    case_dir = Path(case_dir)
    return {
        "snapshot": case_dir / WATCH_DIRNAME / "snapshot.json",
        "state": case_dir / WATCH_DIRNAME / "state.json",
        "changes": case_dir / WATCH_DIRNAME / "changes.jsonl",
        "history": case_dir / WATCH_DIRNAME / "history",
        "mustknow": case_dir / WATCH_DIRNAME / "must-know.md",
        "handoff": case_dir / HANDOFF_NAME,
    }


# ── 内容寻址历史 ───────────────────────────────────────────────────────────
def store_content(case_dir, digest, data):
    """把内容按 sha256 存一份。相同内容只存一次（内容寻址），所以去重是天然的。"""
    if not digest or len(data) > HISTORY_MAX_BYTES:
        return False
    dest = watch_paths(case_dir)["history"] / digest[:2] / digest
    if dest.is_file():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, dest)
    return True


def read_history(case_dir, digest):
    """读回历史内容 —— **必须按字节读**。

    踩过的坑：原先用 read_text 读、再 encode 写回。Python 的通用换行会把
    CRLF 规范化成 LF，字节就变了，sha256 自然对不上（实测 8965 bytes 的文件
    往返后哈希从 2242a13f 变成 35128dc4，还原被正确拒绝）。
    内容寻址存储的前提是字节完全一致，任何文本往返都是破坏性的。
    """
    p = watch_paths(case_dir)["history"] / digest[:2] / digest
    if not p.is_file():
        return None
    try:
        return p.read_bytes()
    except Exception:
        return None


# ── 变更检测 ───────────────────────────────────────────────────────────────
def detect(prev, cur):
    """比较两轮指纹，返回变更列表。"""
    changes = []

    def cat_of(entry):
        return entry[2] if len(entry) > 2 else classify(entry and "") or "未知"

    for rel, entry in cur.items():
        size, mtime = entry[0], entry[1]
        old = prev.get(rel)
        if old is None:
            changes.append({"path": rel, "kind": "added", "size": size,
                            "size_before": 0, "mtime_ns": mtime, "category": cat_of(entry)})
        elif old[0] != size or old[1] != mtime:
            changes.append({"path": rel, "kind": "modified", "size": size,
                            "size_before": old[0], "mtime_ns": mtime, "category": cat_of(entry)})
    for rel, entry in prev.items():
        if rel not in cur:
            changes.append({"path": rel, "kind": "deleted", "size": 0,
                            "size_before": entry[0], "mtime_ns": None,
                            "category": entry[2] if len(entry) > 2 else "未知"})
    changes.sort(key=lambda c: c.get("mtime_ns") or 0)
    return changes


def attribute(case_dir, change, log_entries):
    """归因：先看日志里有没有直接提到这个路径，否则看时间窗。"""
    rel = change["path"]
    name = rel.rsplit("/", 1)[-1]
    mtime = change.get("mtime_ns")
    if mtime:
        when = mtime / 1e9
    elif change.get("file_mtime"):
        when = ts_to_epoch(change["file_mtime"]) or time.time()
    else:
        when = time.time()

    best = None
    for e in log_entries:
        ts = ts_to_epoch(e["ts"])
        if ts is None:
            continue
        blob = " ".join(f["k"] + "=" + f["v"] for f in e["fields"]) + " " + e.get("stage_name", "")
        if (rel in blob) or (name and name in blob):
            if abs(ts - when) <= ATTR_PATH_WINDOW_S:
                if best is None or abs(ts - when) < abs(best[0] - when):
                    best = (ts, e, "path-match")
    if best:
        return best[1].get("actor_of") or actor_of(best[1]), best[1]["ts"], "path-match"

    # 只按时间接近**不做归因** —— 猜错比 unknown 危险得多。
    # 实测踩过：界面改 A 文件写了一条日志，90 秒窗口把另一条绕过账本的
    # 改动错配给了 human(web-ui)。所以这里退化成"线索"。
    nearby = None
    for e in log_entries:
        ts = ts_to_epoch(e["ts"])
        if ts is None:
            continue
        if abs(ts - when) <= ATTR_NEARBY_WINDOW_S:
            if nearby is None or abs(ts - when) < abs(nearby[0] - when):
                nearby = (ts, e)
    return "unknown", (nearby[1]["ts"] if nearby else None), "none"


def actor_of(entry):
    for f in entry.get("fields", []):
        if f["k"] == "操作者":
            return f["v"]
    return "未记录（该条目早于 --actor 引入）"


# ── 一轮 ───────────────────────────────────────────────────────────────────
def tick(case_dir, verbose=False):
    case_dir = Path(case_dir).resolve()
    wp = watch_paths(case_dir)
    wp["snapshot"].parent.mkdir(parents=True, exist_ok=True)

    cur = scan(case_dir)
    prev = read_json_safe(wp["snapshot"], None)
    state = read_json_safe(wp["state"], {}) or {}
    prev_state = dict(state)

    log_text = read_text_safe(case_dir / "LOG.md")
    log_entries = parse_log(log_text)

    # 基线初始化：第一次跑只建快照 + 备份内容，不产生变更记录。
    if prev is None or not state.get("initialized"):
        stored = 0
        for rel in cur:
            data = None
            p = case_dir / rel
            try:
                if p.stat().st_size <= HISTORY_MAX_BYTES:
                    data = p.read_bytes()
            except Exception:
                data = None
            if data is not None:
                if store_content(case_dir, sha256_bytes(data), data):
                    stored += 1
        write_json_atomic(wp["snapshot"], cur)
        write_json_atomic(wp["state"], {
            "initialized": True, "baseline_at": now_iso(),
            "files": len(cur), "history_stored": stored,
        })
        if verbose:
            print("[基线] %d 个文件建立指纹，%d 份内容入历史库" % (len(cur), stored))
        return {"baseline": True, "files": len(cur), "changes": []}

    changes = detect(prev, cur)
    records = []
    for ch in changes:
        rel = ch["path"]
        p = case_dir / rel
        new_sha = None
        old_sha = None

        if ch["kind"] in ("added", "modified") and p.is_file():
            try:
                if p.stat().st_size <= HISTORY_MAX_BYTES:
                    data = p.read_bytes()
                    new_sha = sha256_bytes(data)
                    store_content(case_dir, new_sha, data)
            except Exception:
                pass

        # 备份上一版：快照里没存哈希，所以用历史库反查上一版内容
        if ch["kind"] == "modified":
            old_sha = state.get("hashes", {}).get(rel)

        actor, log_ts, how = attribute(case_dir, ch, log_entries)
        rec = {
            "ts": now_iso(),
            "file_mtime": (_dt.datetime.fromtimestamp(ch["mtime_ns"] / 1e9)
                           .astimezone().replace(microsecond=0).isoformat()
                           if ch.get("mtime_ns") else None),
            "path": rel, "kind": ch["kind"],
            "category": ch.get("category", ""),
            "size": ch["size"], "size_before": ch["size_before"],
            "mtime_ns": ch.get("mtime_ns"),
            "sha256": new_sha, "sha256_before": old_sha,
            "actor": actor, "attribution": how, "log_ts": log_ts,
        }
        if how == "none":
            rec["note"] = "日志中无对应条目 —— 绕过账本的外部写入"
            if log_ts:
                near = next((e for e in log_entries if e["ts"] == log_ts), None)
                if near:
                    act = next((f["v"] for f in near["fields"] if f["k"] == "动作"), "")
                    who = actor_of(near)
                    rec["nearby_log"] = {"ts": log_ts, "actor": who, "action": act[:80]}
                    rec["note"] += ("（同一时段另有一条日志：" + who + " " + act[:50]
                                    + "；但它没有提到本文件，故不据此归因）")
        records.append(rec)

    if records:
        with wp["changes"].open("a", encoding="utf-8", newline="") as fh:
            for rec in records:
                fh.write(json.dumps(rec, ensure_ascii=False) + LF)

    # 记住本轮哈希，供下一轮算 sha256_before
    hashes = state.get("hashes", {})
    for ch in changes:
        p = case_dir / ch["path"]
        if p.is_file():
            h = sha256_file(p)
            if h:
                hashes[ch["path"]] = h
    # last_tick 不进 state.json —— 它是运行状态不是审计信息，落在这里
    # 会让这个入库的文件每 3 秒变一次。心跳单独写 _watch/heartbeat.json。
    state.update({"initialized": True, "files": len(cur),
                  "total_changes": int(state.get("total_changes", 0)) + len(records),
                  "hashes": hashes})
    write_json_if_changed(wp["snapshot"], cur)
    # state.json 只在"有变更记录"或"监视文件数变了"时才落盘 ——
    # 它进 git，每 3 秒刷一次 mtime 会把工作区永远弄脏。
    if records or prev_state.get("files") != len(cur):
        write_json_if_changed(wp["state"], state)
    write_heartbeat(case_dir)

    build_handoff(case_dir, records, cur)
    if verbose and records:
        for r in records:
            print("  %-9s %-58s %s" % (r["kind"], r["path"][:58], r["actor"]))
    return {"baseline": False, "files": len(cur), "changes": records}


# ── 交接简报 ───────────────────────────────────────────────────────────────
def read_changes(case_dir, limit=None):
    p = watch_paths(case_dir)["changes"]
    if not p.is_file():
        return []
    out = []
    for line in read_text_safe(p).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out[-limit:] if limit else out


def build_handoff(case_dir, new_records=None, snapshot=None):
    """生成 HANDOFF.md。目标 <= 120 行 —— 一个"必然被读到"的文件不能太长。"""
    case_dir = Path(case_dir).resolve()
    wp = watch_paths(case_dir)
    manifest = read_json_safe(case_dir / "manifest.json", {}) or {}
    state = read_json_safe(case_dir / "STATE.json", {}) or {}
    watch_state = read_json_safe(wp["state"], {}) or {}
    changes = read_changes(case_dir)
    log_entries = parse_log(read_text_safe(case_dir / "LOG.md"))

    case_id = manifest.get("case_id") or case_dir.name
    stages = state.get("stages") or {}
    order = ["G0", "G1", "G2", "G3", "G4", "G5", "G6"]
    in_prog = [g for g in order if (stages.get(g) or {}).get("status") == "in_progress"]
    done = [g for g in order if (stages.get(g) or {}).get("status") == "done"]
    pending = [g for g in order if (stages.get(g) or {}).get("status") == "pending"]

    L = []
    L.append("# " + case_id + " 交接简报")
    L.append("")
    # 生成时间不参与"内容变了没"的判断：正文一样就沿用旧时间戳，
    # 否则每 tick 都会重写一遍，看守自己把自己的 mtime 刷个没完。
    stamp_path = case_dir / HANDOFF_NAME
    old = ""
    if stamp_path.is_file():
        try:
            old = stamp_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            old = ""
    old_stamp = re.search(r"生成于 (\S+)", old)
    L.append("> **自动生成，勿手改。** 由 tools/case_watch.py 维护。" + LF
             + "> 生成于 " + (old_stamp.group(1) if old_stamp else now_iso())
             + "　·　当前阶段 **" + str(manifest.get("current_stage"))
             + "**　·　revision " + str(manifest.get("revision")) + LF
             + "> **新会话请先读完本文件再动手。**")
    L.append("")

    L.append("## 一句话现状")
    bits = []
    if done:
        bits.append("已完成 " + "/".join(done))
    if in_prog:
        bits.append("**进行中 " + "/".join(in_prog) + "**")
    if pending:
        bits.append("未开始 " + "/".join(pending))
    L.append("　".join(bits) if bits else "阶段状态未知")
    if log_entries:
        last = log_entries[-1]
        act = next((f["v"] for f in last["fields"] if f["k"] == "动作"), "")
        L.append("")
        L.append("最近一次记录：" + last["ts"] + "　" + last["verdict"] + "　" + act[:70])
    L.append("")

    unlogged = [c for c in changes if c.get("attribution") == "none"]
    recent_cut = time.time() - 14 * 86400
    unlogged_recent = [c for c in unlogged
                       if (ts_to_epoch(c.get("file_mtime") or c["ts"]) or 0) > recent_cut]
    if unlogged_recent:
        L.append("## 未登记的改动（近 14 天 " + str(len(unlogged_recent))
                 + " 条，历史共 " + str(len(unlogged)) + " 条）")
        L.append("")
        L.append("这些文件变了，但 LOG.md 里没有对应条目 —— 可能是 AutoBlade 等外部工具改的、")
        L.append("可能是另一个 agent 直接写的、也可能是人手工改的。**接手前请先确认它们是什么。**")
        L.append("")
        for c in unlogged_recent[-8:]:
            when = (c.get("file_mtime") or c["ts"])[11:19]
            L.append("- " + when + "　**" + str(c.get("category") or "?") + "**　"
                     + c["kind"] + "　" + c["path"]
                     + "　" + str(c.get("size_before")) + " -> " + str(c.get("size")) + " bytes")
        if len(unlogged_recent) > 8:
            L.append("- …另有 " + str(len(unlogged_recent) - 8) + " 条，见 _watch/changes.jsonl")
        L.append("")
    else:
        L.append("## 未登记的改动")
        L.append("")
        L.append("无。所有文件变动都能在 LOG.md 里找到对应条目。")
        L.append("")

    L.append("## 最近 10 次变更")
    L.append("")
    if changes:
        L.append("| 时间 | 类别 | 谁 | 改动 | 文件 | 大小变化 |")
        L.append("|---|---|---|---|---|---|")
        for c in changes[-10:][::-1]:
            when = (c.get("file_mtime") or c["ts"])[5:19].replace("T", " ")
            who = c.get("actor", "?")
            if c.get("attribution") == "none":
                who = "**unknown**"
            delta = str(c.get("size_before")) + " -> " + str(c.get("size"))
            L.append("| " + when + " | " + str(c.get("category") or "") + " | " + who
                     + " | " + c.get("kind", "") + " | " + c["path"] + " | " + delta + " |")
    else:
        L.append("（本次基线建立后尚无变更记录）")
    L.append("")

    L.append("## 你接手前必须知道")
    L.append("")
    manual = read_text_safe(wp["mustknow"]).strip()
    if manual:
        L.append(manual)
        L.append("")
    warn_arts = [a for a in (manifest.get("artifacts") or []) if a.get("verdict") in ("WARN", "FAIL")]
    if warn_arts:
        L.append("**结论非 PASS 的产物（" + str(len(warn_arts)) + " 条）**")
        L.append("")
        for a in warn_arts[:8]:
            L.append("- [" + str(a.get("verdict")) + "] " + str(a.get("path"))
                     + ("　— " + a["note"][:80] if a.get("note") else ""))
        L.append("")
    mem = read_text_safe(case_dir / "memory.md")
    pending_promo = re.findall(r"^## (.+)$[\s\S]{0,900}?待晋升", mem, re.M)
    if pending_promo:
        L.append("**待晋升的经验（" + str(len(pending_promo)) + " 条）**")
        L.append("")
        for t in pending_promo[:6]:
            L.append("- " + t.strip())
        L.append("")

    openq = read_text_safe(case_dir / "00-brief" / "open_questions.md")
    rows = re.findall(r"^\|\s*\d+\s*\|[^\n]*$", openq, re.M)
    if rows:
        L.append("## 未决问题（" + str(len(rows)) + " 条）")
        L.append("")
        for r in rows[:10]:
            cells = [c.strip() for c in r.strip("|").split("|")]
            if len(cells) >= 4:
                L.append("- " + cells[1] + "　来源：" + cells[2] + "　" + cells[3])
        L.append("")

    arts = manifest.get("artifacts") or []
    L.append("## 产物（" + str(len(arts)) + " 条）")
    L.append("")
    L.append("| 阶段 | 结论 | 版本 | 路径 | sha256 |")
    L.append("|---|---|---|---|---|")
    for a in arts:
        L.append("| " + str(a.get("stage")) + " | " + str(a.get("verdict")) + " | "
                 + str(a.get("version")) + " | " + str(a.get("path")) + " | "
                 + str(a.get("sha256", ""))[:8] + " |")
    L.append("")

    hist_count = 0
    if wp["history"].is_dir():
        hist_count = sum(1 for f in wp["history"].rglob("*") if f.is_file())
    L.append("---")
    L.append("")
    L.append("看守状态：监视 " + str(watch_state.get("files", 0)) + " 个文件　·　累计变更 "
             + str(watch_state.get("total_changes", len(changes))) + " 条　·　历史库 "
             + str(hist_count) + " 份内容")
    L.append("")
    L.append("**看守边界**：只记录四类工程实质变更 —— 设计参数 / 几何 / 网格 / 算例参数。")
    L.append("跑了什么检查、生成了什么报告、点了什么按钮，都不进变更流。")
    L.append("")
    L.append("变更流明细：_watch/changes.jsonl　·　历史内容：_watch/history/<sha256>")

    text = LF.join(L) + LF
    # 正文与上一版逐字相同 -> 沿用旧文件（含旧时间戳），不落盘。
    if old and re.sub(r"生成于 \S+", "", old) == re.sub(r"生成于 \S+", "", text):
        return old
    # 正文确实变了 -> 换成当前时间戳再写。
    text = re.sub(r"生成于 \S+", "生成于 " + now_iso(), text, count=1)
    write_text_if_changed(wp["handoff"], text)
    return text


def restore(case_dir, rel, digest):
    """从内容寻址历史库还原一个文件到指定版本。

    这是看守的兜底能力：知道"变了"之后，还能拿回"变之前是什么"。
    只接受历史库里真实存在、且哈希自洽的内容。
    """
    case_dir = Path(case_dir).resolve()
    raw = read_history(case_dir, digest)
    if raw is None:
        return {"ok": False, "error": "历史库里没有这一版：" + str(digest)[:16]}
    got = sha256_bytes(raw)
    if got != digest:
        return {"ok": False, "error": "历史内容哈希不自洽，拒绝还原（期望 "
                                      + str(digest)[:16] + " 实得 " + got[:16] + "）"}
    dest = case_dir / rel
    if dest.exists():
        backup = dest.with_name(dest.name + ".before-restore")
        backup.write_bytes(dest.read_bytes())
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    return {"ok": True, "path": rel, "bytes": len(raw), "sha256": got}


def read_heartbeat(case_dir):
    """看守的心跳：最后一次跑是什么时候。

    单独一个小文件，而不是塞进 state.json —— state.json 是要进 git 的，
    每 3 秒改一次会把工作区永远弄脏。心跳文件由 .gitignore 排除。
    """
    return read_json_safe(Path(case_dir).resolve() / WATCH_DIRNAME / "heartbeat.json", {}) or {}


def write_heartbeat(case_dir):
    p = Path(case_dir).resolve() / WATCH_DIRNAME / "heartbeat.json"
    try:
        write_json_atomic(p, {"last_tick": now_iso(), "last_tick_epoch": time.time()})
    except Exception:
        pass


def gc(case_dir, apply=False):
    """清理历史库里不再被引用的 blob。

    **默认只报告，不删**（apply=False）。历史库是"变了之后还能拿回变之前"的
    兜底能力，删错了就真没了 —— 所以默认安全，要删得显式加 --apply。

    什么算"还被引用"：
      1. 监视范围内某个文件**当前的内容**哈希
      2. changes.jsonl 里出现过的 sha256 / sha256_before
    其余就是历史残留。内容寻址天然去重，残留主要来自"同一个文件改了很多版"。
    """
    case_dir = Path(case_dir).resolve()
    wp = watch_paths(case_dir)
    hist = wp["history"]
    if not hist.is_dir():
        return {"ok": True, "blobs": 0, "live": 0, "dead": 0, "freed_bytes": 0,
                "removed": [], "applied": False}

    live = set()
    for rel in scan(case_dir):
        p = case_dir / rel
        try:
            if p.stat().st_size <= HISTORY_MAX_BYTES:
                live.add(sha256_bytes(p.read_bytes()))
        except Exception:
            pass
    for rec in read_changes(case_dir):
        for k in ("sha256", "sha256_before"):
            v = rec.get(k)
            if v:
                live.add(v)

    blobs, dead, freed = [], [], 0
    for f in hist.rglob("*"):
        if not f.is_file():
            continue
        blobs.append(f)
        if f.name not in live:
            dead.append(f)
            try:
                freed += f.stat().st_size
            except Exception:
                pass

    removed = []
    if apply:
        for f in dead:
            try:
                f.unlink()
                removed.append(f.name)
            except Exception:
                pass
        for d in sorted([p for p in hist.rglob("*") if p.is_dir()],
                        key=lambda p: -len(p.parts)):
            try:
                if not any(d.iterdir()):
                    d.rmdir()
            except Exception:
                pass
    return {"ok": True, "blobs": len(blobs), "live": len(live), "dead": len(dead),
            "freed_bytes": freed, "removed": removed[:20], "applied": bool(apply)}


def status(case_dir):
    case_dir = Path(case_dir).resolve()
    wp = watch_paths(case_dir)
    st = read_json_safe(wp["state"], {}) or {}
    st = dict(st, **read_heartbeat(case_dir))
    changes = read_changes(case_dir)
    unlogged = [c for c in changes if c.get("attribution") == "none"]
    hist = 0
    if wp["history"].is_dir():
        hist = sum(1 for f in wp["history"].rglob("*") if f.is_file())
    return {
        "case": str(case_dir),
        "initialized": bool(st.get("initialized")),
        "baseline_at": st.get("baseline_at"),
        "last_tick": st.get("last_tick"),
        "watched_files": st.get("files"),
        "total_changes": st.get("total_changes", len(changes)),
        "unlogged_changes": len(unlogged),
        "history_blobs": hist,
        "has_handoff": wp["handoff"].is_file(),
    }


# ── CLI ────────────────────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(prog="case_watch.py", description="案例文件看守 + 交接简报")
    ap.add_argument("--case", required=True)
    ap.add_argument("--once", action="store_true", help="跑一轮检测")
    ap.add_argument("--loop", action="store_true", help="持续看守")
    ap.add_argument("--interval", type=float, default=3.0)
    ap.add_argument("--handoff", action="store_true", help="只重建 HANDOFF.md")
    ap.add_argument("--status", action="store_true", help="打印看守状态")
    ap.add_argument("--restore", metavar="PATH", help="从历史库还原该文件")
    ap.add_argument("--sha", help="与 --restore 配合：要还原到的 sha256")
    ap.add_argument("--gc", action="store_true",
                    help="报告历史库里不再被引用的 blob（默认不删）")
    ap.add_argument("--apply", action="store_true",
                    help="与 --gc 配合：真的删。不加就只报告")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    case_dir = Path(args.case)
    if not case_dir.is_absolute():
        case_dir = (ROOT / case_dir)
    if not case_dir.is_dir():
        print("案例目录不存在：" + str(case_dir), file=sys.stderr)
        return 3

    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    if args.gc:
        r = gc(case_dir, apply=args.apply)
        if args.json:
            print(json.dumps(r, ensure_ascii=False, indent=2))
        else:
            print("历史库清理" + ("（已执行）" if r["applied"] else "（只报告，未删）"))
            print("  blob 总数   : %d" % r["blobs"])
            print("  仍被引用    : %d" % r["live"])
            print("  可清理      : %d 份，%.1f MB" % (r["dead"], r["freed_bytes"] / 1048576))
            if not r["applied"] and r["dead"]:
                print("  真要删就加 --apply。删掉的是历史版本，删了拿不回来。")
        return 0

    if args.status:
        st = status(case_dir)
        if args.json:
            print(json.dumps(st, ensure_ascii=False, indent=2))
        else:
            print("看守状态　" + st["case"])
            print("  已初始化    : " + str(st["initialized"]) + "（基线 " + str(st["baseline_at"]) + "）")
            print("  上次运行    : " + str(st["last_tick"]))
            print("  监视文件    : " + str(st["watched_files"]))
            print("  累计变更    : " + str(st["total_changes"]))
            print("  未登记改动  : " + str(st["unlogged_changes"]))
            print("  历史内容    : " + str(st["history_blobs"]) + " 份")
            print("  交接简报    : " + ("已生成" if st["has_handoff"] else "未生成"))
        return 0

    if args.restore:
        if not args.sha:
            print("--restore 必须配合 --sha", file=sys.stderr)
            return 2
        r = restore(case_dir, args.restore, args.sha)
        if args.json:
            print(json.dumps(r, ensure_ascii=False, indent=2))
        elif r["ok"]:
            print("已还原 " + r["path"] + "　" + str(r["bytes"]) + " bytes　sha256=" + r["sha256"][:16])
            print("（原文件已备份为 " + r["path"] + ".before-restore）")
        else:
            print("还原失败：" + r["error"], file=sys.stderr)
        return 0 if r["ok"] else 4

    if args.handoff:
        build_handoff(case_dir)
        print("已重建 " + str(watch_paths(case_dir)["handoff"]))
        return 0

    if args.loop:
        print("开始看守 " + str(case_dir) + "　每 " + str(args.interval) + " 秒一轮。Ctrl+C 停止。")
        try:
            while True:
                try:
                    tick(case_dir, verbose=True)
                except Exception as exc:
                    print("  [看守异常] " + repr(exc), file=sys.stderr)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("")
            print("已停止。")
        return 0

    r = tick(case_dir, verbose=True)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        if r["baseline"]:
            print("[基线] 建立 " + str(r["files"]) + " 个文件的指纹与历史库")
        else:
            print("本轮变更 " + str(len(r["changes"])) + " 条（监视 " + str(r["files"]) + " 个文件）")
            for c in r["changes"]:
                print("  %-9s %-58s %s" % (c["kind"], c["path"][:58], c["actor"]))
        print("交接简报：" + str(watch_paths(case_dir)["handoff"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
