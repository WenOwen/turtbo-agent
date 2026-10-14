# Refactor 设计：可视化 Agent 对话 Web 界面

日期：2026-10-14。分支： `wu5-dev-flow`。目标：跑通一个三栏布局的 agent 对话 Web 界面。

## 用户场景

第一位用户是项目设计者本人。第一项用途是边做涵道风扇气动设计、边和 agent 对话、边看实时变化。三个面板：

- **左侧（案例文件夹）**：工作区 `cases/` 下的所有案例（按修改时间倒序）。点选 → 中间面板立刻更新。
- **中间（agent 操作可视化）**：沿用 `liveview.py` 的现有数据汇总（阶段时间线、版本关系图、最近改动、进程、工程日志），改造为卡片列表。
- **右侧（聊天框）**：和 agent 聊天的输入框 + 消息流。常见动作按钮：刷新、跑预检、跑检查、查看文件等。

## 复用与边界

- 复用：`Aggregator` 主体（state / manifest / log / processes / design / version_graph / watch / cases）。
- 复用：`build_views`（几何、网格、CFD 图组）。
- 复用：`case_ledger.log`、`gate_check.py`、`preflight.py` 等子命令。
- 新增：聊天消息流（`chat.py`）、WebSocket 推送、命令路由。
- 不做：迁移到其他 agent 框架；重写 design_summary / gate_check。

## 服务端

`tools/agent_web.py`（基于 `liveview.py`，但拆分为 FastAPI）：

| 路由 | 用途 |
| --- | --- |
| `GET /` | 加载三栏 UI。 |
| `GET /api/cases` | 案例列表。 |
| `GET /api/state?case=` | 当前案例的完整 state（中间面板一次拉全）。 |
| `GET /api/views?case=&force=` | 中间面板的可视化分组。 |
| `GET /api/file?path=` | 读文件（受限路径）。 |
| `POST /api/file` | 写文件（乐观锁）。 |
| `GET /api/chat?case=` | 聊天历史。 |
| `POST /api/chat` | 发消息；返回 agent 回复。 |
| `GET /api/actions` | 工具动作白名单（gate / verify / preflight / replay / audit）。 |
| `POST /api/run` | 跑白名单动作。 |
| `WS /ws?case=` | 推送 watch tick + chat 增量。 |

会话令牌、Host 校验、跨站检查：与 liveview 完全相同的三道门。

聊天命令识别（关键字 → 行为）：

| 用户输入前缀 | 行为 |
| --- | --- |
| `case <id>` | 切换案例；回显已切换。 |
| `open <relpath>` | 读文件并把首 200 字回灌到对话。 |
| `run preflight` | 调预检子进程，把 stdout 摘要回灌。 |
| `run gate G3` | 跑 G3 检查，回灌结论。 |
| `run verify` / `run audit` / `run replay` | 同上。 |
| `help` | 列出命令。 |
| 其它 | 由 `tools/agent_reply.py`（新文件）作为 stub agent：先 echo，再贴该 case 的最近改动的文件 1 条与 current_stage。 |

## 前端

`tools/agent_web_ui.html`：单文件三栏布局。

- 左侧：案例列表 + 搜索框。
- 中间：阶段时间线 + 版本图 + 视图卡片 + 进程 + 日志尾部 + 动作面板。
- 右侧：聊天历史 + 输入框 + 工具栏。

状态由 `GET /api/state` 一次拉全，前端用 diff 渲染；增量由 WebSocket 推送。

## 验证

| 项 | 命令 |
| --- | --- |
| 服务能起 | `python tools/agent_web.py --port 8910 --no-browser` |
| 案例列表 | `curl http://127.0.0.1:8910/api/cases` |
| 中间面板数据 | `curl 'http://127.0.0.1:8910/api/state?case=DF90-001'` |
| 聊天发收 | `curl -X POST -H 'Content-Type: application/json' -d '{"case":"DF90-001","text":"help"}' http://127.0.0.1:8910/api/chat` |
| 浏览器 | 双击 start-agent-web.cmd，浏览器自动打开 `http://127.0.0.1:8910/`。 |

## 落盘节奏

1. `chore(refactor)` 设计 + memory（本文）。
2. `feat(agent-web)` 后端 + FastAPI + WebSocket + 命令路由 + agent_reply。
3. `feat(agent-web-ui)` 前端 + start-agent-web.cmd。
4. `docs(refactor)` README + 快速开始。