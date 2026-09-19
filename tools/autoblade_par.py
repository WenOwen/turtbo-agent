#!/usr/bin/env python3
"""autoblade_par.py - 改 AutoBlade .par 里参数的**正确**做法。

为什么需要这个
--------------
AutoBlade 的批处理流程是：

    ab_project_create(abp)
    ab_project_load_model(par)   # 读我们改过的 .par
    ab_model_update_all()        # 重算一切：VALUE 由 EXPRESSION 重新求值
    ab_project_save_as(abp)
    ab_model_export_geomturbo(geom)

**只改 VALUE 是徒劳的** —— ab_model_update_all() 会按 EXPRESSION 把它算回去。
实测：02-geometry/v10 的构建脚本把新值写进了 VALUE/VALUE_MIN/VALUE_MAX，
报告说「换掉 78 个 VALUE」，但导出的 .geomTurbo 与 v9 **逐字节相同**。
.par 的 88 行差异**全是 VALUE_MIN / VALUE_MAX**，VALUE 与 EXPRESSION 一个没动。

根因是替换窗口差一行：range(i+1, min(i+12, ...)) —— 而 EXPRESSION 在 NAME 之后第 12 行。

详细合同见：
    ~/.agents/skills/numeca-autoblade-geometry/references/par-parameter-contract.md

用法
----
    import autoblade_par as abp
    text, n = abp.replace_parameter(text, "S7_CAMBER_BETA2", -2.0)
    text, n = abp.set_camber_betas(text, 7, beta1_deg=32.5, beta2_deg=-2.0)
    text, n = abp.set_spanwise_betas(text, conv["sections"])
"""

from __future__ import annotations

import re

# 一个 PARAMETER 块从 NAME 到 EXPRESSION 有 13 行，留足余量。
# 旧实现用 12 —— 恰好把 EXPRESSION 挡在外面，是那次故障的直接原因。
WINDOW = 20

FIELD_RE = re.compile(r"(\s*)(VALUE|EXPRESSION)(\s+)(\S+)(\s*)$")


def replace_parameter(text: str, pname: str, value: float) -> tuple[str, int]:
    """改 NAME <pname> 那个 PARAMETER 块的 VALUE 与 EXPRESSION。

    **两行都要改。** 只改 VALUE，ab_model_update_all() 会按 EXPRESSION 算回去。
    返回 (新文本, 改了几行)。
    """
    lines = text.splitlines(keepends=True)
    n = 0
    for i, ln in enumerate(lines):
        if not re.match(r"\s*NAME\s+" + re.escape(pname) + r"\s*$", ln.rstrip("\r")):
            continue
        for j in range(i + 1, min(i + WINDOW, len(lines))):
            m = FIELD_RE.match(lines[j].rstrip("\r"))
            if not m:
                continue
            # EXPRESSION 的值带引号、VALUE 不带 —— 保留各自的引号形态
            q = chr(34) if m.group(4).startswith(chr(34)) else ""
            eol = chr(10) if lines[j].endswith(chr(10)) else ""
            lines[j] = m.group(1) + m.group(2) + m.group(3) + q + ("%.12g" % value) + q + eol
            n += 1
        break
    return "".join(lines), n


def set_camber_betas(text: str, section: int, beta1_deg: float,
                     beta2_deg: float) -> tuple[str, int]:
    """按截面号（1 起）设该截面的两个金属角。返回 (新文本, 改了几行)。"""
    total = 0
    for key, val in (("CAMBER_BETA1", beta1_deg), ("CAMBER_BETA2", beta2_deg)):
        text, n = replace_parameter(text, "S%d_%s" % (section, key), val)
        total += n
    return text, total


def set_spanwise_betas(text: str, sections) -> tuple[str, int]:
    """sections: 按截面顺序排的序列，每项要有 CAMBER_BETA1_deg / CAMBER_BETA2_deg。

    正是 tools/metal_angle_convert.py --json 输出的 sections 字段。
    """
    total = 0
    for i, s in enumerate(sections, 1):
        text, n = set_camber_betas(text, i, s["CAMBER_BETA1_deg"], s["CAMBER_BETA2_deg"])
        total += n
    return text, total


def describe(text: str, pname: str) -> dict:
    """把一个参数的块读成 dict —— 用来判断它是输入还是派生。"""
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if not re.match(r"\s*NAME\s+" + re.escape(pname) + r"\s*$", ln.strip()):
            continue
        out = {}
        for j in range(i + 1, min(i + WINDOW, len(lines))):
            t = lines[j].strip()
            if t.startswith("NI_END"):
                break
            k, _, v = t.partition(" ")
            if k:
                out[k] = v.strip()
        return out
    return {}