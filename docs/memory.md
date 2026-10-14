# memory

分支： `wu5-dev-flow`（从 master 拉出）。GitHub： `WenOwen/turtbo-agent`，已 `git push`。
最近 16 个提交（newest first）：
```
1d2fbc2 fix(agent-web-ui): loadCases 带 token + URL ?case= 直链自动选案例
616570f feat(agent-web-ui): 进程列表可点击跳日志
f05be2b feat(agent-web): chat.jsonl 超 5MB 自动滚动（保留尾部 50%）
e766974 docs(agent-web): 同步面板结构 + 后台任务 + LLM 接入说明
17a2ebd feat(agent-web-ui): 左栏加后台任务区 + 3 个 quickbar 按钮
03864ba feat(agent-web): 加 run_async / jobs / job 后台任务通路
227a23b docs(readme): 加三栏 agent web 工作台章节
84fceb8 feat(agent-reply): 接 LLM（anthropic）+ 模糊建议兜底
41d7f65 feat(agent-web-ui): 中间面板加'文件' tab 渲染目录树
08b3c56 feat(agent-reply): 加 3 个规划/导航命令 tree/ls/next/plan
33c07f8 feat(agent-web): 数据路由全鉴权 + 17 个 HTTP 集成测试
5551822 feat(agent-web-ui): 左栏加'当前案例文件'区
427bc42 feat(agent-web-ui): 加聊天发送中提示 + 清屏按钮 + 扩展 quickbar
a8c415e feat(agent-web-ui): 聊天走 mdLite 渲染 + open/run/switch 链接可点
7d7c7f3 feat(agent-reply): 加 4 个查询/记录命令 pending/get/find/note
371e046 feat(agent-web-ui): 加'版本' tab 渲染 liveview version_graph
a760c94 docs(memory): 更新到 8 步落盘状态
47b8892 docs(agent-web): 三栏 UI 使用说明独立成文件
cca6a87 test(agent-reply): 27 个 pytest 用例覆盖 parse + dispatch + 端到端
31d551f feat(agent-reply): 增 design/manifest/log/summary 四个只读命令
d150215 feat(agent-web): 聊天持久化 + WS 鉴权
fb87ed0 docs(refactor): 记录三栏 UI 落盘节奏 + 验证证据
fbeed1b feat(agent-web-ui): 三栏对话界面前端 + 启动脚本
fb45edb feat(agent-web): 三栏对话界面后端 —— FastAPI 13 路由 + stub agent
da2899f chore(refactor): 起步三栏 agent web UI 设计
11d574b chore: 同步看守状态（收尾，工作区干净）   ← master
b7e0438 feat(solve): G5 完成
```

## 当前任务与状态

主目标：重构 turtbo-agent，**跑通一个可视化 agent 对话 Web 界面**（右侧聊天框 / 左侧案例文件夹 / 中间 agent 操作可视化面板）。沿用现有数据层（liveview / case_watch / design_summary / version_graph / case_ledger），不重写设计工具，只重写 UI 与其服务端。

### 当前能力（自检通过）

**后端 8 个数据路由 + WS（全部 token 鉴权 /api/ping 与 / 除外）**
- `GET /api/cases` — 案例列表（id / stage / revision / artifact_count / mtime）
- `GET /api/state?case=X` — 中间面板一次拉全：现在 / 阶段时间线 / 产物 / 需求 / 版本图 / 文件树 / 后台进程
- `GET /api/views?case=X` — scheme / check / geom / mesh / cfd 5 视图
- `GET /api/asset?path=` — 沙箱内的 SVG / PNG / JPG
- `GET /api/file?path=` + `POST /api/file` — 受限路径读 / 乐观锁写
- `GET /api/chat?case=X` + `POST /api/chat` — 聊天历史 / 消息
- `GET /api/actions` + `POST /api/run` — 工具白名单
- `GET /api/jobs` + `GET /api/jobs/{id}` — 后台任务列表 / 详情
- `WS /ws?case=X&token=Y` — 3s 自动推 state 增量

**聊天 21 个命令（agent_reply.py）**
- 导航：help / case / open / ls / list / where / tree
- 查询：status / refresh / design / manifest / log / summary / pending / get / find / next / plan
- 操作：run / note / jobs / job
- `run_async ...` — 起后台线程（preflight / gate G3 等慢任务）
- LLM 兜底：`ANTHROPIC_API_KEY` 存在 → 调 claude-haiku-4-5；否则 _suggest 模糊匹配 9 关键词组

**UI 增强（agent_web_ui.html, 32KB）**
- 左栏：案例文件夹（搜索 + 计数 3）+ 当前案例文件 + 后台任务
- 中栏：总览 / 可视化 / 文件 / 版本 / 日志 / 操作 6 个 tab
- 右栏：AGENT 对话（mdLite 渲染 / 发送中提示 / 清屏 / 13 个 quickbar）
- WebSocket 自动重连（指数退避 1→2→4→8→16→30s）
- URL `?case=DF90-001` 直链自动选

**测试 85 全过**
- 38 unit（test_agent_reply.py）：parse_command 19 + reply 端到端 18 + dispatch 1
- 17 HTTP（test_agent_web.py）：HTML 注入 / 缺 token→403 / ping / cases / state / chat GET/POST / 4 个只读命令 / note 持久化 / switch / 未知 case→404 / actions / views / file / jobs / 2 个 rotation
- 30+ 中间件与集成

### 验证证据

- `python tools/start_agent_web.py` → http://127.0.0.1:9883 启动 OK
- `pytest tools/test_agent_reply.py tools/test_agent_web.py -q` → **85 passed in 6.79s**
- 真实截图 `docs/agent-web-screenshot.png` 43KB（3 个案例列表 + 现在面板）
- /api/state?case=DF90-001 → version_graph 32 nodes / 24 edges / 106 issues
- /api/chat `pending` → 5 段 LOG 末尾带 [PASS]/[WARN]/[FAIL]
- /api/chat `get requirement.thrust` → 90.0
- /api/chat `find requirements.yaml` → 12 命中
- /api/chat `note` → 写 LOG.md 成功
- /api/cases 无 token → 403

## 决定与教训

- 主分支保留 master 不动；重构在 wu5-dev-flow 分支。
- 三个面板分工 + 一个独立聊天 UI；沿用既有数据层；不引入 agent 框架。
- 不重写设计工具（gate_check / case_ledger / design_summary 复用）。
- 不混合主人另一会话的 WIP；仅在确认无污染时落盘。
- 'ls' 重映射到列阶段文件；list 保留为 5-recent-files。
- 测试修了 3 次：异步上下文、消息 200 上限后断言策略、403/401 期望值。
- LLM 接入：env 设 ANTHROPIC_API_KEY → anthropic 调 haiku 4.5；任何错误回退 stub。
- WebSocket 后台线程 3s 推 state；UI 收到自动 renderState，无需轮询。
- _maybe_rotate_chat 修 keep 越界 bug：`min(max(size//2, 64KB), size)`。
- Edge headless 截图：screenshot 路径必须绝对路径，否则写到工作目录。
