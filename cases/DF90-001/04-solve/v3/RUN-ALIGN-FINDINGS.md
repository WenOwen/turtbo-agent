# `.run` 与 `mesh-v4` 拓扑对齐 —— 卡点与现成答案

> 由编排层写于 2026-09-20 05:0x。**没跑求解，只做了查证。**
>
> **⚠ 硬限制（会改变上游的决策）**：本层尝试再往下转包时被拒 ——
> `ToolCallError: subagent depth 4 exceeds maxDepth 3`。**委托深度上限是 3，本层已在第 3 层，无法再派。**
> 所以这一棒要么由本层亲自做（但上下文预算已基本耗尽），要么由上游在更浅的层级派。

---

## 一、结论：**答案已经在 `numeca-fine-solver` skill 里，而且它明令禁止走第 3 条路**

### 第一优先的条文（`SKILL.md` 第 11 条）

> 把旧 computation 的物理或数值参数迁移到新网格时，**禁止复用旧 `.run` 或只替换 `GRID_FILE`。**
> **必须用新 `.igg` 重新物化 `.run`**，逐块核对名称和 `IMAX/JMAX/KMAX`，
> 并从 `.std` 再确认 EURANUS 实际读到的东西。

**这正好否掉了任务书里的「路 3：纯文本替换 `.run` 里的网格声明」** —— 那不是「最后手段」，是明令禁止。

### 对应的硬审计流程（`SKILL.md` 第 95-97 行）

> 需要沿用旧工况的边界、物性或数值设置，但**几何、hub/shroud、拓扑控制或网格版本已经变化时**，
> 执行以下硬审计：
> 1. **从当前 `.iec + 新 .igg` 生成一个基准 `.run`**，作为新网格块合同；
>    **不得把旧 `.run` 作为尺寸基准。**

**→ 所以「路 2：走 IGG 导 `.iec` 再生成 `.run`」就是 skill 规定的标准路径，也正是任务书里的第 2 条。**

### 还有一条会挡路的规则（第 12 条）

> **一个唯一网格必须对应一个独立 `.iec` 工程。** 网格身份由规范化 `.igg` 路径、SHA256 和块签名共同确定；
> **不同网格不得共用同一个 `.iec`。** 新增粗/中/细网格时必须分别新增 `.iec`，
> 不能把新网格 `.run` 挂在旧网格的 `.iec` 上。

**→ 所以不能改造 v2（或 v1）那套已有的 `.iec`：`mesh-v4` 必须新开一个自己的 `.iec`。**

### 交付合同（第 14 / 15 条，摘要）

- 每个求解目录必须保存**可审计的网格—工程映射**：至少记录 `.iec` / `.igg` / `.run` 的绝对路径与 SHA256、
  computation 名和块签名。任一对不上就停。
- 若工程为 `<root>/<project>.iec`、computation 名为 `<name>`，则所有 `.run/.res/.cgns/.mf/.xmf/.std`
  必须落在 `<root>/<project>_<name>/` 这个**同级目录**里。

---

## 二、本层实测核过的事实（不是转述）

- 卡点是真实的：`.std` 停在 `BLOCK NUMBER 3`，报
  `!ZONE HAVE NOT THE SAME SIZE` / `!CGNS SIZE max I,J,K 49 57 13` / `!IGG SIZE max I,J,K 105 57 1`
- **exit code 0 但求解器失败** —— 正是 skill 里记着的坑
- `03-mesh/` 下 v1 v2 v3 v4 四版都在；`03-mesh/v4/` 六件套齐全，`mesh-v4.audit.json` 里有 16 块签名
- 案例里**已有**一套 `.iec` 构建流程的产物：`04-solve/v1/iec_build_audit.json`（那是 v2 时代的）
- 相关脚本：`numeca-fine-solver/scripts/audit_iec_run_sync.ps1`、`build_multispeed_iec.py`

---

## 三、下一步该怎么做（按 skill 的规定）

1. **为 `mesh-v4` 新建独立 `.iec`**（不得复用旧 `.iec`）
2. **从该 `.iec + mesh-v4.igg` 物化一个基准 `.run`**（不得拿旧 `.run` 当尺寸基准）
3. 迁移物理/数值/边界参数时**逐块核对名称与 `IMAX/JMAX/KMAX`**，写进网格—工程映射
4. 跑 `audit_iec_run_sync.ps1` 做工程—磁盘双向同步审计
5. **验证标准不是「启动没报错」**：`.std` 要跑过 `BLOCK NUMBER 3` 且不再报 ZONE/SIZE 错、
   **出现 `.res` 与 `.xmf`**、残差开始下降
6. 之后再谈 5000 rpm 收敛判据与静推力三列

---

## 四、本层没做的

- **没有跑求解**（上下文预算不足，且这一步需要 IGG/FINE 的多轮操作）
- 没有改任何文件（除本文件）
- 没有 git add / commit