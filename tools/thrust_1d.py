#!/usr/bin/env python3
"""thrust_1d.py - 从一维通流结果算整机静推力（C-004 控制体口径）。

为什么需要它
------------
`通流计算结果表.csv` 有流量/压比/效率/功率/扭矩，**没有推力**；
对标闸门的 B-1..B-7 里**也没有一条是推力**。而需求 ACC-1 就是推力。
所以「这台机器能不能达到 90 kgf」在方案阶段根本答不了。这个工具补上这一格。

口径（C-004）
------------
    T = mdot_out * Vx_out + (p_out - p_inf) * A_out

难点在于 **p_out 与 A_out 取自哪个截面**：
  一维平均线给的是**叶排域末端**（流道表的 OUTLET 站）；
  C-004 要求的是**涵道出口边界**。两者之间隔着一段涵道。

所以这里算三个模型，全部列出，不许只挑一个好看的：

  A 域末即涵道出口   T = mdot*Vx + (ps_exit - p_inf)*A_exit
                     （C-004 直接套；压力项是真实存在的，不是凑数）
  B 完全膨胀到环境压     把同一股气流等熵膨胀到 p_inf，再取那时动量
                     T = mdot*V           （亚声速自由射流要求出口静压=环境压）
  C 面积一致性            要让域末截面 p= p_inf，需要多大面积；与实际比

损失模型
--------
默认等熵（无损失），这是**上界**。另外给 Darcy-Weisbach 摩擦与一个敏感性扫描：
    dp0 = f * (L/Dh) * 0.5*rho*V^2 ，Dh = 2*(r_shroud - r_hub)（环道水力直径）
f 取 0.02：光滑管湍流区，Moody 图 Re~1e6 处 0.018-0.02。**这是引用值，不是拟合值。**

用法
----
  python tools/thrust_1d.py --case cases/DF90-001 --version v3
  python tools/thrust_1d.py --case cases/DF90-001 --version v3 --json
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

GAMMA = 1.4
RGAS = 287.05287
CP = 1006.0          # 与案例 .xmf 自报的 Cp 一致；288-292 K 附近误差 < 0.1%
P_INF = 101325.0     # 环境静压；C-004 规定静止环境 p_inf = 0 Pa(g)
F_DARCY = 0.02       # 光滑管湍流区，Moody 图 Re~1e6；引用值


def read_csv(path):
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return [{k.strip(): (v or "").strip() for k, v in r.items() if k}
                for r in csv.DictReader(fh)]


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def perf_map(rows):
    out = {}
    for r in rows:
        k = (r.get("参数名称") or "").strip()
        if k:
            out[k] = (r.get("数值") or "").strip()
    return out


def mach_from_p0_ps(p0, ps):
    if not p0 or not ps or ps <= 0 or p0 <= ps:
        return None
    return math.sqrt(2.0 / (GAMMA - 1.0) * ((p0 / ps) ** ((GAMMA - 1.0) / GAMMA) - 1.0))


def state(p0, t0, ps):
    """由总压/总温/静压定状态。返回 (M, Ts, rho, V, a)。"""
    m = mach_from_p0_ps(p0, ps)
    if m is None:
        return None
    ts = t0 / (1.0 + 0.5 * (GAMMA - 1.0) * m * m)
    a = math.sqrt(GAMMA * RGAS * ts)
    rho = ps / (RGAS * ts)
    return {"M": m, "Ts": ts, "rho": rho, "V": m * a, "a": a}


def find_ambient_area(mdot, p0, t0, p_inf):
    """完全膨胀到 p_inf 时需要的面积（连续性）。"""
    st = state(p0, t0, p_inf)
    if st is None:
        return None
    return mdot / (st["rho"] * st["V"]), st


def duct_dp0(mdot, rho, v, length_m, gap_m):
    """Darcy-Weisbach 总压损失。Dh 取环道水力直径 = 2*gap。"""
    if gap_m <= 0 or length_m <= 0:
        return 0.0
    dh = 2.0 * gap_m
    return F_DARCY * (length_m / dh) * 0.5 * rho * v * v


def compute(case, version):
    scheme = Path(case) / "01-scheme" / version
    perf = perf_map(read_csv(scheme / "通流计算结果表.csv"))
    ann = read_csv(scheme / "流道尺寸表.csv")
    if not perf or not ann:
        raise SystemExit("PRECONDITION: 读不到 " + str(scheme) + " 的三表")

    mdot = fnum(perf.get("出口质量流量")) or fnum(perf.get("进口质量流量"))
    p0 = fnum(perf.get("出口总压"))
    ps_exit = fnum(perf.get("出口静压"))
    t0_in = fnum(perf.get("进口总温")) or 288.15
    dh0 = fnum(perf.get("级单位功"))
    rpm = fnum(perf.get("转速"))
    if None in (mdot, p0, ps_exit):
        raise SystemExit("PRECONDITION: 计算表缺 出口质量流量/出口总压/出口静压")

    t0 = t0_in + (dh0 / CP if dh0 else 0.0)

    out = [a for a in ann if a.get("站位") == "OUTLET"]
    last = out[0] if out else ann[-1]
    a_exit = fnum(last.get("通流面积(m2)"))
    r_hub = fnum(last.get("轮毂半径(m)"))
    r_shroud = fnum(last.get("机匣半径(m)"))
    x_exit = fnum(last.get("轴向坐标(m)"))
    gap = (r_shroud - r_hub) if (r_shroud and r_hub) else 0.0

    # 域末截面状态（由一维自己给的 p0/ps 定）
    st_exit = state(p0, t0, ps_exit)
    vx = st_exit["V"] if st_exit else None

    res = {
        "case": str(case), "version": version, "rpm": rpm,
        "station": {"id": last.get("站位"), "x_m": x_exit,
                    "hub_r_m": r_hub, "shroud_r_m": r_shroud, "area_m2": a_exit},
        "mdot_kg_s": mdot, "p0_exit_pa": p0, "ps_exit_pa": ps_exit,
        "t0_exit_k": t0, "p_inf_pa": P_INF,
    }

    if vx is None:
        res["error"] = "p0 <= ps_exit，无法定出口状态"
        return res

    # ---- 模型 A：域末截面即涵道出口 ----
    mom_a = mdot * vx
    pres_a = (ps_exit - P_INF) * a_exit
    res["model_A"] = {
        "desc": "域末截面即涵道出口（C-004 直接套）",
        "Vx_m_s": vx, "M": st_exit["M"], "Ts_k": st_exit["Ts"], "rho": st_exit["rho"],
        "momentum_thrust_n": mom_a, "pressure_thrust_n": pres_a,
        "static_thrust_n": mom_a + pres_a,
        "static_thrust_kgf": (mom_a + pres_a) / 9.80665,
    }

    # ---- 模型 B：完全膨胀到环境压 ----
    st_amb = state(p0, t0, P_INF)
    if st_amb:
        mom_b = mdot * st_amb["V"]
        res["model_B"] = {
            "desc": "等熵膨胀到 p_inf 后的动量（亚声速自由射流的出口静压应等于环境压）",
            "V_m_s": st_amb["V"], "M": st_amb["M"], "Ts_k": st_amb["Ts"],
            "momentum_thrust_n": mom_b, "pressure_thrust_n": 0.0,
            "static_thrust_n": mom_b, "static_thrust_kgf": mom_b / 9.80665,
        }
        # ---- 模型 C：面积一致性 ----
        ar = find_ambient_area(mdot, p0, t0, P_INF)
        if ar:
            a_req, _ = ar
            res["model_C"] = {
                "desc": "要让域末截面静压等于环境压，需要的面积",
                "area_required_m2": a_req, "area_actual_m2": a_exit,
                "ratio": a_exit / a_req if a_req else None,
                "verdict": ("出口偏大，气流未完全膨胀" if a_exit > a_req
                            else "出口偏小，气流过膨胀"),
            }
    else:
        res["model_B"] = {"error": "p0 <= p_inf，无法膨胀到环境压"}

    # ---- 摩擦损失敏感性（模型 B 的等熵假设有多重要）----
    length = (x_exit - 0.0) if x_exit else 0.0
    sens = []
    for tag, frac in (("等熵（默认，上界）", 0.0), ("+0.5% p0 损失", 0.005),
                      ("+1% p0 损失", 0.01), ("+2% p0 损失", 0.02)):
        p0l = p0 * (1.0 - frac) if frac else p0
        stl = state(p0l, t0, P_INF)
        stx = state(p0l, t0, ps_exit)
        if stl and stx:
            sens.append({"loss": tag, "V_exit_m_s": stx["V"], "V_expanded_m_s": stl["V"],
                         "static_thrust_n_A": mdot * stx["V"] + (ps_exit - P_INF) * a_exit,
                         "static_thrust_n_B": mdot * stl["V"]})
    res["loss_sensitivity"] = sens
    if st_exit and gap > 0 and length > 0:
        dp = duct_dp0(mdot, st_exit["rho"], st_exit["V"], length, gap)
        res["darcy"] = {"f": F_DARCY, "Dh_m": 2 * gap, "L_m": length,
                        "dp0_pa": dp, "dp0_over_p0": dp / p0 if p0 else None,
                        "source": "光滑管湍流 Moody 图 Re~1e6, f=0.018-0.02"}

    # ---- 已知答案校核：拿本案例 CFD 的真实出口状态喂模型 ----
    # 这是判断"模型对不对"的唯一硬证据。数据取自 04-solve/v2 的 .xmf 站位（v8 几何，5000 rpm）：
    #   Outlet  P0 = 102628.00 Pa  T0 = 289.4150 K  mdot = 13.48909 kg/s
    #   CFD 自己的静推力闭合 = 618.72 N（C-004 三列，已单独登记）
    # 如果模型给不出 618.72 N，那就是模型错，不是设计错。
    kn = {"mdot": 13.48909, "p0": 102628.00, "t0": 289.4150, "p_inf": P_INF}
    st_kn = state(kn["p0"], kn["t0"], kn["p_inf"])
    if st_kn:
        t_kn = kn["mdot"] * st_kn["V"]
        res["known_answer_check"] = {
            "desc": "把 CFD 的真实出口状态喂进模型 B，看能不能复现 CFD 自己算的静推力",
            "input": kn, "V_m_s": st_kn["V"], "model_thrust_n": t_kn,
            "cfd_thrust_n": 618.72, "rel_err": abs(t_kn - 618.72) / 618.72,
            "source": "04-solve/v2/n05000_p101325/thrust_closure.json（已登记）",
        }

    # ---- 交叉核验（跨血缘，只作量级参考）----
    res["cross_check"] = {
        "note": "两项都是别的几何，只作量级参考，不构成合格判据",
        "v7_5000rpm_kgf": 65.6, "v7_source": "v7 自己 CFView 逐扇区提取 58.5204*11",
        "v8_cfd_5000rpm_kgf": 63.09, "v8_source": "本轮 CFD 静推力闭合 618.72 N",
        "v8_cfd_scaled_6100rpm_kgf": 63.09 * (6100.0 / 5000.0) ** 2,
        "scale_note": "n^2 一阶外推；本算例桨尖马赫从 0.461 升到 0.563，压缩性不可忽略",
    }
    return res


def write_out(case, version, res):
    scheme = Path(case) / "01-scheme" / version
    (scheme / "thrust_1d.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8", newline="")
    rows = []
    for tag in ("model_A", "model_B"):
        m = res.get(tag) or {}
        if "static_thrust_n" in m:
            rows.append([tag, m["desc"],
                         "%.4f" % m["momentum_thrust_n"],
                         "%.4f" % m["pressure_thrust_n"],
                         "%.4f" % m["static_thrust_n"],
                         "%.4f" % m["static_thrust_kgf"]])
    with (scheme / "thrust_1d.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["模型", "说明", "动量推力_n", "压力推力_n",
                    "static_thrust_n", "static_thrust_kgf"])
        for r in rows:
            w.writerow(r)
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(prog="thrust_1d.py", description="一维整机静推力（C-004）")
    ap.add_argument("--case", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    case = Path(args.case).resolve()
    res = compute(case, args.version)
    rows = write_out(case, args.version, res)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    print("一维整机静推力（C-004 控制体口径）  " + args.version)
    print("  出口站 x=%.4f m  A=%.6f m2  mdot=%.5f kg/s"
          % (res["station"]["x_m"], res["station"]["area_m2"], res["mdot_kg_s"]))
    print("  出口 p0=%.2f Pa  ps=%.2f Pa  T0=%.3f K"
          % (res["p0_exit_pa"], res["ps_exit_pa"], res["t0_exit_k"]))
    print()
    for r in rows:
        print("  %-8s 动量 %8.2f N  压力 %8.2f N  静推力 %8.2f N = %6.2f kgf"
              % (r[0], float(r[2]), float(r[3]), float(r[4]), float(r[5])))
        print("           " + r[1])
    c = res.get("model_C")
    if c:
        print()
        print("  面积一致性：需要 %.6f m2，实际 %.6f m2（比 %.3f）-> %s"
              % (c["area_required_m2"], c["area_actual_m2"], c["ratio"], c["verdict"]))
    cc = res.get("cross_check") or {}
    if cc:
        print()
        print("  跨血缘参考（不构成判据）：v7@5000 %.1f kgf | v8 CFD@5000 %.2f kgf | n^2 外推到 6100 %.1f kgf"
              % (cc["v7_5000rpm_kgf"], cc["v8_cfd_5000rpm_kgf"],
                 cc["v8_cfd_scaled_6100rpm_kgf"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())