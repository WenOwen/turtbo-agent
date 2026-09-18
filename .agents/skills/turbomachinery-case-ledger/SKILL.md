---
name: turbomachinery-case-ledger
description: "叶轮机械设计案例的版本沉淀与工程日志合同 / design-case versioning and engineering log contract. 定义案例目录契约、版本号规则、manifest 溯源链、LOG.md 条目格式、memory.md 经验晋升机制、幂等登记与哈希要求。用于任何需要\"交付物有版本、日志可追溯、经验可沉淀\"的 CFD/气动设计任务；开新案例、登记产物、判定何时该升版本、审计交付可追溯性、把经验写回 skill 时使用。"
---

# 案例账本｜版本沉淀与工程日志

本 skill 回答三个问题：**产物放哪、版本怎么涨、经验怎么沉淀。**

它是 `ducted-fan-aero-design` 的地基；任何阶段技能（AutoBlade / AutoGrid / FINE / CFView）
产出的文件，都必须经本 skill 的合同登记，才算"交付物"。**没有登记的文件只是一堆文件。**

## 适用与不适用

**用**：需要跨天/跨会话延续的工程设计案例；需要向他人（导师、甲方、评审）证明
"这个结果是怎么来的"；需要把踩过的坑变成下次不会再踩的规则。

**不用**：一次性探索脚本、纯学习性质的试算、不打算复现的快速验证。
这类工作写进 `cases/<id>/_scratch/` 即可，不登记。

---

## 一、目录契约（不可即兴改动）

```
cases/<CASE-ID>/
  requirements.yaml      需求基线（G0 唯一输入，全案溯源根）
  STATE.json             状态机：current_stage / stages{} / blockers[]
  LOG.md                 只追加的工程日志
  manifest.json          机器可读产物索引 + 溯源链
  memory.md              本案例经验条目（晋升候选池）

  00-brief/              G0 需求、G1 设计大纲
  01-scheme/vN/          G2 1D/通流方案（三表 + scheme.json）
  02-geometry/vN/        G3 叶片造型（geomTurbo + manifest + preview）
  03-mesh/vN/            G4 网格（trb/igg/cgns/bcs/config/qualityReport + audit）
  04-solve/vN/           G5 求解（iec + 原生工况目录 + std + verdict）
  05-post/vN/            G6 后处理（曲线、yplus、operating_points）
  06-delivery/vN/        G6 交付快照（三表 + dashboard.html）
  _replay/               只读回放区（对历史案例做验收复现，不产生新物理结果）
```

**禁止**：把多个版本的产物平铺在同一层；用日期代替版本号（`20260917/`）；
把 `.cgns/.iec/.res` 等大二进制提交进 git（见 §五）。

### 版本号规则

| 层 | 目录 | 递增条件 |
|---|---|---|
| 方案 | `01-scheme/v1, v2…` | 任一设计参数变更 |
| 几何 | `02-geometry/v1, v2…` | 造型参数、积叠方式、截面数变更 |
| 网格 | `03-mesh/v1, v2…` | TRB 控制、第一层高度、叶尖间隙、拓扑变更 |
| 求解 | `04-solve/v1…` | 换网格、换物性、换湍流模型 → **必须换** `.iec` |
| 交付 | `06-delivery/v1…` | 每次出表一个不可变快照 |

**跨阶段命名沿用既有全局习惯**：网格用 `mesh-vN`，求解工程用 `fine-vN` 或 `<case>-optimized`。
新工程的网格版本号从 `v1` 起，不继承 `Ducted-Fan` 的 `mesh-v6` 等历史编号。

### 何时开新案例（而不是新版本）

| 情形 | 处置 |
|---|---|
| 需求变了（推力目标 / 桨盘直径 / 环境条件） | **新案例** |
| 只是设计参数改了（转速、弦长、叶排数） | 同案例升 `v` |
| 换了一套完全不同的机器（压气机 → 涵道风扇） | **新案例** |
| 同一机器的第二个设计点 | 同案例，多 `.run` computation |

---

## 二、产物登记（幂等）

### 命令

```powershell
python tools/case_ledger.py add `
  --case cases/DF90-001 `
  --stage G4 --kind mesh `
  --path 03-mesh/v1/mesh-v1.igg `
  --version v1 `
  --verdict PASS `
  --from 02-geometry/v1/DF90-001.geomTurbo `
  --criteria "负单元=0（硬）；最小偏斜角>=10deg（硬）" `
  --note "转子吸力面流向控制值 101"
```

### 幂等语义

同一 `(stage, path, sha256)` 重复登记 → 返回 `idempotent: true`，**不新增记录、不写日志、不涨 revision**。
文件内容变了（sha256 不同）→ 替换该条记录、revision +1，**是同一个版本号的修订，不自动升 v**。

> 内容变了却不升 `v`，是本合同允许的唯一"原地修订"情形。若该产物已经被下游引用，
> 必须先升 `v` 并在 `LOG.md` 写明"下游需重跑"，否则溯源链会指向一个不再存在的字节。

### manifest 溯源链

```json
{
  "schema": "turtbo-agent/case-manifest@1",
  "case_id": "DF90-001",
  "requirement_ref": {"file": "requirements.yaml", "sha256": "…", "bytes": 1842},
  "current_stage": "G4",
  "revision": 7,
  "artifacts": [
    {
      "stage": "G4", "kind": "mesh", "path": "03-mesh/v1/mesh-v1.igg",
      "version": "v1", "sha256": "…", "bytes": 487036, "verdict": "PASS",
      "ts": "2026-09-17T15:20:31+08:00", "note": "",
      "provenance": {"from": "02-geometry/v1/DF90-001.geomTurbo", "from_sha256": "…"}
    }
  ]
}
```

**溯源完整性要求**：G2 之后的每个产物都应带 `provenance.from`。
`case_ledger.py verify` 会把缺 provenance 的产物列为警告——**不是错误，但必须在 `LOG.md` 说明理由**
（例如"该产物为环境预检输出，无上游产物"）。

**`requirement_ref` 是全案根**：`requirements.yaml` 一变，全案版本作废。审计时先核对这个哈希。

---

## 三、LOG.md：工程日志

### 格式（由工具生成，不要手写）

```markdown
## 2026-09-17T15:20:31+08:00 | G4 网格 | PASS
- 动作：AutoGrid5 生成 mesh-v1
- 命令：python tools/gate_check.py mesh --case cases/DF90-001 --version v1
- 实测：最小偏斜角 15.682 / 最大膨胀率 2.3068 / 负单元 0 / 单元数 1811316
- 上游：02-geometry/v1/DF90-001.geomTurbo
- 判据：负单元=0（硬）| 偏斜角>=10deg（硬）| 膨胀比<=5（本案例沿用量，来源见 criteria 表）
- 结论：PASS
- 产物：03-mesh/v1/mesh_audit.json  sha256=…
- 备注：偏斜角上限为工程判断，非通用设计判据。
```

### 四条纪律

1. **只追加，不复写。** 修正结论要新增一条并注明"更正 <时间戳> 的条目"，不能改历史。
2. **必须有判据。** `--criteria` 是必填。写了结论却没写判据 = 无效条目。
3. **判据必须可溯源。** 自造阈值要注明来源（用户指定 / 引用文献 / 沿袭既有工程合同）。
   无法注明来源的数字，写"工程判断，待验证"。
4. **区分状态词。** 严格区分：`已准备 / 已排队 / 正在运行 / 已正常退出 / 已验收`。
   进入迭代只代表"正在运行"，**不得写成"计算完成"**。

### 日志里禁止出现的话

- "收敛了" —— 除非写了具体判据与实测值
- "效果不错" —— 非可判定陈述
- "应该没问题" —— 无证据
- 把 `finished`、退出码 0 当作收敛证明

---

## 三点五、还原已登记的产物：只能用内容寻址历史库，不能用 git

**合同**：`manifest.json` 里登记的 `sha256` 是对**工作区字节**算的。
任何会改变字节的操作都会让 `verify` 失败 —— **git 就是其中之一**。

```powershell
# 正确：按字节还原，哈希自校验，不自洽就拒绝执行
python tools/case_watch.py --case cases/<ID> --restore <相对路径> --sha <完整 sha256>
```

**反例（实测踩到）**：用 `git checkout -- <文件>` 还原 `PROVENANCE.md`，
仓库开着 `autocrlf`，checkout 把 LF 转成 CRLF，文件从 **4697 涨到 4815 字节**
（多出 118 个 CRLF），`verify` 立刻报"哈希不符"。

已加 `.gitattributes` 的 `cases/** -text` 关闭转换，但**这不能使 git 成为还原手段** ——
历史提交里的字节与登记时的字节本来就可能不同。

**两条硬规则**：
1. 还原产物走 `case_watch --restore`，不要走 git。
2. 内容寻址存储（`_watch/history/`）**必须按字节读写**。
   用 `read_text` + `encode` 往返会把 CRLF 规范化成 LF，哈希必然对不上。
   这个 bug 本轮也踩到过，是哈希自校验把它挡下来的。

**来源**：2026-09-19 实测（本轮连续三次 CRLF 事故）
**适用边界**：所有对已登记产物做写回/还原的操作；所有内容寻址存储。

---

## 四、memory.md：经验沉淀与晋升

### 条目格式

```markdown
## 2026-09-17 | <一句话结论>
- 来源：用户纠正 / 实测发现 / 回放不一致
- 现象：<观察到什么>
- 合同：<可执行的硬规则，写成祈使句>
- 证据：cases/DF90-001#G4-0007 或 run/90kg-duct-fan-v7/final_delivery_audit.json
- 适用边界：<不得泛化到哪里>
- 晋升状态：待晋升 -> <目标 skill>/references/contracts.md#C-0NN
```

### 晋升三条件（满足任一即触发）

1. 同类条目在同一案例或跨案例累计 **>= 3 条**
2. **用户明确纠正过一次**（用户纠正的权重等于 3 条实测）
3. 回放审计结果与黄金基准**不一致**

### 晋升动作

1. 把条目改写为**可执行判据**（含阈值、单位、检查方法），写入目标 skill 的
   `references/contracts.md`，编号 `C-0NN`。
2. 在条目里把"待晋升"改为"已晋升 -> C-0NN"。
3. 在 `references/contracts.md` 的该条目标注 `source:` 指向原始案例与日志序号。

### 两条禁令

- **不自动改 skill 正文。** 晋升是显式动作，需用户确认后落盘。
  （与 `skill-evolution` 的"只生成补丁建议、不自动编辑"一致。）
- **不把项目特例写成通用判据。** 例如"0.2% 相对极差"是当前项目的工程合同，
  写进 contracts 时必须带适用边界。

---

## 五、大文件与 git

`.gitignore` 已排除 `.cgns/.adf/.res/.mf/.xmf/.iec/.run/.std/.geom`。
**这些文件只登记 sha256 与路径，不入库。** 体积参考（`Ducted-Fan` 实测）：

| 类型 | 单文件量级 | 处置 |
|---|---|---|
| `.cgns` | 54–101 MB | 不入库，登记哈希 |
| `.iec` | 19–25 MB | 不入库，登记哈希；快照按交付版本 |
| `.adf` | 3 MB | 不入库 |
| `.geom` | 1.7 MB | 不入库 |
| `.igg` / `.trb` / `.bcs` / `.config` / `.geomTurbo` | 0.3–500 KB | **入库**（可 diff，是版本沉淀的核心） |
| `.qualityReport` / `*_audit.json` / `manifest.json` | KB 级 | **入库** |

**磁盘预算**：一个设计点约 100–200 MB 峰值。开扫点前先估算
`点数 x 单点体积`，并在 `LOG.md` 记录预算。清理需显式确认，且**不得删除
`accepted` 点的最终解、`.std`、`convergence.csv`**。

---

## 六、命令速查

```powershell
[Console]::OutputEncoding = [Text.Encoding]::UTF8   # Windows 控制台中文

# 建案例
python tools/case_ledger.py new --case-id DF90-001 --root cases

# 登记产物（带上游溯源）
python tools/case_ledger.py add --case cases/DF90-001 --stage G3 --kind geometry `
  --path 02-geometry/v1/DF90-001.geomTurbo --version v1 --verdict PASS `
  --from 01-scheme/v1/叶片几何参数表.csv --criteria "截面数=5（硬）"

# 追加日志
python tools/case_ledger.py log --case cases/DF90-001 --stage G4 --action "AutoGrid 试跑" `
  --verdict WARN --criteria "膨胀比<=5" --measured "最大膨胀率 3.257" --note "超过旧阈值 3，按现行 5 通过"

# 阶段状态
python tools/case_ledger.py stage --case cases/DF90-001 --stage G4 --status done
python tools/case_ledger.py stage --case cases/DF90-001 --stage G5 --status blocked --reason "授权未就绪"

# 校验与总览
python tools/case_ledger.py verify --case cases/DF90-001
python tools/case_ledger.py show   --case cases/DF90-001
```

**退出码**：`0` 成功 ｜ `2` 用法错误 ｜ `3` 前置条件不满足 ｜ `4` 校验失败 ｜ `5` 内部错误。

---

## 七、完成前自检

- [ ] `requirements.yaml` 存在且 `manifest.requirement_ref.sha256` 与当前文件一致
- [ ] `case_ledger.py verify` 退出码为 0
- [ ] 每个 G2+ 产物都有 `provenance.from`
- [ ] `LOG.md` 每条都有判据；没有"收敛了/效果不错/应该没问题"
- [ ] `memory.md` 中达到晋升条件的条目已标注或已晋升
- [ ] 没有 `.cgns/.iec/.res` 被提交进 git（`git status` 干净）
- [ ] `STATE.json` 的 `current_stage` 与实际进展一致；阻塞项已记录
