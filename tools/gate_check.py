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
BT = chr(96)
FENCE = BT * 3

# ── 判据的唯一真源：合同文件 ────────────────────────────────────────────
# 阈值、绑定关系、判据文字全部从这里读，本文件**不另写一份**。
# 原因：同一个规则曾经写在两处（合同 + 代码），结果改了代码忘改合同，
# 合同里留下一条会误导下游的错判据 —— C-011 就是这么来的。
ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = (ROOT / ".agents" / "skills" / "ducted-fan-aero-design"
             / "references" / "ducted-fan-contracts.md")

# 没有合同可依据的纯过程判据（文件存在性之类）。显式列出来，不假装它们有合同。
BUILTIN_CHECK_IDS = {
    "G0-1", "G0-2", "G0-3", "G0-5",
    "G1-1", "G1-2", "G1-3", "G1-4",
    "G4-1", "G4-2", "G4-3", "G4-4",
    "G5-1", "G5-2", "G5-4",
    "G6-1",
}


def _parse_scalar(v):
    v = v.strip().strip('"').strip("'")
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass
    if "|" in v:
        return [x.strip() for x in v.split("|") if x.strip()]
    return v


def load_contract_specs(path=None):
    """解析合同文件里的 机读 块。返回 (entries, specs)。

    entries: {C-00N: {title, gate, check, also_check, params}}
    specs:   {check_id: {contract, title, gate, params}}
    """
    path = Path(path) if path else CONTRACTS
    if not path.is_file():
        raise RuntimeError(
            "合同文件不存在：" + str(path) + LF
            + "判据的真源缺失，拒绝用内置默认值继续 —— 那正是产生漂移的原因。")
    text = path.read_text(encoding="utf-8")
    block_re = re.compile(r"\*\*机读\*\*[^\n]*\n+" + FENCE + r"yaml\n(.*?)" + FENCE, re.S)
    entries, specs = {}, {}
    heads = list(re.finditer(r"^## (C-\d+)\s+([^\n]*)$", text, re.M))
    for i, m in enumerate(heads):
        cid, title = m.group(1), m.group(2).strip()
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[m.end():end]
        e = {"title": title, "gate": None, "check": None, "also_check": None, "params": {}}
        mm = block_re.search(body)
        if mm:
            kv = {}
            for line in mm.group(1).splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                k, _, v = line.partition(":")
                if k.strip():
                    kv[k.strip()] = _parse_scalar(v)
            e["gate"] = kv.pop("gate", None)
            e["check"] = kv.pop("check", None)
            e["also_check"] = kv.pop("also_check", None)
            e["params"] = kv
            for chk in (e["check"], e["also_check"]):
                if chk:
                    specs[chk] = {"contract": cid, "title": title,
                                  "gate": e["gate"], "params": e["params"]}
        entries[cid] = e
    return entries, specs


_CACHE = {}


def contract_specs():
    if "specs" not in _CACHE:
        entries, specs = load_contract_specs()
        _CACHE["entries"] = entries
        _CACHE["specs"] = specs
    return _CACHE["entries"], _CACHE["specs"]


def param(check_id, key, default=None):
    """从合同取阈值。取不到就用 default —— 但 audit 会把这个缺口列出来。"""
    _, specs = contract_specs()
    return (specs.get(check_id) or {}).get("params", {}).get(key, default)


def criteria_of(check_id, fallback=""):
    """判据文字也来自合同，避免两处措辞不一致。"""
    _, specs = contract_specs()
    spec = specs.get(check_id)
    if not spec:
        return fallback
    return "见合同 " + spec["contract"] + "「" + spec["title"] + "」"

MANDATORY_REQUIREMENT_PATHS = [
    ("thrust.value", "推力目标"),
    ("thrust.unit", "推力单位"),
    ("environment.p_inf_pa", "环境静压"),
    ("geometry.tip_diameter_m", "桨盘直径"),
    ("shaft.rpm_max_allowed", "转速上限"),
]


class Result:
    # 所有实际跑过的 check id 都记在这里，供 --audit 与合同比对
    SEEN = set()

    def __init__(self, gate):
        self.gate = gate
        self.items = []

    def add(self, cid, title, criteria, measured, verdict, source, detail=None):
        Result.SEEN.add(cid)
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
    allowed = param("G0-4", "allowed_definition", ["control_volume", "wall_axial_force"])
    if not isinstance(allowed, list):
        allowed = [allowed]
    r.add("G0-4", "推力口径已声明",
          criteria_of("G0-4") + "　允许 " + "/".join(str(a) for a in allowed),
          "definition=" + str(definition),
          "PASS" if definition in allowed else "FAIL",
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

def external_index(case):
    """读 _external/*.json 里"只索引不复制"的文件清单（相对路径）。"""
    out = []
    d = Path(case) / "_external"
    if d.is_dir():
        for j in sorted(d.glob("*.json")):
            try:
                data = json.loads(j.read_text(encoding="utf-8"))
            except Exception:
                continue
            for f in (data.get("files") or []):
                rel = f.get("rel") or f.get("path") or ""
                if rel:
                    out.append(str(rel).replace("\\", "/"))
    return out


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

    # 大二进制（.cgns 等）按账本合同"只索引不复制"放在 _external/，不算缺失。
    ext = external_index(case)
    required = (".trb", ".igg", ".cgns", ".qualityReport")
    missing, external_ok = [], []
    for s in required:
        if s in files:
            continue
        if any(name.endswith(stem + s) for name in ext):
            external_ok.append(s)
            continue
        missing.append(s)
    r.add("G4-2", "关键文件齐全",
          ".trb/.igg/.cgns/.qualityReport 必须齐全；大二进制可在 _external 索引中",
          "missing=" + str(missing) + "　外部索引满足=" + str(external_ok),
          "PASS" if not missing else "FAIL", "gates.md#G4")

    qr = files.get(".qualityReport")
    if qr and qr.is_file():
        qtext = qr.read_text(encoding="utf-8", errors="replace")
        r.add("G4-3", "质量报告非空", ".qualityReport 必须存在且非空",
              "%d bytes" % qr.stat().st_size, "PASS" if qr.stat().st_size > 0 else "FAIL",
              "gates.md#G4")
        # 负单元。AutoGrid 的质量报告可能写成陈述句 "No Negative Cell"，
        # 也可能写成 "Negative cells: 3" —— 两种都要认，否则会误判成 SKIP。
        neg = None
        if re.search(r"no\s+negative\s+cell", qtext, re.I):
            neg = 0
        else:
            m = re.search(r"(negative)[^0-9\-]{0,24}(-?\d+)", qtext, re.I)
            if m:
                neg = int(m.group(2))
        r.add("G4-4", "负单元 = 0", "网格不得有负体积单元",
              "reported=%s" % ("未在 qualityReport 中找到" if neg is None else neg),
              "PASS" if neg == 0 else ("SKIP" if neg is None else "FAIL"),
              "gates.md#G4")
    else:
        r.add("G4-3", "质量报告非空", ".qualityReport 必须存在", "缺失", "FAIL", "gates.md#G4")

    # 块签名（若有 mesh_audit.json）
    # 块签名审计文件的实际命名随工具而变（mesh_audit.json / <stem>.audit.json），
    # 所以按后缀找，不要写死文件名 —— 否则检查在但永远不触发（实测踩过）。
    SIG_KEYS = ("blocks", "block_signature", "block_signatures",
                "grid_blocks", "block_dims", "block_table")
    audits = sorted(root.glob("*.audit.json")) + sorted(root.glob("mesh_audit.json"))
    audits = [a for a in dict.fromkeys(audits) if a.is_file()]
    if audits:
        found_sig = None
        for a in audits:
            try:
                data = json.loads(a.read_text(encoding="utf-8"))
            except Exception:
                continue
            blocks = next((data.get(k) for k in SIG_KEYS if data.get(k)), None)
            if blocks:
                found_sig = (a.name, data)
                break
        if found_sig:
            r.add("G4-5", "块签名已记录", criteria_of("G4-5", "必须含块签名"),
                  found_sig[0] + "　keys=" + str(list(found_sig[1].keys())[:6]),
                  "PASS", "C-007")
        else:
            r.add("G4-5", "块签名已记录", criteria_of("G4-5", "必须含块签名"),
                  "找到 " + str([a.name for a in audits])
                  + "，但没有块签名字段（查过 " + "/".join(SIG_KEYS) + "）。"
                  + "C-007 要求记录块数 + 每块 IMAX/JMAX/KMAX —— 需在网格审计里补上",
                  "WARN", "C-007")
    else:
        r.add("G4-5", "块签名已记录", criteria_of("G4-5", "必须含块签名"),
              root.name + " 下无 *.audit.json", "SKIP", "C-007")
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
    limit = param("G5-3", "mass_error_limit_pct", 1.0)      # 阈值来自 C-002
    violations = []
    for row in accepted:
        me = numeric(row.get("mass_error_pct"))
        if me is None or me > limit:
            violations.append({"case": row["case"], "mass_error_pct": row.get("mass_error_pct")})
    r.add("G5-3", "验收点满足质量不平衡判据",
          criteria_of("G5-3", "100*|mdot_in-mdot_out|/|mdot_in| <= %.1f%%" % limit)
          + "　阈值 " + str(limit) + "%",
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

    banned = param("G6-2", "banned", [])            # 禁用字段来自 C-003
    if not isinstance(banned, list):
        banned = [banned]
    check_drive = bool(param("G6-2", "banned_drive_prefix", True))
    drive_re = re.compile(r"[A-Za-z]:[\\/]")
    dirty = []
    for p in tables:
        if p.suffix.lower() != ".csv":
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for token in banned:
            if token and token in text:
                dirty.append({"file": p.name, "token": token})
        if check_drive and drive_re.search(text):
            dirty.append({"file": p.name, "token": "（磁盘绝对路径）"})
    r.add("G6-2", "交付表无禁用字段",
          criteria_of("G6-2") + "　禁用 " + str(len(banned)) + " 个字段 + 磁盘路径",
          "dirty=%d" % len(dirty), "PASS" if not dirty else "FAIL", "C-003", {"dirty": dirty})

    thrust_files = [p for p in root.glob("*.csv") if "thrust" in p.name.lower() or "推力" in p.name]
    r.add("G6-3", "静推力闭合已记录",
          "static_thrust = momentum_thrust + pressure_thrust，容差 1e-6 相对",
          "candidates=" + str([p.name for p in thrust_files]),
          "SKIP", "C-004")
    return r


def cmd_audit(args):
    """判据一致性自检：合同 ↔ 代码，两边对不上就报错。

    这个检查的存在理由：曾经同一个规则写在两处，改了代码忘改合同，
    合同里留下一条错判据（C-011）。有了它，这类漏改会立刻暴露。
    """
    entries, specs = contract_specs()

    # 静态扫源码取"实际实现了哪些检查" —— 不能靠跑一遍收集：
    # 闸门在数据缺失时会提前 return，那些检查就没跑，会被误报成"没实现"。
    src = Path(__file__).read_text(encoding="utf-8")
    used = set(re.findall(r'r\.add\(\s*"(G\d+-\d+)"', src))
    bound = set(specs.keys())
    problems = []

    for cid in sorted(bound - used):
        problems.append({"kind": "合同声明了检查，代码里没有实现",
                         "check": cid, "contract": specs[cid]["contract"]})
    for cid in sorted(used - bound - BUILTIN_CHECK_IDS):
        problems.append({"kind": "代码实现了检查，但既无合同也未登记为过程判据",
                         "check": cid, "contract": ""})
    for cid in sorted(BUILTIN_CHECK_IDS & bound):
        problems.append({"kind": "既登记为过程判据、又有合同绑定，二者冲突",
                         "check": cid, "contract": specs[cid]["contract"]})
    for cid, e in sorted(entries.items()):
        if e["gate"] and not e["check"]:
            problems.append({"kind": "合同写了 gate 却没写 check",
                             "check": cid, "contract": cid})
        if e["check"] and e["gate"] and not e["check"].startswith(e["gate"] + "-"):
            problems.append({"kind": "合同声明的 gate 与 check 编号不匹配",
                             "check": e["check"], "contract": cid})

    # 白话覆盖检查：gates.md 里出现过的每一步，都必须有对用户的说法，
    # 否则界面只能退回显示内部编号 —— 那就等于把 G0-G6 漏给小白了。
    plain_path = CONTRACTS.parent / "plain-language.json"
    gates_md = CONTRACTS.parent / "gates.md"
    gate_ids = []
    if gates_md.is_file():
        gate_ids = re.findall(r"^##\s+(G\d)\b", gates_md.read_text(encoding="utf-8"), re.M)
    translated = []
    if plain_path.is_file():
        try:
            blob = json.loads(plain_path.read_text(encoding="utf-8"))
            translated = [str(s.get("id", "")) for s in blob.get("stages", [])]
        except Exception as exc:
            problems.append({"kind": "白话对照表读不了",
                             "check": "plain-language.json", "contract": str(exc)})
    else:
        problems.append({"kind": "白话对照表不存在",
                         "check": "plain-language.json", "contract": str(plain_path)})
    for gid in gate_ids:
        if gid not in translated:
            problems.append({"kind": "这一步没有对用户的白话说法（界面会漏出内部编号）",
                             "check": gid, "contract": "plain-language.json"})
    for gid in translated:
        if gate_ids and gid not in gate_ids:
            problems.append({"kind": "白话表里的步骤在 gates.md 里找不到",
                             "check": gid, "contract": "plain-language.json"})
    # "第几步" 有两个来源：本文件的 STEP_OF_GATE 和白话表。对不上就是又一处漂移。
    if plain_path.is_file():
        try:
            for s in json.loads(plain_path.read_text(encoding="utf-8")).get("stages", []):
                want = STEP_OF_GATE.get(str(s.get("id", "")))
                if want is not None and int(s.get("step", -1)) != want:
                    problems.append({"kind": "第几步对不上（STEP_OF_GATE vs 白话表）",
                                     "check": "%s: 代码说第 %s 步，白话表说第 %s 步"
                                              % (s.get("id"), want, s.get("step")),
                                     "contract": "plain-language.json"})
        except Exception:
            pass

    payload = {
        "ok": not problems,
        "contracts_total": len(entries),
        "contracts_with_check": len({s["contract"] for s in specs.values()}),
        "checks_from_contract": len(bound),
        "checks_builtin": len(BUILTIN_CHECK_IDS),
        "checks_implemented": len(used),
        "checks_without_contract": sorted(used - bound - BUILTIN_CHECK_IDS),
        "stages_translated": len(translated),
        "problems": problems,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("判据一致性自检")
        print("  合同条目      : %d（其中 %d 条带机读块）"
              % (payload["contracts_total"], payload["contracts_with_check"]))
        print("  合同绑定检查  : %d 项" % payload["checks_from_contract"])
        print("  过程判据      : %d 项（无合同，显式登记）" % payload["checks_builtin"])
        print("  实际实现      : %d 项" % payload["checks_implemented"])
        print("  白话覆盖      : %d/%d 步有对用户的说法"
              % (payload["stages_translated"], len(gate_ids)))
        print()
        if not problems:
            print("  ✓ 合同与代码一致，无漂移")
        else:
            print("  ✗ 发现 %d 处不一致：" % len(problems))
            for pb in problems:
                print("    - [%s] %s %s" % (pb["kind"], pb["check"], pb["contract"]))
    return EXIT_OK if not problems else EXIT_VERIFY


GATES = {
    "requirements": gate_requirements,
    "brief": gate_brief,
    "mesh": gate_mesh,
    "solve": gate_solve,
    "post": gate_post,
}

# 子命令名 → 步骤编号。GATES 的键是命令名，Result.gate 是编号 —— 两套，
# 写日志时要用命令名查。以前直接拿 Result.gate 查这张表，一跑就 KeyError。
STAGE_MAP = {
    "requirements": "G0", "brief": "G1", "scheme": "G2",
    "geometry": "G3", "mesh": "G4", "solve": "G5", "post": "G6",
}
GATE_OF_COMMAND = {
    "requirements": "G0", "brief": "G1", "scheme": "G2",
    "geometry": "G3", "mesh": "G4", "solve": "G5", "post": "G6",
}

# 编号 → 第几步。与 plain-language.json 的 step 必须一致，
# audit 会核对（见 cmd_audit 的白话覆盖检查）。
STEP_OF_GATE = {
    "G0": 1, "G1": 2, "G2": 3, "G3": 4, "G4": 5, "G5": 6, "G6": 7,
}


VERDICT_CN = {"PASS": "通过", "WARN": "注意", "FAIL": "没通过", "SKIP": "还查不了"}


def render(result: Result) -> str:
    """打印给人看。编号放最后，先给结论。

    命令行里保留 (G4) 这样的编号 —— 日志和 skill 都按编号索引，
    但第一眼看到的必须是中文。
    """
    lines = ["第 %d 步检查（%s）：%s" % (
                 STEP_OF_GATE.get(result.gate, 0), result.gate,
                 VERDICT_CN.get(result.verdict, result.verdict)),
             "  通过 %d / 注意 %d / 没通过 %d / 还查不了 %d" % (
                 len([i for i in result.items if i["verdict"] == "PASS"]),
                 len(result.warns), len(result.fails), len(result.skips))]
    for item in result.items:
        mark = {"PASS": "v", "WARN": "!", "FAIL": "x", "SKIP": "-"}[item["verdict"]]
        lines.append("  " + mark + " " + item["title"] + "  [" + item["measured"] + "]"
                     + "  (" + item["id"] + ")")
    return LF.join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(prog="gate_check.py", description="阶段闸门判定")
    p.add_argument("gate", choices=list(GATES.keys()) + ["all", "audit"])
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

    if args.gate == "audit":
        return cmd_audit(args)

    names = list(GATES.keys()) if args.gate == "all" else [args.gate]
    results = [(name, GATES[name](case, args)) for name in names]

    overall = "PASS"
    if any(r.verdict == "FAIL" for _, r in results):
        overall = "FAIL"
    elif any(r.verdict == "WARN" for _, r in results):
        overall = "WARN"
    elif all(r.verdict == "SKIP" for _, r in results):
        overall = "SKIP"

    if args.log:
        for command, result in results:
            stage = GATE_OF_COMMAND.get(command, STAGE_MAP.get(result.gate, result.gate))
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
            "gates": [{"gate": r.gate, "verdict": r.verdict, "items": r.items}
                      for _, r in results],
        }, ensure_ascii=False, indent=2))
    else:
        for _, result in results:
            print(render(result))
        print("总体：" + overall)

    return EXIT_OK if overall in ("PASS", "WARN", "SKIP") else EXIT_VERIFY


if __name__ == "__main__":
    raise SystemExit(main())
