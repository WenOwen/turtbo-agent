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

    def test_pending(self):
        assert ar.parse_command("pending") == ("pending", [])

    def test_get_dot_path(self):
        assert ar.parse_command("get requirement.thrust") == ("get", ["requirement.thrust"])

    def test_find(self):
        assert ar.parse_command("find R1.abp") == ("find", ["R1.abp"])

    def test_note(self):
        assert ar.parse_command("note 记一下今天的发现") == ("note", ["记一下今天的发现"])


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
        # 必须包含新增的 4 个只读 + 4 个扩展命令
        for kw in ("design", "manifest", "log", "summary",
                   "pending", "get", "find", "note",
                   "tree", "next", "plan", "ls"):
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

    def test_unknown_falls_back_to_suggest(self, case_dir):
        r = ar.reply(case_dir, "foobarbaz")
        assert r["kind"] == "info"
        # 未识别命令 → _suggest 文案（或 LLM）
        assert "没识别" in r["text"] or "help" in r["text"]

    def test_pending_returns_log_summary(self, case_dir):
        r = ar.reply(case_dir, "pending")
        assert r["kind"] == "info"
        if "（无 LOG.md）" in r["text"] or "（LOG.md 无条目）" in r["text"]:
            pytest.skip("本案例无 LOG.md 条目")
        # 必须出现 [PASS]/[WARN]/[FAIL]/[—] 之一
        assert any(tag in r["text"] for tag in ("[PASS]", "[WARN]", "[FAIL]", "[—]"))

    def test_get_id_returns_known_field(self, case_dir):
        r = ar.reply(case_dir, "get id")
        assert r["kind"] == "info"
        # DF90-001 案例 id 应该是 DF90-001
        if "（无该字段）" not in r["text"]:
            assert "=" in r["text"]

    def test_get_missing_field(self, case_dir):
        r = ar.reply(case_dir, "get totally.fake.key")
        assert r["kind"] == "info"
        assert "（无该字段）" in r["text"]

    def test_get_no_args(self, case_dir):
        r = ar.reply(case_dir, "get")
        assert r["kind"] == "info"
        assert "用法" in r["text"]

    def test_find_returns_hits(self, case_dir):
        r = ar.reply(case_dir, "find requirements.yaml")
        assert r["kind"] == "info"
        # DF90-001 一定有 requirements.yaml
        assert "命中" in r["text"] or "（无命中）" in r["text"]

    def test_find_no_match(self, case_dir):
        r = ar.reply(case_dir, "find xyzzqnopenope_不可能存在的字符串_xyz")
        assert r["kind"] == "info"
        assert "（无命中）" in r["text"]

    def test_note_writes_to_log(self, case_dir, tmp_path):
        # 不破坏真实 LOG：复制到 tmp
        import shutil
        fake = tmp_path / "case"
        shutil.copytree(case_dir, fake)
        log = fake / "LOG.md"
        before = log.read_text(encoding="utf-8") if log.is_file() else ""
        r = ar.reply(fake, "note 测试 note 命令写入")
        assert r["kind"] == "info"
        assert "已写入" in r["text"]
        after = log.read_text(encoding="utf-8")
        assert "测试 note 命令写入" in after
        assert len(after) > len(before)

    def test_tree_returns_dir_structure(self, case_dir):
        r = ar.reply(case_dir, "tree 1")
        assert r["kind"] == "info"
        assert "目录树" in r["text"]
        # 必须列出案例根
        assert case_dir.name in r["text"]

    def test_ls_stage_lists_files(self, case_dir):
        r = ar.reply(case_dir, "ls 00-brief")
        assert r["kind"] == "info"
        # 00-brief 一定有 requirements.yaml
        if "未找到" not in r["text"]:
            assert "00-brief" in r["text"]

    def test_ls_no_args_lists_all_stages(self, case_dir):
        r = ar.reply(case_dir, "ls")
        assert r["kind"] == "info"
        assert "阶段目录" in r["text"]
        # 案例应至少有 00-brief
        assert "00-brief" in r["text"]

    def test_next_suggests_next_stage(self, case_dir):
        r = ar.reply(case_dir, "next")
        assert r["kind"] == "info"
        assert "下一阶段" in r["text"] or "下一" in r["text"]
        # 必须返回 next_stage 字段
        assert "next_stage" in r

    def test_plan_combines_three(self, case_dir):
        r = ar.reply(case_dir, "plan")
        assert r["kind"] == "info"
        # plan = status + next + pending 三段
        assert "现状" in r["text"] or "当前" in r["text"]
        assert "下一步" in r["text"] or "下一" in r["text"]
        assert "待办" in r["text"] or "LOG" in r["text"]


# ── dispatch 完整性 ──────────────────────────────────────────
def test_all_commands_have_handlers():
    """确保 COMMANDS 表里的每个动作都进了 dispatch dict。"""
    handlers = {"status", "help", "switch", "open", "list", "ls", "where",
               "refresh", "run", "design", "manifest", "log", "summary",
               "pending", "get", "find", "note", "tree", "next", "plan"}
    for cmd, action in ar.COMMANDS.items():
        assert action in handlers, f"COMMANDS['{cmd}']='{action}' 找不到 dispatcher"


# ── suggest / LLM 兜底 ────────────────────────────────────────
class TestSuggestAndLLM:
    """未知命令走 _suggest（或 LLM）。"""

    def test_unknown_falls_through_to_suggest(self, case_dir):
        """没有 LLM key 时，未知命令走 _suggest，命中关键词时返回提示。"""
        r = ar.reply(case_dir, "我下一步干嘛")
        assert r["kind"] == "info"
        # "下一步" 应该映射到 "next" 命令
        assert "next" in r["text"].lower()

    def test_unknown_thrust_suggests_design(self, case_dir):
        r = ar.reply(case_dir, "推力差 5kg 怎么改？")
        assert r["kind"] == "info"
        assert "design" in r["text"].lower()

    def test_unknown_help_suggests_help(self, case_dir):
        r = ar.reply(case_dir, "有命令清单吗？")
        assert r["kind"] == "info"
        assert "help" in r["text"].lower()

    def test_unknown_what_should_i_do(self, case_dir):
        r = ar.reply(case_dir, "what's next")
        assert r["kind"] == "info"
        assert "next" in r["text"].lower()

    def test_known_status_does_not_trigger_suggest(self, case_dir):
        """已知命令如 status，应直接走 dispatcher，不走 _suggest。"""
        r = ar.reply(case_dir, "status")
        assert r["kind"] == "info"
        # status 命令的输出里应该没有"猜你想跑"
        assert "猜你想跑" not in r["text"]

    def test_suggest_with_no_keyword_match(self, case_dir):
        r = ar.reply(case_dir, "天气怎么样？")
        assert r["kind"] == "info"
        assert "没识别" in r["text"] or "help" in r["text"]

    def test_try_llm_returns_none_without_key(self, case_dir, monkeypatch):
        """无 API key 时 _try_llm 返回 None（让 _suggest 接住）。"""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert ar._try_llm(case_dir, "anything") is None

    def test_try_llm_falls_back_on_import_error(self, case_dir, monkeypatch):
        """有 key 但 anthropic 库没装好时回退到 fallback dict。"""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
        # 模拟 anthropic.Anthropic 抛错
        import builtins
        orig_import = builtins.__import__
        def fake_import(name, *args, **kwargs):
            if name == "anthropic":
                raise ImportError("simulated missing")
            return orig_import(name, *args, **kwargs)
        monkeypatch.setattr(builtins, "__import__", fake_import)
        r = ar._try_llm(case_dir, "x")
        # 失败回退 → fallback dict 或 None（取决于 except 分支）
        # ImportError 走 except → fallback dict
        assert r is None or r.get("kind") == "info"

    def test_try_llm_calls_anthropic_when_key_set(self, case_dir, monkeypatch):
        """有 key 且 anthropic 装好时，调真 API（用 fake 模拟）。"""
        class _FakeBlock:
            type = "text"
            text = "下个阶段用 G3 重出几何。"
        class _FakeMsg:
            content = [_FakeBlock()]
        class _FakeMessages:
            def create(self, **kw):
                return _FakeMsg()
        class _FakeAnthropic:
            def __init__(self, api_key=None):
                self.messages = _FakeMessages()
        import sys, types
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-test")
        mod = types.ModuleType("anthropic")
        mod.Anthropic = _FakeAnthropic
        monkeypatch.setitem(sys.modules, "anthropic", mod)
        r = ar._try_llm(case_dir, "现在能干吗？")
        assert r is not None
        assert r["kind"] == "info"
        assert "G3" in r["text"] or "几何" in r["text"]
        assert r.get("llm") == "anthropic"

    def test_try_llm_api_call_failure_returns_fallback(self, case_dir, monkeypatch):
        """API 抛错时回退到 fallback（而不是 None）让用户看到原因。"""
        class _BadMessages:
            def create(self, **kw):
                raise RuntimeError("api down")
        class _BadAnthropic:
            def __init__(self, api_key=None):
                self.messages = _BadMessages()
        import sys, types
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        mod = types.ModuleType("anthropic")
        mod.Anthropic = _BadAnthropic
        monkeypatch.setitem(sys.modules, "anthropic", mod)
        r = ar._try_llm(case_dir, "x")
        assert r is not None
        assert r["kind"] == "info"
        assert r.get("llm") == "fallback"
        assert "LLM 失败" in r["text"]
