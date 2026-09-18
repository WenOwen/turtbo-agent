#!/usr/bin/env python3
"""v8 / main builder: v7 5-section AutoBlade model -> v8 13-section model.

Changes applied (nothing else is touched):

1. BLADE SECTION COUNT 5 -> 13
   * PRIMARY_SPAN_PARAMETERS rebuilt with 13 cosine-spaced spans;
   * DZ_PRIM / DR_PRIM / DM_PRIM rebuilt with the same 13 spans;
   * the five SECTION blocks are replaced by thirteen, whose 33+ stored
     parameters are sampled from a shape-preserving (PCHIP) interpolant through
     the v7 values in span.  Section parameters are matched POSITIONALLY because
     S#_LE_RADIUS / S#_TE_RADIUS legitimately occur twice per section (once in
     SSPS_PARAMETERS, once in the suction-side thickness B-spline).
2. HUB LINE 5 -> 10 control points (motor envelope 84 mm x 0.188 m, contraction).
3. LEAN / SWEEP adjusted through the two "simple Bezier" (BEZIER_BETA) laws:
   LEAN_BETA (tangential / 弯) and SWEEP_BETA (meridional / 掠).
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v8_ab_lib as ab  # noqa: E402

V7 = Path(r"D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v7\autoblade")
OUT_DIR = Path(r"D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v8\automation\build-par")
EXTRACT = Path(r"D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v8\automation\v7_extract.json")

SECTION_RE = re.compile(r"(?P<section>\s*NI_BEGIN\s+SECTION\s+(?P<index>\d+)\b.*?^\s*NI_END\s+SECTION\s+(?P=index)\s*)", re.M | re.S)
PRIMARY_SPAN_RE = re.compile(r"(?P<head>\s*NI_BEGIN\s+PRIMARY_SPAN_PARAMETERS\s*\n)(?P<body>.*?)(?P<tail>^\s*NI_END\s+PRIMARY_SPAN_PARAMETERS)", re.M | re.S)

# ---------------------------------------------------------------- hub table --
# Selected from the AutoBlade oracle sweeps (v8_hub_oracle*.py): this pair keeps
# the exported hub curve flat at r = 0.094 m over the 84 mm motor window to
# 0.6 um (bore 188.000 +- 0.001 mm) while holding the outlet hub slope to ~23 deg.
AFT_Z = [0.188, 0.212, 0.234, 0.262, 0.300]
AFT_P = 3.2
R_MOTOR, Z4, Z5, R_OUT = 0.094, 0.080, 0.164, 0.125167
HUB_POINTS: list[tuple[float, float]] = [
    (0.000, R_MOTOR),
    (0.020, R_MOTOR),
    (0.050, R_MOTOR),
    (Z4, R_MOTOR),
    (Z5, R_MOTOR),
] + [(z, R_MOTOR + (R_OUT - R_MOTOR) * (k / 5.0) ** AFT_P) for k, z in enumerate(AFT_Z, 1)]

# simple-Bezier stacking angles: 弯 (lean, tangential) and 掠 (sweep, meridional)
LEAN_BETA_NEW = 1.5
SWEEP_BETA_NEW = 1.0


def cosine_spans(count: int) -> list[float]:
    return [0.5 * (1.0 - math.cos(i * math.pi / (count - 1))) for i in range(count)]


# ------------------------------------------------------------- interpolation --
def pchip_slopes(xs: list[float], ys: list[float]) -> list[float]:
    n = len(xs)
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    delta = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]
    d = [0.0] * n
    for i in range(1, n - 1):
        if delta[i - 1] * delta[i] > 0.0:
            w1 = 2 * h[i] + h[i - 1]
            w2 = h[i] + 2 * h[i - 1]
            d[i] = (w1 + w2) / (w1 / delta[i - 1] + w2 / delta[i])
        else:
            d[i] = 0.0
    # scipy-compatible shape-preserving end slopes
    def edge(h0, h1, d0, d1):
        v = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1)
        if v * d0 <= 0:
            return 0.0
        if d0 * d1 < 0 and abs(v) > abs(3 * d0):
            return 3 * d0
        return v

    d[0] = edge(h[0], h[1], delta[0], delta[1])
    d[-1] = edge(h[-1], h[-2], delta[-1], delta[-2])
    return d


class Pchip:
    def __init__(self, xs: list[float], ys: list[float]):
        self.x, self.y = xs, ys
        self.h = [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
        self.d = pchip_slopes(xs, ys)

    def __call__(self, x: float) -> float:
        xs, ys, h, d = self.x, self.y, self.h, self.d
        n = len(xs)
        if x <= xs[0]:
            return ys[0]
        if x >= xs[-1]:
            return ys[-1]
        i = max(j for j in range(n - 1) if xs[j] <= x)
        t = (x - xs[i]) / h[i]
        t2, t3 = t * t, t * t * t
        return (
            (2 * t3 - 3 * t2 + 1) * ys[i]
            + (t3 - 2 * t2 + t) * h[i] * d[i]
            + (-2 * t3 + 3 * t2) * ys[i + 1]
            + (t3 - t2) * h[i] * d[i + 1]
        )


# ------------------------------------------------------------------ builders --
def expand_primary_spans(text: str, spans: list[float]) -> str:
    def repl(match: re.Match[str]) -> str:
        indent_match = re.search(r"(?m)^(\s*)NUMBER_OF_PARAMETERS", match.group("body"))
        indent = indent_match.group(1) if indent_match else "         "
        lines = [f"{indent}NUMBER_OF_PARAMETERS                               +{len(spans)}"]
        for index, span in enumerate(spans, 1):
            lines.append(ab.parameter_block(f"S{index}_SPAN", span, indent))
        return match.group("head") + "\n".join(lines) + "\n" + match.group("tail")

    out, count = PRIMARY_SPAN_RE.subn(repl, text, count=1)
    if count != 1:
        raise RuntimeError("PRIMARY_SPAN_PARAMETERS block not found")
    return out


def expand_prim_container(text: str, container: str, values: list[float], suffix: str) -> str:
    pattern = re.compile(
        rf"(?P<head>\s*NI_BEGIN\s+{re.escape(container)}\s*\n)(?P<body>.*?)(?P<tail>^\s*NI_END\s+{re.escape(container)})",
        re.M | re.S,
    )

    def repl(match: re.Match[str]) -> str:
        indent_match = re.search(r"(?m)^(\s*)NUMBER_OF_PARAMETERS", match.group("body"))
        indent = indent_match.group(1) if indent_match else "            "
        lines = [f"{indent}NUMBER_OF_PARAMETERS                               +{len(values)}"]
        for index, value in enumerate(values, 1):
            lines.append(ab.parameter_block(f"S{index}_{suffix}", value, indent))
        return match.group("head") + "\n".join(lines) + "\n" + match.group("tail")

    out, count = pattern.subn(repl, text, count=1)
    if count != 1:
        raise RuntimeError(f"{container} container not found")
    return out


def section_blocks(text: str) -> list[re.Match[str]]:
    return list(SECTION_RE.finditer(text))


def ordered_parameters(section_text: str) -> list[tuple[str, float]]:
    out = []
    for match in ab.PARAMETER_BLOCK_RE.finditer(section_text):
        block = match.group("block")
        name = ab.PARAMETER_NAME_RE.search(block)
        value = re.search(r"^\s*VALUE\s+(\S+)\s*$", block, re.M)
        out.append((name.group("name"), float(value.group(1))))
    return out


def expand_sections(text: str, spans: list[float]) -> tuple[str, list[list[str]]]:
    matches = section_blocks(text)
    if len(matches) != 5:
        raise RuntimeError(f"expected 5 SECTION blocks, found {len(matches)}")
    templates = [m.group("section") for m in matches]
    first_params = ordered_parameters(templates[0])
    names_norm = [re.sub(r"^S\d+_", "", n) for n, _ in first_params]
    table: list[list[float]] = [[] for _ in first_params]
    for sample, block in enumerate(templates):
        params = ordered_parameters(block)
        if [re.sub(r"^S\d+_", "", n) for n, _ in params] != names_norm:
            raise RuntimeError(f"SECTION {sample + 1} parameter layout differs from SECTION 1")
        for j, (_, value) in enumerate(params):
            table[j].append(value)

    interpolants = [Pchip([0.0, 0.25, 0.5, 0.75, 1.0], row) for row in table]
    new_blocks = []
    for index, span in enumerate(spans, 1):
        block = templates[0]
        block = re.sub(r"NI_BEGIN(\s+)SECTION(\s+)1\b", lambda m: f"NI_BEGIN{m.group(1)}SECTION{m.group(2)}{index}", block)
        block = re.sub(r"NI_END(\s+)SECTION(\s+)1\b", lambda m: f"NI_END{m.group(1)}SECTION{m.group(2)}{index}", block)
        block = re.sub(r"\bS1_", f"S{index}_", block)
        values = [interp(span) for interp in interpolants]
        block = ab.set_parameter_blocks_in_order(block, values)
        new_blocks.append(block.rstrip() + "\n")

    head = text[: matches[0].start()]
    tail = text[matches[-1].end():]
    while head.endswith("\n\n"):
        head = head[:-1]
    body = "\n".join(block.rstrip("\n") for block in new_blocks)
    return head + body + "\n" + tail, names_norm


def normalize_number_of_parameters(text: str) -> str:
    out: list[str] = []
    stack: list[dict] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("NI_BEGIN"):
            tokens = stripped.split()
            tag = tokens[1] if len(tokens) > 1 else ""
            if tag == "PARAMETER" and stack:
                # every PARAMETER block belongs to its direct parent container,
                # whatever that container is called (PARAMETERS, SSPS_PARAMETERS,
                # CT_PARAMETERS, DZ_PRIM, EDGE_LOCATIONS, ...)
                stack[-1]["count"] += 1
            stack.append({"tag": tag, "count": 0, "count_line": None})
        elif stripped.startswith("NI_END"):
            if stack:
                top = stack.pop()
                if top["count_line"] is not None:
                    out[top["count_line"]] = re.sub(
                        r"(NUMBER_OF_PARAMETERS\s+)\+\d+", rf"\g<1>+{top['count']}", out[top["count_line"]]
                    )
        elif stack:
            match = re.match(r"NUMBER_OF_PARAMETERS\s+\+?(\d+)", stripped)
            if match:
                stack[-1]["count_line"] = len(out)
                stack[-1]["count"] = 0
        out.append(line)
    return "\n".join(out)


def build_row(label: str, source: Path, spans: list[float]) -> str:
    text = source.read_text(encoding="utf-8")
    text = ab.replace_curve_parameters(text, "HUB_CURVE", "HUB", HUB_POINTS)
    text = expand_primary_spans(text, spans)
    for container, suffix in (("DZ_PRIM", "DZ_PRIM"), ("DR_PRIM", "DR_PRIM"), ("DM_PRIM", "DM_PRIM")):
        block = re.search(
            rf"NI_BEGIN\s+{container}\s*\n(?P<body>.*?)^\s*NI_END\s+{container}",
            text, re.M | re.S,
        )
        values = [float(v) for v in re.findall(r"^\s*VALUE\s+(\S+)\s*$", block.group("body"), re.M)]
        if len(values) != 5:
            raise RuntimeError(f"{container}: expected 5 values, found {len(values)}")
        interp = Pchip([0.0, 0.25, 0.5, 0.75, 1.0], values)
        text = expand_prim_container(text, container, [interp(s) for s in spans], suffix)
    text, names = expand_sections(text, spans)
    text = ab.set_parameter_block(text, "LEAN_BETA", LEAN_BETA_NEW)
    text = ab.set_parameter_block(text, "SWEEP_BETA", SWEEP_BETA_NEW)
    # GeomTurbo chirality.  v7's delivered R1.geomTurbo wraps negatively at the
    # rotor (R2 positively), which is only reproducible with REVERSE_THETA = 0:
    # re-running the untouched v7 R1.par with its stored "+1" mirrors the rotor.
    # v8 therefore stores the value that actually reproduces the delivered
    # rotor/stator relative direction (see v8_chirality.py evidence).
    text = ab.set_flat_parameter(text, "REVERSE_THETA", 0)
    text = normalize_number_of_parameters(text)
    print(f"  {label}: {len(ordered_parameters(section_blocks(text)[0].group('section')))} parameter blocks/section, "
          f"{len(section_blocks(text))} sections")
    return text


def main() -> int:
    spans = cosine_spans(13)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("hub control points:")
    for index, (z, r) in enumerate(HUB_POINTS, 1):
        print(f"  P{index:<2d} z={z:.6f}  r={r:.6f}  D={2 * r * 1000:.3f} mm")
    print(f"  |P5-P4| = {math.hypot(HUB_POINTS[4][0]-HUB_POINTS[3][0], HUB_POINTS[4][1]-HUB_POINTS[3][1]) * 1000:.4f} mm")
    print("13 span stations:", ", ".join(f"{s:.6f}" for s in spans))
    print(f"lean (弯) LEAN_BETA = {LEAN_BETA_NEW} deg, sweep (掠) SWEEP_BETA = {SWEEP_BETA_NEW} deg")
    for label, relative in (("R1", r"R1_5span\R1.par"), ("R2", r"R2_5span\R2.par")):
        print(f"building {label}")
        text = build_row(label, V7 / relative, spans)
        (OUT_DIR / f"{label}.par").write_text(text, encoding="utf-8")
    (OUT_DIR / "v8_build_manifest.json").write_text(
        json.dumps(
            {
                "spans": spans,
                "hub_points": HUB_POINTS,
                "lean_beta_deg": LEAN_BETA_NEW,
                "sweep_beta_deg": SWEEP_BETA_NEW,
                "sections": 13,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    print("written to", OUT_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
