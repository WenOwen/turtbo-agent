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
  python tools/gate_check.py scheme       --case cases/DF90-001
  python tools/gate_check.py geometry     --case cases/DF90-001
  python tools/gate_check.py mesh         --case cases/DF90-001 --version v1
  python tools/gate_check.py solve        --case cases/DF90-001 --summary <sweep_summary.csv>
  python tools/gate_check.py all          --case cases/DF90-001
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import case_ledger as ledger  # noqa: E402

# 退出码语义：让"查不了"和"过了"在机器眼里也不是一回事。
# 以前 PASS/WARN/SKIP 一律 exit 0，JSON 里写着 "ok": false，进程照样报成功 ——
# 任何用退出码判断的脚本/CI/agent 都会把"还查不了"读成"过了"。
EXIT_OK = 0            # 全部通过
EXIT_USAGE = 2         # 用法错误
EXIT_PRECONDITION = 3  # 前置条件不满足（案例目录不存在等）
EXIT_VERIFY = 4        # 有检查没通过
EXIT_WARN = 5          # 有注意项（能走，但挂着已知问题）
EXIT_SKIP = 6          # 有必查项还查不了
EXIT_INTERNAL = 7      # 工具自身出错

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
    "G0-1", "G0-2", "G0-3", "G0-5", "G0-6",
    "G1-1", "G1-2", "G1-3", "G1-4",
    # G2/G3 的判据写在各自 skill 里（ducted-fan-1d-scheme 的输出契约、
    # cascade-forge-geometry-handoff 的 G3-1..G3-9），不在 ducted-fan-contracts.md。
    # 按本集合的定义（无合同可依据的过程判据）显式登记，不假装它们有合同。
    "G2-1", "G2-2", "G2-3", "G2-4", "G2-5", "G2-6", "G2-7", "G2-8",
    "G3-0", "G3-1", "G3-2", "G3-3", "G3-4", "G3-5", "G3-6", "G3-7", "G3-8", "G3-9",
    "G4-0", "G4-1", "G4-2", "G4-3", "G4-4",
    "G5-1", "G5-2", "G5-4",
    # G5-6 的判据正文写在 requirements.yaml 的 verification_plan 与 gates.md#G5 里
    "G5-6",
    "G6-0", "G6-1",
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


# 这些检查"没数据"就是没做完，不能算通过。
# 判别标准：它查的是**本步骤必须交付的东西**，而不是"有就顺便看一眼"。
REQUIRED_CHECKS = {
    "G0-1", "G0-2", "G0-3", "G0-4", "G0-6",  # 需求基线：没有它后面全是空中楼阁
    "G1-1", "G1-2",                           # 设计大纲
    # G2：三表 + 列名 + 流道自洽 + 叶排数 + 溯源（哪一份求解生成了这三表）
    "G2-1", "G2-2", "G2-3", "G2-4", "G2-7",
    # G3：路径 + 展向 + 剖面 + 与参数表一致 + 周期数 + 由参数表导出
    "G3-0", "G3-1", "G3-3", "G3-4", "G3-5", "G3-7", "G3-9",
    "G4-0", "G4-1", "G4-2", "G4-3", "G4-4",  # 网格六件套 + 负单元
    "G5-1", "G5-2", "G5-3", "G5-4", "G5-5",  # 求解：没跑就没跑
    "G6-0", "G6-1", "G6-2", "G6-3",          # 交付：三表 + 推力闭合
}


class Result:
    # 所有实际跑过的 check id 都记在这里，供 --audit 与合同比对
    SEEN = set()

    def __init__(self, gate):
        self.gate = gate
        self.items = []

    def add(self, cid, title, criteria, measured, verdict, source, detail=None):
        Result.SEEN.add(cid)
        # 必查项没有数据 = 没做完。以前这里原样记 SKIP，然后 verdict 把 SKIP
        # 整个忽略掉 —— 结果就是"最关键的推力闭合判据恒 SKIP，时间线却显示绿灯"。
        if verdict == "SKIP" and cid in REQUIRED_CHECKS:
            verdict = "FAIL"
            measured = str(measured) + "　→ 本项必查，缺数据即未完成"
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
        if self.skips:
            # 还有查不了的项 —— 能往下走，但绝不能显示成"通过"。
            return "WARN"
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

    # 推力数值自洽：value_n 是手填的，必须等于 value × 换算系数。
    # 为什么单列一条：G1-3 的盘载荷/诱导速度全靠 value_n 算，
    # 它一旦和 value 不一致，后面所有量级判断都建在错数上，而没有任何检查会发现。
    unit = str(flat.get("thrust.unit") or "").strip().lower()
    val = numeric(flat.get("thrust.value"))
    val_n = numeric(flat.get("thrust.value_n"))
    KGF = 9.80665
    factor = {"kgf": KGF, "n": 1.0, "kn": 1000.0, "lbf": 4.4482216152605}.get(unit)
    if val is None or val_n is None:
        r.add("G0-6", "推力数值自洽", "value_n 必须等于 value × 单位换算系数",
              "value=%s value_n=%s" % (val, val_n), "SKIP", "gates.md#G0")
    elif factor is None:
        r.add("G0-6", "推力数值自洽", "value_n 必须等于 value × 单位换算系数",
              "单位 %s 没有换算系数，无法校验" % unit, "WARN", "gates.md#G0")
    else:
        want = val * factor
        err = abs(val_n - want) / want if want else 1.0
        r.add("G0-6", "推力数值自洽",
              "value_n == value × %.5f（%s→N），相对误差 <= 0.1%%" % (factor, unit or "?"),
              "value_n=%.4f　应为 %.4f　相对误差 %.4f%%" % (val_n, want, err * 100),
              "PASS" if err <= 1e-3 else "FAIL", "gates.md#G0")

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
        r.add("G1-3", "盘载荷与诱导速度落在工程区间", "需求中必须能取到推力(N)与桨盘面积",
              "thrust_n=%s area=%s" % (thrust_n, area), "SKIP", "gates.md#G1")

    # 不得出现确定性性能预测
    banned = re.findall(r"(保证|一定|必然达到|确保达到)", text)
    r.add("G1-4", "未做确定性性能预测", "大纲中不得出现「保证/一定/必然达到」等断言",
          "hits=%d" % len(banned), "PASS" if not banned else "WARN", "gates.md#G1",
          {"hits": banned})
    return r


# ── G2 1D/通流方案 ─────────────────────────────────────────────────────────
# 判据来自 gates.md#G2 与 ducted-fan-1d-scheme/SKILL.md 的输出契约。
#
# 这两道闸门（G2/G3）长期是**空的**：GATES 里只有 G0/G1/G4/G5/G6，
# 而 STAGE_MAP / GATE_OF_COMMAND 却写着 scheme=G2、geometry=G3。
# 结果是「七道闸门」实际只跑了五道 —— 恰好是「需求 → 形状」这两步没人查，
# 而 DF90-001 卡住的地方正是这里。
SCHEME_TABLES = {
    "流道尺寸表.csv": ["站位", "类型", "序号", "轴向坐标(m)", "轮毂半径(m)",
                       "机匣半径(m)", "中径半径(m)", "通流面积(m2)"],
    "叶片几何参数表.csv": ["叶排", "类型", "级", "轴向坐标(m)", "叶片数", "弦长(m)",
                           "稠度", "展弦比", "进口金属角(deg,相对轴向)",
                           "出口金属角(deg,相对轴向)", "叶尖间隙(m)", "堵塞"],
    "通流计算结果表.csv": ["参数类别", "参数名称", "单位", "数值"],
}
TIP_RADIUS_TOL_M = 1e-4          # 与 turboflow_adapter 的 B-4 同值：改一处要改两处


def csv_rows(path):
    """读一张 CSV 成 list[dict]。列名与值都 strip。"""
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return [{k.strip(): (v or "").strip() for k, v in r.items() if k}
                for r in csv.DictReader(fh)]


def perf_map(rows):
    """通流计算结果表是「参数类别/参数名称/单位/数值」长表，转成 名称 → 数值。"""
    out = {}
    for r in rows:
        k = (r.get("参数名称") or "").strip()
        if k:
            out[k] = (r.get("数值") or "").strip()
    return out


def rel_diff(a, b):
    if a is None or b is None:
        return None
    return abs(a - b) / max(abs(a), abs(b), 1e-300)


def is_ascii(text):
    try:
        text.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def result_matches(blob, perf):
    """这份 result.json 是不是那三张表的来源？

    用三个互相独立的数字认（效率 / 轴功率 / 扭矩），**不靠文件名、不靠目录名**。
    实测：01-scheme/v1 下同时躺着三份 result.json，效率分别是
    0.7597 / 0.7976 / 0.8794，只有一份对得上交付的三表 ——
    而没有任何记录说明用的是哪一份。旁边那两份会给出一套完全不同的答案。
    """
    s = blob.get("summary") or {}
    pairs = (("总总效率", s.get("efficiency_tt")),
             ("轴功率", s.get("power_w")),
             ("扭矩", s.get("torque_nm")))
    hits, missed = 0, []
    for label, actual in pairs:
        want = numeric(perf.get(label))
        if want is None or actual is None:
            missed.append(label)
            continue
        rel = rel_diff(float(actual), want)
        if rel is not None and rel <= 1e-9:
            hits += 1
        else:
            missed.append(label)
    return hits, missed


def gate_scheme(case: Path, args) -> Result:
    r = Result("G2")
    version = args.version or latest_version(case / "01-scheme")
    root = case / "01-scheme" / version
    if not root.is_dir():
        r.add("G2-1", "三表齐全", "01-scheme/<version>/ 必须存在",
              "缺失：" + str(root), "SKIP", "gates.md#G2")
        return r

    missing = [n for n in SCHEME_TABLES if not (root / n).is_file()]
    empty = [n for n in SCHEME_TABLES
             if (root / n).is_file() and (root / n).stat().st_size == 0]
    r.add("G2-1", "三表齐全",
          "流道尺寸表 / 叶片几何参数表 / 通流计算结果表 必须都存在且非空",
          "缺 %d 张、空 %d 张%s" % (len(missing), len(empty),
                                  ("　缺：" + "、".join(missing)) if missing else ""),
          "PASS" if not missing and not empty else "FAIL", "gates.md#G2",
          {"missing": missing, "empty": empty})
    if missing or empty:
        return r

    tables = {n: csv_rows(root / n) for n in SCHEME_TABLES}

    # G2-2 列名 —— 列名错位是最难发现的一类错：数字都在，就是不在该在的地方。
    bad_cols = {}
    for name, want in SCHEME_TABLES.items():
        got = set(tables[name][0].keys()) if tables[name] else set()
        lack = [c for c in want if c not in got]
        if lack:
            bad_cols[name] = lack
    r.add("G2-2", "三表列名齐全",
          "按 ducted-fan-1d-scheme 输出契约逐列核对（含单位后缀）",
          "有问题的表 %d 张%s" % (len(bad_cols),
                               ("　" + json.dumps(bad_cols, ensure_ascii=False))
                                if bad_cols else ""),
          "PASS" if not bad_cols else "FAIL",
          "ducted-fan-1d-scheme/SKILL.md#输出契约", {"missing_columns": bad_cols})

    flat = {}
    req = case / "requirements.yaml"
    if req.is_file():
        flat = load_flat_yaml(req)

    # G2-3 流道几何自洽：站位单调 + 半径序 + 被需求锁死的机匣半径没被改。
    ann = tables["流道尺寸表.csv"]
    zs = [z for z in (numeric(x.get("轴向坐标(m)")) for x in ann) if z is not None]
    mono = len(zs) >= 2 and all(zs[i] < zs[i + 1] for i in range(len(zs) - 1))
    order_bad = []
    for x in ann:
        h = numeric(x.get("轮毂半径(m)"))
        m = numeric(x.get("中径半径(m)"))
        s = numeric(x.get("机匣半径(m)"))
        if None in (h, m, s) or not (h < m < s):
            order_bad.append(x.get("站位"))
    tip_req = numeric(flat.get("geometry.tip_radius_m"))
    locked = str(flat.get("geometry.constraint") or "").strip().lower() == "locked"
    tips = [t for t in (numeric(x.get("机匣半径(m)")) for x in ann) if t is not None]
    # 四个分支都要显式写出来。以前只有"tip_req 取到了"那一条会比对，
    # 其余情况 tip_ok 默认 True —— 判据标题写着"不得被静默改动"，
    # 代码却正是**静默通过**，同一种错换了个地方又犯一次。
    if not locked:
        tip_ok = True
        tip_txt = ("需求未锁定机匣半径（constraint=%s），不做一致性比对"
                   % (flat.get("geometry.constraint") or "未声明"))
    elif tip_req is None:
        tip_ok = False
        tip_txt = "需求声明了 constraint=locked，却取不到 geometry.tip_radius_m —— 无基准可比"
    elif not tips:
        tip_ok = False
        tip_txt = "流道尺寸表里取不到机匣半径"
    else:
        worst = max(abs(t - tip_req) for t in tips)
        tip_ok = worst <= TIP_RADIUS_TOL_M
        tip_txt = ("需求锁定 r_tip=%.4f　实测 %.4f–%.4f　最大偏差 %.2e m"
                   % (tip_req, min(tips), max(tips), worst))
    g23_ok = mono and not order_bad and tip_ok
    r.add("G2-3", "流道几何自洽",
          "站位轴向坐标单调递增；轮毂 < 中径 < 机匣；"
          "被需求锁定的机匣半径不得被静默改动（容差 %.0e m）" % TIP_RADIUS_TOL_M,
          "站位 %d 个，单调=%s；半径序异常 %d 个；%s　锁定=%s"
          % (len(zs), "是" if mono else "否", len(order_bad), tip_txt,
             "是" if locked else "否"),
          "PASS" if g23_ok else "FAIL", "gates.md#G2 + ducted-fan-1d-scheme#A",
          {"order_bad": order_bad, "monotonic": mono, "tip_ok": tip_ok})

    # G2-4 叶排数：与需求 rows.count 一致，且与计算表的自述一致。
    blades = tables["叶片几何参数表.csv"]
    perf = perf_map(tables["通流计算结果表.csv"])
    want_rows = numeric(flat.get("rows.count"))
    got_rows = len(blades)
    said_rows = numeric(perf.get("叶排数"))
    if want_rows is None:
        # 需求没写 rows.count，这条判据的一半就没得查。以前它退化成
        # "两张表自述一致" 然后照样 PASS —— 需求与方案的叶排数不符也查不出来。
        # G2-4 在 REQUIRED_CHECKS 里，所以这个 SKIP 会被转成 FAIL：
        # "必查项没数据 = 没做完"。
        r.add("G2-4", "叶排数与需求一致",
              "叶片几何参数表的行数 == requirements rows.count，且 == 计算表的「叶排数」",
              "requirements.yaml 未声明 rows.count（参数表 %d 行）" % got_rows,
              "SKIP", "gates.md#G2（对标 B-5）")
    else:
        row_ok = int(want_rows) == got_rows \
            and (said_rows is None or int(said_rows) == got_rows)
        r.add("G2-4", "叶排数与需求一致",
              "叶片几何参数表的行数 == requirements rows.count，且 == 计算表的「叶排数」",
              "需求 %.0f　参数表 %d 行　计算表自述 %s"
              % (want_rows, got_rows,
                 ("%.0f" % said_rows) if said_rows is not None else "未声明"),
              "PASS" if row_ok else "FAIL", "gates.md#G2（对标 B-5）")

    # G2-5 对标闸门：结论可读，且每一项都带着出处。
    bg = root / "benchmark_gate.json"
    blob = None
    if not bg.is_file():
        r.add("G2-5", "对标闸门有结论",
              "benchmark_gate.json 必须存在，逐项带 source，且无 FAIL 项",
              "缺失：" + bg.name, "SKIP", "gates.md#G2")
    else:
        try:
            blob = json.loads(bg.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            r.add("G2-5", "对标闸门有结论", "benchmark_gate.json 必须可解析",
                  "解析失败：" + repr(exc), "FAIL", "gates.md#G2")
        if blob is not None:
            items = blob.get("items") or []
            naked = [i.get("id") for i in items if not (i.get("source") or "").strip()]
            verdict = str(blob.get("verdict") or "").strip().upper()
            hard_fail = [i.get("id") for i in items if i.get("verdict") == "FAIL"]
            # 对标有 FAIL 项时**不判死**。gates.md#G2 的失败出口写得很清楚：
            # 「对标不通过 → 如实记 FAIL → 降级为专家表格 + 文档化 1D 闭合 →
            #   不阻塞 G3+，但要在大纲与交付说明里标注 G2 未通过独立验证」。
            # 以前这里直接判 FAIL，把"不阻塞"变成"阻塞"，和写下来的规则打架。
            ok = bool(items) and verdict in ("PASS", "WARN", "FAIL") and not naked
            if not ok:
                v25, note25 = "FAIL", ""
            elif hard_fail:
                v25 = "WARN"
                note25 = ("　→ 对标有 %d 项没对上。按失败出口：不阻塞下一步，"
                           "但必须在设计大纲与交付说明里标注「G2 未通过独立验证」"
                           % len(hard_fail))
            else:
                v25, note25 = "PASS", ""
            r.add("G2-5", "对标闸门有结论",
                  "benchmark_gate.json 必须存在、逐项带 source；对标不通过记 FAIL 但**不阻塞下一步**",
                  "结论=%s　逐项 %d 条　无出处 %d 条　FAIL %d 条%s"
                  % (verdict or "?", len(items), len(naked), len(hard_fail), note25),
                  v25, "gates.md#G2",
                  {"verdict": verdict, "naked": naked, "fail": hard_fail})

    # G2-6 质量守恒 —— gates.md#G2 的硬判据，容差 1e-6。
    mi = numeric(perf.get("进口质量流量"))
    mo = numeric(perf.get("出口质量流量"))
    rel = rel_diff(mi, mo)
    if rel is None:
        r.add("G2-6", "质量守恒", "|mdot_in - mdot_out| / |mdot_in| <= 1e-6",
              "计算表里取不到进口/出口质量流量", "SKIP", "gates.md#G2")
    else:
        r.add("G2-6", "质量守恒", "|mdot_in - mdot_out| / |mdot_in| <= 1e-6",
              "进口 %.8g　出口 %.8g　相对差 %.2e" % (mi, mo, rel),
              "PASS" if rel <= 1e-6 else "FAIL", "gates.md#G2")

    # G2-7 溯源：这三张表到底是哪一次求解生成的？
    # 这是本闸门最重要的一条 —— 目录里躺着多份 result.json 时，
    # 没有任何记录说明用的是哪一份，而它们给出的是完全不同的方案。
    cands = sorted(p for p in root.rglob("result.json") if p.is_file())
    hit, lines = [], []
    for p in cands:
        try:
            one = json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            lines.append("%s：解析失败 %r" % (p.relative_to(root).as_posix(), exc))
            continue
        hits, _missed = result_matches(one, perf)
        s = one.get("summary") or {}
        lines.append("%s　效率 %.4f 功率 %.1f 扭矩 %.2f　命中 %d/3"
                     % (p.relative_to(root).as_posix(),
                        s.get("efficiency_tt") or 0.0, s.get("power_w") or 0.0,
                        s.get("torque_nm") or 0.0, hits))
        if hits == 3:
            hit.append(p.relative_to(root).as_posix())
    if not cands:
        r.add("G2-7", "三表可溯源",
              "三张表必须能追到生成它们的那一份 result.json",
              "01-scheme/%s 下找不到任何 result.json" % version, "FAIL",
              "gates.md#G2（禁止项：阈值没写来源）")
    elif len(hit) == 1:
        r.add("G2-7", "三表可溯源",
              "三张表必须能追到生成它们的那一份 result.json（按效率/功率/扭矩三项认）",
              "候选 %d 份，唯一命中：%s" % (len(cands), hit[0]),
              "PASS" if len(cands) == 1 else "WARN", "gates.md#G2",
              {"candidates": lines, "hit": hit})
    else:
        r.add("G2-7", "三表可溯源",
              "三张表必须能追到生成它们的那一份 result.json（按效率/功率/扭矩三项认）",
              "候选 %d 份，命中 %d 份 —— 无法确定用的是哪一份"
              % (len(cands), len(hit)), "FAIL", "gates.md#G2",
              {"candidates": lines, "hit": hit})

    # G2-8 「工程可行」这个字段会被读成「方案不可行」，必须能被解释。
    feasible = str(perf.get("工程可行") or "").strip().lower()
    crit8 = "计算表里必须有「工程可行」，且结论要能由约束清单解释"
    if feasible not in ("true", "false"):
        r.add("G2-8", "「工程可行」结论可解释", crit8,
              "工程可行=%s" % (perf.get("工程可行") or "缺失"), "SKIP", "gates.md#G2")
    elif feasible == "true":
        r.add("G2-8", "「工程可行」结论可解释", crit8,
              "工程可行=True", "PASS", "gates.md#G2")
    else:
        src = hit[0] if len(hit) == 1 else (cands[0].relative_to(root).as_posix()
                                            if cands else None)
        cons = []
        if src:
            try:
                cons = (json.loads((root / src).read_text(encoding="utf-8-sig"))
                        .get("constraints") or [])
            except Exception:
                cons = []
        eng_fail = [c for c in cons
                    if c.get("kind") == "engineering" and not c.get("passed")]
        des_fail = [c for c in cons
                    if c.get("kind") == "design" and not c.get("passed")]
        if not cons:
            r.add("G2-8", "「工程可行」结论可解释", crit8,
                  "工程可行=False，但取不到约束清单（%s）" % (src or "无 result"),
                  "WARN", "gates.md#G2")
        elif eng_fail:
            r.add("G2-8", "「工程可行」结论可解释", crit8,
                  "工程可行=False，且确有 %d 条工程约束不通过：%s"
                  % (len(eng_fail),
                     "、".join("%s.%s" % (c.get("row_id"), c.get("name"))
                               for c in eng_fail)),
                  "FAIL", "gates.md#G2", {"engineering_failed": eng_fail})
        else:
            note8 = ("工程可行=False，但工程约束 %d 条全通过；False 来自 %d 条 design 类约束"
                     "（射击目标，不是工程约束）—— 表里只写 False 会被读成「方案不可行」"
                     % (len(cons) - len(des_fail), len(des_fail)))
            r.add("G2-8", "「工程可行」结论可解释", crit8, note8,
                  "WARN", "gates.md#G2",
                  {"design_failed": [c.get("name") for c in des_fail]})
    return r


# ── G3 叶片造型 ────────────────────────────────────────────────────────────
# 判据来自 cascade-forge-geometry-handoff/SKILL.md 的「输出前自查清单」与 gates.md#G3。
G3_PREVIEW_SUFFIXES = (".png", ".jpg", ".jpeg", ".svg")


def interp_curve(curve, x):
    """在 [(x, r), ...] 上线性插值；超出端点就取端点。"""
    if not curve:
        return None
    pts = sorted(curve)
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for i in range(len(pts) - 1):
        x0, r0 = pts[i]
        x1, r1 = pts[i + 1]
        if x0 <= x <= x1:
            t = (x - x0) / (x1 - x0) if x1 > x0 else 0.0
            return r0 + (r1 - r0) * t
    return pts[-1][1]


def pt_dist(a, b):
    return sum((p - q) ** 2 for p, q in zip(a, b)) ** 0.5


def pair_rows(parsed, tbl):
    """把几何里的叶排与参数表的行配对。

    **不能只按同名配。** 几何里的 NIROW NAME 是 AutoBlade 的默认名
    （实测是 "row 1" / "row 2"），参数表里写的是 "R1" / "S1" —— 对不上。
    只按同名配会静默跳过整行，报出「参数表无此行」，看着像数据缺失，
    其实是配对根本没做。规则与 tools/geom_check.py 保持一致：
    同名 → 按叶片数 → 按顺序（并标注存疑）。
    """
    by_name = {}
    for x in tbl:
        by_name.setdefault((x.get("叶排") or "").strip(), x)
    used, out = set(), []
    for p, g in parsed:
        for row in (g.get("rows") or []):
            name = (row.get("name") or "").strip()
            nb = row.get("blades") or row.get("periodicity") or 0
            trow, how = None, "没找到"
            if name in by_name and name not in used:
                trow, how = by_name[name], "同名"
            else:
                for key, cand in by_name.items():
                    if key in used:
                        continue
                    w = numeric(cand.get("叶片数"))
                    if w is not None and nb and int(w) == int(nb):
                        trow, how = cand, "按叶片数配对"
                        break
            if trow is None:
                for key, cand in by_name.items():
                    if key not in used:
                        trow, how = cand, "按顺序（叶片数没对上，存疑）"
                        break
            if trow is not None:
                used.add((trow.get("叶排") or "").strip())
            out.append({"geom_path": p, "geom_file": p.name, "geom_row": name,
                        "blades_geom": nb, "table_row": (trow or {}).get("叶排"),
                        "matched_by": how, "row": row})
    return out


def gate_geometry(case: Path, args) -> Result:
    r = Result("G3")
    version = args.version or latest_version(case / "02-geometry")
    root = case / "02-geometry" / version
    if not root.is_dir():
        r.add("G3-0", "几何产物可用", "02-geometry/<version>/ 必须存在",
              "缺失：" + str(root), "SKIP", "gates.md#G3")
        return r
    files = [p for p in sorted(root.rglob("*.geomTurbo"))
             if ".bak" not in p.name.lower()]
    if not files:
        r.add("G3-0", "几何产物可用", "02-geometry/<version>/ 下必须有 .geomTurbo",
              "0 个", "SKIP", "gates.md#G3")
        return r

    try:
        import geom_view
    except Exception as exc:
        r.add("G3-0", "几何产物可用", "需要 tools/geom_view.py",
              "导入失败：" + repr(exc), "SKIP", "gates.md#G3")
        return r

    scheme = case / "01-scheme" / latest_version(case / "01-scheme")
    tbl = csv_rows(scheme / "叶片几何参数表.csv")
    by_name = {}
    for x in tbl:
        by_name.setdefault((x.get("叶排") or "").strip(), x)

    parsed, perr = [], []
    for p in files:
        try:
            parsed.append((p, geom_view.parse_geomturbo(p)))
        except Exception as exc:
            perr.append("%s：%r" % (p.name, exc))
    if not parsed:
        r.add("G3-0", "几何产物可用", "每个 .geomTurbo 都必须能解析出截面",
              "全部解析失败：" + "；".join(perr), "FAIL", "gates.md#G3")
        return r

    # G3-1 路径纯 ASCII —— 非 ASCII 路径会让 AutoGrid 把合法几何误报成格式错误。
    bad_path = [str(p) for p in files if not is_ascii(str(p))]
    r.add("G3-1", "输出路径纯 ASCII",
          "全链路路径不得含非 ASCII 字符（否则 AutoGrid 会误报格式错误）",
          "几何 %d 个，非 ASCII 路径 %d 个" % (len(files), len(bad_path)),
          "PASS" if not bad_path else "FAIL", "gates.md#G3（F-001）",
          {"bad": bad_path})

    # G3-2 截面数：上游的 SectionSchedule 说几个截面，几何就得有几个。
    # schedule 按**参数表的叶排名**命名（schedule-R1.json），
    # 几何里的 NIROW NAME 却是 "row 1" —— 必须先配对再找文件。
    pairs = pair_rows(parsed, tbl)
    sched_dir = case / "_automation" / "g3"
    sc_checked, sc_bad, sc_missing = 0, [], []
    for pr in pairs:
        key = pr["table_row"] or pr["geom_row"]
        sp = sched_dir / ("schedule-%s.json" % key)
        if not sp.is_file():
            sc_missing.append(key)
            continue
        try:
            want = json.loads(sp.read_text(encoding="utf-8-sig"))
        except Exception:
            sc_missing.append(key)
            continue
        n_want = want.get("output_section_count") or len(want.get("sections") or [])
        n_got = len(pr["row"].get("sections") or [])
        sc_checked += 1
        if n_want and int(n_want) != n_got:
            sc_bad.append({"row": key, "schedule": n_want, "geom": n_got})
    if not sc_checked:
        r.add("G3-2", "截面数与上游一致",
              "_automation/g3/schedule-<叶排>.json 的截面数 == 几何的截面数",
              "没有可比对的 SectionSchedule（%s）—— 这条判据当前无判别力"
              % ("、".join(sc_missing[:6]) or "目录不存在"), "SKIP",
              "cascade-forge-geometry-handoff/SKILL.md#G3-2")
    else:
        # **缺项必须进结论。** 以前只要 sc_checked >= 1 就只看 sc_bad，
        # sc_missing 被整段丢掉 —— 真实案例里几何有 2 个叶排、schedule 只有 R1，
        # 却报「比对 1 个叶排，不一致 0 个」→ PASS。
        # "根本没比的那一半"被当成了"比过了且一致"，正是原则 1 的反例。
        n_total = sc_checked + len(sc_missing)
        v32 = "FAIL" if sc_bad else ("WARN" if sc_missing else "PASS")
        r.add("G3-2", "截面数与上游一致",
              "_automation/g3/schedule-<叶排>.json 的截面数 == 几何的截面数；缺一份就不算比过",
              "应比 %d 个叶排，实比 %d 个，缺 %d 个（%s）；不一致 %d 个%s"
              % (n_total, sc_checked, len(sc_missing),
                 "、".join(sc_missing[:6]) or "无", len(sc_bad),
                 ("　" + json.dumps(sc_bad, ensure_ascii=False)) if sc_bad else ""),
              v32, "cascade-forge-geometry-handoff/SKILL.md#G3-2",
              {"bad": sc_bad, "missing": sc_missing})

    # G3-3 展向位置单调递增且覆盖 0→1（用几何自带的 hub/shroud 通道曲线定位）。
    span_bad, span_lines = [], []
    for p, g in parsed:
        hub_c = (g.get("channel") or {}).get("hub") or []
        shr_c = (g.get("channel") or {}).get("shroud") or []
        for row in (g.get("rows") or []):
            secs = row.get("sections") or []
            spans = []
            for sec in secs:
                try:
                    m = geom_view.section_metrics(sec)
                except Exception:
                    continue
                z = sum(m["z"]) / len(m["z"])
                rh = interp_curve(hub_c, z)
                rs = interp_curve(shr_c, z)
                if rh is None or rs is None or rs <= rh:
                    continue
                spans.append((m["rmid"] - rh) / (rs - rh))
            if len(spans) < 2:
                span_bad.append({"row": row.get("name"),
                                 "why": "只有 %d 个截面能定位展向" % len(spans)})
                continue
            mono_s = all(spans[i] < spans[i + 1] for i in range(len(spans) - 1))
            lo, hi = min(spans), max(spans)
            covers = abs(lo) <= 0.02 and abs(hi - 1.0) <= 0.02
            span_lines.append("%s：%d 截面　%.4f→%.4f　单调=%s　覆盖=%s"
                              % (row.get("name"), len(spans), lo, hi,
                                 "是" if mono_s else "否", "是" if covers else "否"))
            if not mono_s or not covers:
                span_bad.append({"row": row.get("name"), "lo": lo, "hi": hi,
                                 "monotonic": mono_s, "covers": covers})
    r.add("G3-3", "展向位置单调且覆盖 0→1",
          "各截面相对展向位置单调递增，最小 ≈0、最大 ≈1（容差 0.02）",
          "有问题的叶排 %d 个　%s" % (len(span_bad), "　".join(span_lines[:4])),
          ("PASS" if span_lines else "SKIP") if not span_bad else "FAIL",
          "cascade-forge-geometry-handoff/SKILL.md#G3-3",
          {"bad": span_bad, "lines": span_lines})

    # G3-4 剖面闭合、无重复点。
    prof_bad, prof_n = [], 0
    for p, g in parsed:
        for row in (g.get("rows") or []):
            for sec in (row.get("sections") or []):
                prof = sec.get("profile") or []
                if len(prof) < 4:
                    prof_bad.append({"row": row.get("name"), "sec": sec.get("index"),
                                     "why": "点数 %d" % len(prof)})
                    continue
                prof_n += 1
                suc = sec.get("suction") or []
                prs = sec.get("pressure") or []
                # 闭合：suction 与 pressure 都从 LE 走到 TE，两端点应重合。
                if suc and prs:
                    gap = max(pt_dist(suc[0], prs[0]), pt_dist(suc[-1], prs[-1]))
                else:
                    gap = pt_dist(prof[0], prof[-1])
                ref = max((pt_dist(prof[i], prof[i + 1])
                           for i in range(len(prof) - 1)), default=0.0)
                closed = gap <= max(1e-9, 1e-6 * ref)
                # 重复点只在**每一侧内部**查。拼接出来的 profile 在尾缘处
                # 天然有两个重合点（suction 的末点与 reversed(pressure) 的首点），
                # 那是解析器构造方式的固有属性，不是几何缺陷 ——
                # 拿它当重复点会把 26/26 个截面全报成 FAIL（实测踩过）。
                dup = 0
                for side in (suc, prs):
                    dup += sum(1 for i in range(len(side) - 1)
                               if pt_dist(side[i], side[i + 1]) <= 1e-12)
                if not closed or dup:
                    prof_bad.append({"row": row.get("name"), "sec": sec.get("index"),
                                     "端点间距_m": gap, "侧内重复点": dup})
    r.add("G3-4", "剖面闭合、无重复点",
          "每个截面点序闭合（首尾点重合）、相邻点不重复",
          "检查 %d 个截面，有问题 %d 个%s"
          % (prof_n, len(prof_bad),
             ("　" + json.dumps(prof_bad[:4], ensure_ascii=False)) if prof_bad else ""),
          ("PASS" if prof_n else "SKIP") if not prof_bad else "FAIL",
          "cascade-forge-geometry-handoff/SKILL.md#G3-4", {"bad": prof_bad[:20]})

    # G3-5 几何与参数表一致（稠度/弦长/叶片数）。
    # **复用 geom_check 的比对与阈值** —— 阈值只能有一份，否则界面和图会各说各话。
    try:
        import geom_check
        data = geom_check.build_rows(case, scheme_version=scheme.name,
                                     geom_version=version)
        items = data.get("items") or []
        fails = [i for i in items if i.get("verdict") == "FAIL"]
        warns = [i for i in items if i.get("verdict") == "WARN"]
        r.add("G3-5", "几何与参数表一致",
              "逐项比对设计表与几何实测（稠度按**同一半径**比、弦长、叶片数）；"
              "阈值与 tools/geom_check.py 同源",
              "比对 %d 项　FAIL %d　WARN %d%s"
              % (len(items), len(fails), len(warns),
                 ("　" + "；".join("%s %s" % (i.get("row"), i.get("what"))
                                   for i in fails[:4])) if fails else ""),
              ("PASS" if items else "SKIP") if not fails else "FAIL",
              "cascade-forge-geometry-handoff/SKILL.md#G3-5",
              {"fail": fails[:12], "warn": warns[:12],
               "pairing": data.get("pairing")})
    except Exception as exc:
        r.add("G3-5", "几何与参数表一致", "复用 tools/geom_check.py 的逐项比对",
              "比对失败：" + repr(exc), "SKIP",
              "cascade-forge-geometry-handoff/SKILL.md#G3-5")

    # G3-6 弦长 > 0。
    chord_bad, chord_n = [], 0
    for p, g in parsed:
        for row in (g.get("rows") or []):
            for sec in (row.get("sections") or []):
                try:
                    m = geom_view.section_metrics(sec)
                except Exception:
                    continue
                chord_n += 1
                if not (m["chord_m"] > 0):
                    chord_bad.append({"row": row.get("name"), "sec": sec.get("index"),
                                      "chord_m": m["chord_m"]})
    r.add("G3-6", "弦长 > 0", "每个截面的弦长必须为正",
          "检查 %d 个截面，弦长非正 %d 个" % (chord_n, len(chord_bad)),
          ("PASS" if chord_n else "SKIP") if not chord_bad else "FAIL",
          "cascade-forge-geometry-handoff/SKILL.md#G3-6", {"bad": chord_bad[:12]})

    # G3-7 行名 / 周期数 / 方向开关。
    # REVERSE_THETA 与 SIDES_EXCHANGE 写在 .par 里（.geomTurbo 不记这两项）——
    # 这两个开关错会让叶片整体镜像，而网格阶段**不会报错**。
    g37_bad, g37_warn, g37_lines = [], [], []
    for pr in pairs:
        row = pr["row"]
        name = pr["geom_row"]
        par = pr["geom_path"].with_suffix(".par")
        ptxt = par.read_text(encoding="utf-8", errors="replace") if par.is_file() else ""
        per = row.get("periodicity") or 0
        nb = row.get("blades") or 0
        want = numeric((by_name.get(pr["table_row"] or "") or {}).get("叶片数"))
        ok = bool(per) and per == nb and (want is None or int(want) == per)
        rev = re.search(r"REVERSE_THETA\s+([+-]?\d+)", ptxt)
        sed = re.search(r"SIDES_EXCHANGE\s+([+-]?\d+)", ptxt)
        # 判据里写着"方向开关必须已核对" —— 只查周期数就成了判据与实现不一致。
        # 没记录不是错，是没核对过；记 WARN，不判死。
        if not (rev and sed):
            g37_warn.append(pr["table_row"] or name)
        g37_lines.append("%s（几何名 %s，%s）：周期 %d / 叶片 %d / 参数表 %s　"
                         "REVERSE_THETA=%s　SIDES_EXCHANGE=%s"
                         % (pr["table_row"] or "?", name, pr["matched_by"], per, nb,
                            ("%.0f" % want) if want is not None else "无此行",
                            rev.group(1) if rev else "未记录",
                            sed.group(1) if sed else "未记录"))
        if not ok:
            g37_bad.append({"row": pr["table_row"] or name, "periodicity": per,
                            "blades": nb, "table": want})
    if not g37_lines:
        v37 = "SKIP"
    elif g37_bad:
        v37 = "FAIL"
    elif g37_warn:
        v37 = "WARN"
    else:
        v37 = "PASS"
    r.add("G3-7", "行名 / 周期数 / 方向开关已核对",
          "周期数 == 叶片数 == 参数表叶片数；REVERSE_THETA / SIDES_EXCHANGE 必须已记录",
          "叶排 %d 个，周期数不符 %d 个，方向开关未记录 %d 个　%s"
          % (len(g37_lines), len(g37_bad), len(g37_warn),
             "　".join(g37_lines[:4])),
          v37, "cascade-forge-geometry-handoff/SKILL.md#G3-7",
          {"bad": g37_bad, "no_switch_record": g37_warn})

    # G3-8 预览图。工具只能查「在不在」，「像不像叶片」是人的事。
    previews = [q for q in root.rglob("*")
                if q.is_file() and q.suffix.lower() in G3_PREVIEW_SUFFIXES]
    r.add("G3-8", "预览图存在",
          "几何目录下必须有可看的预览图（目视是否像叶片由人判断，工具只查在不在）",
          "找到 %d 张：%s" % (len(previews),
                            "、".join(q.name for q in previews[:5]) or "无"),
          "PASS" if previews else "WARN",
          "cascade-forge-geometry-handoff/SKILL.md#G3-8")

    # G3-9 由参数表导出 —— **这是 DF90-001 真正失败的那一条**。
    # 原先只在 SKILL 的禁止项里写着「不手工编辑几何文件」，没有检查 id，
    # 于是 v8 几何（人工调轮毂 + 人工选弯掠）在工具眼里完全合法。
    manifests = [q for q in root.rglob("*.manifest.json") if q.is_file()]
    prov_docs = [q for q in root.rglob("*PROVENANCE*.md") if q.is_file()]
    if not manifests:
        note9 = ("没有 manifest.json%s —— 无法证明这套几何由参数表导出"
                 % (("；但有 " + "、".join(q.name for q in prov_docs[:3])
                     + "（人写的说明，不是机器可读溯源）") if prov_docs else ""))
        r.add("G3-9", "由参数表导出",
              "几何必须带机器可读的溯源记录（*.manifest.json），记下它由哪份参数表导出",
              note9, "FAIL", "cascade-forge-geometry-handoff/SKILL.md#G3-9",
              {"provenance_docs": [str(q.relative_to(root)) for q in prov_docs]})
    elif not by_name:
        # 参数表读不到就无从比对。以前这里因为循环一次都不进，mism 恒空 → PASS。
        r.add("G3-9", "由参数表导出",
              "几何必须带机器可读的溯源记录（*.manifest.json），其记录的源参数与参数表对得上",
              "有 manifest %d 份，但读不到参数表（%s）—— 无基准可比"
              % (len(manifests), scheme.name), "FAIL",
              "cascade-forge-geometry-handoff/SKILL.md#G3-9")
    else:
        # **结构化断言，不是在 JSON 文本里搜数字子串。**
        # 旧实现是 `("%.0f" % 叶片数) not in json.dumps(blob)` ——
        # 于是 {"note": "handmade", "digits": "9 and 11"} 这种假 manifest 直接 PASS，
        # 连空 {} 都能过。而这条判据正是为「手工几何」新加的，它挡不住手工几何。
        #
        # 真实 manifest 的形态（实测 cascade-forge/UDF/artifacts/NASA120859-R1/）：
        #   {schema_version, blade_id, geomturbo_path, geomturbo_sha256,
        #    schedule: {name, blade_count, rotation_direction, sections:[{chord_m,…}]}}
        mism, lines9, matched_rows = [], [], set()
        for q in manifests:
            try:
                blob9 = json.loads(q.read_text(encoding="utf-8-sig"))
            except Exception as exc:
                mism.append("%s 解析失败 %r" % (q.name, exc))
                continue
            lines9.append(q.relative_to(root).as_posix())
            if not isinstance(blob9, dict):
                mism.append("%s 顶层不是对象" % q.name)
                continue
            sha = str(blob9.get("geomturbo_sha256") or "")
            if len(sha) != 64 or not re.fullmatch(r"[0-9a-fA-F]{64}", sha):
                mism.append("%s 没有可用的 geomturbo_sha256（拿不到它对应哪份几何）" % q.name)
            sch = blob9.get("schedule")
            if not isinstance(sch, dict):
                mism.append("%s 没有 schedule 块 —— 看不出它由哪份参数表导出" % q.name)
                continue
            bc = numeric(sch.get("blade_count"))
            secs = sch.get("sections") or []
            if bc is None or not secs:
                mism.append("%s 的 schedule 缺 blade_count 或 sections" % q.name)
                continue
            # 叶片数：manifest 自述 vs 参数表
            hit_name = None
            for name, trow in by_name.items():
                want = numeric(trow.get("叶片数"))
                if want is not None and int(want) == int(bc):
                    hit_name = name
                    break
            if hit_name is None:
                mism.append("%s 的 blade_count=%.0f 在参数表里找不到对应叶排" % (q.name, bc))
                continue
            matched_rows.add(hit_name)
            # 弦长：manifest 逐截面的 chord_m 中位数 vs 参数表该排的弦长
            chords = [numeric(s.get("chord_m")) for s in secs if isinstance(s, dict)]
            chords = [c for c in chords if c]
            want_chord = numeric(by_name[hit_name].get("弦长(m)"))
            if chords and want_chord:
                chords.sort()
                med = chords[len(chords) // 2]
                dev = abs(med - want_chord) / want_chord
                if dev > 0.05:
                    mism.append("%s：%s 截面弦长中位数 %.4f 与参数表 %.4f 差 %.1f%%"
                                % (q.name, hit_name, med, want_chord, dev * 100))
        uncovered = sorted(set(by_name) - matched_rows)
        if uncovered:
            mism.append("参数表里的 %s 没有任何 manifest 覆盖" % "、".join(uncovered))
        r.add("G3-9", "由参数表导出",
              "*.manifest.json 必须带 geomturbo_sha256 与 schedule（blade_count + sections），"
              "且 blade_count 与截面弦长与参数表对得上（弦长容差 5%）",
              "manifest %d 份（%s）；覆盖 %d/%d 个叶排；对不上 %d 处%s"
              % (len(manifests), "、".join(lines9[:3]), len(matched_rows), len(by_name),
                 len(mism), ("　" + "；".join(mism[:4])) if mism else ""),
              "PASS" if not mism else "FAIL",
              "cascade-forge-geometry-handoff/SKILL.md#G3-9", {"mismatch": mism})
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
                data = json.loads(j.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
            for f in (data.get("files") or []):
                rel = f.get("rel") or f.get("path") or ""
                if rel:
                    out.append(str(rel).replace("\\", "/"))
    return out


SIG_KEYS = ("blocks", "block_signature", "block_signatures",
            "grid_blocks", "block_dims", "block_table")


def igg_block_signature(igg):
    """直接从 .igg 里数块 —— 它才是求解器真正读的那份网格。

    IGG 文件 98.7% 可打印，块记录长这样：
        Block 0
        1 row_1_flux_1_Main_Blade_downStream domain1  6 89 73 33 ...
    即 "Block <序号>" 后跟块数、块名，再接 IMAX/JMAX/KMAX。
    审计 JSON 里没记块签名时这里能补上 —— 比"记不了"有用。
    """
    if igg is None:
        return None
    try:
        raw = igg.read_bytes()
    except Exception:
        return None
    if len(raw) > 64 * 1024 * 1024:
        return None
    text = raw.decode("latin-1", errors="replace")
    blocks = []
    for m in re.finditer(
            r"Block\s+(\d+)\s*\r?\n\s*(\d+)\s+(\S+)\s+(\S+)\s+"
            r"(\d+)\s+(\d+)\s+(\d+)", text):
        blocks.append({
            "index": int(m.group(1)), "name": m.group(3), "domain": m.group(4),
            "imax": int(m.group(5)), "jmax": int(m.group(6)), "kmax": int(m.group(7)),
        })
    return blocks or None


def latest_version(parent: Path, fallback="v1"):
    """取版本号最大的那一版（v10 > v9 > v2 > v1，按数字比不是按字符串比）。

    默认查最旧那版是危险的：案例当前是 v2，默认却汇报 v1 的结论，还不告警。
    """
    if not parent.is_dir():
        return fallback
    vs = [p.name for p in parent.iterdir()
          if p.is_dir() and re.fullmatch(r"v\d+", p.name)]
    if not vs:
        return fallback
    return max(vs, key=lambda s: int(s[1:]))


def gate_mesh(case: Path, args) -> Result:
    r = Result("G4")
    version = args.version or latest_version(case / "03-mesh")
    root = case / "03-mesh" / version
    if not root.is_dir():
        r.add("G4-0", "网格产物可用", "03-mesh/<version>/ 必须存在",
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
    audits = sorted(root.glob("*.audit.json")) + sorted(root.glob("mesh_audit.json"))
    audits = [a for a in dict.fromkeys(audits) if a.is_file()]
    if audits:
        found_sig = None
        for a in audits:
            try:
                data = json.loads(a.read_text(encoding="utf-8-sig"))
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
            igg = next(iter(sorted(root.glob("*.igg"))), None)
            sig = igg_block_signature(igg) if igg else None
            if sig:
                r.add("G4-5", "块签名已记录", criteria_of("G4-5", "必须含块签名"),
                      "%s　%d 块　%s" % (igg.name, len(sig),
                                         " ".join("%s:%dx%dx%d" % (b["name"][:14], b["imax"],
                                                                   b["jmax"], b["kmax"])
                                                  for b in sig[:3])),
                      "PASS", "C-007", {"blocks": sig})
            else:
                r.add("G4-5", "块签名已记录", criteria_of("G4-5", "必须含块签名"),
                      "找到 " + str([a.name for a in audits])
                      + "，但没有块签名字段（查过 " + "/".join(SIG_KEYS) + "）；"
                      + "也没能从 .igg 里解析出块记录",
                      "WARN", "C-007")
    else:
        igg = next(iter(sorted(root.glob("*.igg"))), None)
        sig = igg_block_signature(igg) if igg else None
        if sig:
            r.add("G4-5", "块签名已记录", criteria_of("G4-5", "必须含块签名"),
                  "无审计 JSON；从 %s 直接解析出 %d 块" % (igg.name, len(sig)),
                  "PASS", "C-007", {"blocks": sig})
        else:
            r.add("G4-5", "块签名已记录", criteria_of("G4-5", "必须含块签名"),
                  root.name + " 下既无 *.audit.json 也无可用 .igg", "SKIP", "C-007")
    return r


# ── G5 求解 ────────────────────────────────────────────────────────────────
def gate_solve(case: Path, args) -> Result:
    r = Result("G5")
    summary_path = Path(args.summary) if args.summary else None
    if summary_path is None:
        cands = []
        for sub in ("04-solve", "_replay", "05-post"):
            d = case / sub
            if d.is_dir():
                cands += sorted(d.glob("**/sweep_summary.csv"))
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
    # G5-6 同转速 + 同环形几何 锚点对照
    #
    # requirements.yaml 的 verification_plan.first_point 写着这个案例的核实点，
    # 但在这之前**没有任何工具会去读它** —— 于是 5000 rpm 的算例被拿去比
    # 6100 rpm 的设计目标（90 kgf），得出「差 -29.7%、达不到要求」，
    # 而那是两个不同工况的数直接相减。这跟 G2-7 是同一类错：口径不同，而没人查。
    #
    # 而且不能只比转速：本轮转速对上了（5000 = 5000），环形几何没对上
    # （v7 锚点入口轮毂 0.103457 vs 本次 0.08，差 22.7%）。
    # 只比转速不比几何，等于换个方式再犯同一个错。
    try:
        import anchor_check
        cmp6 = anchor_check.compare(case)
        r.add("G5-6", "同转速 + 同环形几何 锚点对照",
              "requirements.yaml 的 verification_plan.first_point 定义了核实点；"
              "必须用**同转速**的算例去比，且环形几何必须同源。"
              "转速对不上记「还查不了」，因为拿不同转速的数直接相减正是这条要防的错",
              anchor_check.headline(cmp6), cmp6.get("verdict", "SKIP"),
              "requirements.yaml#verification_plan.first_point",
              {"rpm": cmp6.get("rpm"), "annulus_rows": cmp6.get("annulus_rows"),
               "items": cmp6.get("items"), "reasons": cmp6.get("reasons"),
               "anchor_annulus_source": (cmp6.get("anchor") or {}).get("annulus_source")})
    except Exception as exc:
        r.add("G5-6", "同转速 + 同环形几何 锚点对照",
              "requirements.yaml 的 verification_plan.first_point 定义了核实点",
              "对照工具不可用或失败：" + repr(exc), "SKIP",
              "requirements.yaml#verification_plan.first_point")
    return r



# ── G6 后处理与交付 ────────────────────────────────────────────────────────
DELIVERY_BANNED = ["CFD质量状态", "质量状态", "警告", "D:\\", "C:\\", "sha256"]

def gate_post(case: Path, args) -> Result:
    r = Result("G6")
    version = args.version or latest_version(case / "06-delivery")
    root = case / "06-delivery" / version
    if not root.is_dir():
        r.add("G6-0", "交付产物可用", "06-delivery/<version>/ 必须存在", "缺失", "SKIP", "gates.md#G6")
        return r
    # .html 是看板交付物；.png/.svg 是图；都算交付文件。
    # 但"交付三表"是硬要求：CSV 一个都没有 = 这步没做完。
    tables = [p for p in root.iterdir()
              if p.suffix.lower() in (".csv", ".xlsx", ".md", ".html", ".png", ".svg")]
    csvs = [p for p in tables if p.suffix.lower() in (".csv", ".xlsx")]
    r.add("G6-1", "交付表存在", "交付目录必须有 CSV/XLSX 交付表（三表是硬要求）",
          "files=%d　其中表=%d" % (len(tables), len(csvs)),
          "PASS" if csvs else "FAIL", "gates.md#G6")

    banned = param("G6-2", "banned", [])            # 禁用字段来自 C-003
    if not isinstance(banned, list):
        banned = [banned]
    check_drive = bool(param("G6-2", "banned_drive_prefix", True))
    drive_re = re.compile(r"[A-Za-z]:[\\/]")
    dirty = []
    # 以前这里 continue 掉所有非 .csv —— 于是唯一的交付物 dashboard.html
    # 里明晃晃的 D:\ 路径和 sha256 全部免检通过。交付物就是交付物，不看后缀。
    for p in tables:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for token in banned:
            if token and token in text:
                dirty.append({"file": p.name, "token": token})
        if check_drive and drive_re.search(text):
            dirty.append({"file": p.name, "token": "（磁盘绝对路径）"})
    r.add("G6-2", "交付物无禁用字段",
          criteria_of("G6-2") + "　禁用 " + str(len(banned)) + " 个字段 + 磁盘路径"
          + "（覆盖 " + str(len(tables)) + " 个交付文件，不限后缀）",
          "dirty=%d" % len(dirty), "PASS" if not dirty else "FAIL", "C-003", {"dirty": dirty})

    # G6-3：真的去找推力闭合数据，找不到就是 FAIL（它在 REQUIRED_CHECKS 里）。
    tol = float(param("G6-3", "closure_tol_rel", 1e-6))
    cands = [p for p in root.rglob("*.csv")
             if any(k in p.name.lower() for k in ("thrust", "推力", "closure", "闭合"))]
    if not cands:
        cands = [p for p in root.rglob("*.csv")]
    checked, worst, bad = 0, 0.0, []
    for p in cands:
        try:
            with p.open("r", encoding="utf-8-sig", newline="") as fh:
                for row in csv.DictReader(fh):
                    keys = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
                    def num(*names):
                        for n in names:
                            if n in keys:
                                try:
                                    return float(keys[n])
                                except ValueError:
                                    return None
                        return None
                    total = num("static_thrust_n", "static_thrust", "静推力_n", "静推力")
                    mom = num("momentum_thrust_n", "momentum_thrust", "动量推力_n")
                    pres = num("pressure_thrust_n", "pressure_thrust", "压力推力_n")
                    if total is None or mom is None or pres is None:
                        continue
                    checked += 1
                    denom = max(abs(total), 1e-12)
                    err = abs(total - (mom + pres)) / denom
                    worst = max(worst, err)
                    if err > tol:
                        bad.append({"file": p.name, "static": total,
                                    "sum": mom + pres, "rel_err": err})
        except Exception:
            continue
    if checked == 0:
        r.add("G6-3", "静推力闭合",
              criteria_of("G6-3"), "交付表里找不到 静推力/动量推力/压力推力 三列",
              "SKIP", "C-004")
    else:
        r.add("G6-3", "静推力闭合",
              criteria_of("G6-3") + "　容差 %.0e（来自合同机读块）" % tol,
              "checked=%d　worst_rel_err=%.3e" % (checked, worst),
              "PASS" if not bad else "FAIL", "C-004", {"bad": bad})
    return r


def cmd_audit(args):
    """判据一致性自检：合同 ↔ 代码，两边对不上就报错。

    这个检查的存在理由：曾经同一个规则写在两处，改了代码忘改合同，
    合同里留下一条错判据（C-011）。有了它，这类漏改会立刻暴露。
    """
    entries, specs = contract_specs()

    # 静态扫源码取"实际实现了哪些检查" —— 不能靠跑一遍收集：
    # 闸门在数据缺失时会提前 return，那些检查就没跑，会被误报成"没实现"。
    #
    # 用 AST 而不是正则：正则只认 r.add("G5-3" 这一种写法，
    # 换成单引号、中间加注释、跨行，就会**静默漏报**（漏报比误报危险 ——
    # 它会让人以为"合同与代码一致"）。AST 认的是语法结构，不是字符。
    used = set()
    titles = {}
    try:
        tree = ast.parse(Path(__file__).read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if not (isinstance(fn, ast.Attribute) and fn.attr == "add"):
                continue
            if not node.args:
                continue
            a0 = node.args[0]
            if isinstance(a0, ast.Constant) and isinstance(a0.value, str) \
                    and re.fullmatch(r"G\d+-\d+", a0.value):
                used.add(a0.value)
                # 同一个 id 挂几个**不同的标题**？标题不同 = 含义不同。
                if len(node.args) > 1 and isinstance(node.args[1], ast.Constant) \
                        and isinstance(node.args[1].value, str):
                    titles.setdefault(a0.value, set()).add(node.args[1].value)
    except SyntaxError as exc:
        problems_pre = [{"kind": "gate_check.py 语法错误，判据自检无法进行",
                         "check": str(exc), "contract": ""}]
        used = set()
    else:
        problems_pre = []
    bound = set(specs.keys())
    problems = list(problems_pre)

    # 一码多义：同一个编号在代码里挂着几个不同的标题，读日志的人就分不清
    # 是哪一种"没通过"。实测 G3-1 曾经被 5 处复用（目录不存在 / 无几何文件 /
    # 无解析器 / 解析失败 / 路径非 ASCII），而 SKILL.md 里 G3-1 只等于"输出路径纯 ASCII"。
    # audit 以前只数 id 的**集合**，结构上看不见这种事。
    multi = {cid: sorted(t) for cid, t in titles.items() if len(t) > 1}
    for cid, t in sorted(multi.items()):
        problems.append({"kind": "一码多义：同一 id 挂了 %d 个不同标题" % len(t),
                         "check": cid + " → " + " / ".join(t), "contract": ""})

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
            blob = json.loads(plain_path.read_text(encoding="utf-8-sig"))
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
            for s in json.loads(plain_path.read_text(encoding="utf-8-sig")).get("stages", []):
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
        "checks_multi_meaning": sorted(multi),
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
            print("  [OK] 合同与代码一致，无漂移")
        else:
            print("  [!!] 发现 %d 处不一致：" % len(problems))
            for pb in problems:
                print("    - [%s] %s %s" % (pb["kind"], pb["check"], pb["contract"]))
    return EXIT_OK if not problems else EXIT_VERIFY


GATES = {
    "requirements": gate_requirements,
    "brief": gate_brief,
    "scheme": gate_scheme,
    "geometry": gate_geometry,
    "mesh": gate_mesh,
    "solve": gate_solve,
    "post": gate_post,
}

# 子命令名 → 步骤编号。GATES 的键是命令名，Result.gate 是编号 —— 两套，
# 写日志时要用命令名查。以前直接拿 Result.gate 查这张表，一跑就 KeyError。
#
# 这张表曾经被抄成两份（STAGE_MAP / GATE_OF_COMMAND），内容一字不差。
# 两份一模一样的东西就是两处会漂移的地方 —— 留着别名，但只维护一份。
STAGE_MAP = {
    "requirements": "G0", "brief": "G1", "scheme": "G2",
    "geometry": "G3", "mesh": "G4", "solve": "G5", "post": "G6",
}
GATE_OF_COMMAND = STAGE_MAP

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
    p.add_argument("--version", default=None,
                   help="版本目录名，如 v1/v2；不给就取最新版")
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
                    # 记的是**子命令名**（geometry），不是编号（G3）。
                    # 以前写 result.gate，于是日志里躺着
                    # "python tools/gate_check.py G3 --case ..." ——
                    # 抄下来直接 argparse 报错。日志里的命令必须能原样跑。
                    "命令": "python tools/gate_check.py " + command
                            + " --case " + args.case
                            + ((" --version " + args.version) if args.version else ""),
                    "实测": measured,
                },
            )
        manifest = ledger.load_manifest(case)
        manifest["updated"] = ledger.now_iso()
        manifest["revision"] = int(manifest.get("revision", 0)) + 1
        ledger.write_json_atomic(ledger.manifest_path(case), manifest)

    if args.json:
        print(json.dumps({
            "ok": overall == "PASS",
            "exit_code": {"PASS": EXIT_OK, "FAIL": EXIT_VERIFY,
                          "WARN": EXIT_WARN, "SKIP": EXIT_SKIP}[overall],
            "overall": overall,
            "gates": [{"gate": r.gate, "verdict": r.verdict, "items": r.items}
                      for _, r in results],
        }, ensure_ascii=False, indent=2))
    else:
        for _, result in results:
            print(render(result))
        print("总体：" + overall)

    if overall == "PASS":
        return EXIT_OK
    if overall == "FAIL":
        return EXIT_VERIFY
    if overall == "WARN":
        return EXIT_WARN
    return EXIT_SKIP


if __name__ == "__main__":
    raise SystemExit(main())
