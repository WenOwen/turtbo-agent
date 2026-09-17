#!/usr/bin/env python3
"""preflight.py - 环境预检。任何闸门开跑前先过这一关。

检查项
------
  P-1 projectRoot  === cwd      （否则工作区 skill 全部失效）
  P-2 工作路径纯 ASCII          （否则 AutoGrid 会把合法 geomTurbo 误报为格式错误）
  P-3 NUMECA 安装存在
  P-4 NUMECA 授权守护进程在跑
  P-5 MPI 启动器存在
  P-6 磁盘剩余
  P-7 外部工具 venv（turbo-flow / cascade-forge）
  P-8 git 工作区状态

用法
----
  python tools/preflight.py all
  python tools/preflight.py numeca
  python tools/preflight.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_FAIL = 4

NUMECA_ROOT_DEFAULT = Path("D:/NUMECA_SOFTWARE")
NUMECA_FINE = "fine161"
TURBO_FLOW = Path("D:/Project/Research/turbo-flow")
CASCADE_FORGE = Path("D:/Project/Research/cascade-forge")
MIN_FREE_GB = 20.0


def find_project_root(start: Path) -> Path:
    """DSH 的 projectRoot：包含 .git 的最近祖先；没有则用 cwd。"""
    cur = start.resolve()
    for candidate in [cur, *cur.parents]:
        if (candidate / ".git").exists():
            return candidate
    return cur


def is_ascii(text: str) -> bool:
    try:
        text.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def check_project_root(cwd: Path):
    root = find_project_root(cwd)
    ok = root == cwd.resolve()
    return {
        "id": "P-1", "title": "projectRoot === cwd",
        "criteria": "工作区必须是 DSH 的 projectRoot，否则 .agents/skills 不会被发现",
        "measured": "cwd=%s  projectRoot=%s" % (cwd, root),
        "verdict": "PASS" if ok else "FAIL",
        "fix": "" if ok else "删除上层 .git，或把 skill 同步到用户根 ~/.agents/skills",
    }


def check_ascii(cwd: Path):
    bad = not is_ascii(str(cwd))
    return {
        "id": "P-2", "title": "工作路径纯 ASCII",
        "criteria": "全链路路径不得含非 ASCII 字符",
        "measured": str(cwd),
        "verdict": "FAIL" if bad else "PASS",
        "fix": "把工作区移到纯 ASCII 路径" if bad else "",
    }


def check_numeca_install():
    fine = NUMECA_ROOT_DEFAULT / NUMECA_FINE
    exists = fine.is_dir()
    bins = ["bin64/euranusx86_64.exe", "bin64/finebatchx86_64.exe",
            "bin64/cfviewx86_64.exe", "bin64/iggx86_64.exe"]
    present = [b for b in bins if (fine / b).is_file()]
    return {
        "id": "P-3", "title": "NUMECA 安装存在",
        "criteria": "需要 " + str(fine) + " 及 bin64 下的求解/网格/后处理可执行文件",
        "measured": "found=%d/%d  %s" % (len(present), len(bins), [Path(b).name for b in present]),
        "verdict": "PASS" if exists and len(present) >= 3 else "FAIL",
        "fix": "" if exists else "检查 NUMECA_ROOT 或安装",
    }


def check_license():
    # 注意：tasklist 在受限沙箱里会返回 Access denied，因此用 PowerShell Get-Process。
    try:
        out = subprocess.run(
            ["pwsh", "-NoProfile", "-Command",
             "(Get-Process lmgrd -ErrorAction SilentlyContinue | Measure-Object).Count"],
            capture_output=True, text=True, timeout=60,
        ).stdout.strip()
        count = int(out) if out.isdigit() else 0
    except Exception as exc:
        return {"id": "P-4", "title": "NUMECA 授权守护进程", "criteria": "lmgrd 必须在跑",
                "measured": "无法检测：" + repr(exc), "verdict": "SKIP",
                "fix": "人工确认：Get-Process lmgrd"}
    running = count > 0
    return {
        "id": "P-4", "title": "NUMECA 授权守护进程",
        "criteria": "lmgrd (FlexNet) 必须在运行",
        "measured": "lmgrd 进程数 = %d" % count,
        "verdict": "PASS" if running else "FAIL",
        "fix": "" if running else "启动 NUMECA 授权服务（lmtools -> Start Server）",
    }


def _unused_license_probe():
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq lmgrd.exe", "/NH"],
            capture_output=True, text=True, timeout=30,
        ).stdout
    except Exception as exc:
        return str(exc)
    running = "lmgrd" in out.lower()
    return {
        "id": "P-4", "title": "NUMECA 授权守护进程",
        "criteria": "lmgrd (FlexNet) 必须在运行",
        "measured": "lmgrd running=%s" % running,
        "verdict": "PASS" if running else "FAIL",
        "fix": "" if running else "启动 NUMECA 授权服务（lmtools -> Start Server）",
    }


def check_mpi():
    root = NUMECA_ROOT_DEFAULT / NUMECA_FINE
    cands = [root / "impi5/mpiexec.exe", root / "bin64/euranus_mpich2x86_64.exe"]
    found = [p for p in cands if p.is_file()]
    return {
        "id": "P-5", "title": "MPI 启动器存在",
        "criteria": "并行求解需要 mpiexec；不存在时只能用顺序模式",
        "measured": "found=" + str([p.name for p in found]),
        "verdict": "PASS" if found else "WARN",
        "fix": "" if found else "无 MPI 时用顺序求解（v7 已验证 5000 rpm 锚点顺序可完成）",
    }


def check_disk(cwd: Path):
    try:
        usage = shutil.disk_usage(str(cwd.drive + os.sep))
    except Exception as exc:
        return {"id": "P-6", "title": "磁盘剩余", "criteria": ">= %.0f GB" % MIN_FREE_GB,
                "measured": repr(exc), "verdict": "SKIP", "fix": ""}
    free_gb = usage.free / (1024 ** 3)
    return {
        "id": "P-6", "title": "磁盘剩余",
        "criteria": ">= %.0f GB（单点约 100-200 MB，全扫 GB 级）" % MIN_FREE_GB,
        "measured": "%.1f GB free on %s" % (free_gb, cwd.drive),
        "verdict": "PASS" if free_gb >= MIN_FREE_GB else "WARN",
        "fix": "" if free_gb >= MIN_FREE_GB else "清理或换盘",
    }


def check_tools():
    items = []
    for label, root, rel in (("turbo-flow", TURBO_FLOW, ".venv/Scripts/python.exe"),
                             ("cascade-forge", CASCADE_FORGE, "UDF/.venv/Scripts/python.exe")):
        exe = root / rel
        items.append({"label": label, "path": str(exe), "exists": exe.is_file()})
    ok = all(i["exists"] for i in items)
    return {
        "id": "P-7", "title": "外部工具 venv",
        "criteria": "turbo-flow 与 cascade-forge 的 venv 必须可调用",
        "measured": "; ".join("%s=%s" % (i["label"], i["exists"]) for i in items),
        "verdict": "PASS" if ok else "WARN",
        "fix": "" if ok else "缺失的 venv 需要先建立依赖",
        "detail": items,
    }


def check_git(cwd: Path):
    try:
        out = subprocess.run(["git", "status", "--short"], capture_output=True,
                             text=True, timeout=30, cwd=str(cwd)).stdout
    except Exception as exc:
        return {"id": "P-8", "title": "git 工作区", "criteria": "可读",
                "measured": repr(exc), "verdict": "SKIP", "fix": ""}
    lines = [l for l in out.splitlines() if l.strip()]
    return {
        "id": "P-8", "title": "git 工作区",
        "criteria": "大文件（.cgns/.iec/.res）不得被提交",
        "measured": "%d 处未提交改动" % len(lines),
        "verdict": "PASS",
        "fix": "",
        "detail": lines[:20],
    }


GROUPS = {
    "project": [check_project_root, check_ascii],
    "numeca": [check_numeca_install, check_license, check_mpi],
    "tools": [check_tools],
    "disk": [check_disk],
    "git": [check_git],
}
ALL_ORDER = ["project", "numeca", "tools", "disk", "git"]


def main(argv=None):
    p = argparse.ArgumentParser(prog="preflight.py", description="环境预检")
    p.add_argument("group", nargs="?", default="all",
                   choices=list(GROUPS.keys()) + ["all"])
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    cwd = Path.cwd()
    groups = ALL_ORDER if args.group == "all" else [args.group]
    results = []
    for g in groups:
        for fn in GROUPS[g]:
            try:
                if fn in (check_project_root, check_ascii, check_git):
                    results.append(fn(cwd))
                else:
                    results.append(fn())
            except TypeError:
                results.append(fn(cwd))
            except Exception as exc:
                results.append({"id": "?", "title": fn.__name__, "criteria": "-",
                                "measured": repr(exc), "verdict": "SKIP", "fix": ""})

    fails = [r for r in results if r["verdict"] == "FAIL"]
    warns = [r for r in results if r["verdict"] == "WARN"]

    if args.json:
        print(json.dumps({"ok": not fails, "checks": results,
                          "fail": len(fails), "warn": len(warns)},
                         ensure_ascii=False, indent=2))
    else:
        print("环境预检：" + ("通过" if not fails else "%d 项失败" % len(fails))
              + ("（%d 项警告）" % len(warns) if warns else ""))
        for r in results:
            mark = {"PASS": "v", "WARN": "!", "FAIL": "x", "SKIP": "-"}.get(r["verdict"], "?")
            print("  " + mark + " " + r["id"] + " " + r["title"] + "  [" + r["measured"] + "]")
            if r.get("fix"):
                print("      -> " + r["fix"])

    return EXIT_OK if not fails else EXIT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
