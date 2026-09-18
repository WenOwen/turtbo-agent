#!/usr/bin/env python3
"""v8 / step 1: extract the full parameter set of the v7 AutoBlade .par files.

Reads  run/90kg-duct-fan-v7/autoblade/{R1_5span/R1.par, R2_5span/R2.par}
Writes run/90kg-duct-fan-v8/automation/v7_extract.json

No AutoBlade call, no geometry write: pure text extraction so the v8 rebuild
starts from auditable numbers instead of hand-copied tables.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

V7 = Path(r"D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v7\autoblade")
OUT = Path(r"D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v8\automation\v7_extract.json")

BEGIN = re.compile(r"^\s*NI_BEGIN\s+(\S+)(?:\s+(.*?))?\s*$")
END = re.compile(r"^\s*NI_END\s+(\S+)")
SCALAR = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s\s+(.*?)\s*$")


def parse_tree(path: Path) -> dict:
    root = {"tag": "ROOT", "arg": "", "scalars": [], "children": [], "line": 0}
    stack = [root]
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        m = BEGIN.match(raw)
        if m:
            node = {
                "tag": m.group(1),
                "arg": (m.group(2) or "").strip(),
                "scalars": [],
                "children": [],
                "line": lineno,
            }
            stack[-1]["children"].append(node)
            stack.append(node)
            continue
        if END.match(raw):
            stack.pop()
            continue
        m = SCALAR.match(raw)
        if m:
            stack[-1]["scalars"].append([m.group(1), m.group(2)])
    return root


def find_all(node: dict, tag: str) -> list[dict]:
    out = []
    if node["tag"] == tag:
        out.append(node)
    for child in node["children"]:
        out.extend(find_all(child, tag))
    return out


def find_one(node: dict, tag: str, arg: str | None = None) -> dict | None:
    for candidate in find_all(node, tag):
        if arg is None or candidate.get("arg", "") == arg:
            return candidate
    return None


def scalars(node: dict) -> dict:
    return {k: v for k, v in node["scalars"]}


def param_values(node: dict) -> dict:
    """name -> {value, expression} for every PARAMETER block under node (recursive)."""
    out = {}
    for child in find_all(node, "PARAMETER"):
        sc = scalars(child)
        name = sc.get("NAME")
        if name:
            out[name] = {"value": sc.get("VALUE"), "expression": sc.get("EXPRESSION")}
    return out


def curve(node: dict) -> dict:
    return {
        "tag": node["tag"],
        "scalars": scalars(node),
        "params": param_values(node),
    }


def extract(par_path: Path) -> dict:
    root = parse_tree(par_path)
    endwalls = find_one(root, "ENDWALLS")
    hub = find_one(endwalls, "PARAM_CURVE_2D")
    shroud = [c for c in endwalls["children"] if c["tag"] == "PARAM_CURVE_2D"][1]
    stream = find_one(root, "STREAM_SURFACES")
    merid = find_one(root, "MERIDIONAL_STACKING")
    tang = find_one(root, "TANGENTIAL_STACKING")
    sections = find_all(root, "SECTION")

    section_data = []
    for sec in sections:
        entry = {"index": int(sec["arg"]), "params": {}}
        main = find_one(sec, "MAIN_SECTION")
        for container_tag in (
            "PARAM_CURVE_2D_BEZIER",
            "PARAM_CTRLPOINTS_CURVE",
            "PARAM_CURVE_2D",
        ):
            for node in find_all(main, container_tag):
                entry["params"].update(param_values(node))
        for container_tag in ("SSPS_PARAMETERS", "CT_PARAMETERS"):
            node = find_one(main, container_tag)
            if node is not None:
                entry["params"].update(param_values(node))
        entry["n_params"] = len(entry["params"])
        entry["main_scalars"] = scalars(main)
        section_data.append(entry)

    return {
        "source": str(par_path),
        "endwalls": {
            "scalars": scalars(endwalls),
            "hub": {
                "scalars": scalars(hub),
                "points": point_list(param_values(hub)),
            },
            "shroud": {
                "scalars": scalars(shroud),
                "points": point_list(param_values(shroud), "SHROUD"),
            },
        },
        "stream_surfaces": {
            "scalars": scalars(stream),
            "reference_traces": param_values(find_one(stream, "REFERENCE_STREAM_TRACES")),
            "primary_span": param_values(find_one(stream, "PRIMARY_SPAN_PARAMETERS")),
            "rounded_tip": param_values(find_one(stream, "ROUNDED_TIP_PARAMETERS")),
        },
        "stacking_point": scalars(find_one(root, "STACKING_POINT")),
        "meridional_stacking": {
            "scalars": scalars(merid),
            "sweep_law": scalars(find_one(merid, "SWEEP_LAW")),
            "sweep_locations": param_values(find_one(merid, "SWEEP_LOCATIONS")),
            "dz_prim": param_values(find_one(merid, "DZ_PRIM")),
            "dr_prim": param_values(find_one(merid, "DR_PRIM")),
            "dm_prim": param_values(find_one(merid, "DM_PRIM")),
            "sweep_curve": curve(find_one(merid, "PARAM_CURVE_2D")),
            "edge_traces": scalars(find_one(merid, "EDGE_TRACES")),
            "edge_locations": param_values(find_one(merid, "EDGE_LOCATIONS")),
            "le_curve": curve(find_all(merid, "PARAM_CURVE_2D_BEZIER")[0]),
            "te_curve": curve(find_all(merid, "PARAM_CURVE_2D_BEZIER")[1]),
        },
        "tangential_stacking": {
            "scalars": scalars(tang),
            "lean_locations": param_values(find_one(tang, "LEAN_LOCATIONS")),
            "lean_curve": curve(find_one(tang, "PARAM_CURVE_2D")),
        },
        "abblade_main": {
            "scalars": scalars(find_one(root, "ABBLADE")),
            "parameters": param_values(find_one(find_one(root, "ABBLADE"), "PARAMETERS")),
        },
        "blade_sections": {
            "scalars": scalars(find_one(root, "BLADE_SECTIONS")),
            "secondary": scalars(find_one(root, "SECONDARY_SECTIONS")),
        },
        "general_parameters": {
            "scalars": param_values(find_one(root, "GENERAL_PARAMETERS")),
        },
        "sections": section_data,
    }


def point_list(params: dict, prefix: str = "HUB") -> list[list[str]]:
    paired = []
    index = 1
    while f"{prefix}_Z{index}" in params:
        z = params[f"{prefix}_Z{index}"]
        r = params.get(f"{prefix}_R{index}")
        paired.append([z["value"] if z else None, r["value"] if r else None])
        index += 1
    return paired


def main() -> int:
    result = {}
    for label, relative in (("R1", r"R1_5span\R1.par"), ("R2", r"R2_5span\R2.par")):
        result[label] = extract(V7 / relative)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    for label in ("R1", "R2"):
        data = result[label]
        print(f"--- {label} ---")
        print("  hub points   :", data["endwalls"]["hub"]["points"])
        print("  shroud points:", data["endwalls"]["shroud"]["points"])
        print("  spans        :", [v["value"] for v in data["stream_surfaces"]["primary_span"].values()])
        print("  sections     :", [(s["index"], s["n_params"]) for s in data["sections"]])
        print("  DZ_PRIM      :", [v["value"] for v in data["meridional_stacking"]["dz_prim"].values()])
        print("  DM_PRIM      :", [v["value"] for v in data["meridional_stacking"]["dm_prim"].values()])
        print("  SWEEP_BETA   :", data["meridional_stacking"]["sweep_curve"]["params"])
        print("  LE_CURVE     :", data["meridional_stacking"]["le_curve"]["params"])
        print("  TE_CURVE     :", data["meridional_stacking"]["te_curve"]["params"])
        print("  LEAN         :", data["tangential_stacking"]["lean_curve"]["params"],
              data["tangential_stacking"]["lean_locations"])
        print("  edge locs    :", {k: v["value"] for k, v in data["meridional_stacking"]["edge_locations"].items()})
    print("written:", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
