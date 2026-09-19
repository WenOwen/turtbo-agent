#!/usr/bin/env python3
r"""setup_n05000.py - 把 5000rpm/101325Pa 算例重新布置进案例，并改绑网格路径。

为什么需要它
------------
v8 那条线的 .run 里 GRID_FILE 指向**原始目录**：
    D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v8\mesh\mesh-v2\mesh-v2.igg
而案例自己有一份**逐字节相同**的网格：
    cases/DF90-001/03-mesh/v2/mesh-v2.igg   (sha256 433150fa56c18eca..., 483468 B)
两者哈希一致 —— 所以改绑是**纯路径变化，物理零变化**。这不是假设，是验证过的。

做了三件事：
  1. 逐字节替换 .run 里的 GRID_FILE
  2. 逐字节替换 .steering 里的 NAME（它指向自己的绝对路径）
  3. 写 setup.json 记录改了什么、从哪来、凭什么

安全措施：改之前先确认两件事 ——
  (a) 文件里不含 >= 0x80 的字节（否则按 ASCII 读写会损坏内容）
  (b) 每个待替换串的出现次数与预期一致（少了说明路径变了，多了说明有别的引用）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ORIG = Path(r"D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v8"
            r"\fine\v8-optimized\v8-optimized_n05000_p101325")
ORIG_STEM = "v8-optimized_n05000_p101325"


def sha256(p: Path):
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rebind(src: Path, dst: Path, pairs):
    """逐字节替换。pairs 是 [(旧串, 新串, 预期出现次数)]。"""
    raw = src.read_bytes()
    high = [b for b in raw if b >= 0x80]
    if high:
        raise SystemExit("拒绝：%s 含 %d 个 >=0x80 的字节，按 ASCII 改写会损坏内容"
                         % (src.name, len(high)))
    text = raw.decode("ascii")
    log = []
    for old, new, expect in pairs:
        n = text.count(old)
        if n != expect:
            raise SystemExit("拒绝：%s 里 %r 出现 %d 次，预期 %d 次 —— 先查清再加改"
                             % (src.name, old[:60], n, expect))
        text = text.replace(old, new)
        log.append({"旧": old, "新": new, "替换次数": n})
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(text.encode("ascii"))
    return {"src": str(src), "dst": str(dst),
            "src_bytes": len(raw), "dst_bytes": dst.stat().st_size,
            "src_sha256": sha256(src), "dst_sha256": sha256(dst),
            "替换": log}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default=r"D:\Project\Research\turtbo-agent\cases\DF90-001")
    ap.add_argument("--dest", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    case = Path(args.case).resolve()
    dest = Path(args.dest).resolve() if args.dest else case / "04-solve" / "v2" / "n05000_p101325"
    case_mesh = case / "03-mesh" / "v2" / "mesh-v2.igg"
    if not case_mesh.is_file():
        raise SystemExit("案例网格不在：" + str(case_mesh))

    orig_run = ORIG / (ORIG_STEM + ".run")
    orig_steer = ORIG / (ORIG_STEM + ".steering")
    for p in (orig_run, orig_steer):
        if not p.is_file():
            raise SystemExit("原始文件不在：" + str(p))

    orig_mesh = ORIG.parent.parent.parent / "mesh" / "mesh-v2" / "mesh-v2.igg"
    stem = "n05000_p101325"
    new_run = dest / (stem + ".run")
    new_steer = dest / (stem + ".steering")

    r1 = rebind(orig_run, new_run, [(str(orig_mesh), str(case_mesh), 1)])
    r2 = rebind(orig_steer, new_steer, [(str(ORIG / (ORIG_STEM + ".steering")),
                                        str(new_steer), 1)])

    leftover = []
    for p in (new_run, new_steer):
        t = p.read_bytes().decode("ascii")
        for token in ("Ducted-Fan", "v8-optimized"):
            c = t.count(token)
            if c:
                leftover.append({"file": p.name, "token": token, "count": c})

    same = sha256(case_mesh) == sha256(orig_mesh)
    setup = {
        "case": "DF90-001",
        "version": "v2",
        "case_name": stem,
        "work_point": {"rpm": 5000, "outlet_static_pressure_pa": 101325,
                       "omega_rad_s": 523.598775571636,
                       "source": "原始算例目录的 boundary_audit.json（实测）"},
        "why_redo": ("04-solve/v1 下 60 个工况只有 1 个留下结果，且残差停在 1e-3.5 未收敛。",
                     "这一版把那个唯一的真解重新布置进案例，让产物落在案例内。"),
        "mesh_rebind": {
            "reason": "案例自带网格与原网格逐字节相同，改绑是纯路径变化，物理零变化",
            "from": str(orig_mesh),
            "to": str(case_mesh),
            "from_sha256": sha256(orig_mesh),
            "to_sha256": sha256(case_mesh),
            "identical": same,
            "bytes": case_mesh.stat().st_size,
        },
        "edits": [r1, r2],
        "leftover_source_refs": leftover,
        "source": {"orig_case_dir": str(ORIG), "orig_stem": ORIG_STEM},
        "command": (r"D:\NUMECA_SOFTWARE\fine161\bin64\euranusx86_64.exe "
                    + chr(34) + str(new_run) + chr(34)
                    + " -steering " + chr(34) + str(new_steer) + chr(34)
                    + " -niversion " + chr(34) + "161" + chr(34) + " -seq"),
    }
    (dest / "setup.json").write_text(json.dumps(setup, ensure_ascii=False, indent=2) + chr(10),
                                     encoding="utf-8", newline="")

    if args.json:
        print(json.dumps({"ok": not leftover, "dest": str(dest), "setup": setup},
                         ensure_ascii=False, indent=2))
    else:
        print("已布置：" + str(dest))
        print("  .run      %d -> %d 字节" % (r1["src_bytes"], r1["dst_bytes"]))
        print("  .steering %d -> %d 字节" % (r2["src_bytes"], r2["dst_bytes"]))
        print("  网格哈希一致：" + str(same))
        print("  残留原始目录引用：" + (str(leftover) if leftover else "无"))
    return 0 if not leftover else 4


if __name__ == "__main__":
    raise SystemExit(main())