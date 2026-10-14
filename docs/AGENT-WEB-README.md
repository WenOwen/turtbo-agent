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
| **左侧** | 案例文件夹 + 文件 + 后台任务 | `cases/` 下所有登记案例（带搜索）；当前案例最近 12 个文件（点击发到聊天）；后台任务列表（点击查 job 结果） |
| **中间** | agent 操作可视化 | tabs：总览（阶段时间线 / 设计摘要 / 进程 / 最近改动）/ **版本**（liveview version_graph 节点边问题数）/ **文件**（目录树 深度 3）/ **日志** / **操作**（跑检查/校验/预检/回放/闸门） |
| **右侧** | 聊天框 | 13 个 quickbar 按钮 + 文本输入；mdLite 渲染；命中后回 `open`/`run`/`switch` 的可点 link；发送中提示 + 耗时显示 + 清屏 |

> 这个界面是新增的"主入口"，并未取代上面的工作台。`start-liveview.cmd` 仍然可用。
> 数据来自 `tools/liveview.py` 的同一份 `Aggregator` / `build_views` / `ACTIONS`。

**会话令牌**：服务端启动时生成 `secrets.token_urlsafe(24)`，
所有数据路由（`/api/cases`、`/api/state`、`/api/views`、`/api/asset`、`/api/file`、
`/api/chat`、`/api/actions`、`/api/jobs`）都必须带 `X-DSH-Token` 头或 `?token=`。
浏览器打开页面时令牌已自动注入 `__DSH_TOKEN__`，无需手动复制。
WS 链接也带 `?token=`，错就 403。`/` 与 `/api/ping` 仍开放（前者带 token，后者是存活探针）。

**聊天持久化**：每次发消息落到 `cases/<id>/_watch/chat.jsonl`（v=1，带 case/ts/msg）。
重启服务后会自动回灌最近 200 条。
测试 marker `__persist_test_*` 是开发时留下的，请不要在生产用。

**后台任务**：发 `run_async preflight` / `run_async gate G3` / `run_async verify` /
`run_async audit` / `run_async replay` 会起后台线程跑子进程，**不阻塞聊天框**；
立即返回 `job_id`。查结果发 `job <id>`，列所有发 `jobs`。
左栏 "后台任务" 区域会实时显示状态（⏳/✓/⏱/✗），点击查结果。
**零依赖**：仅需 `fastapi` / `uvicorn` / `pydantic` / `websockets`（已装），不引入新包。
**LLM 接入**：`env ANTHROPIC_API_KEY=sk-...` 时未知命令自动调 claude-haiku-4-5；
没设或调用失败回退到关键词模糊建议（"我下一步干嘛" → `next`）。

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
python -m pytest tools/test_agent_reply.py tools/test_agent_web.py -v
# 当前 83 个用例：parse_command、dispatch、端到端 reply、HTTP 端点、jobs、run_async、LLM fallback
```

## 限制

- chat.jsonl 没有上限；只缓存 200 条但磁盘会涨（待加滚动切割）
- WS 重连没做指数退避；网络断了页面要刷新
- run_async 任务超时是 900 秒，preflight/gate 实际不会到上限
- 长期任务在前台时 console 不会显示，要去 /api/jobs 看

## 文件清单

| 文件 | 行数 | 作用 |
|---|---|---|
| `tools/agent_web.py` | ~600 | FastAPI 15 路由 + WS + 聊天持久化 + 后台任务 |
| `tools/agent_reply.py` | ~700 | 命令解析 + 22 个 handler + LLM fallback + 真实 CLI 调子进程 |
| `tools/job_state.py` | ~60 | 后台任务共享状态（线程安全） |
| `tools/agent_web_ui.html` | ~940 | 三栏 HTML + CSS grid + 原生 JS（无框架） |
| `tools/test_agent_reply.py` | ~370 | 56 个 pytest 用例（parse / reply / suggest / LLM / jobs） |
| `tools/test_agent_web.py` | ~330 | 27 个 HTTP 用例（ASGITransport） |
| `start-agent-web.cmd` | 12 | Windows 一键启动 |
| `docs/REFACTOR-DESIGN.md` | — | 设计说明 + 路由表 + 落盘节奏 |
| `docs/AGENT-WEB-README.md` | — | 本文件 |
