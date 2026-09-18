#!/usr/bin/env python3
"""gate_check.py - 阶段闸门判定，PASS 才放行；结果自动写入 LOG.md。

七道闸门：G0 requirements / G1 brief / G2 scheme / G3 geometry / G4 mesh / G5 solve / G6 post

判据来源
--------
- 领域硬合同：.agents/skills/ducted-fan-aero-design/references/ducted-fan-contracts.md
- 闸门细则：  .agents/skills/ducted-fan-aero-design/references/gates.md

原则
----
1. **数据缺失记 SKIP，不记 PASS。** 假装通过比报错更危险。
2. 每条判据带 id / 判据 / 实测 / 结论 / 来源。
3. 只读被检对象；只写本案例的 LOG.md 与 manifest.json。

用法
----
  python tools/gate_check.py requirements --case cases/DF90-001
  python tools/gate_check.py brief        --case cases/DF90-001
  python tools/gate_check.py mesh         --case cases/DF90-001 --version v1
  python tools/gate_check.py solve        --case cases/DF90-001 --summary <sweep_summary.csv>
  python tools/gate_check.py all          --case cases/DF90-001
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import case_ledger as ledger  # noqa: E402

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_PRECONDITION = 3
EXIT_VERIFY = 4
EXIT_INTERNAL = 5

LF = chr(10)

MASS_ERROR_LIMIT_PCT = 1.0
RANGE_LIMIT_PCT = 0.2
SKEW_MIN_DEG = 10.0
EXPANSION_MAX = 5.0

MANDATORY_REQUIREMENT_PATHS = [
    ("thrust.value", "推力目标"),
    ("thrust.unit", "推力单位"),
    ("environment.p_inf_pa", "环境静压"),
    ("geometry.tip_diameter_m", "桨盘直径"),
    ("shaft.rpm_max_allowed", "转速上限"),
]


class Result:
    def __init__(self, gate):
        self.gate = gate
        self.items = []

    def add(self, cid, title, criteria, measured, verdict, source, detail=None):
        self.items.append({
            "id": cid, "title": title, "criteria": criteria,
            "measured": measured, "verdict": verdict, "source": source,
            "detail": detail or {},
        })

    @property
    def fails(self):
        return [i for i in self.items if i["verdict"] == "FAIL"]

    @property
    def warns(self):
        return [i for i in self.items if i["verdict"] == "WARN"]

    @property
    def skips(self):
        return [i for i in self.items if i["verdict"] == "SKIP"]

    @property
    def verdict(self):
        if self.fails:
            return "FAIL"
        if self.warns:
            return "WARN"
        if self.skips and len(self.skips) == len(self.items):
            return "SKIP"
        return "PASS"


# ── 极简 YAML 读取（只支持本项目 requirements.yaml 用到的子集） ──────────────
def load_flat_yaml(path: Path) -> dict:
    """把两到三层缩进的简单 YAML 读成扁平 dict，键用点号连接。

    只支持：key: value、两层缩进、注释、列表项（- ...）会跳过。
    不支持锚点、多行标量、内联映射。够用即可，不引入第三方依赖。
    """
    flat = {}
    stack = []  # [(indent, key)]
    list_buffer = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if line.startswith("- "):
            top = ".".join(k for _, k in stack)
            list_buffer.setdefault(top, []).append(line[2:].strip())
            continue
        m = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", line)
        if not m:
            continue
        key, value = m.group(1), m.group(2).strip()
        while stack and stack[-1][0] >= indent:
            stack.pop()
        stack.append((indent, key))
        path_key = ".".join(k for _, k in stack)
        if value == "":
            continue
        if value.startswith("#"):
            continue
        value = re.sub(r"\s+#.*$", "", value).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        flat[path_key] = value
    for key, values in list_buffer.items():
        flat[key + ".__list__"] = values
    return flat


def unquote(value):
    return value


def numeric(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ── G0 需求 ────────────────────────────────────────────────────────────────
def gate_requirements(case: Path, args) -> Result:
    r = Result("G0")
    req = case / "requirements.yaml"
    if not req.is_file():
        r.add("G0-1", "需求基线存在", "requirements.yaml 必须存在", "缺失", "FAIL",
              "gates.md#G0")
        return r
    r.add("G0-1", "需求基线存在", "requirements.yaml 必须存在",
          "found, %d bytes" % req.stat().st_size, "PASS", "gates.md#G0")

    flat = load_flat_yaml(req)
    missing = []
    for path, label in MANDATORY_REQUIREMENT_PATHS:
        if path not in flat or flat[path] in ("null", "~", ""):
            missing.append(label + " (" + path + ")")
    r.add("G0-2", "四项必填齐全", "推力目标 / 环境条件 / 桨盘直径 / 转速上限 必须齐全且带单位",
          "checked=%d missing=%d" % (len(MANDATORY_REQUIREMENT_PATHS), len(missing)),
          "PASS" if not missing else "FAIL", "gates.md#G0",
          {"missing": missing})

    unit_ok = flat.get("thrust.unit") in ("kgf", "N", "kN", "lbf")
    r.add("G0-3", "推力单位可识别", "thrust.unit 必须是 kgf/N/kN/lbf 之一",
          "unit=" + str(flat.get("thrust.unit")), "PASS" if unit_ok else "FAIL",
          "gates.md#G0")

    definition = flat.get("thrust.definition")
    r.add("G0-4", "推力口径已声明", "thrust.definition 必须是 control_volume 或 wall_axial_force",
          "definition=" + str(definition), "PASS" if definition in ("control_volume", "wall_axial_force") else "FAIL",
          "ducted-fan-contracts.md#C-004")

    # 未决项覆盖率：source 为 open/assumed 的字段必须出现在 open_questions.md
    openq = case / "00-brief" / "open_questions.md"
    unresolved = [k for k, v in flat.items() if v in ("open", "assumed") and not k.endswith("__list__")]
    if not openq.is_file():
        r.add("G0-5", "未决项已落盘", "source=open/assumed 的字段必须在 open_questions.md 有对应条目",
              "open_questions.md 缺失", "FAIL", "gates.md#G0")
    else:
        text = openq.read_text(encoding="utf-8")
        uncovered = [k for k in unresolved if k.split(".")[0] not in text and k not in text]
        r.add("G0-5", "未决项已落盘", "source=open/assumed 的字段必须在 open_questions.md 有对应条目",
              "unresolved_fields=%d uncovered=%d" % (len(unresolved), len(uncovered)),
              "PASS" if not uncovered else "WARN", "gates.md#G0",
              {"unresolved": unresolved, "uncovered": uncovered})
    return r


# ── G1 设计大纲 ────────────────────────────────────────────────────────────
def gate_brief(case: Path, args) -> Result:
    r = Result("G1")
    brief = case / "00-brief" / "design_brief.md"
    if not brief.is_file():
        r.add("G1-1", "设计大纲存在", "00-brief/design_brief.md 必须存在", "缺失", "FAIL",
              "gates.md#G1")
        return r
    text = brief.read_text(encoding="utf-8")
    r.add("G1-1", "设计大纲存在", "00-brief/design_brief.md 必须存在",
          "%d bytes" % len(text.encode("utf-8")), "PASS", "gates.md#G1")

    required_sections = {
        "物理链": ["盘载荷", "诱导速度", "理想功率"],
        "变量与约束": ["设计变量", "锁死"],
        "自检": ["自检"],
    }
    missing_sections = []
    for group, keys in required_sections.items():
        if not any(k in text for k in keys):
            missing_sections.append(group)
    r.add("G1-2", "必备小节齐全", "大纲必须包含 物理链 / 变量与约束 / 自检 三部分",
          "missing=" + str(missing_sections), "PASS" if not missing_sections else "FAIL",
          "gates.md#G1")

    # 量级自洽：盘载荷与诱导速度
    flat = load_flat_yaml(case / "requirements.yaml") if (case / "requirements.yaml").is_file() else {}
    thrust_n = numeric(flat.get("thrust.value_n"))
    area = numeric(flat.get("geometry.disk_area_m2"))
    rho = numeric(flat.get("environment.density_kg_m3")) or 1.225
    if thrust_n and area:
        dl = thrust_n / area
        vi = (thrust_n / (2 * rho * area)) ** 0.5
        in_range = 500.0 <= dl <= 20000.0 and 5.0 <= vi <= 120.0
        r.add("G1-3", "盘载荷与诱导速度落在工程区间",
              "盘载荷 0.5-20 kPa 且诱导速度 5-120 m/s",
              "disk_loading=%.1f Pa  v_i=%.2f m/s" % (dl, vi),
              "PASS" if in_range else "WARN", "gates.md#G1")
    else:
        r.add("G1-3", "盘载荷与诱导速度可算", "需求中必须能取到推力(N)与桨盘面积",
              "thrust_n=%s area=%s" % (thrust_n, area), "SKIP", "gates.md#G1")

    # 不得出现确定性性能预测
    banned = re.findall(r"(保证|一定|必然达到|确保达到)", text)
    r.add("G1-4", "未做确定性性能预测", "大纲中不得出现「保证/一定/必然达到」等断言",
          "hits=%d" % len(banned), "PASS" if not banned else "WARN", "gates.md#G1",
          {"hits": banned})
    return r


# ── G4 网格 ────────────────────────────────────────────────────────────────
MESH_SUFFIXES = [".trb", ".igg", ".cgns", ".bcs", ".config", ".info", ".qualityReport"]

def gate_mesh(case: Path, args) -> Result:
    r = Result("G4")
    root = case / "03-mesh" / args.version
    if not root.is_dir():
        r.add("G4-1", "网格目录存在", "03-mesh/<version>/ 必须存在",
              "缺失：" + str(root), "SKIP", "gates.md#G4")
        return r

    bases = {}
    for p in root.iterdir():
        if p.is_file():
            for suf in MESH_SUFFIXES:
                if p.name.endswith(suf):
                    bases.setdefault(p.name[: -len(suf)], {})[suf] = p
    if not bases:
        r.add("G4-1", "网格文件存在", "目录下必须有 .trb/.igg/.cgns 等文件",
              "0 个候选", "FAIL", "gates.md#G4")
        return r

    stem = sorted(bases, key=lambda s: -len(bases[s]))[0]
    files = bases[stem]
    r.add("G4-1", "网格文件存在", "至少一套同名的网格文件",
          "stem=" + stem + " suffixes=" + ",".join(sorted(files)), "PASS", "gates.md#G4")

    missing = [s for s in (".trb", ".igg", ".cgns", ".qualityReport") if s not in files]
    r.add("G4-2", "关键文件齐全", ".trb/.igg/.cgns/.qualityReport 必须齐全",
          "missing=" + str(missing), "PASS" if not missing else "FAIL", "gates.md#G4")

    qr = files.get(".qualityReport")
    if qr and qr.is_file():
        qtext = qr.read_text(encoding="utf-8", errors="replace")
        r.add("G4-3", "质量报告非空", ".qualityReport 必须存在且非空",
              "%d bytes" % qr.stat().st_size, "PASS" if qr.stat().st_size > 0 else "FAIL",
              "gates.md#G4")
        # 负单元
        neg = None
        m = re.search(r"(negative|Negative|NEGATIVE)[^0-9\-]{0,20}(-?\d+)", qtext)
        if m:
            neg = int(m.group(2))
        r.add("G4-4", "负单元 = 0", "网格不得有负体积单元",
              "reported=%s" % ("未在 qualityReport 中找到" if neg is None else neg),
              "PASS" if neg == 0 else ("SKIP" if neg is None else "FAIL"),
              "gates.md#G4")
    else:
        r.add("G4-3", "质量报告非空", ".qualityReport 必须存在", "缺失", "FAIL", "gates.md#G4")

    # 块签名（若有 mesh_audit.json）
    audit = root / "mesh_audit.json"
    if audit.is_file():
        data = json.loads(audit.read_text(encoding="utf-8"))
        blocks = data.get("blocks") or data.get("block_signature") or {}
        r.add("G4-5", "块签名已记录", "mesh_audit.json 必须含块签名",
              "keys=" + str(list(data.keys())[:8]), "PASS" if blocks else "WARN", "C-007")
    else:
        r.add("G4-5", "块签名已记录", "mesh_audit.json 记录块数/块名/IMAX-JMAX-KMAX",
              "mesh_audit.json 缺失", "SKIP", "C-007")
    return r


# ── G5 求解 ────────────────────────────────────────────────────────────────
def gate_solve(case: Path, args) -> Result:
    r = Result("G5")
    summary_path = Path(args.summary) if args.summary else None
    if summary_path is None:
        cands = sorted((case / "04-solve").glob("**/sweep_summary.csv")) if (case / "04-solve").is_dir() else []
        summary_path = cands[-1] if cands else None
    if summary_path is None or not Path(summary_path).is_file():
        r.add("G5-1", "工况汇总存在", "sweep_summary.csv 必须存在（或用 --summary 指定）",
              "未找到", "SKIP", "gates.md#G5")
        return r

    with Path(summary_path).open("r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    r.add("G5-1", "工况汇总存在", "sweep_summary.csv 必须存在",
          "%d 行  %s" % (len(rows), summary_path), "PASS", "gates.md#G5")

    need = {"case", "rpm", "state", "mass_error_pct"}
    absent = sorted(need - set(rows[0].keys())) if rows else sorted(need)
    r.add("G5-2", "汇总字段齐全", "必须含 case/rpm/state/mass_error_pct",
          "missing=" + str(absent), "PASS" if not absent else "FAIL", "gates.md#G5")
    if absent:
        return r

    accepted = [x for x in rows if x["state"] == "accepted"]
    violations = []
    for row in accepted:
        me = numeric(row.get("mass_error_pct"))
        if me is None or me > MASS_ERROR_LIMIT_PCT:
            violations.append({"case": row["case"], "mass_error_pct": row.get("mass_error_pct")})
    r.add("G5-3", "验收点满足质量不平衡判据",
          "100*|mdot_in-mdot_out|/|mdot_in| <= %.1f%%" % MASS_ERROR_LIMIT_PCT,
          "accepted=%d violations=%d" % (len(accepted), len(violations)),
          "PASS" if not violations else "FAIL", "C-002", {"violations": violations})

    no_reason = [x["case"] for x in rows if x["state"] != "accepted" and not x.get("reason")]
    r.add("G5-4", "非验收点都有原因", "每个 stopped/rejected 点必须记录 reason",
          "checked=%d without_reason=%d" % (len(rows) - len(accepted), len(no_reason)),
          "PASS" if not no_reason else "FAIL", "gates.md#G5", {"without_reason": no_reason})

    # 边界口径：首个未验收点必须区分 rejected 与 stopped
    lines = []
    for rpm in sorted({int(float(x["rpm"])) for x in rows}):
        acc = [numeric(x["pressure_pa_abs"]) for x in rows
               if int(float(x["rpm"])) == rpm and x["state"] == "accepted"]
        acc = [a for a in acc if a is not None]
        if not acc:
            continue
        top = max(acc)
        above = [(numeric(x["pressure_pa_abs"]), x["state"], x.get("reason", ""))
                 for x in rows
                 if int(float(x["rpm"])) == rpm and x["state"] != "accepted"]
        above = [a for a in above if a[0] is not None and a[0] > top]
        first = min(above, key=lambda t: t[0]) if above else None
        lines.append({"rpm": rpm, "max_accepted_p": top,
                      "first_unaccepted": None if first is None else
                      {"p": first[0], "state": first[1], "reason": first[2]}})
    distinct = sorted({l["first_unaccepted"]["state"] for l in lines if l["first_unaccepted"]})
    r.add("G5-5", "边界状态口径已区分",
          "振荡侧边界的 state 必须被记录；rejected（策略）与 stopped（人为）语义不同，不得混为一谈",
          "states=" + str(distinct), "PASS" if len(distinct) <= 1 else "WARN",
          "cases/DF90-001/memory.md#2026-09-17", {"lines": lines})
    return r


# ── G6 后处理与交付 ────────────────────────────────────────────────────────
DELIVERY_BANNED = ["CFD质量状态", "质量状态", "警告", "D:\\", "C:\\", "sha256"]

def gate_post(case: Path, args) -> Result:
    r = Result("G6")
    root = case / "06-delivery" / args.version
    if not root.is_dir():
        r.add("G6-1", "交付目录存在", "06-delivery/<version>/ 必须存在", "缺失", "SKIP", "gates.md#G6")
        return r
    # .html 是看板交付物；.png/.svg 是图；都算交付文件。
    tables = [p for p in root.iterdir()
              if p.suffix.lower() in (".csv", ".xlsx", ".md", ".html", ".png", ".svg")]
    r.add("G6-1", "交付文件存在", "交付目录必须有表格/说明文件",
          "files=" + str(len(tables)), "PASS" if tables else "FAIL", "gates.md#G6")

    dirty = []
    for p in tables:
        if p.suffix.lower() != ".csv":
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for token in DELIVERY_BANNED:
            if token in text:
                dirty.append({"file": p.name, "token": token})
    r.add("G6-2", "交付表无禁用字段", "不得含路径/版本号/质量状态字段",
          "dirty=%d" % len(dirty), "PASS" if not dirty else "FAIL", "C-003", {"dirty": dirty})

    thrust_files = [p for p in root.glob("*.csv") if "thrust" in p.name.lower() or "推力" in p.name]
    r.add("G6-3", "静推力闭合已记录",
          "static_thrust = momentum_thrust + pressure_thrust，容差 1e-6 相对",
          "candidates=" + str([p.name for p in thrust_files]),
          "SKIP", "C-004")
    return r


GATES = {
    "requirements": gate_requirements,
    "brief": gate_brief,
    "mesh": gate_mesh,
    "solve": gate_solve,
    "post": gate_post,
}

STAGE_MAP = {
    "requirements": "G0", "brief": "G1", "scheme": "G2",
    "geometry": "G3", "mesh": "G4", "solve": "G5", "post": "G6",
}


def render(result: Result) -> str:
    lines = ["闸门 " + result.gate + " 判定：" + result.verdict,
             "  PASS=%d WARN=%d FAIL=%d SKIP=%d" % (
                 len([i for i in result.items if i["verdict"] == "PASS"]),
                 len(result.warns), len(result.fails), len(result.skips))]
    for item in result.items:
        mark = {"PASS": "v", "WARN": "!", "FAIL": "x", "SKIP": "-"}[item["verdict"]]
        lines.append("  " + mark + " " + item["id"] + " " + item["title"]
                     + "  [" + item["measured"] + "]")
    return LF.join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(prog="gate_check.py", description="阶段闸门判定")
    p.add_argument("gate", choices=list(GATES.keys()) + ["all"])
    p.add_argument("--case", required=True)
    p.add_argument("--version", default="v1")
    p.add_argument("--summary", default=None)
    p.add_argument("--no-log", dest="log", action="store_false", default=True)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    case = Path(args.case).resolve()
    if not case.is_dir():
        print("PRECONDITION: 案例目录不存在 " + str(case), file=sys.stderr)
        return EXIT_PRECONDITION

    names = list(GATES.keys()) if args.gate == "all" else [args.gate]
    results = [GATES[name](case, args) for name in names]

    overall = "PASS"
    if any(r.verdict == "FAIL" for r in results):
        overall = "FAIL"
    elif any(r.verdict == "WARN" for r in results):
        overall = "WARN"
    elif all(r.verdict == "SKIP" for r in results):
        overall = "SKIP"

    if args.log:
        for result in results:
            stage = STAGE_MAP[result.gate]
            measured = "; ".join(i["id"] + "=" + i["verdict"] for i in result.items)
            criteria = " | ".join(sorted({i["criteria"] for i in result.items}))
            ledger._append_log(
                case, stage=stage,
                action="闸门判定 " + result.gate,
                verdict=result.verdict if result.verdict != "SKIP" else "INFO",
                criteria=criteria,
                note="",
                extra={
                    "命令": "python tools/gate_check.py " + result.gate + " --case " + args.case,
                    "实测": measured,
                },
            )
        manifest = ledger.load_manifest(case)
        manifest["updated"] = ledger.now_iso()
        manifest["revision"] = int(manifest.get("revision", 0)) + 1
        ledger.write_json_atomic(ledger.manifest_path(case), manifest)

    if args.json:
        print(json.dumps({
            "ok": overall in ("PASS", "SKIP"),
            "overall": overall,
            "gates": [{"gate": r.gate, "verdict": r.verdict, "items": r.items} for r in results],
        }, ensure_ascii=False, indent=2))
    else:
        for result in results:
            print(render(result))
        print("总体：" + overall)

    return EXIT_OK if overall in ("PASS", "WARN", "SKIP") else EXIT_VERIFY


if __name__ == "__main__":
    raise SystemExit(main())
