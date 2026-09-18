#!/usr/bin/env python3
"""v8 / AutoBlade 16.1 batch helper library.

Text-level .par editing + batch execution + GeomTurbo read-back, shared by the
v8 build and audit scripts.  No third-party dependency.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

AUTOBLADE_EXE = Path(r"D:\NUMECA_SOFTWARE\fine161\bin64\autobladex86_64.exe")

AB_BATCH_SCRIPT = """import os
par_path = r"{par}"
abp_path = r"{abp}"
geom_path = r"{geom}"
print("SCRIPT_BEGIN v8_build")
if not ab_project_create(abp_path):
    raise RuntimeError("ab_project_create failed: %s" % abp_path)
if not ab_project_load_model(par_path):
    raise RuntimeError("ab_project_load_model failed: %s" % par_path)
if not ab_model_update_all():
    raise RuntimeError("ab_model_update_all failed")
if not ab_project_save_as(abp_path):
    raise RuntimeError("ab_project_save_as failed")
export_result = ab_model_export_geomturbo(geom_path)
print("GEOMTURBO_EXPORT_RESULT %s" % export_result)
if (not export_result) and (not os.path.exists(geom_path)):
    raise RuntimeError("ab_model_export_geomturbo failed: %s" % geom_path)
print("SCRIPT_RETURN_VALUE 1")
"""

AB_REOPEN_SCRIPT = """import os
print("SCRIPT_BEGIN v8_reopen")
for project in [{projects}]:
    if not ab_project_open(project):
        raise RuntimeError("ab_project_open failed: %s" % project)
    ab_project_close()
print("SCRIPT_RETURN_VALUE 1")
"""

PARAMETER_BLOCK_RE = re.compile(r"(?P<block>\s*NI_BEGIN\s+PARAMETER\b.*?^\s*NI_END\s+PARAMETER\s*)", re.M | re.S)
PARAMETER_NAME_RE = re.compile(r"^\s*NAME\s+(?P<name>[A-Za-z0-9_]+)\s*$", re.M)


def fmt(value: float) -> str:
    return f"{value:.12g}"


def parameter_block(name: str, value: float, indent: str = "            ") -> str:
    v = fmt(value)
    return "\n".join(
        [
            f"{indent}NI_BEGIN\tPARAMETER",
            f"{indent}   NAME                           {name}",
            f"{indent}   PARAMETRIC_TYPE                DOUBLE",
            f"{indent}   LIMIT_MIN                      -1000000000",
            f"{indent}   LIMIT_MAX                      1000000000",
            f"{indent}   VALUE                          {v}",
            f"{indent}   VALUE_MIN                      {v}",
            f"{indent}   VALUE_MAX                      {v}",
            f"{indent}   VALUE_REF                      0.001",
            f"{indent}   NB_LEVELS                      +2",
            f"{indent}   QUANTITY_TYPE                  EXPRESSION",
            f"{indent}   UNCERTAIN                      FALSE",
            f"{indent}   REDUCTION                      FALSE",
            f'{indent}   EXPRESSION                     "{v}"',
            f"{indent}NI_END\tPARAMETER",
        ]
    )


def replace_curve_parameters(text: str, curve_name: str, prefix: str, points: list[tuple[float, float]],
                             limit: float = 1.0e9) -> str:
    """Rebuild a PARAM_CURVE_2D whose NAME is <curve_name> with Z/R control points."""
    pattern = re.compile(
        rf"(?P<head>\s*NI_BEGIN\s+PARAM_CURVE_2D\b.*?^\s*NAME\s+{re.escape(curve_name)}\s*$.*?^\s*NI_BEGIN\s+PARAMETERS\s*\n)"
        r"(?P<body>.*?)"
        r"(?P<tail>^\s*NI_END\s+PARAMETERS)",
        re.M | re.S,
    )

    def repl(match: re.Match[str]) -> str:
        indent_match = re.search(r"(?m)^(\s*)NUMBER_OF_PARAMETERS", match.group("body"))
        indent = indent_match.group(1) if indent_match else "            "
        lines = [f"{indent}NUMBER_OF_PARAMETERS                               +{2 * len(points)}"]
        for index, (z_value, radius) in enumerate(points, start=1):
            lines.append(parameter_block(f"{prefix}_Z{index}", z_value, indent))
            lines.append(parameter_block(f"{prefix}_R{index}", radius, indent))
        return match.group("head") + "\n".join(lines) + "\n" + match.group("tail")

    out, count = pattern.subn(repl, text, count=1)
    if count != 1:
        raise RuntimeError(f"curve block not found: {curve_name}")
    return out


def set_flat_parameter(text: str, name: str, value: float) -> str:
    """Set VALUE / VALUE_MIN / VALUE_MAX / EXPRESSION of a flat (non-block) parameter line."""
    pattern = re.compile(rf"^(?P<indent>\s*)(?P<name>{re.escape(name)})(?P<sep>\s+)(?P<rest>.*?)(?P<tail>\s*)$", re.M)

    def repl(match: re.Match[str]) -> str:
        tokens = match.group("rest").split()
        if tokens and tokens[0] in {"+0", "+1"} and len(tokens) >= 7:
            tokens[3] = fmt(value)
            tokens[4] = fmt(value)
            tokens[5] = fmt(value)
        elif tokens:
            tokens[0] = fmt(value)
        return f"{match.group('indent')}{match.group('name')}{match.group('sep')}" + "\t".join(tokens) + match.group("tail")

    out, count = pattern.subn(repl, text, count=1)
    if count != 1:
        raise RuntimeError(f"flat parameter not found: {name}")
    return out


def _rewrite_parameter_values(block: str, token: str) -> str:
    """Rewrite VALUE / VALUE_MIN / VALUE_MAX / EXPRESSION inside one PARAMETER block.

    The field separators are matched with [ \t]{2,} on purpose: \s would also match
    the newline, so "QUANTITY_TYPE   VALUE" followed by the UNCERTAIN line would be
    swallowed and the block silently corrupted.
    """
    block = re.sub(r"(VALUE[ \t]{2,})[^\n]*", lambda m: m.group(1) + token, block)
    block = re.sub(r"(VALUE_MIN[ \t]{2,})[^\n]*", lambda m: m.group(1) + token, block)
    block = re.sub(r"(VALUE_MAX[ \t]{2,})[^\n]*", lambda m: m.group(1) + token, block)
    return re.sub(r'(EXPRESSION[ \t]{2,})"[^"]*"', lambda m: m.group(1) + f'"{token}"', block)


def set_parameter_block(text: str, name: str, value: float) -> str:
    """Set VALUE / VALUE_MIN / VALUE_MAX / EXPRESSION inside the PARAMETER block named <name>."""
    token = fmt(value)
    found = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal found
        block = match.group("block")
        name_match = PARAMETER_NAME_RE.search(block)
        if not name_match or name_match.group("name") != name:
            return block
        found += 1
        block = _rewrite_parameter_values(block, token)
        return block

    out = PARAMETER_BLOCK_RE.sub(repl, text)
    if found == 0:
        raise RuntimeError(f"parameter block not found: {name}")
    return out


def set_parameter_blocks_in_order(text: str, values: list[float]) -> str:
    """Rewrite the VALUE/EXPRESSION of every PARAMETER block in document order."""
    index = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal index
        block = match.group("block")
        if index >= len(values):
            return block
        token = fmt(values[index])
        index += 1
        return _rewrite_parameter_values(block, token)

    out = PARAMETER_BLOCK_RE.sub(repl, text)
    if index != len(values):
        raise RuntimeError(f"expected {len(values)} parameter blocks, rewrote {index}")
    return out


def run_batch(work_dir: Path, tag: str, par_text: str, rename_par: str | None = None) -> dict:
    """Write <tag>.par, run AutoBlade, return status + paths + log."""
    work_dir.mkdir(parents=True, exist_ok=True)
    name = rename_par or tag
    par_path = work_dir / f"{name}.par"
    abp_path = work_dir / f"{name}.abp"
    geom_path = work_dir / f"{name}.geomTurbo"
    script_path = work_dir / f"run_{tag}.py"
    par_path.write_text(par_text, encoding="utf-8")
    script_path.write_text(
        AB_BATCH_SCRIPT.format(par=par_path.as_posix(), abp=abp_path.as_posix(), geom=geom_path.as_posix()),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [str(AUTOBLADE_EXE), "-batch", "-script", str(script_path), "-print"],
        cwd=str(work_dir), text=True, capture_output=True,
    )
    log = (completed.stdout or "") + (completed.stderr or "")
    (work_dir / f"{tag}.autoblade.log").write_text(log, encoding="utf-8")
    model_dir = work_dir / name
    return {
        "ok": (
            completed.returncode == 0
            and "SCRIPT_RETURN_VALUE 1" in log
            and "[error]" not in log.lower()
            and geom_path.exists()
            and abp_path.exists()
        ),
        "returncode": completed.returncode,
        "par": par_path,
        "abp": abp_path,
        "geom": geom_path,
        "model_dir": model_dir,
        "abm": sorted(p.name for p in model_dir.glob("model*.abm")) if model_dir.exists() else [],
        "log": log,
    }


def reopen_projects(work_dir: Path, projects: list[Path]) -> bool:
    script_path = work_dir / "reopen.py"
    joined = ", ".join(f'r"{p.as_posix()}"' for p in projects)
    script_path.write_text(AB_REOPEN_SCRIPT.format(projects=joined), encoding="utf-8")
    completed = subprocess.run(
        [str(AUTOBLADE_EXE), "-batch", "-script", str(script_path), "-print"],
        cwd=str(work_dir), text=True, capture_output=True,
    )
    log = (completed.stdout or "") + (completed.stderr or "")
    (work_dir / "reopen.autoblade.log").write_text(log, encoding="utf-8")
    return completed.returncode == 0 and "SCRIPT_RETURN_VALUE 1" in log and "[error]" not in log.lower()


def read_zr_curves(geom: Path) -> dict[str, list[tuple[float, float]]]:
    text = geom.read_text(encoding="utf-8", errors="replace")
    curves: dict[str, list[tuple[float, float]]] = {}
    for block in re.finditer(r"NI_BEGIN\s+basic_curve(.*?)NI_END\s+basic_curve", text, re.S):
        body = block.group(1)
        name = re.search(r"NAME\s+(\S+)", body).group(1)
        zr = re.search(r"ZR\s*\n\s*\+?(\d+)\s*\n(.*?)NI_END\s+zrcurve", body, re.S)
        curves[name] = [
            (float(t[0]), float(t[1]))
            for t in (line.split() for line in zr.group(2).splitlines())
            if len(t) >= 2
        ]
    return curves


def read_geomturbo_sections(geom: Path) -> dict[str, int]:
    """number of blade sections per row, as exported."""
    text = geom.read_text(encoding="utf-8", errors="replace")
    out = {}
    for m in re.finditer(r"NI_BEGIN\s+NIBLADEGEOMETRY(.*?)NI_END\s+NIBLADEGEOMETRY", text, re.S):
        body = m.group(1)
        n = re.search(r"number_of_blades\s+(\d+)", body)
        sec = re.search(r"number_of_sections\s+(\d+)", body)
        out[f"row{len(out)+1}"] = int(sec.group(1)) if sec else -1
    return out


def interp(curve: list[tuple[float, float]], z: float) -> float | None:
    for i in range(len(curve) - 1):
        z0, z1 = curve[i][0], curve[i + 1][0]
        if z0 <= z <= z1:
            if z1 == z0:
                return curve[i][1]
            w = (z - z0) / (z1 - z0)
            return curve[i][1] + w * (curve[i + 1][1] - curve[i][1])
    return None
