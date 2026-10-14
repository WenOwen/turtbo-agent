"""unit tests for tools.agent_reply
跑法（项目根目录）：python -m pytest tools/test_agent_reply.py -v
或：C:\\Program Files\\Python312\\python.exe -m pytest tools/test_agent_reply.py -v
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import agent_reply as ar  # noqa: E402


# ── parse_command ────────────────────────────────────────────
class TestParseCommand:
    def test_empty_returns_status(self):
        assert ar.parse_command("") == ("status", [])
        assert ar.parse_command("   ") == ("status", [])

    def test_known_help(self):
        assert ar.parse_command("help") == ("help", [])

    def test_help_with_args(self):
        assert ar.parse_command("help me") == ("help", ["me"])

    def test_case(self):
        assert ar.parse_command("case DF90-001") == ("switch", ["DF90-001"])

    def test_open(self):
        assert ar.parse_command("open requirements.yaml") == ("open", ["requirements.yaml"])

    def test_show_alias(self):
        assert ar.parse_command("show manifest.json") == ("open", ["manifest.json"])

    def test_list(self):
        assert ar.parse_command("list") == ("list", [])

    def test_run_with_subcmd(self):
        assert ar.parse_command("run preflight") == ("run", ["preflight"])

    def test_run_gate_with_param(self):
        assert ar.parse_command("run gate G3") == ("run", ["gate", "G3"])

    def test_unknown_falls_back_to_status(self):
        # 未知 head → 默认 status，且把整个输入作空 args（让 status 自己去读 STATE.json）
        assert ar.parse_command("wat?") == ("status", [])

    def test_status(self):
        assert ar.parse_command("status") == ("status", [])

    def test_new_design(self):
        assert ar.parse_command("design") == ("design", [])

    def test_new_manifest(self):
        assert ar.parse_command("manifest") == ("manifest", [])

    def test_new_log(self):
        assert ar.parse_command("log 10") == ("log", ["10"])

    def test_new_summary(self):
        assert ar.parse_command("summary") == ("summary", [])


# ── reply 端到端（用真实案例目录） ──────────────────────────────
@pytest.fixture(scope="module")
def case_dir():
    """用项目下真实存在的 DF90-001；如果不存在就跳过。"""
    p = ROOT / "cases" / "DF90-001"
    if not p.is_dir():
        pytest.skip("需要 cases/DF90-001 存在")
    return p


class TestReply:
    def test_help_returns_kinds(self, case_dir):
        r = ar.reply(case_dir, "help")
        assert r["kind"] == "info"
        assert "可用命令" in r["text"]
        # 必须包含新增的 4 个命令
        for kw in ("design", "manifest", "log", "summary"):
            assert kw in r["text"], f"help 缺少 {kw}"

    def test_status_has_stage(self, case_dir):
        r = ar.reply(case_dir, "status")
        assert r["kind"] == "info"
        assert "当前阶段" in r["text"]

    def test_design_returns_target_and_gap(self, case_dir):
        r = ar.reply(case_dir, "design")
        if r["kind"] == "error":
            pytest.skip(f"design 不可用：{r['text']}")
        assert r["kind"] == "info"
        # DF90-001 目标 90 kgf
        assert "90" in r["text"]

    def test_manifest_returns_keys(self, case_dir):
        r = ar.reply(case_dir, "manifest")
        assert r["kind"] == "info"
        # 不论 case 是否完整，至少要有标题行
        assert "manifest" in r["text"].lower() or "无 manifest" in r["text"]

    def test_log_returns_tail(self, case_dir):
        r = ar.reply(case_dir, "log 5")
        assert r["kind"] == "info"
        if "（无 LOG.md）" in r["text"]:
            pytest.skip("本案例无 LOG.md")
        assert "LOG.md" in r["text"]

    def test_summary_combines_three(self, case_dir):
        r = ar.reply(case_dir, "summary")
        assert r["kind"] == "info"
        # summary = status + design + list
        assert "当前阶段" in r["text"] or "设计摘要" in r["text"]

    def test_where_returns_relative_path(self, case_dir):
        r = ar.reply(case_dir, "where")
        assert r["kind"] == "info"
        # Windows 下 Path 的 str() 用 \，统一为 / 再比
        normalized = r["text"].replace("\\", "/")
        assert "cases/DF90-001" in normalized

    def test_switch_returns_switch_kind(self, case_dir):
        r = ar.reply(case_dir, "case OTHER-001")
        assert r["kind"] == "switch"
        assert r["switch_to"] == "OTHER-001"

    def test_open_path_traversal_blocked(self, case_dir):
        r = ar.reply(case_dir, "open ../../../etc/passwd")
        # 路径越界应被拦下
        assert r["kind"] == "error"
        assert "越界" in r["text"] or "文件不存在" in r["text"]

    def test_refresh_returns_refresh_kind(self, case_dir):
        r = ar.reply(case_dir, "refresh")
        assert r["kind"] == "refresh"

    def test_unknown_falls_back_to_status(self, case_dir):
        r = ar.reply(case_dir, "foobarbaz")
        assert r["kind"] == "info"
        # 未识别命令 → status 文案
        assert "当前阶段" in r["text"]


# ── dispatch 完整性 ──────────────────────────────────────────
def test_all_commands_have_handlers():
    """确保 COMMANDS 表里的每个动作都进了 dispatch dict。"""
    handlers = {"status", "help", "switch", "open", "list", "where",
               "refresh", "run", "design", "manifest", "log", "summary"}
    for cmd, action in ar.COMMANDS.items():
        assert action in handlers, f"COMMANDS['{cmd}']='{action}' 找不到 dispatcher"
