"""v10_build_par.py - 由 01-scheme/v4 造几何 v10：叶片金属角真正来自参数表。

与 v9 的区别：v9 只换流道，叶片原样照抄 v8（来自 v7 的 AutoBlade，血缘是 AxSTREAM）。
v10 额外把 S<N>_CAMBER_BETA1/2 换成由 v4 参数表展开的展向分布。

展向律：--law free（自由涡 r*Cth = const）。
理由：v4 的输入 JSON 里 vortex_law 就是 free，这是上游的设计选择，保持一致。
**但这是设计选择不是数据**，转换器的 assumptions 一并保留进 manifest。
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASE = HERE.parents[1]
ROOT = CASE.parents[1]

sys.path.insert(0, str(CASE / "_automation" / "v8"))
sys.path.insert(0, str(ROOT / "tools"))
import v8_ab_lib as ab  # noqa: E402
import metal_angle_convert as mac  # noqa: E402

V8_AB = CASE / "02-geometry" / "v8" / "autoblade"
OUT = CASE / "02-geometry" / "v10" / "autoblade"
SCHEME = "v4"
LAW = "free"

# 01-scheme/v4 的流道（与 v3 相同：6 个控制点 + 机匣 0.300）
HUB = [(0.000, 0.080000), (0.050, 0.086000), (0.095, 0.094500),
       (0.185, 0.095800), (0.230, 0.098500), (0.300, 0.113200)]
SHROUD = [(0.000, 0.300000), (0.300, 0.300000)]

# (几何标签, 参数表叶排名, .par 相对路径)
# **参数表里静子叫 S1，几何文件却叫 R2** —— 名字不同，必须显式对上。
# 依据：01-scheme/v4 参数表 R1=9叶 / S1=11叶；几何 R1=周期9 / R2=周期11。
ROWS = (("R1", "R1", "R1_13span/R1.par"), ("R2", "S1", "R2_13span/R2.par"))


def replace_parameter(text: str, pname: str, value: float) -> tuple[str, int]:
    """把 NAME <pname> 那个 PARAMETER 块里的 VALUE/VALUE_MIN/VALUE_MAX 换掉。

    实测结构（v8 R1.par）：
        NI_BEGIN   PARAMETER
           NAME       S1_CAMBER_BETA1
           ...
           VALUE      -56.0714853487
           VALUE_MIN  -56.0714853487
           VALUE_MAX  -56.0714853487
    """
    lines = text.splitlines(keepends=True)
    n = 0
    for i, ln in enumerate(lines):
        if not re.match(r"\s*NAME\s+" + re.escape(pname) + r"\s*$", ln.rstrip(chr(13))):
            continue
        for j in range(i + 1, min(i + 12, len(lines))):
            m = re.match(r"(\s*)(VALUE(?:_MIN|_MAX)?)(\s+)([-+0-9.eE]+)(\s*)$",
                         lines[j].rstrip(chr(13)))
            if m:
                eol = chr(10) if lines[j].endswith(chr(10)) else ""
                lines[j] = "%s%s%s%.6f%s" % (m.group(1), m.group(2), m.group(3), value, eol)
                n += 1
        break
    return "".join(lines), n


def build_row(label: str, source: Path, sections):
    text = source.read_text(encoding="utf-8")
    text = ab.replace_curve_parameters(text, "HUB_CURVE", "HUB", HUB)
    text = ab.replace_curve_parameters(text, "TIP_CURVE", "SHROUD", SHROUD)
    changed = 0
    for s in sections:
        idx = int(round(s["span_fraction"] * (len(sections) - 1))) + 1
        for key, val in (("CAMBER_BETA1", s["CAMBER_BETA1_deg"]),
                         ("CAMBER_BETA2", s["CAMBER_BETA2_deg"])):
            text, n = replace_parameter(text, "S%d_%s" % (idx, key), val)
            changed += n
    print("  %s: 换掉 %d 个 VALUE（%d 截面 x 2 角 x 3 行）" % (label, changed, len(sections)))
    return text, changed


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    report = {"scheme": SCHEME, "law": LAW, "hub_points": HUB, "shroud_points": SHROUD,
              "rows": {}, "converter_assumptions": None}
    for label, scheme_row, rel in ROWS:
        print("converting %s (参数表叶排 %s)" % (label, scheme_row))
        conv = mac.build(CASE, SCHEME, scheme_row, 13, LAW)
        report["converter_assumptions"] = conv.get("assumptions")
        report["rows"].setdefault(label, {})["table_beta1"] = conv.get("table_beta1_deg")
        report["rows"][label]["table_beta2"] = conv.get("table_beta2_deg")
        report["rows"][label]["ref_gap_beta1"] = conv.get("ref_beta1_gap_deg")
        report["rows"][label]["ref_gap_beta2"] = conv.get("ref_beta2_gap_deg")
        report["rows"][label]["mid"] = conv.get("mid_section")
        print("  table b1=%.3f b2=%.3f  mid b1=%.3f b2=%.3f" % (
            conv["table_beta1_deg"], conv["table_beta2_deg"],
            conv["mid_section"]["CAMBER_BETA1_deg"], conv["mid_section"]["CAMBER_BETA2_deg"]))
        text, changed = build_row(label, V8_AB / rel.replace("/", "\\"), conv["sections"])
        work = OUT / ("%s_13span" % label)
        result = ab.run_batch(work, label, text)
        report["rows"][label].update({
            "ok": result["ok"], "values_changed": changed,
            "par": str(result["par"]), "geomTurbo": str(result["geom"]),
            "geom_bytes": result["geom"].stat().st_size if result["geom"].is_file() else 0,
            "abm": result["abm"],
        })
        print("  ok=%s geom=%d B" % (result["ok"], report["rows"][label]["geom_bytes"]))
        if not result["ok"]:
            print(chr(10).join(result["log"].splitlines()[-25:]))
    (OUT.parent / "v10_build_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("written to", OUT)
    return 0 if all(v["ok"] for v in report["rows"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())