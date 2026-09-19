# G5 交底：我做不完，如实说

> 编排/执行层（本会话）写于 2026-09-20 05:0x。
> **我不能再转包（委托深度上限 3），而我的上下文预算已接近耗尽。这一棒我做不到底。**
> 把状态与下一步写清，让接手的人能直接干。

---

## 一、实测核过的现状（不是转述）

- **HEAD = `c1f09ad`**，工作区**干净**
- `04-solve/v3/` 现有：
  - `RUN-ALIGN-FINDINGS.md`（3.9 KB）—— 上一棒把 skill 条文与本层实测落盘了，**接手先读它**
  - `G5-ORCHESTRATOR-REPORT.md`
  - `n05000_p101325/` 下的失败算例：`.run` 262 KB、`.std` **只有 8.2 KB**（停在 BLOCK 3）、
    `.log` 63 KB、`.steering`、`setup.json`、`G5-REPORT.md`
  - **没有 `.res`、没有 `.xmf`、没有 `.iec`** —— 求解从来没真的跑起来

## 二、卡点（已定论，别再重复踩）

```
!ZONE HAVE NOT THE SAME SIZE
!CGNS SIZE max I,J,K 49 57 13
!IGG  SIZE max I,J,K 105 57 1
```

`.run` 内部记着块拓扑。v2 网格 1,779,880 点，`mesh-v4` 1,596,448 点 —— **拓扑不同，一读就退出**。
**exit code 0**（euranus 失败也返回 0，退出码不是成功信号）。

## 三、skill 已经明令禁止的做法

`C:\Users\Administrator\.agents\skills\numeca-fine-solver\SKILL.md`：
- 第 11 条：**禁止复用旧 `.run` 或只替换 `GRID_FILE`**；必须用新 `.igg` 重新物化 `.run`，逐块核对名称与 `IMAX/JMAX/KMAX`
- 第 95-97 行：**从当前 `.iec + 新 .igg` 生成基准 `.run`**，不得把旧 `.run` 作尺寸基准
- 第 12 条：**一个唯一网格必须对应一个独立 `.iec`**，不同网格不得共用同一个 `.iec`

→ **纯文本替换 `.run` 里网格声明那条路已被排除。**

## 四、接手要做的（按顺序）

1. **为 `mesh-v4` 新开一个 IGG 工程**（不能改造 v1/v2 那套已有 `.iec`）
2. 由 **`.iec` + `03-mesh/v4/mesh-v4.igg`** 物化基准 `.run`
3. **逐块核对**块名与 `IMAX/JMAX/KMAX`（签名解析器现成：`tools/gate_check.py` 的 `igg_block_signature()`；
   参照 `03-mesh/v4/mesh-v4.audit.json` 的 16 块）
4. 跑 `audit_iec_run_sync.ps1`（skill 第 95-97 行提到的硬审计）
5. 起求解：`euranusx86_64.exe "<run>" -steering "<steering>" -niversion 161 -seq -batch`，stdout 重定向到 `.std`

**验证标准（光"启动没报错"不算成功）**：
- `.std` 跑过 `BLOCK NUMBER 3` 后不再报 ZONE/SIZE 错
- **出现 `.res` 与 `.xmf`** —— 这是"求解器真的在算"的唯一证据
- 残差开始下降、质量流量开始稳定

6. 跑起来后：5000 rpm / 101325 Pa；收敛判据用 `tools/convergence_check.py`（**别用步数当完成条件**，有认输线）
7. **静推力三列**用 `tools/thrust_closure.py`；**`A_out` 必须交叉核验**（周期扇区面积 x 出口叶排周期数 vs 解析环面积）
8. **不许拿壁面轴向力当整机推力**（C-004）
9. **G5-6 锚点对照**用 `tools/anchor_check.py`（转速 + 环形几何都要对）

## 五、这台机器的背景（做对比时必须知道）

- **v11 不能与 v8 当成同一台机器**：v8 = `scheme v1 + 人工改的几何`（断链）；v11 = `scheme v4 -> geometry v11`（**血缘接通**）
- 两者**流道几乎相同**（v4 的流道是从 v8 实测反推的），但**叶片金属角是按 v4 重做的** —— **差值的来源是叶片**
- v8 在 5000 rpm 的实测基准：静推力 618.72 N、流量 13.489 kg/s、总压比 1.01286、eta_tt 0.83308、转子扭矩 32.25 N·m

## 六、我为什么没做完

**上下文预算耗尽**。这一夜我连续指挥了 9 个执行层子 agent（金属角约定 / G2 v4 / 几何 v10 / AutoBlade 参数 /
v11 / G4 / G5 / run 对齐…），每一步都要读报告、核数据、写任务书。到这一棒已经没有余量亲自做 IGG + FINE 的长流程。

**我没有做的事**：没有 git add/commit（本轮产物已由上层提交为 `c1f09ad`）；没有改任何比对口径；没有编造任何数字。