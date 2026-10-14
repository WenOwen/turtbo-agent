# memory

分支： `wu5-dev-flow`（从 master 拉出）。GitHub： `WenOwen/turtbo-agent`，已 `git push`。

## 当前任务与状态

重构 turtbo-agent，目标是**跑通一个可视化 agent 对话 Web 界面**：右侧聊天框、左侧案例文件夹、中间 agent 操作时可视化面板。沿用现有数据层（liveview / case_watch / design_summary / version_graph），不重写设计工具，只重写 UI 与其服务端。

每个子模块独立落盘到 wu5-dev-flow 分支，每个提交都是可验证的小步：
- `chore(refactor)` 起步：memory + 设计文档 + git remote 验证
- `feat(agent-web)` 后端：FastAPI 服务 + WebSocket + 命令路由器
- `feat(agent-web-ui)` 前端：三栏布局 + 案例浏览器 + 可视化卡片 + 聊天
- `docs(refactor)` 用户文档与回退

## 最新一次验证

- 2026-10-13 17:57 +08:00：本地 git checkout -b wu5-dev-flow，gh repo create WenOwen/turtbo-agent --public --push → https://github.com/WenOwen/turtbo-agent。基础提交（master 历史）已同步到远端。

## 未解决问题与下一步

1. 工作区有未提交修改（skill 与 modified case 文件）—— 不进本次提交。后续步骤只动新文件 + agent_web 相关修改。
2. 当前 liveview 服务的会话令牌 / 文件写入安全机制需要保留到新 UI。
4. 当前未提交的 skill / README / cases/DF90-001/* 修改是主人另一会话的 WIP，不混合进本次重构。

## 仍然有效的决定

- 主分支保留 master 不动；重构在 wu5-dev-flow 分支。
- 三个面板分工与一个独立聊天 UI，沿用既有数据层；不引入 agent 框架。
- 不重写设计工具（gate_check / case_ledger / design_summary 复用。
- 每个步骤可独立启动验证，失败立即停下。