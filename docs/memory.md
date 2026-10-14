# memory

分支： `wu5-dev-flow`（从 master 拉出）。GitHub： `WenOwen/turtbo-agent`，已 `git push`。
最近 8 个提交：
```
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

主目标：重构 turtbo-agent，**跑通一个可视化 agent 对话 Web 界面**（右侧聊天框 / 左侧案例文件夹 / 中间 agent 操作可视化面板）。沿用现有数据层（liveview / case_watch / design_summary / version_graph），不重写设计工具，只重写 UI 与其服务端。

### 验证证据（最近一次实跑）

- `python -m uvicorn tools.agent_web:app --host 127.0.0.1 --port 8765` 启动 OK
- `pytest tools/test_agent_reply.py -v` → 27 passed
- `curl /api/ping` / `/api/cases` / `/api/state` / `/api/views` / `/api/actions` 全 200
- 3 个案例：DF90-001 v191/117 产物、DF90-002 v61/33 产物、DF120-HS-VERIFY v604/495 产物
- `POST /api/chat` → 14 个命令：help/case/open/list/where/refresh/status/design/manifest/log/summary + 5 个 run 子命令
- `POST /api/chat {text:'summary'}` → 把 status + design + list 三段拼成一条
- `POST /api/chat {text:'design'}` → 输出 90.00/82.36/-7.636 kgf（与 design_summary 同源）
- `POST /api/run {action:'gate', params:{gate:'G2'}}` → G2 通过 7/注 1/0/0
- WS /ws 无 token → 403；错 token → 403；正确 token → 101
- 浏览器 HTML 23.7KB，token 注入成功，残留 0
- 聊天持久化 marker `__persist_test_*` 写入 `cases/DF90-001/_watch/chat.jsonl` 1218B，重启可回灌

## 未解决问题与下一步

1. **README.md 留平行会话维护** — 三栏 UI 段已放在 `docs/AGENT-WEB-README.md`，README.md 留出空位。后续若主人确认可一起 commit。
2. **真实 LLM 接入** — stub agent 只识别命令（14 个）。可加 `provider=anthropic` / `openai` 选项，默认仍走 stub；用户前缀未匹配时给 LLM 解释。
3. **更细的操作动作** — 现阶段只把"跑闸门 / 校验 / 预检 / 回放"接通；下一轮接：编辑 case 文件、加/查 manifest 字段、把 gate check 失败原因反向回写。
4. **chat.jsonl 不限上限** — 每条都 append，只缓存 200 条；磁盘会涨。下一步加滚动切割。
5. **WS 鉴权细节** — 当前缺/错 token 都返回 HTTP 403（FastAPI 层），不是 WS 1008 close。已能挡 99% 攻击，但客户端判断"会话过期"不直观。
6. **preflight 失败** — `run preflight` 报 `OSError(8, '%1 不是有效的 Win32 应用程序')`。preflight 自身兼容问题，与 agent_web 无关；不阻塞本次重构。

## 仍然有效的决定

- 主分支保留 master 不动；重构在 wu5-dev-flow 分支。
- 三个面板分工 + 一个独立聊天 UI；沿用既有数据层；不引入 agent 框架。
- 不重写设计工具（gate_check / case_ledger / design_summary 复用）。
- 每步独立可验证；当前任务 ✅ `47b8892` / `cca6a87` / `31d551f` / `d150215` / `fb87ed0` / `fbeed1b` / `fb45edb` / `da2899f`。
- 不混合主人另一会话的 WIP；仅在确认无污染时落盘。
