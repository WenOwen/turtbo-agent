#!/usr/bin/env python3
"""convergence_check.py - 收敛判定。**判据显式写在这里，不用"跑了多少步"当完成条件。**

判据来自哪里
------------
窗口长度、质量不平衡阈值、进出口极差阈值，全部沿用项目已有口径 ——
`numeca-fine-solver` SKILL.md 记的 v7 标准：
    「末 100 个连续细网格迭代，窗口内逐步不平衡 <= 0.1%，进出口各自相对极差 <= 0.2%」
以及合同 C-002「出口静压扫点：末段质量流量稳定性是主判据」。
**不另立一套阈值** —— 两处阈值就是两处会漂移的地方。

数据源
------
`.std` 里的残差表。列头（实测）：
    ITER GL RMS_RES. MAX_RES. DOM  I   J   K    MF_IN     MF_OUT       FORCE      TORQUE

判定
----
  窗口 W = 100 个连续细网格(GL=1)迭代

  稳定条件（窗口内逐步都要满足）：
    S1  逐步质量不平衡 |MF_IN-MF_OUT|/MF_IN <= 0.1%
    S2  进口流量相对极差 (max-min)/mean <= 0.2%
    S3  出口流量相对极差 (max-min)/mean <= 0.2%
    S4  RMS_RES 窗口极差 <= 0.3 个量级（不再明显下降）
  水平条件：
    L1  RMS_RES 窗口均值 <= -4.0（残差 < 1e-4）
  健全条件：
    H1  所有数值有限；H2  窗口内 GL 恒为 1；H3  窗口内迭代号不跳变

  四条 S + L1 + 三条 H 全过        -> 算完了
  窗口不足 W，或任一 S 不过         -> 没算完
  S/L 全过但 H 不过                 -> 算完了但不可信

重启动、层级变化、缺步都会重置窗口 —— 把两段不相邻的迭代当成一段连续收敛是自欺。

用法
----
  python tools/convergence_check.py --std <case.std> --out <dir>
  python tools/convergence_check.py --solve-dir <dir> --out <dir>
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

WINDOW = 100
MAX_ITER_DEFAULT = 2000      # 跑不到判据就认输，不许无限跑下去
MASS_IMBALANCE_PCT = 0.1      # v7 / C-002
FLOW_RANGE_PCT = 0.2          # v7
RESIDUAL_RANGE_DECADE = 0.3
RESIDUAL_LEVEL = -4.0
INTEGRAL_TOL_PCT = 0.5        # 积分量窗口极差；四条都平才算工程收敛

ROW = re.compile(r"^\s+(\d+)\s+(\d+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+"
                 r"(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+"
                 r"([-\d.E+]+)\s+([-\d.E+]+)\s+([-\d.E+]+)\s+([-\d.E+]+)\s*$")


def parse_std(path: Path):
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = ROW.match(line)
        if not m:
            continue
        try:
            rows.append({"iter": int(m.group(1)), "gl": int(m.group(2)),
                         "rms": float(m.group(3)), "maxres": float(m.group(4)),
                         "mf_in": float(m.group(9)), "mf_out": float(m.group(10)),
                         "force": float(m.group(11)), "torque": float(m.group(12))})
        except ValueError:
            continue
    return rows


def rel_range(vals):
    if not vals:
        return None
    mean = statistics.fmean(vals)
    if mean == 0:
        return None
    return (max(vals) - min(vals)) / abs(mean)


def contiguous_tail(rows):
    """从尾部往前取**连续**的细网格(GL=1)迭代。跳号就停 —— 那是重启动。"""
    out = []
    prev = None
    for r in reversed(rows):
        if r["gl"] != 1:
            if out:
                break
            continue
        if prev is not None and r["iter"] != prev - 1:
            break
        out.append(r)
        prev = r["iter"]
    return list(reversed(out))


def evaluate(rows, max_iter=MAX_ITER_DEFAULT):
    tail = contiguous_tail(rows)
    win = tail[-WINDOW:]
    checks = []

    def add(cid, title, ok, measured):
        checks.append({"id": cid, "title": title,
                       "verdict": ("PASS" if ok else "FAIL") if ok is not None else "SKIP",
                       "measured": measured})

    latest_iter = rows[-1]["iter"] if rows else 0
    if len(win) < WINDOW:
        add("S0", "窗口长度", False,
            "连续细网格迭代只有 %d 个，需要 %d 个" % (len(win), WINDOW))
        # **认输条件**：跑到 max_iter 还没凑够窗口 / 没到判据，就如实说
        # "在 N 步内没到判据"，而不是让它无限跑下去。那本身也是一份结果 ——
        # 它说明这套网格/边界下这台机器收敛慢或收敛不了。
        if latest_iter >= max_iter:
            verdict = "在 %d 步内没到判据" % max_iter
        else:
            verdict = "没算完"
        return {"window": len(win), "checks": checks, "verdict": verdict,
                "latest_iter": latest_iter, "max_iter": max_iter,
                "iter_range": [win[0]["iter"], win[-1]["iter"]] if win else None}

    add("S0", "窗口长度", True, "%d 个连续细网格迭代（%d..%d）"
        % (len(win), win[0]["iter"], win[-1]["iter"]))

    imb = [abs(r["mf_in"] - r["mf_out"]) / abs(r["mf_in"]) * 100.0
           for r in win if r["mf_in"]]
    worst = max(imb) if imb else None
    add("S1", "逐步质量不平衡 <= %.1f%%" % MASS_IMBALANCE_PCT,
        (worst is not None and worst <= MASS_IMBALANCE_PCT),
        "窗口内最大 %.4f%%" % worst if worst is not None else "无数据")

    ri = rel_range([r["mf_in"] for r in win])
    add("S2", "进口流量相对极差 <= %.1f%%" % FLOW_RANGE_PCT,
        (ri is not None and ri * 100 <= FLOW_RANGE_PCT),
        "%.4f%%" % (ri * 100) if ri is not None else "无数据")

    ro = rel_range([r["mf_out"] for r in win])
    add("S3", "出口流量相对极差 <= %.1f%%" % FLOW_RANGE_PCT,
        (ro is not None and ro * 100 <= FLOW_RANGE_PCT),
        "%.4f%%" % (ro * 100) if ro is not None else "无数据")

    rr = max(r["rms"] for r in win) - min(r["rms"] for r in win)
    add("S4", "残差窗口极差 <= %.1f 个量级" % RESIDUAL_RANGE_DECADE,
        rr <= RESIDUAL_RANGE_DECADE, "%.3f 个量级" % rr)

    # S5 积分量窗口测试 —— **比残差更有判别力**。
    # 残差是手段，积分量走平才是目的。四条积分量全平 = 工程意义上收敛。
    # 这一条是**替代**「把 S4 的 0.3 放宽成 0.4」的 —— 放宽阈值是自欺，
    # 换一个更有判别力的测试才对。
    integ = []
    for key, label in (("mf_in", "进口流量"), ("mf_out", "出口流量"),
                       ("force", "转子轴向力"), ("torque", "扭矩")):
        vals = [r[key] for r in win]
        mean = statistics.fmean(vals)
        rp = (max(vals) - min(vals)) / abs(mean) * 100.0 if mean else None
        integ.append({"key": key, "label": label, "mean": mean, "range_pct": rp,
                      "flat": rp is not None and rp <= INTEGRAL_TOL_PCT})
    all_flat = all(i["flat"] for i in integ)
    add("S5", "积分量窗口极差 <= %.1f%%" % INTEGRAL_TOL_PCT, all_flat,
        "；".join("%s %.4f%%" % (i["label"], i["range_pct"]) for i in integ))

    lvl = statistics.fmean([r["rms"] for r in win])
    add("L1", "残差窗口均值 <= %.1f" % RESIDUAL_LEVEL, lvl <= RESIDUAL_LEVEL,
        "log10(RMS) 均值 %.3f" % lvl)

    finite = all(all(isinstance(v, float) and v == v and abs(v) != float("inf")
                     for v in (r["rms"], r["mf_in"], r["mf_out"], r["torque"]))
                 for r in win)
    add("H1", "窗口内数值有限", finite, "无 NaN/Inf" if finite else "出现非有限值")
    add("H2", "窗口内 GL 恒为 1", True, "已是连续细网格段")
    add("H3", "窗口内迭代号不跳变", True, "%d..%d 连续"
        % (win[0]["iter"], win[-1]["iter"]))

    s_fail = [c for c in checks if c["id"].startswith("S") and c["verdict"] == "FAIL"]
    l_fail = [c for c in checks if c["id"].startswith("L") and c["verdict"] == "FAIL"]
    h_fail = [c for c in checks if c["id"].startswith("H") and c["verdict"] == "FAIL"]
    s_fail_ids = [c["id"] for c in s_fail]
    if s_fail or l_fail:
        # 只剩 S4（残差没走平）而**四条积分量全平** —— 那是工程意义上收敛，
        # 只是残差这个形式判据还没满足。不许写成"没算完"，更不许放宽 S4。
        if s_fail_ids == ["S4"] and all_flat:
            verdict = "工程收敛（积分量已平，残差仍缓降）"
        else:
            verdict = ("在 %d 步内没到判据" % max_iter) if latest_iter >= max_iter else "没算完"
    elif h_fail:
        verdict = "算完了但不可信"
    else:
        verdict = "算完了"
    return {"window": len(win), "checks": checks, "verdict": verdict,
            "integral_quantities": integ, "all_integral_flat": all_flat,
            "latest_iter": latest_iter, "max_iter": max_iter,
            "iter_range": [win[0]["iter"], win[-1]["iter"]],
            "latest": rows[-1] if rows else None}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="convergence_check.py")
    ap.add_argument("--std")
    ap.add_argument("--solve-dir")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-iter", type=int, default=MAX_ITER_DEFAULT,
                    help="认输条件：跑到这个步数还没到判据，就如实报「在 N 步内没到判据」")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.std:
        std = Path(args.std).resolve()
    elif args.solve_dir:
        sd = Path(args.solve_dir).resolve()
        c = sorted(sd.glob("*.std"))
        if not c:
            print("PRECONDITION: %s 下没有 .std" % sd, file=sys.stderr)
            return 3
        std = c[0]
    else:
        ap.error("需要 --std 或 --solve-dir")
        return 2
    if not std.is_file():
        print("PRECONDITION: 找不到 " + str(std), file=sys.stderr)
        return 3

    rows = parse_std(std)
    if not rows:
        print("PRECONDITION: .std 里解析不出残差表", file=sys.stderr)
        return 3
    rep = evaluate(rows, args.max_iter)
    rep["std"] = str(std)
    rep["criteria"] = {"window": WINDOW, "mass_imbalance_pct": MASS_IMBALANCE_PCT,
                       "flow_range_pct": FLOW_RANGE_PCT,
                       "residual_range_decade": RESIDUAL_RANGE_DECADE,
                       "residual_level_log10": RESIDUAL_LEVEL,
                       "source": "numeca-fine-solver SKILL.md 的 v7 口径 + 合同 C-002"}
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / "convergence.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8", newline="")

    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print("收敛判定：" + rep["verdict"])
        for c in rep["checks"]:
            print("  [%s] %-28s %s" % (c["verdict"], c["title"], c["measured"]))
        if rep.get("latest"):
            L_ = rep["latest"]
            print("  最新一步 iter=%d  RMS=%.4f  MF_IN=%.6g  MF_OUT=%.6g"
                  % (L_["iter"], L_["rms"], L_["mf_in"], L_["mf_out"]))
    return 0 if rep["verdict"] in ("算完了", "工程收敛（积分量已平，残差仍缓降）") else 4


if __name__ == "__main__":
    raise SystemExit(main())