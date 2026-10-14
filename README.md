# turtbo-agent

**Agent 驱动的叶轮机械气动设计工作流。** 以 DSH（DeepSeek Harness）为运行宿主，
把「需求 → 设计大纲 → 1D/通流方案 → 叶片造型 → AutoGrid 网格 → FINE 求解 →
CFView 后处理 → 交付三表」整条链沉淀为可被 agent 自动加载、可审计、可版本追溯的 skill。

首个落地场景：**涵道风扇气动设计（ducted-fan aerodynamic design）**。

---

## 为什么是现在这个目录

本目录是**工作区**，也是 DSH 的 **projectRoot**（无任何 `.git` 祖先，故 projectRoot = cwd）。
因此：

```
turtbo-agent/.agents/skills/     ← rank 200 项目级 skill 根
```

会被 DSH **自动发现并热加载**（`@deepseek-ai/dsh-skill-filesystem`，无需重启、无需提权）。
这是把「经验沉淀」变成**默认行为**而不是口头约定的结构前提。

> ⚠️ **不要在 `D:\Project\Research` 或更上层执行 `git init`。**
> 一旦上层出现 `.git`，projectRoot 会上移，本目录的 skill 会**静默全部失效**。
> `tools/preflight.py` 每次会校验这一点。

---

## 目录结构

```
.agents/skills/          本轮核心交付：4 个新 skill（唯一真源，随 git 版本化）
  ducted-fan-aero-design/      主编排：七步流程 + 小白引导 + 需求问答
  turbomachinery-case-ledger/     版本沉淀 + 工程日志 + 文件清单规矩
  ducted-fan-1d-scheme/           一维/通流方案规矩（需求 → 三表）
  cascade-forge-geometry-handoff/ 叶栅参数 → geomTurbo 调用契约
tools/                   薄封装 CLI：--json / --dry-run / manifest / 稳定退出码
  case_ledger.py         幂等登记产物、哈希、溯源
  gate_check.py          每一步做完的验收判定，自动写 LOG.md
  replay_audit.py        对既有算例做只读回放验收
  build_dashboard.py     生成单文件自包含 HTML 看板
  preflight.py           授权 / MPI / 磁盘 / 路径 / projectRoot 预检
cases/<CASE-ID>/         版本沉淀的物理形态（见 cases/DF90-001）
docs/                    面向小白的快速开始与术语
scripts/                 环境脚本（sync_skills.ps1 等）
templates/               需求 / 大纲 / 日志模板
```

---

## 复用的阶段技能（用户根，不改写）

`C:\Users\Administrator\.agents\skills\` 下的
`numeca-autoblade-geometry` · `numeca-autogrid-meshing` · `numeca-fine-solver` ·
`numeca-cfview-post` · `numeca-cli-automation` · `numeca-igg-skills` ·
`extract-fine-autoblade-tables` · `cfd-report-postprocess`

本仓库**只做编排与契约**，不重写这些阶段技能。

---

## 外部工具

| 工具 | 位置 | 在本链路的角色 |
|---|---|---|
| NUMECA FINE 16.1 / IGG / AutoGrid | `D:\NUMECA_SOFTWARE\fine161` | G4 网格、G5 求解、G6 后处理 |
| turbo-flow | `D:\Project\Research\turbo-flow` | G2 一维平均线 / S2 通流（**只读调用**） |
| cascade-forge | `D:\Project\Research\cascade-forge` | G3 二维叶片造型 → `.geomTurbo`（**只读调用**） |
| Ducted-Fan（历史工程） | `D:\Project\Research\Ducted-Fan` | **只读黄金基准**（v7 45 个验收点） |

---

## 看见它在做什么（实时工作台）

这个仓库里的阶段、版本、判据、日志都写在文件里——翻文件才能看懂。工作台把它们变成
**一扇会自己刷新的窗口**：

```
双击  start-liveview.cmd          （或 python tools/liveview.py）
```

浏览器自动打开 `http://127.0.0.1:8899/`，左侧和 DSH 对话并排放即可。

**它显示什么**

| 面板 | 内容 | 数据来自 |
|---|---|---|
| **案例选择器** | 右上角下拉，列出 `cases/` 下所有登记案例 | 各案例的 `manifest.json` |
| 设计进度 | 七步流程的状态，**可点击**；内部编号以小灰字附在右上角 | `STATE.json` |
| **阶段详情** | 点任意阶段 → 该阶段的**全部产物**（含体积/sha256/上游/备注）+ **全部过程记录**（判据/实测/结论） | `manifest.json` + `LOG.md` |
| 现在在做什么 | 从**进程 + 文件变动**推断，不说没根据的话 | `Get-Process` + mtime |
| 正在运行的进程 | 只列 NUMECA / 求解 / MPI 相关 | `Get-Process` |
| 最近改动的文件 | 全监视根下最新的 8 个 | 目录遍历 |
| 工程日志 | `LOG.md` 尾部 70 行，自动滚到最新 | `LOG.md` |
| 为什么有这些条条框框 | 每条规矩点开看白话 + 当初为什么加 + 来源 | `ducted-fan-contracts.md` |
| **变更流** | **只看四类工程实质变更**（设计参数/几何/网格/算例参数）；未登记的改动高亮 | `_watch/changes.jsonl` |
| **操作台** | 跑检查 / 校验 / 预检 / 回放；**点产物路径可编辑并保存** | 人工操作记 `human(web-ui)` |

**设计原则**：**不虚报活动。** 只有检测到求解器进程才说"求解器正在算"；
只开着 IGG 界面而没在算，会如实显示「NUMECA 界面打开着（未在计算）」。
日志若停在几分钟前，也会如实写"最近写入 N 分钟前"。

---

## 与 agent 对话的三栏 Web 工作台（重构新增）

`liveview` 是只读看板。重构在 `tools/agent_web.py` 里加了**可对话**的姊妹服务：

```
python tools/agent_web.py        # 默认 :8765
```

浏览器打开 `http://127.0.0.1:8765/`，是**三栏**布局：

| 栏 | 内容 |
|---|---|
| **左 · 案例文件夹** | 当前案例目录树（深度 3）+ 最近改动的 12 个文件，点击直接发到聊天框 |
| **中 · agent 操作可视化** | Tab 切换：「阶段」(G0-G6 七道闸门) / **版本**（节点/边/问题）/ **文件**（目录树）/ **日志**（实时 tail） |
| **右 · 聊天框** | 10 个 quickbar 按钮 + 文本输入；mdLite 渲染；命中后回 `open`/`run`/`switch` 的可点 link |

**全部命令清单**（聊天框输入即可）：

| 命令 | 作用 | 类型 |
|---|---|---|
| `status` | 当前阶段/产物/阻塞 | 读 |
| `summary` | 关键摘要 | 读 |
| `design` | 目标推力/实测/差距 | 读 |
| `manifest` | manifest 关键字段 | 读 |
| `get <key>` | 按点路径读 manifest 字段 | 读 |
| `pending` | LOG.md 末尾 5 段 PASS/WARN/FAIL | 读 |
| `find <text>` | 案例目录文本片段搜 | 读 |
| `tree` / `ls` | 目录树 / 阶段文件 | 读 |
| `next` | 下一步建议（带 `next_stage` 字段） | 读 |
| `plan` | 现状+下一步+待办三段 | 读 |
| `open <path>` | 读文件回灌首 200 字 | 读 |
| `log` | LOG.md 尾部 | 读 |
| `where` | 当前 case_dir | 读 |
| `list` | 5 个最近文件 | 读 |
| `switch <id>` | 切到另一案例 | 写 |
| `note <text>` | 把一行手记写进 LOG.md | 写 |
| `run <tool> [args]` | 跑 `preflight` / `gate_check` / `gate G3` 等 | 写 |
| `refresh` | 强制刷新 manifest | 写 |
| `help` | 命令清单 | 读 |

**未知命令**先尝试调 LLM（`ANTHROPIC_API_KEY` 在 env 时调 haiku 4.5），失败回退到
**模糊建议**（"我下一步干嘛" → `next`；"推力差" → `design`；"找 requirements" → `find`）。

**安全**：所有数据路由要求 `X-DSH-Token` 头或 `?token=` 查询；token 在启动时打印到控制台。
HTML 注入 token 用 `__DSH_TOKEN__` 占位，根 `/` 与 `/api/ping` 开放用于浏览器/存活探针。

**测试**：`python -m pytest tools/test_agent_reply.py tools/test_agent_web.py`
—— 当前 74 passed（38 unit + 36 HTTP）。

**详细文档**：[docs/AGENT-WEB-README.md](docs/AGENT-WEB-README.md)。

**参数**

```powershell
python tools/liveview.py --port 8900
python tools/liveview.py --case cases/DF90-001
python tools/liveview.py --watch "D:\some\other\run"   # 额外监视目录（可重复）
python tools/liveview.py --no-browser
```

零第三方依赖、只读、不写工作区以外的任何文件。
（截图见 `docs/liveview-screenshot.png`。）

**术语翻译**：界面和 agent 对用户说话时，不出现「闸门 / 合同 / 判据」这类内部词。
唯一的翻译源是 `.agents/skills/ducted-fan-aero-design/references/plain-language.json`，
`python tools/gate_check.py audit` 会检查每一步都有对应的白话说法，缺了就报漂移。

**尚未实现**（面板里是占位）：版本沉淀树、对标数字与曲线。

---

## 快速开始

见 `docs/QUICKSTART-BEGINNER.md`（从零到第一个网格，命令可粘贴执行）。

---

## 三条不可违背的规矩

1. **一个唯一网格 ↔ 一个独立 `.iec`。** 不同网格不得共用工程。
2. **整机静推力只认控制体口径** `T = ṁ_out·Vx_out + (p_out − p∞)·A_out`。
   XMF 壁面轴向力**不是**整机净推力。
3. **收敛主判据是末段质量流量稳定性**，不是固定残差数值。
   残差只用于识别 NaN、爆炸与持续恶化。

完整清单见 `.agents/skills/ducted-fan-aero-design/references/ducted-fan-contracts.md`。

---

## 许可与边界

本仓库不包含、不修改任何 NUMECA / AxSTREAM 安装文件，不绕过授权控制。
所有商业求解器调用均使用本机已授权的正版安装。
