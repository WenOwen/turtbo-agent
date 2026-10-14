# memory

分支： `wu5-dev-flow`（从 master 拉出）。GitHub： `WenOwen/turtbo-agent`，已 `git push`。
最近 5 个提交：
```
fbeed1b feat(agent-web-ui): 三栏对话界面前端 + 启动脚本
fb45edb feat(agent-web): 三栏对话界面后端 —— FastAPI 13 路由 + stub agent
da2899f chore(refactor): 起步三栏 agent web UI 设计
11d574b chore: 同步看守状态（收尾，工作区干净）   ← master
b7e0438 feat(solve): G5 完成 —— 5000 rpm 收敛到判据，整机静推力实测 566.604 N = 57.78 kgf
```

## 当前任务与状态

主目标：重构 turtbo-agent，**跑通一个可视化 agent 对话 Web 界面**（右侧聊天框 / 左侧案例文件夹 / 中间 agent 操作可视化面板）。沿用现有数据层（liveview / case_watch / design_summary / version_graph），不重写设计工具，只重写 UI 与其服务端。

### 已落盘（远程）
1. `da2899f chore(refactor)` — 起步：memory + 设计文档 + 远端
2. `fb45edb feat(agent-web)` — 后端：FastAPI 13 路由 + WebSocket + 命令路由 + stub agent
   - 文件：`tools/agent_web.py`（446 行）、`tools/agent_reply.py`（192 行）
3. `fbeed1b feat(agent-web-ui)` — 前端：单文件三栏 240/1fr/360 + start-agent-web.cmd
   - 文件：`tools/agent_web_ui.html`（≈600 行）、`start-agent-web.cmd`

### 三栏 UI 实际验证
- `python -m uvicorn tools.agent_web:app --host 127.0.0.1 --port 8765` 启动 OK
- `GET /api/ping` → 200
- `GET /api/cases` → 200，3 个案例（DF90-001 v191/117 产物、DF90-002 v61/33 产物、DF120-HS-VERIFY v604/495 产物）
- `GET /api/state?case=DF90-001` → 200
- `GET /api/views?case=DF90-001` → 5 个分组（方案 / 设计值对照 / 几何 / 网格 / CFD 结果）
- `POST /api/chat {case:'DF90-001', text:'help'}` → 200，10 项命令字典
- `POST /api/run {case, action:'gate', params:{gate:'G2'}}` → 200，G2 通过 7/注 1/0/0
- `WS /ws?case=DF90-001` → 101 Switching Protocols
- `POST /api/file` 无 token → 403；有 token 但路径越界 → liveview 拒绝（符合 liveview 的 read-only 规则）
- 浏览器：HTML 23.7KB，token 已注入，`__DSH_TOKEN__` 残留 0

## 未解决问题与下一步

1. **README.md 更新** — 三栏 UI 段已写在本地，但工作区有平行会话的 WIP 改动，本次提交不污染其 diff。后续若主人确认可一并 commit。
2. **真实 LLM 接入** — stub agent 只识别命令（help/status/list/where/case/open/run/refresh）。下一步可加 `provider=anthropic` 或 `provider=openai` 选项，默认仍走 stub；用户前缀未匹配时给一段 LLM 解释而非 echo status。
3. **操作面板的细动作** — 现阶段只把"跑闸门"接通；后续接：把某条 case 文件编辑后端到端、加/删/查 manifest 字段、把 gate check 的"行不通原因"反向回写到对话。
4. **chat 持久化** — 当前 `CHAT_LOG` 是内存 Dict，断电即丢；下一步可挂 `cases/<id>/_watch/chat.jsonl`（与 `changes.jsonl` 同目录）。
5. **WS 鉴权** — 当前 `WS /ws` 不校验 token。下一轮接 `?token=` 头，复用 `SESSION_TOKEN`。
6. **preflight 失败** — 跑 `run preflight` 报 `OSError(8, '%1 不是有效的 Win32 应用程序')`。这是工具自身的兼容问题，与 agent_web 无关；不阻塞本次重构。

## 仍然有效的决定

- 主分支保留 master 不动；重构在 wu5-dev-flow 分支。
- 三个面板分工与一个独立聊天 UI，沿用既有数据层；不引入 agent 框架。
- 不重写设计工具（gate_check / case_ledger / design_summary 复用）。
- 每步独立可验证；当前任务 ✅ 提交号 `fbeed1b`（UI）、`fb45edb`（后端）、`da2899f`（设计）。
- 不混合主人另一会话的 WIP；仅在确认无污染时落盘。
