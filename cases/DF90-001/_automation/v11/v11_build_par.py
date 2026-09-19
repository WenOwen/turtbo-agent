"""v11_build_par.py - 由 01-scheme/v4 造几何 v11：叶片金属角真正来自参数表。

与 v10 的区别（v10 建出来了，但导出的几何与 v9 逐字节相同）：
  v10 只改 VALUE，而 ab_model_update_all() 会按 EXPRESSION 重算 —— 徒劳。
  v10 的替换窗口是 12 行，而 EXPRESSION 在 NAME 之后第 12 行，恰好被挡在窗口外。
  v11 改用 tools/autoblade_par.py（WINDOW=20，同时改 VALUE 与 EXPRESSION）。

展向律：--law linear（30.9 度扭转，最接近已验证的 v8 叶片的 36.0 度）。
free 是 92.4 度、constant 是 47.1 度。**这是待用户确认的默认选择。**
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASE = HERE.parents[1]
ROOT = CASE.parents[1]

sys.path.insert(0, str(CASE / "_automation" / "v8"))
sys.path.insert(0, str(ROOT / "tools"))
import v8_ab_lib as ab  # noqa: E402
import metal_angle_convert as mac  # noqa: E402
import autoblade_par as abp  # noqa: E402

V8_AB = CASE / "02-geometry" / "v8" / "autoblade"
OUT = CASE / "02-geometry" / "v11" / "autoblade"
SCHEME = "v4"
LAW = "linear"

HUB = [(0.000, 0.080000), (0.050, 0.086000), (0.095, 0.094500),
       (0.185, 0.095800), (0.230, 0.098500), (0.300, 0.113200)]
SHROUD = [(0.000, 0.300000), (0.300, 0.300000)]
ROWS = (("R1", "R1", "R1_13span/R1.par"), ("R2", "S1", "R2_13span/R2.par"))


def build_row(source: Path, sections):
    text = source.read_text(encoding="utf-8")
    text = ab.replace_curve_parameters(text, "HUB_CURVE", "HUB", HUB)
    text = ab.replace_curve_parameters(text, "TIP_CURVE", "SHROUD", SHROUD)
    text, changed = abp.set_spanwise_betas(text, sections)
    return text, changed


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    report = {"scheme": SCHEME, "law": LAW, "hub_points": HUB, "shroud_points": SHROUD,
              "rows": {}, "converter_assumptions": None,
              "law_note": "linear 是待用户确认的默认选择，见 PLAN.md 的展向律对比"}
    for label, scheme_row, rel in ROWS:
        print("converting %s (参数表叶排 %s)" % (label, scheme_row))
        conv = mac.build(CASE, SCHEME, scheme_row, 13, LAW)
        report["converter_assumptions"] = conv.get("assumptions")
        r = report["rows"].setdefault(label, {})
        r["table_beta1"] = conv.get("table_beta1_deg")
        r["table_beta2"] = conv.get("table_beta2_deg")
        r["ref_gap_beta1"] = conv.get("ref_beta1_gap_deg")
        r["ref_gap_beta2"] = conv.get("ref_beta2_gap_deg")
        r["mid"] = conv.get("mid_section")
        text, changed = build_row(V8_AB / rel.replace("/", chr(92)), conv["sections"])
        work = OUT / ("%s_13span" % label)
        result = ab.run_batch(work, label, text)
        r.update({"ok": result["ok"], "changes": changed,
                  "par": str(result["par"]), "geomTurbo": str(result["geom"]),
                  "geom_bytes": result["geom"].stat().st_size if result["geom"].is_file() else 0,
                  "abm": result["abm"]})
        print("  ok=%s changes=%d geom=%d B" % (result["ok"], changed, r["geom_bytes"]))
        if not result["ok"]:
            print(chr(10).join(result["log"].splitlines()[-25:]))
    (OUT.parent / "v11_build_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("written to", OUT)
    return 0 if all(v["ok"] for v in report["rows"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())