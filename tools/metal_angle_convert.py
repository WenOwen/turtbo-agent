#!/usr/bin/env python3
"""metal_angle_convert.py - 把一维方案的金属角展开成 AutoBlade 的 CAMBER_BETA 序列。

为什么要这个
----------
G3 的判据 G3-9 问的是「这套几何能不能由参数表导出」。
`01-scheme/v3` 的**流道**已经能导出了（逐点偏差 0.0061 mm），但**叶片不能** ——
因为 turbo-flow 的一维平均线**每排只给一个金属角**（中径处），
而 AutoBlade 的 `.par` 要的是**逐截面**的 `S#_CAMBER_BETA1` / `S#_CAMBER_BETA2`。

两边是不是同一个约定？**是**（2026-09-20 实测确认）：

  turbo-flow:  metal_angle = atan2(Wtheta, Vm)      losses.py:10-11
               Wtheta = Ctheta - U（转子）/ Ctheta（静子）   meanline.py:412-416
               截断 ±85 度（models.py:145-146 的 Field(ge=-85, le=85)）

  AutoBlade:   S#_CAMBER_BETA1 / BETA2 = 中弧线前后缘切线角，
               在 (z, s) 平面里**从轴向量起**，正方向朝 + 周向

  **实测证据**（不是推断）：把 v8 的 `.par` 逐截面值与从 `geomTurbo` 反算的中弧线
  前后缘切线角对比 —— R1 的 BETA2 差 -2.19 度（叶根）单调衰减到 +0.04 度（叶尖）；
  同一份 `.par` 的 `CAMBER_GAMMA` 与几何实测安装角在叶尖差 0.0000 度。
  残差沿展向单调衰减 = 反算方法的截断误差，不是约定差（约定差会是常数或反号）。

  **所以参考方向与符号都不需要换算**，直接对应。

缺的那一块是**展向分布**
----------------------
`result.json` 里 `metal_angle_in_profile` / `metal_angle_out_profile` **全是空数组** ——
turbo-flow 的一维平均线本来就只给中径一个值，没有展向分布。
所以从一维到几何，展向律是**设计选择**，不是数据。这个脚本把它显式化：

  --law free      自由涡   r*Ctheta = const      （本项目 vortex_law: free）
  --law linear    线性     Ctheta ∝ r
  --law constant  等环量   Ctheta = const

另一个假设：**Vm 沿展向取常数**（圆柱面假设）。真值要三维才算得出来。

用法
----
  python tools/metal_angle_convert.py --case cases/DF90-001 --scheme v3 --row R1
  python tools/metal_angle_convert.py --case cases/DF90-001 --scheme v3 --row R1 --law linear --json
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

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_PRECONDITION = 3


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


def cosine_spans(n):
    """余弦展向律：叶根叶尖加密。与 v8 那套 13 截面的分布一致。"""
    if n < 2:
        return [0.0]
    return [0.5 * (1.0 - math.cos(math.pi * i / (n - 1))) for i in range(n)]


def find_result(scheme: Path):
    """找这一版方案唯一的 result.json。多份就拒绝 —— 和 G2-7 同一个理由。"""
    cands = sorted(p for p in scheme.rglob("result.json") if p.is_file())
    if len(cands) != 1:
        raise SystemExit("★ %s 下有 %d 份 result.json，必须唯一：%s"
                         % (scheme, len(cands), [p.name for p in cands]))
    return cands[0]


def annulus_at(annulus_rows, x):
    """在流道尺寸表上按轴向坐标线性插值出 hub / tip。"""
    pts = []
    for a in annulus_rows:
        z = fnum(a.get("轴向坐标(m)"))
        h = fnum(a.get("轮毂半径(m)"))
        t = fnum(a.get("机匣半径(m)"))
        if z is not None and h is not None and t is not None:
            pts.append((z, h, t))
    if not pts:
        return None, None
    pts.sort()
    if x <= pts[0][0]:
        return pts[0][1], pts[0][2]
    if x >= pts[-1][0]:
        return pts[-1][1], pts[-1][2]
    for i in range(len(pts) - 1):
        z0, h0, t0 = pts[i]
        z1, h1, t1 = pts[i + 1]
        if z0 <= x <= z1:
            f = (x - z0) / (z1 - z0) if z1 > z0 else 0.0
            return h0 + (h1 - h0) * f, t0 + (t1 - t0) * f
    return pts[-1][1], pts[-1][2]


def ct_at(r, r_mean, ct_mean, law):
    """按展向律把中径的切向速度铺到半径 r 上。"""
    if law == "free":
        return ct_mean * r_mean / r
    if law == "linear":
        return ct_mean * r / r_mean
    return ct_mean


def build(case: Path, scheme_name, row_name, n_sections, law):
    scheme = case / "01-scheme" / scheme_name
    if not scheme.is_dir():
        raise SystemExit("★ 找不到方案目录：" + str(scheme))
    row = next((r for r in read_csv(scheme / "叶片几何参数表.csv")
                if r.get("叶排") == row_name), None)
    if row is None:
        raise SystemExit("★ 参数表里没有叶排 " + row_name)
    annulus = read_csv(scheme / "流道尺寸表.csv")
    res = json.loads(find_result(scheme).read_text(encoding="utf-8-sig"))

    rows = res.get("metadata", {}).get("generated_rows") or []
    order = [r.get("id") for r in rows]
    if row_name not in order:
        raise SystemExit("★ result.json 的叶排是 %s，没有 %s" % (order, row_name))
    k = order.index(row_name)
    sts = res.get("stations") or []
    if len(sts) < k + 2:
        raise SystemExit("★ result.json 站位不足：%d 个，需要到第 %d 个" % (len(sts), k + 2))
    before, after = sts[k], sts[k + 1]

    rpm = (res.get("summary") or {}).get("rpm")
    if not rpm:
        raise SystemExit("★ result.json 里没有 rpm")
    omega = 2.0 * math.pi * float(rpm) / 60.0
    is_rotor = (row.get("类型") or "").strip() == "rotor"

    vm_m = fnum(before.get("meridional_velocity_m_s"))
    ct1_m = fnum(before.get("tangential_velocity_m_s")) or 0.0
    r1_m = fnum(before.get("mean_radius_m"))
    vm2_m = fnum(after.get("meridional_velocity_m_s"))
    ct2_m = fnum(after.get("tangential_velocity_m_s")) or 0.0
    r2_m = fnum(after.get("mean_radius_m"))
    if None in (vm_m, r1_m, vm2_m, r2_m):
        raise SystemExit("★ result.json 的站位缺 Vm / 中径")

    # deviation：与 turbo-flow meanline.py:414 同一式
    a1_m = math.degrees(math.atan2(ct1_m - (omega * r1_m if is_rotor else 0.0), vm_m))
    a2_m = math.degrees(math.atan2(ct2_m - (omega * r2_m if is_rotor else 0.0), vm2_m))
    dev_base = 2.0
    deviation = -math.copysign(abs(dev_base), a2_m - a1_m)
    # 表里的单值是在**各自站位的中径**上算的：beta1 用进口中径、beta2 用出口中径。
    # 自校核必须比这个，不能比"序列均值" —— 均值里混了展向分布，比出来的差没有意义。
    ref_b1 = a1_m
    ref_b2 = a2_m - deviation

    x_row = fnum(row.get("轴向坐标(m)")) or 0.0
    hub, tip = annulus_at(annulus, x_row)
    if hub is None:
        raise SystemExit("★ 流道尺寸表读不出 hub / tip")

    secs = []
    for sp in cosine_spans(n_sections):
        r = hub + (tip - hub) * sp
        u = omega * r if is_rotor else 0.0
        b1 = math.degrees(math.atan2(ct_at(r, r1_m, ct1_m, law) - u, vm_m))
        b2 = math.degrees(math.atan2(ct_at(r, r2_m, ct2_m, law) - u, vm2_m)) - deviation
        b1 = max(-85.0, min(85.0, b1))
        b2 = max(-85.0, min(85.0, b2))
        secs.append({"span_fraction": round(sp, 10), "radius_m": round(r, 10),
                     "CAMBER_GAMMA_approx_deg": round(0.5 * (b1 + b2), 4),
                     "CAMBER_BETA1_deg": round(b1, 4),
                     "CAMBER_BETA2_deg": round(b2, 4),
                     "blade_speed_m_s": round(u, 4)})

    table_b1 = fnum(row.get("进口金属角(deg,相对轴向)"))
    table_b2 = fnum(row.get("出口金属角(deg,相对轴向)"))
    mid = secs[len(secs) // 2] if len(secs) % 2 else None
    return {
        "row": row_name, "row_type": row.get("类型"), "rotor": is_rotor,
        "sections_used": n_sections, "vortex_law": law,
        "rpm": rpm, "omega_rad_s": round(omega, 6),
        "hub_r": hub, "tip_r": tip, "x_row_m": x_row,
        "mean_radius_in_m": r1_m, "mean_radius_out_m": r2_m,
        "deviation_deg": round(deviation, 6),
        "table_beta1_deg": table_b1, "table_beta2_deg": table_b2,
        "ref_beta1_deg": round(ref_b1, 4), "ref_beta2_deg": round(ref_b2, 4),
        "ref_beta1_gap_deg": (round(ref_b1 - table_b1, 4) if table_b1 is not None else None),
        "ref_beta2_gap_deg": (round(ref_b2 - table_b2, 4) if table_b2 is not None else None),
        "mid_section": mid,
        "sections": secs,
        "assumptions": [
            "Vm 沿展向取常数（圆柱面假设）—— 真值要三维才算得出来",
            "展向律 %s 是设计选择，不是数据；result.json 的 metal_angle_*_profile 是空数组" % law,
            "CAMBER_GAMMA 用 (BETA1+BETA2)/2 近似 —— 中弧线弯曲时它不是严格解",
            "deviation 固定 2.0 度，与 turbo-flow 的 deviation_base_deg 默认值一致",
        ],
    }


def render(out):
    L = []
    L.append("%s（%s）展向金属角 —— 由 %s 展向律展开 %d 个截面"
             % (out["row"], out["row_type"], out["vortex_law"], out["sections_used"]))
    L.append("  rpm=%.1f  hub=%.4f  tip=%.4f  中径 进口 %.4f / 出口 %.4f  deviation=%+.2f"
             % (out["rpm"], out["hub_r"], out["tip_r"], out["mean_radius_in_m"],
                out["mean_radius_out_m"], out["deviation_deg"]))
    L.append("")
    L.append("  span      r(m)   BETA1      BETA2     GAMMA(近似)   U(m/s)")
    for s in out["sections"]:
        L.append("  %-7.4f  %-7.4f  %-9.3f  %-9.3f  %-11.3f  %-.2f"
                 % (s["span_fraction"], s["radius_m"], s["CAMBER_BETA1_deg"],
                    s["CAMBER_BETA2_deg"], s["CAMBER_GAMMA_approx_deg"],
                    s["blade_speed_m_s"]))
    L.append("")
    L.append("  自校核（在各自站位的中径上重算，与参数表的单值对）：")
    L.append("    BETA1  表 %-10.3f  重算 %-10.3f  差 %+.3f 度"
             % (out["table_beta1_deg"], out["ref_beta1_deg"], out["ref_beta1_gap_deg"]))
    L.append("    BETA2  表 %-10.3f  重算 %-10.3f  差 %+.3f 度"
             % (out["table_beta2_deg"], out["ref_beta2_deg"], out["ref_beta2_gap_deg"]))
    L.append("    （差不为 0 是 turbo-flow 内部用值与 reported 站位的残差，不是约定差）")
    L.append("")
    L.append("  这一版是模型，不是数据。假设：")
    for a in out["assumptions"]:
        L.append("    - " + a)
    return chr(10).join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="metal_angle_convert.py",
                                 description="一维金属角 -> AutoBlade CAMBER_BETA 序列")
    ap.add_argument("--case", required=True)
    ap.add_argument("--scheme", default="v1")
    ap.add_argument("--row", required=True)
    ap.add_argument("--sections", type=int, default=13)
    ap.add_argument("--law", default="free", choices=["free", "linear", "constant"])
    ap.add_argument("--out")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    case = Path(args.case).resolve()
    if not case.is_dir():
        print("★ 案例目录不存在：" + str(case), file=sys.stderr)
        return EXIT_PRECONDITION
    out = build(case, args.scheme, args.row, args.sections, args.law)
    text = render(out) if not args.json else json.dumps(out, ensure_ascii=False, indent=2)
    if args.out:
        p = Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text + chr(10), encoding="utf-8", newline="")
        print("已写入 " + str(p))
    else:
        print(text)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())