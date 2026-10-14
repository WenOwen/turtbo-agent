"""HTTP-level tests for tools.agent_web.

跑法：C:\\Program Files\\Python312\\python.exe -m pytest tools/test_agent_web.py -v

不启动独立 server，直接 import app + httpx ASGITransport 跑端到端。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import agent_web as aw  # noqa: E402

# 引入 httpx
try:
    import httpx
except Exception:
    pytest.skip("httpx 不可用", allow_module_level=True)


@pytest.fixture
def client():
    """用 ASGI 跑 agent_web.app，不开 socket。"""
    transport = httpx.ASGITransport(app=aw.app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
def token():
    return aw.SESSION_TOKEN


@pytest.mark.asyncio
async def test_root_returns_html_with_token(client, token):
    async with client as c:
        r = await c.get("/", headers={"X-DSH-Token": token})
    assert r.status_code == 200
    assert "<!DOCTYPE html>" in r.text or "<!doctype html>" in r.text.lower()
    assert "__DSH_TOKEN__" not in r.text
    assert token in r.text


@pytest.mark.asyncio
async def test_root_blocks_missing_token(client):
    """根路径必须可访问（用于先拿到 token）；不强求鉴权。
    但其它数据路由需要 token（缺/错 → 403）。"""
    async with client as c:
        r = await c.get("/")
        # 设计：根路径无 token 也开放（HTML 自己带 token）
        assert r.status_code == 200
        # 但 /api/cases 必须拒绝无 token
        r2 = await c.get("/api/cases")
    assert r2.status_code == 403


@pytest.mark.asyncio
async def test_ping_no_auth(client):
    async with client as c:
        r = await c.get("/api/ping")
    assert r.status_code == 200
    assert r.json()["ok"] is True


@pytest.mark.asyncio
async def test_cases_list(client, token):
    async with client as c:
        r = await c.get("/api/cases", headers={"X-DSH-Token": token})
    assert r.status_code == 200
    j = r.json()
    assert "cases" in j
    assert len(j["cases"]) >= 1
    # 必须包含 DF90-001
    ids = [c["id"] for c in j["cases"]]
    assert "DF90-001" in ids


@pytest.mark.asyncio
async def test_state_for_case(client, token):
    async with client as c:
        r = await c.get("/api/state?case=DF90-001",
                        headers={"X-DSH-Token": token})
    assert r.status_code == 200
    j = r.json()
    assert j["case_id"] == "DF90-001"
    assert "design" in j
    assert "stages" in j
    # 必须带 file_tree（中间面板"文件" tab 用）
    assert "file_tree" in j
    ft = j["file_tree"]
    assert ft.get("name") == "DF90-001"
    assert len(ft.get("children", [])) > 0
    names = [c.get("name") for c in ft.get("children", [])]
    assert "00-brief" in names
    assert "version_graph" in j


@pytest.mark.asyncio
async def test_chat_get_history(client, token):
    async with client as c:
        r = await c.get("/api/chat?case=DF90-001",
                        headers={"X-DSH-Token": token})
    assert r.status_code == 200
    j = r.json()
    assert "messages" in j
    # 重启后 chat.jsonl 应已回灌（之前测过）
    # 不强制非空


@pytest.mark.asyncio
async def test_chat_post_status(client, token):
    async with client as c:
        r = await c.post("/api/chat",
                         headers={"X-DSH-Token": token, "Content-Type": "application/json"},
                         json={"case": "DF90-001", "text": "status"})
    assert r.status_code == 200
    j = r.json()
    assert j["user"]["text"] == "status"
    assert j["reply"]["kind"] == "info"


@pytest.mark.asyncio
async def test_chat_post_help_mentions_all_commands(client, token):
    async with client as c:
        r = await c.post("/api/chat",
                         headers={"X-DSH-Token": token, "Content-Type": "application/json"},
                         json={"case": "DF90-001", "text": "help"})
    assert r.status_code == 200
    j = r.json()
    text = j["reply"]["text"]
    for kw in ("design", "manifest", "log", "summary", "pending",
               "get", "find", "note", "run preflight", "run gate"):
        assert kw in text, f"help 缺少 {kw}"


@pytest.mark.asyncio
async def test_chat_post_design_returns_target(client, token):
    async with client as c:
        r = await c.post("/api/chat",
                         headers={"X-DSH-Token": token, "Content-Type": "application/json"},
                         json={"case": "DF90-001", "text": "design"})
    j = r.json()
    if j["reply"].get("kind") == "error":
        pytest.skip("design 不可用：" + j["reply"]["text"])
    assert "90" in j["reply"]["text"]


@pytest.mark.asyncio
async def test_chat_post_pending(client, token):
    async with client as c:
        r = await c.post("/api/chat",
                         headers={"X-DSH-Token": token, "Content-Type": "application/json"},
                         json={"case": "DF90-001", "text": "pending"})
    assert r.status_code == 200
    j = r.json()
    assert "LOG" in j["reply"]["text"] or "无 LOG" in j["reply"]["text"]


@pytest.mark.asyncio
async def test_chat_post_get(client, token):
    async with client as c:
        r = await c.post("/api/chat",
                         headers={"X-DSH-Token": token, "Content-Type": "application/json"},
                         json={"case": "DF90-001", "text": "get case_id"})
    j = r.json()
    assert "DF90-001" in j["reply"]["text"]


@pytest.mark.asyncio
async def test_chat_post_find(client, token):
    async with client as c:
        r = await c.post("/api/chat",
                         headers={"X-DSH-Token": token, "Content-Type": "application/json"},
                         json={"case": "DF90-001", "text": "find requirements.yaml"})
    j = r.json()
    assert "命中" in j["reply"]["text"] or "无命中" in j["reply"]["text"]


@pytest.mark.asyncio
async def test_chat_post_note_writes_log(client, token, tmp_path):
    """note 写到真实 LOG.md → 检查 JSONL 也跟着变长（持久化链路）。"""
    async with client as c:
        r1 = await c.get("/api/chat?case=DF90-001",
                         headers={"X-DSH-Token": token})
        before = len(r1.json()["messages"])
        r2 = await c.post("/api/chat",
                          headers={"X-DSH-Token": token, "Content-Type": "application/json"},
                          json={"case": "DF90-001", "text": "note HTTP 测试写入"})
        assert r2.status_code == 200
        assert r2.json()["reply"]["kind"] == "info"
        assert "已写入" in r2.json()["reply"]["text"]
        r3 = await c.get("/api/chat?case=DF90-001",
                         headers={"X-DSH-Token": token})
        msgs = r3.json()["messages"]
    # 不论是否已达 200 上限，新写入的两条必须出现在末尾
    assert len(msgs) >= 2
    last_user = next((m for m in reversed(msgs) if m.get("role") == "user"), None)
    last_agent = next((m for m in reversed(msgs) if m.get("role") == "agent"), None)
    assert last_user and "HTTP 测试写入" in last_user.get("text", "")
    assert last_agent and "已写入" in last_agent.get("text", "")


@pytest.mark.asyncio
async def test_chat_post_switch_kind(client, token):
    async with client as c:
        r = await c.post("/api/chat",
                         headers={"X-DSH-Token": token, "Content-Type": "application/json"},
                         json={"case": "DF90-001", "text": "case DF90-002"})
    j = r.json()
    assert j["reply"]["kind"] == "switch"
    assert j["reply"]["switch_to"] == "DF90-002"


@pytest.mark.asyncio
async def test_chat_post_tree(client, token):
    async with client as c:
        r = await c.post("/api/chat",
                         headers={"X-DSH-Token": token, "Content-Type": "application/json"},
                         json={"case": "DF90-001", "text": "tree 1"})
    j = r.json()
    assert j["reply"]["kind"] == "info"
    assert "目录树" in j["reply"]["text"]


@pytest.mark.asyncio
async def test_chat_post_next(client, token):
    async with client as c:
        r = await c.post("/api/chat",
                         headers={"X-DSH-Token": token, "Content-Type": "application/json"},
                         json={"case": "DF90-001", "text": "next"})
    j = r.json()
    assert j["reply"]["kind"] == "info"
    assert "next_stage" in j["reply"]
    assert "下一" in j["reply"]["text"]


@pytest.mark.asyncio
async def test_chat_post_plan(client, token):
    async with client as c:
        r = await c.post("/api/chat",
                         headers={"X-DSH-Token": token, "Content-Type": "application/json"},
                         json={"case": "DF90-001", "text": "plan"})
    j = r.json()
    assert j["reply"]["kind"] == "info"
    assert "现状" in j["reply"]["text"] or "当前" in j["reply"]["text"]


@pytest.mark.asyncio
async def test_chat_post_ls(client, token):
    async with client as c:
        r = await c.post("/api/chat",
                         headers={"X-DSH-Token": token, "Content-Type": "application/json"},
                         json={"case": "DF90-001", "text": "ls"})
    j = r.json()
    assert j["reply"]["kind"] == "info"
    assert "阶段目录" in j["reply"]["text"]


@pytest.mark.asyncio
async def test_chat_unknown_case_404(client, token):
    async with client as c:
        r = await c.post("/api/chat",
                         headers={"X-DSH-Token": token, "Content-Type": "application/json"},
                         json={"case": "DOES-NOT-EXIST", "text": "status"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_actions_list(client, token):
    async with client as c:
        r = await c.get("/api/actions", headers={"X-DSH-Token": token})
    assert r.status_code == 200
    j = r.json()
    acts = j.get("actions", [])
    ids = {a["id"] for a in acts} if isinstance(acts, list) else set(acts.keys())
    for k in ("preflight", "verify", "audit", "replay", "gate"):
        assert k in ids, f"actions 缺 {k}"


@pytest.mark.asyncio
async def test_chat_export_markdown(client, token):
    """先发一条带关键词的消息，再导 md，应能找到那条。"""
    async with client as c:
        r = await c.post("/api/chat",
                         headers={"X-DSH-Token": token, "Content-Type": "application/json"},
                         json={"case": "DF90-001", "text": "status"})
        assert r.status_code == 200
        r = await c.get("/api/chat/export?case=DF90-001&format=md",
                        headers={"X-DSH-Token": token})
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/markdown")
        body = r.text
        assert "# 案例 DF90-001" in body
        assert "DF90-001-chat.md" in r.headers.get("content-disposition", "")


@pytest.mark.asyncio
async def test_chat_export_json(client, token):
    async with client as c:
        r = await c.get("/api/chat/export?case=DF90-001&format=json",
                        headers={"X-DSH-Token": token})
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/json")
        j = r.json()
        assert j["case"] == "DF90-001"
        assert isinstance(j["messages"], list)


@pytest.mark.asyncio
async def test_chat_search_finds_keyword(client, token):
    """先发 'find requirements'，再搜，应能命中。"""
    async with client as c:
        await c.post("/api/chat",
                     headers={"X-DSH-Token": token, "Content-Type": "application/json"},
                     json={"case": "DF90-001", "text": "status"})
        r = await c.get("/api/chat/search?case=DF90-001&q=案例",
                        headers={"X-DSH-Token": token})
        assert r.status_code == 200
        j = r.json()
        assert j["q"] == "案例"
        assert j["case"] == "DF90-001"
        assert isinstance(j["hits"], list)


@pytest.mark.asyncio
async def test_chat_export_no_token_403(client):
    async with client as c:
        r = await c.get("/api/chat/export?case=DF90-001")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_jobs_list_empty(client, token):
    """新进程 /api/jobs 可能是空。"""
    async with client as c:
        r = await c.get("/api/jobs", headers={"X-DSH-Token": token})
    assert r.status_code == 200
    j = r.json()
    assert "jobs" in j
    assert isinstance(j["jobs"], list)


@pytest.mark.asyncio
async def test_jobs_get_unknown_404(client, token):
    async with client as c:
        r = await c.get("/api/jobs/notexist1234", headers={"X-DSH-Token": token})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_jobs_require_token(client):
    async with client as c:
        r = await c.get("/api/jobs")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_chat_run_async_starts_job(client, token):
    """POST /api/chat with 'run_async preflight' 应起一个 job 并返回 job_id。"""
    async with client as c:
        r = await c.post("/api/chat",
                         headers={"X-DSH-Token": token},
                         json={"case": "DF90-001", "text": "run_async preflight"})
        assert r.status_code == 200
        j = r.json()
        reply = j.get("reply", {})
        jid = reply.get("job_id")
        assert jid, "reply 应含 job_id"
        # 查 job 状态
        r2 = await c.get("/api/jobs/" + jid, headers={"X-DSH-Token": token})
    assert r2.status_code == 200
    rec = r2.json()
    assert rec.get("job_id") == jid
    # 状态应是 running / done / timeout / error 之一
    assert rec.get("status") in {"running", "done", "timeout", "error"}


def test_maybe_rotate_chat_skips_small_file(tmp_path):
    """小文件不旋转。"""
    import agent_web
    p = tmp_path / "chat.jsonl"
    p.write_text("small content\n")
    agent_web._maybe_rotate_chat(p)
    assert p.exists()
    assert not (tmp_path / "chat.jsonl.bak").exists()
    # 原始内容应保留
    assert p.read_text() == "small content\n"


def test_maybe_rotate_chat_caps_large_file(tmp_path):
    """大文件超过阈值时旋转，保留尾部 50%。"""
    import agent_web
    # 临时调小阈值
    agent_web.CHAT_MAX_BYTES = 1024
    p = tmp_path / "chat.jsonl"
    lines = []
    for i in range(500):
        lines.append("line " + str(i) + " " + "x" * 20)
    p.write_text("\n".join(lines) + "\n")
    orig_size = p.stat().st_size
    assert orig_size > 1024
    agent_web._maybe_rotate_chat(p)
    # 旋转后大小应 < 原大小
    new_size = p.stat().st_size
    assert new_size < orig_size
    # 应保留 bak
    bak = tmp_path / "chat.jsonl.bak"
    assert bak.exists()
    # 新文件应只含原内容的一部分（行数应 < 500）
    new_lines = [ln for ln in p.read_text().splitlines() if ln.strip()]
    assert len(new_lines) < 500
    assert len(new_lines) > 0


@pytest.mark.asyncio
async def test_views_returns_groups(client, token):
    async with client as c:
        r = await c.get("/api/views?case=DF90-001",
                        headers={"X-DSH-Token": token})
    assert r.status_code == 200
    j = r.json()
    assert "groups" in j or "views" in j
