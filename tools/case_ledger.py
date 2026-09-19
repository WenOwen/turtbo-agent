#!/usr/bin/env python3
"""case_ledger.py - 叶轮机械设计案例的产物登记 / 版本沉淀 / 工程日志。

设计原则
--------
1. 磁盘是唯一真源：manifest.json 只索引磁盘上真实存在的文件，不复制内容。
2. 幂等：同一 (stage, path, sha256) 重复登记不产生新版本、不重复写日志。
3. 原子写：所有 JSON 经 tmp + os.replace 落盘，中断不会留半截文件。
4. 判据可溯源：日志条目必须带 criteria（判据），不允许裸结论。
5. 稳定退出码：0=成功, 2=用法错误, 3=前置条件不满足, 4=校验失败, 5=内部错误。

用法速查
--------
  python tools/case_ledger.py new   --case-id DF90-001 --root cases
  python tools/case_ledger.py add   --case cases/DF90-001 --stage G4 --kind mesh
                                    --path 03-mesh/v1/mesh-v1.igg --version v1
                                    --verdict PASS --criteria "负单元=0" --from <上游相对路径>
  python tools/case_ledger.py log   --case cases/DF90-001 --stage G4 --action "AutoGrid 生成"
                                    --verdict PASS --criteria "..." --note "..."
  python tools/case_ledger.py stage --case cases/DF90-001 --stage G4 --status done
  python tools/case_ledger.py verify --case cases/DF90-001
  python tools/case_ledger.py show   --case cases/DF90-001

所有命令支持 --json 输出机器可读结果。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
from pathlib import Path

SCHEMA_MANIFEST = "turtbo-agent/case-manifest@1"
SCHEMA_STATE = "turtbo-agent/case-state@1"

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_PRECONDITION = 3
EXIT_VERIFY = 4
EXIT_INTERNAL = 5

LF = chr(10)

# 七道闸门：G0..G6
STAGES = [
    {"id": "G0", "name": "需求", "dir": "00-brief"},
    {"id": "G1", "name": "设计大纲", "dir": "00-brief"},
    {"id": "G2", "name": "1D通流方案", "dir": "01-scheme"},
    {"id": "G3", "name": "叶片造型", "dir": "02-geometry"},
    {"id": "G4", "name": "网格", "dir": "03-mesh"},
    {"id": "G5", "name": "求解", "dir": "04-solve"},
    {"id": "G6", "name": "后处理与交付", "dir": "05-post"},
]
STAGE_IDS = [s["id"] for s in STAGES]
STAGE_BY_ID = {s["id"]: s for s in STAGES}

CASE_DIRS = [
    "00-brief",
    "01-scheme",
    "02-geometry",
    "03-mesh",
    "04-solve",
    "05-post",
    "06-delivery",
    "_replay",
]

VERDICTS = ("PASS", "FAIL", "WARN", "INFO", "BLOCKED")


def now_iso():
    return _dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def as_posix(value):
    return Path(value).as_posix()


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json_atomic(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write(LF)
    os.replace(tmp, path)


def append_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as fh:
        fh.write(text)


def die(code, message, as_json):
    if as_json:
        print(json.dumps({"ok": False, "exit": code, "error": message}, ensure_ascii=False))
    else:
        print("ERROR: " + str(message), file=sys.stderr)
    raise SystemExit(code)


def manifest_path(case):
    return Path(case) / "manifest.json"


def state_path(case):
    return Path(case) / "STATE.json"


def load_manifest(case):
    data = read_json(manifest_path(case))
    if data is None:
        return {
            "schema": SCHEMA_MANIFEST,
            "case_id": Path(case).name,
            "created": now_iso(),
            "updated": now_iso(),
            "revision": 0,
            "requirement_ref": None,
            "current_stage": "G0",
            "artifacts": [],
        }
    return data


def load_state(case, case_id):
    data = read_json(state_path(case))
    if data is None:
        return {
            "schema": SCHEMA_STATE,
            "case_id": case_id,
            "created": now_iso(),
            "updated": now_iso(),
            "revision": 0,
            "current_stage": "G0",
            "stages": {s["id"]: {"name": s["name"], "status": "pending", "updated": None} for s in STAGES},
            "blockers": [],
        }
    return data


def refresh_requirement_ref(case, manifest):
    req = Path(case) / "requirements.yaml"
    if req.exists():
        manifest["requirement_ref"] = {
            "file": "requirements.yaml",
            "sha256": sha256_file(req),
            "bytes": req.stat().st_size,
        }


def _append_log(case, stage, action, verdict, criteria, note, extra=None):
    name = STAGE_BY_ID.get(stage, {}).get("name", "")
    lines = [
        "## " + now_iso() + " | " + stage + " " + name + " | " + verdict,
        "- 动作：" + action,
    ]
    for key, val in (extra or {}).items():
        lines.append("- " + key + "：" + str(val))
    lines.append("- 判据：" + criteria)
    lines.append("- 结论：" + verdict)
    if note:
        lines.append("- 备注：" + note)
    lines.append("")
    log = Path(case) / "LOG.md"
    # 追加前先确认上一段以换行收尾。以前直接追加 —— 只要文件末尾少一个换行，
    # 新条目的 "## " 就粘在上一行屁股后面（实测 DF90-001 的 LOG.md 开头变成
    # "x## 2026-09-19T16:03:33+08:00"，第一条日志的标题被吃掉一个字节）。
    prefix = ""
    try:
        if log.is_file() and log.stat().st_size:
            with log.open("rb") as fh:
                fh.seek(-1, 2)
                if fh.read(1) not in (b"\n", b"\r"):
                    prefix = LF
    except OSError:
        prefix = ""
    append_text(log, prefix + LF.join(lines) + LF)


def cmd_new(args):
    root = Path(args.root).resolve()
    case = (root / args.case_id).resolve()
    if case.exists() and any(case.iterdir()) and not args.force:
        die(EXIT_PRECONDITION, "案例目录已存在且非空：" + str(case) + "（用 --force 覆盖骨架文件）", args.json)

    case.mkdir(parents=True, exist_ok=True)
    for d in CASE_DIRS:
        (case / d).mkdir(exist_ok=True)

    manifest = load_manifest(case)
    manifest["case_id"] = args.case_id
    manifest["updated"] = now_iso()
    write_json_atomic(manifest_path(case), manifest)

    state = load_state(case, args.case_id)
    write_json_atomic(state_path(case), state)

    log = case / "LOG.md"
    if not log.exists():
        append_text(
            log,
            "# 工程日志 | " + args.case_id + LF + LF
            + "> 只追加，不复写。每条含 时间 / 阶段 / 动作 / 输入哈希 / 实测 / 判据 / 结论 / 产物。" + LF
            + "> 由 tools/case_ledger.py 或 tools/gate_check.py 自动写入。" + LF + LF
            + "## " + now_iso() + " | 案例创建 | " + args.case_id + LF
            + "- 命令行：case_ledger.py new --case-id " + args.case_id + LF
            + "- 结论：案例骨架已建立，当前阶段 G0" + LF + LF,
        )

    mem = case / "memory.md"
    if not mem.exists():
        append_text(
            mem,
            "# 案例经验记录 | " + args.case_id + LF + LF
            + "> 条目格式见 .agents/skills/turbomachinery-case-ledger/SKILL.md。" + LF
            + "> 满足晋升三条件之一时，改写为可执行判据进入 skill 的 references/contracts.md。" + LF + LF,
        )

    payload = {"ok": True, "case": str(case), "case_id": args.case_id, "dirs": CASE_DIRS}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("已创建案例 " + args.case_id + " -> " + str(case))
        for d in CASE_DIRS:
            print("  " + d + "/")
    return EXIT_OK


def cmd_add(args):
    case = Path(args.case).resolve()
    if not case.is_dir():
        die(EXIT_PRECONDITION, "案例目录不存在：" + str(case), args.json)
    if args.stage not in STAGE_BY_ID:
        die(EXIT_USAGE, "未知阶段 " + args.stage, args.json)

    rel = Path(args.path)
    if rel.is_absolute():
        die(EXIT_USAGE, "--path 必须是相对案例目录的路径", args.json)
    target = case / rel
    if not target.exists():
        die(EXIT_PRECONDITION, "产物不存在，拒绝登记：" + str(target), args.json)
    if not target.is_file():
        die(EXIT_USAGE, "--path 必须指向文件：" + str(target), args.json)

    digest = "SKIPPED" if args.no_hash else sha256_file(target)
    size = target.stat().st_size
    rel_posix = as_posix(rel)

    manifest = load_manifest(case)
    artifacts = manifest.setdefault("artifacts", [])

    duplicate = None
    for item in artifacts:
        if item.get("stage") == args.stage and item.get("path") == rel_posix:
            duplicate = item
            break

    if duplicate and duplicate.get("sha256") == digest and not args.force:
        payload = {
            "ok": True,
            "idempotent": True,
            "artifact": duplicate,
            "message": "同一 (stage, path, sha256) 已登记，未产生新记录",
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("[幂等] " + args.stage + " " + rel_posix + " 未变化，跳过")
        return EXIT_OK

    entry = {
        "stage": args.stage,
        "kind": args.kind,
        "path": rel_posix,
        "version": args.version,
        "sha256": digest,
        "bytes": size,
        "verdict": args.verdict,
        "ts": now_iso(),
        "note": args.note or "",
        "provenance": None,
    }
    if args.from_path:
        src = case / args.from_path
        entry["provenance"] = {
            "from": as_posix(args.from_path),
            "from_sha256": sha256_file(src) if (src.is_file() and not args.no_hash) else None,
        }

    if duplicate:
        artifacts[artifacts.index(duplicate)] = entry
        action = "updated"
    else:
        artifacts.append(entry)
        action = "added"

    manifest["updated"] = now_iso()
    manifest["revision"] = int(manifest.get("revision", 0)) + 1
    manifest["current_stage"] = args.stage
    refresh_requirement_ref(case, manifest)
    write_json_atomic(manifest_path(case), manifest)

    if args.log:
        _append_log(
            case,
            stage=args.stage,
            action="登记产物 " + rel_posix,
            verdict=args.verdict,
            criteria=args.criteria or "（未提供判据，仅登记）",
            note=args.note or "",
            extra={
                "操作者": getattr(args, "actor", "agent"),
                "输入": rel_posix + "  sha256=" + digest[:16] + "  bytes=" + str(size),
                "上游": (entry["provenance"] or {}).get("from") or "无",
                "产物": rel_posix + "  sha256=" + digest,
            },
        )

    payload = {"ok": True, "action": action, "artifact": entry, "revision": manifest["revision"]}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("[" + action + "] " + args.stage + " " + rel_posix + " sha256=" + digest[:12] + " (" + str(size) + " B)")
    return EXIT_OK


def cmd_log(args):
    case = Path(args.case).resolve()
    if not case.is_dir():
        die(EXIT_PRECONDITION, "案例目录不存在：" + str(case), args.json)
    if args.stage not in STAGE_BY_ID:
        die(EXIT_USAGE, "未知阶段 " + args.stage, args.json)
    if args.verdict not in VERDICTS:
        die(EXIT_USAGE, "未知结论 " + args.verdict, args.json)

    extra = {"操作者": getattr(args, "actor", "agent")}
    if args.command:
        extra["命令"] = args.command
    if args.measured:
        extra["实测"] = args.measured
    if args.artifact:
        p = case / args.artifact
        digest = sha256_file(p) if (p.is_file() and not args.no_hash) else "（文件不存在）"
        extra["产物"] = as_posix(args.artifact) + "  sha256=" + digest

    _append_log(
        case, stage=args.stage, action=args.action, verdict=args.verdict,
        criteria=args.criteria, note=args.note or "", extra=extra,
    )

    manifest = load_manifest(case)
    manifest["updated"] = now_iso()
    manifest["revision"] = int(manifest.get("revision", 0)) + 1
    write_json_atomic(manifest_path(case), manifest)

    payload = {"ok": True, "stage": args.stage, "verdict": args.verdict}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("[日志已追加] " + args.stage + " " + args.verdict + " - " + args.action)
    return EXIT_OK


def cmd_stage(args):
    case = Path(args.case).resolve()
    if not case.is_dir():
        die(EXIT_PRECONDITION, "案例目录不存在：" + str(case), args.json)
    if args.stage not in STAGE_BY_ID:
        die(EXIT_USAGE, "未知阶段 " + args.stage, args.json)
    if args.status not in ("pending", "in_progress", "done", "blocked"):
        die(EXIT_USAGE, "status 应为 pending|in_progress|done|blocked", args.json)

    manifest = load_manifest(case)
    state = load_state(case, manifest.get("case_id", case.name))
    state["stages"][args.stage]["status"] = args.status
    state["stages"][args.stage]["updated"] = now_iso()
    state["current_stage"] = args.stage
    state["updated"] = now_iso()
    state["revision"] = int(state.get("revision", 0)) + 1

    if args.status == "blocked" and args.reason:
        state.setdefault("blockers", []).append(
            {"stage": args.stage, "reason": args.reason, "ts": now_iso()}
        )
    elif args.status == "done":
        state["blockers"] = [b for b in state.get("blockers", []) if b.get("stage") != args.stage]

    write_json_atomic(state_path(case), state)

    manifest["current_stage"] = args.stage
    manifest["updated"] = now_iso()
    write_json_atomic(manifest_path(case), manifest)

    if args.status in ("done", "blocked"):
        _append_log(
            case, stage=args.stage,
            action="阶段状态 -> " + args.status,
            verdict="PASS" if args.status == "done" else "BLOCKED",
            criteria=args.criteria or "（阶段状态变更）",
            note=args.reason or "",
            extra={"操作者": getattr(args, "actor", "agent")},
        )

    payload = {"ok": True, "stage": args.stage, "status": args.status}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("[" + args.stage + "] status = " + args.status)
    return EXIT_OK


def cmd_verify(args):
    case = Path(args.case).resolve()
    if not case.is_dir():
        die(EXIT_PRECONDITION, "案例目录不存在：" + str(case), args.json)

    manifest = load_manifest(case)
    problems = []
    checked = 0

    for art in manifest.get("artifacts", []):
        rel = art.get("path")
        target = case / rel
        checked += 1
        if not target.is_file():
            problems.append("缺失：" + str(rel) + " (" + str(art.get("stage")) + ")")
            continue
        expected = art.get("sha256")
        if expected and expected != "SKIPPED":
            actual = sha256_file(target)
            if actual != expected:
                problems.append("哈希不符：" + str(rel) + " 期望 " + expected[:12] + " 实际 " + actual[:12])

    missing_prov = [
        a["path"] for a in manifest.get("artifacts", [])
        if a.get("stage") not in ("G0", "G1") and not a.get("provenance")
    ]

    # 支撑脚本也要算哈希 —— 它们不在闸门里，但**改了脚本会改全套结果**。
    # 案例里的 _automation/*.py 就是这种：13 个脚本驱动几何/网格/求解，
    # 改一个没人发现，产物的哈希却全都对（因为产物确实没动过）。
    # 这里把它们登记成 supporting，只算哈希、不参与闸门判定。
    support = []
    for pat in ("_automation/**/*.py", "_automation/**/*.ps1", "_replay/**/*.py"):
        for p in sorted(case.glob(pat)):
            if p.is_file():
                support.append({"path": p.relative_to(case).as_posix(),
                                "sha256": sha256_file(p),
                                "bytes": p.stat().st_size})
    support_bad = []
    recorded = {s["path"]: s.get("sha256") for s in (manifest.get("supporting") or [])}
    if recorded:
        for s in support:
            was = recorded.get(s["path"])
            if was and was != s["sha256"]:
                support_bad.append("脚本变了：" + s["path"])
        for rel in recorded:
            if rel not in {s["path"] for s in support}:
                support_bad.append("脚本没了：" + rel)
    manifest["supporting"] = support
    try:
        write_json_atomic(manifest_path(case), manifest)
    except Exception:
        pass

    if support_bad:
        problems += support_bad

    payload = {
        "ok": not problems,
        "case_id": manifest.get("case_id"),
        "supporting_count": len(support),
        "supporting_changed": support_bad,
        "checked": checked,
        "problems": problems,
        "artifacts_without_provenance": missing_prov,
        "revision": manifest.get("revision"),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        verdict = "全部通过" if not problems else str(len(problems)) + " 个问题"
        print("校验 " + str(checked) + " 个产物：" + verdict)
        for p in problems:
            print("  x " + p)
        if missing_prov:
            print("  ! " + str(len(missing_prov)) + " 个产物缺 provenance（建议补 --from）")
    return EXIT_OK if not problems else EXIT_VERIFY


def cmd_show(args):
    case = Path(args.case).resolve()
    manifest = load_manifest(case)
    state = load_state(case, manifest.get("case_id", case.name))

    if args.json:
        print(json.dumps({"manifest": manifest, "state": state}, ensure_ascii=False, indent=2))
        return EXIT_OK

    print("案例 " + str(manifest.get("case_id")) + " | 当前阶段 " + str(manifest.get("current_stage"))
          + " | revision " + str(manifest.get("revision")))
    ref = manifest.get("requirement_ref")
    print("需求基线：" + (ref["file"] if ref else "（未建立）"))
    print("")
    print("阶段：")
    marks = {"done": "v", "in_progress": ">", "blocked": "x", "pending": "."}
    for s in STAGES:
        st = state["stages"].get(s["id"], {})
        print("  " + marks.get(st.get("status"), "?") + " " + s["id"] + " " + s["name"] + " : " + str(st.get("status")))
    print("")
    arts = manifest.get("artifacts", [])
    print("产物（" + str(len(arts)) + "）：")
    for a in arts:
        print("  [" + str(a.get("stage")) + "] " + str(a.get("version")) + " " + str(a.get("verdict"))
              + " " + str(a.get("path")))
    blockers = state.get("blockers", [])
    if blockers:
        print("")
        print("阻塞：")
        for b in blockers:
            print("  x " + str(b.get("stage")) + " " + str(b.get("reason")))
    return EXIT_OK


def build_parser():
    p = argparse.ArgumentParser(
        prog="case_ledger.py",
        description="叶轮机械设计案例的产物登记 / 版本沉淀 / 工程日志",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    n = sub.add_parser("new", help="建立案例骨架")
    n.add_argument("--case-id", required=True)
    n.add_argument("--root", default="cases")
    n.add_argument("--force", action="store_true")
    n.add_argument("--json", action="store_true")
    n.set_defaults(func=cmd_new)

    a = sub.add_parser("add", help="登记产物（幂等）")
    a.add_argument("--case", required=True)
    a.add_argument("--stage", required=True, choices=STAGE_IDS)
    a.add_argument("--kind", required=True)
    a.add_argument("--path", required=True)
    a.add_argument("--version", default="v1")
    a.add_argument("--verdict", default="INFO", choices=VERDICTS)
    a.add_argument("--from", dest="from_path", default=None)
    a.add_argument("--criteria", default=None)
    a.add_argument("--note", default=None)
    a.add_argument("--no-hash", action="store_true")
    a.add_argument("--actor", default="agent", help="操作者标识：agent / human(web-ui)")
    a.add_argument("--no-log", dest="log", action="store_false", default=True)
    a.add_argument("--force", action="store_true")
    a.add_argument("--json", action="store_true")
    a.set_defaults(func=cmd_add)

    lo = sub.add_parser("log", help="向 LOG.md 追加一条结构化条目")
    lo.add_argument("--case", required=True)
    lo.add_argument("--stage", required=True, choices=STAGE_IDS)
    lo.add_argument("--action", required=True)
    lo.add_argument("--verdict", required=True, choices=VERDICTS)
    lo.add_argument("--criteria", required=True)
    lo.add_argument("--command", default=None)
    lo.add_argument("--measured", default=None)
    lo.add_argument("--artifact", default=None)
    lo.add_argument("--note", default=None)
    lo.add_argument("--actor", default="agent", help="操作者标识：agent / human(web-ui)")
    lo.add_argument("--no-hash", action="store_true")
    lo.add_argument("--json", action="store_true")
    lo.set_defaults(func=cmd_log)

    s = sub.add_parser("stage", help="更新阶段状态机")
    s.add_argument("--case", required=True)
    s.add_argument("--stage", required=True, choices=STAGE_IDS)
    s.add_argument("--status", required=True, choices=["pending", "in_progress", "done", "blocked"])
    s.add_argument("--reason", default=None)
    s.add_argument("--criteria", default=None)
    s.add_argument("--actor", default="agent", help="操作者标识：agent / human(web-ui)")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_stage)

    v = sub.add_parser("verify", help="校验产物存在性与哈希")
    v.add_argument("--case", required=True)
    v.add_argument("--json", action="store_true")
    v.set_defaults(func=cmd_verify)

    sh = sub.add_parser("show", help="打印案例状态总览")
    sh.add_argument("--case", required=True)
    sh.add_argument("--json", action="store_true")
    sh.set_defaults(func=cmd_show)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except SystemExit:
        raise
    except Exception as exc:
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "exit": EXIT_INTERNAL, "error": repr(exc)}, ensure_ascii=False))
        else:
            print("INTERNAL ERROR: " + repr(exc), file=sys.stderr)
        return EXIT_INTERNAL


if __name__ == "__main__":
    raise SystemExit(main())
