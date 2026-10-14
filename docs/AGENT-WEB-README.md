# 三栏 Agent 对话界面（主入口）

> 这是一份独立说明，README.md 的内容正由并行会话维护。
> 真正的"主入口" 改这块的描述请直接读这份文件。

`tools/agent_web.py` + `tools/agent_web_ui.html` 是一站式的
"案例 + 可视化 + 对话" 主面板，按以下步骤起服务后用浏览器打开
`http://127.0.0.1:8765/`：

```powershell
双击  start-agent-web.cmd
# 或
python -m uvicorn tools.agent_web:app --host 127.0.0.1 --port 8765
```

| 面板 | 角色 | 干的事 |
|---|---|---|
| **左侧** | 案例文件夹 | `cases/` 下所有登记案例；搜索框；点选 → 中间面板立刻更新 |
| **中间** | agent 操作可视化 | tabs：总览（阶段时间线 / 设计摘要 / 进程 / 最近改动）/ 可视化（几何、网格、CFD 图组）/ 日志 / 操作（跑检查/校验/预检/回放/闸门） |
| **右侧** | 聊天框 | 与 agent 对话：`help` / `status` / `list` / `where` / `case <id>` / `open <path>` / `run preflight` / `run gate G<0..6>` / `run verify` / `run audit` / `run replay` / `refresh` / `design` / `manifest` / `log [N]` / `summary` |

> 这个界面是新增的"主入口"，并未取代上面的工作台。`start-liveview.cmd` 仍然可用。
> 数据来自 `tools/liveview.py` 的同一份 `Aggregator` / `build_views` / `ACTIONS`。

**会话令牌**：服务端启动时生成 `secrets.token_urlsafe(24)`，
所有写操作（`POST /api/file`）都必须带 `X-DSH-Token` 头，与 `liveview` 同款三道门。
浏览器打开页面时令牌已自动注入 `__DSH_TOKEN__`，无需手动复制。
WS 链接也带 `?token=`，错就 403。

**聊天持久化**：每次发消息落到 `cases/<id>/_watch/chat.jsonl`（v=1，带 case/ts/msg）。
重启服务后会自动回灌最近 200 条。
测试 marker `__persist_test_*` 是开发时留下的，请不要在生产用。

**零依赖**：仅需 `fastapi` / `uvicorn` / `pydantic` / `websockets`（已装），不引入新包。

## 跑通检查

```powershell
# 1) 起服务（后台）
python -m uvicorn tools.agent_web:app --host 127.0.0.1 --port 8765

# 2) 基本端点
curl http://127.0.0.1:8765/api/ping
curl http://127.0.0.1:8765/api/cases
curl 'http://127.0.0.1:8765/api/state?case=DF90-001'

# 3) 聊天（要带 X-DSH-Token；启动时打印）
curl -X POST http://127.0.0.1:8765/api/chat \
  -H "X-DSH-Token: $env:AGENT_TOKEN" -H "Content-Type: application/json" \
  -d '{"case":"DF90-001","text":"summary"}'

# 4) 跑闸门
curl -X POST http://127.0.0.1:8765/api/run \
  -H "X-DSH-Token: $env:AGENT_TOKEN" -H "Content-Type: application/json" \
  -d '{"case":"DF90-001","action":"gate","params":{"gate":"G2"}}'
```

## 单元测试

```powershell
python -m pytest tools/test_agent_reply.py -v
# 27 个用例：parse_command、dispatch、端到端 reply
```

## 限制

- 聊天是 stub agent（解析 + 跑 CLI），未接 LLM
- chat.jsonl 没有上限；只缓存 200 条但磁盘会涨
- 串行 LLM 调用未接（无 ANTHROPIC_API_KEY / OPENAI_API_KEY）
- WS 重连没做指数退避；网络断了页面要刷新

## 文件清单

| 文件 | 行数 | 作用 |
|---|---|---|
| `tools/agent_web.py` | ~520 | FastAPI 13 路由 + WS + 聊天持久化 |
| `tools/agent_reply.py` | ~300 | 命令解析 + 14 个 handler + 真实 CLI 调子进程 |
| `tools/agent_web_ui.html` | ~600 | 三栏 HTML + CSS grid + 原生 JS（无框架） |
| `tools/test_agent_reply.py` | 165 | 27 个 pytest 用例 |
| `start-agent-web.cmd` | 12 | Windows 一键启动 |
| `docs/REFACTOR-DESIGN.md` | — | 设计说明 + 路由表 + 落盘节奏 |
| `docs/AGENT-WEB-README.md` | — | 本文件 |
