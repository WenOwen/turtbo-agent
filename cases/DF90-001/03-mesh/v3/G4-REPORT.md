# G4 执行层记录 —— 03-mesh/v3（v11 几何的 as-built 网格）

> 执行者：委派子 agent（G4 任务）。这是一手记录，含命令、原始输出与实测数据。
> 与同目录的 `G4-ORCHESTRATOR-REPORT.md` 互补，**不互相覆盖**。
>
> **时间**：2026-09-20 04:1x–04:3x　**输入几何**：`02-geometry/v11`（叶片第一版真正由参数表导出）

---

## 1. 六件套清单 + sha256（实测）

| 文件 | 字节 | sha256 |
|---|---:|---|
| `mesh-v3.trb` | 36,031 | `c2b431b3a251e9385d4b1651a5622c50cdb4da0fb11981dc5ba2cdb1e689539e` |
| `mesh-v3.igg` | 456,301 | `a11cef26d56d7673fc3f4287931909322e8796df7b2818d9b7b2d72af618c93c` |
| `mesh-v3.cgns` | 49,188,864 | `a03eb9721d466cce877671d150c6b7ab2f7dd8ae02c175fde59cf71e89e594b2` |
| `mesh-v3.bcs` | 15,972 | `202235d0cdaec403e66030355155e7871fd634bb3224bb7f4681e9b002c2a878` |
| `mesh-v3.config` | 13,326 | `865c667e9eddb23d8dfd19df01da3eb748886f8dcfae858bf616b25582077b6e` |
| `mesh-v3.qualityReport` | 4,463 | `1522861575e6840ed03a69567fe3a23464ef046904bf561350790b717fc06d8d` |
| `mesh-v3.geomTurbo` | 353,777 | `c4cc6340c8b0a6bb5719ab6263f67bcef85991f8ca033fac00e79a399a597ed7` |

## 2. 「改绑取证」—— 这条路线上不需要改绑，但做了等价取证

任务书里提到的坑（`03-mesh/v2/mesh-v2.autogrid_job.py` 用绝对路径指向 `Ducted-Fan`）**确实存在**，
但**只存在于 `optimize_existing_mesh.py` 生成的那条路线**。

我这次用的是 `build_autogrid_mesh.py` 的 **`new-project`** 模式，它生成的脚本**全部路径都在案例目录内**，
从 v11 的 `.geomTurbo` 从零初始化，不打开任何外部 `.trb`。

**等价取证（零残留检查）**：

```
Select-String -Path "cases/DF90-001/03-mesh/v3/*" -Pattern "Ducted-Fan"
→ 零命中（job.py / expected.json / run_manifest.json / audit.json 全查过）
```

`run_manifest.json` 里记了输入哈希：
- `R1.geomTurbo` = `87dba87cabb4dee512ae32adc3dd70ccc929028c36b4c8c4c8b7a548bdc5c40e`
- `R2.geomTurbo` = `7ab3080ac0bbadeb8ddceaa5a04a8398b313bf4da4ede262433649dfaf861197`

**所以没有「新旧网格哈希比对证明是纯路径变化」这一步 —— 因为根本没有复制模板，是重新生成的。**
v2 与 v3 的 `.igg` 本就应当不同（几何与网格设置都变了）。

### 为什么用 `new-project` 而不是 `template-replace`

`numeca-autogrid-meshing/SKILL.md` 写着：「AutoBlade 导出的 hub/shroud 或进出口延伸发生变化时，
网格工程使用 `new-project` 从首排 `.geomTurbo` 初始化，**禁止**使用保留旧流道的 `template-replace`」，
且「最终 `.geomTurbo` 的 hub/shroud 点数与坐标哈希必须等于首排 AutoBlade 源」。

实测三条流道互不相同：

| 来源 | 轮毂起点 r | 轮毂终点 r | 备注 |
|---|---:|---:|---|
| v11 R1/R2 | 0.080000 | **0.113200** | 本轮目标 |
| `03-mesh/v2` 的 geomTurbo | 0.080000 | 0.113178 | v8 时代的十点人工线，**差 22 µm** |
| skill 资产模板 `duct_fan_90kg` | **0.103457** | 0.129758 | 旧流道（= v1 的入口轮毂），**完全不同** |

**模板的流道与 v11 不是一族，`template-replace` 会保留错流道。所以必须 `new-project`。**

## 3. 叶尖间隙 —— 实测答案（这是本任务的核心问题）

### 3.1 结论

> **参数表的「叶尖间隙」列描述的是网格设置（AutoGrid 的 `tip_gap_width_m`），不是叶片几何。**
> **`geomTurbo` 里的 `WIDTH_AT_LEADING_EDGE = 0.002` 是另一个量。**
> **所以 G3-5 拿参数表的值去比 `geomTurbo` 的 `WIDTH_AT_LEADING_EDGE` 是比错了口径 —— 它应该在 G4 比。**

### 3.2 证据一：生成的脚本里显式设了它

`mesh-v3.autogrid_job.py` 第 31–33 行：

```python
current_wizard.tip_gap_is_asked(1)
current_wizard.set_tip_gap_width_at_leading_edge(0.0005)
current_wizard.set_tip_gap_width_at_trailing_edge(0.0005)
```

（该值来自我写的作业配置 `rows[0].tip_gap_width_m: 0.0005`。若省略，脚本按
`build_autogrid_mesh.py` 的 `DEFAULT_TIP_GAP_WIDTH_M = 0.0005` 填。）

### 3.3 证据二：TRB 里读出来的实际值

`mesh-v3.audit.json` → `trb.rows.row 1`：

```
tip_gap              = true
tip_gap_width_le_m   = 0.0005
tip_gap_width_te_m   = 0.0005
```

同一份 audit 里 `geomturbo.rows.row 1.has_tip_gap = true` —— **`geomTurbo` 侧只报布尔，不报宽度。**

### 3.4 证据三：受控对照实验（0.0005 vs 0.002）

同一份 v11 几何、同一套其余设置，**只改 `tip_gap_width_m`**，各建一次网格：

| 请求的 `tip_gap_width_m` | TRB `tip_gap_width_le_m` | TRB `tip_gap_width_te_m` | `.igg` sha256 前 32 | `.trb` 字节 |
|---|---|---|---|---:|
| **0.0005** | **0.0005** | **0.0005** | `a11cef26d56d7673fc3f428793190932` | 36,031 |
| **0.002** | **0.002** | **0.002** | `c7c473ba3bc1fec3d4a25abf0d2459ec` | 36,017 |

**请求值原样进了 TRB，而且 `.igg` 与 `.trb` 的哈希都不同 —— 网格真的变了。**
（点数与最小偏斜角两组相同：1,573,124 / 14.896°。这符合预期 —— 间隙的层数不变，
变的只是物理宽度，所以节点数不变。）

### 3.5 边界（这不是通用结论）

- 数据来源：`cases/DF90-001/03-mesh/v3/mesh-v3.audit.json` 的 `trb.rows.row 1.*` 与
  `geomturbo.rows.row 1.*` 字段；对照组的同名文件在 `%TEMP%\g4ctrl\mesh-gap002.audit.json`
- **这是本案例（AutoGrid 16.1 `new-project` 模式）的实测结论**，不是对所有 NUMECA 版本/模式的通用结论
- **我没有改 `gate_check.py` / `geom_check.py` 的任何比对口径** —— 口径要不要改是判据变更，归上游/用户
- 附带一条观察：`v7_mesh_optimization.md` 写着 v7 用的是 **2 mm** 转子叶尖间隙；
  而本案例参数表写 0.5 mm。**哪个是设计意图，需要用户判断**（0.17% vs 0.67% 叶尖半径，会显著影响效率）

## 4. G4 闸门逐条（实测）

```
$ python tools/gate_check.py mesh --case cases/DF90-001 --version v3 --no-log

第 5 步检查（G4）：通过
  通过 5 / 注意 0 / 没通过 0 / 还查不了 0
  v 网格文件存在  [stem=mesh-v3 suffixes=.bcs,.cgns,.config,.igg,.info,.qualityReport,.trb]  (G4-1)
  v 关键文件齐全  [missing=[]　外部索引满足=[]]  (G4-2)
  v 质量报告非空  [4463 bytes]  (G4-3)
  v 负单元 = 0  [reported=0]  (G4-4)
  v 块签名已记录  [mesh-v3.igg　16 块　row_1_flux_1_M:6x93x73 row_1_flux_1_M:6x17x73 row_1_flux_1_M:6x93x73]  (G4-5)
总体：PASS
```

### 与 v2 并排

| | v2（v8 几何） | **v3（v11 几何）** |
|---|---:|---:|
| 点数 | 1,779,880 | 1,573,124 |
| 最小偏斜角 | **16.406°** | **14.896°** ⚠ |
| 最大膨胀率 | 1.7729（展向） | 2.2528 |
| 负单元 | 0 | 0 |
| Mesh Validity | OK | OK |
| 块数 | 16 | **16**（同拓扑） |

**一条 warn**：内置审计报 `low_skewness` —— 最小偏斜角 14.896°，低于本项目的 15.0° 验收线。
**根因不是网格坏了，是叶片换了**（v11 的金属角与 v8 不同），网格还没跟上。**已在 `03-mesh/v4` 处理。**

## 5. 登记与自查

```
$ python tools/case_ledger.py add --case cases/DF90-001 --stage G4 --kind mesh \
    --path "03-mesh/v3/mesh-v3.igg" --version v3 --verdict PASS \
    --from "02-geometry/v11/autoblade/R1_13span/R1.geomTurbo"
[added] G4 03-mesh/v3/mesh-v3.igg sha256=a11cef26d56d (456301 B)

$ python tools/case_ledger.py add ... --path "03-mesh/v3/mesh-v3.qualityReport" \
    --from "03-mesh/v3/mesh-v3.igg"
[added] G4 03-mesh/v3/mesh-v3.qualityReport sha256=1522861575e6 (4463 B)

$ python tools/gate_check.py audit --case cases/DF90-001
  [OK] 合同与代码一致，无漂移

$ python tools/case_ledger.py verify --case cases/DF90-001
校验 59 个产物：全部通过
```

## 6. `03-mesh/v4` —— 单因素优化（已完成）

### 6.1 为什么做

v3 的最小偏斜角 14.896° 低于本项目 15.0° 验收线。**根因不是网格坏了，是叶片换了**
（v11 的金属角与 v8 不同），网格还没跟上新叶片。拿去跑 CFD 结果会被质疑。

### 6.2 单因素扫描（实测，全部 `new-project` 重建）

控制量 `streamwise_blade_upper_points`（其余设置与 v3 完全相同）：

| 叶顶流向点 | 总点数 | 最小偏斜角 | 最大膨胀率 | vs 97 点数 | Mesh Validity |
|---:|---:|---:|---:|---:|---|
| 97（= v3） | 1,573,124 | 14.896° | 2.2528 | — | OK |
| **101** | 1,596,448 | **16.496°** ✓ | 2.3496 | +1.48% | OK |
| 105 | 1,619,772 | 18.188° | 2.4462 | +2.96% | OK |
| 109 | 1,643,096 | 20.151° | 2.5433 | +4.45% | OK |
| 113 | 1,666,420 | 21.861° | 2.6424 | +5.93% | OK |

**选 101** —— 按 `v7_mesh_optimization.md` 那条已验证的经验：**「选满足目标的最低代价点」**。
点数增量 +1.48%，远低于验收允许的 +10%；最大膨胀率 2.3496 < 3。

### 6.3 v4 成品（实测）

```
points    = 1596448
min_skew  = 16.496      <- 目标 >=16 达成
max_exp   = 2.3496      <- 验收上限 3
validity  = OK  (No Overlapping Cells Generated)
neg_ok    = True
issues    = []          <- 内置审计零 issue（v3 有一条 low_skewness warn）
tip_gap   = True 0.0005
streamwise_upper = 101
块数      = 16（与 v3 / v2 同拓扑）
```

### 6.4 G4 闸门（v4）

```
$ python tools/gate_check.py mesh --case cases/DF90-001 --version v4 --no-log

第 5 步检查（G4）：通过
  通过 5 / 注意 0 / 没通过 0 / 还查不了 0
  v 网格文件存在  [stem=mesh-v4 suffixes=.bcs,.cgns,.config,.igg,.info,.qualityReport,.trb]  (G4-1)
  v 关键文件齐全  [missing=[]]  (G4-2)
  v 质量报告非空  [4462 bytes]  (G4-3)
  v 负单元 = 0  [reported=0]  (G4-4)
  v 块签名已记录  [mesh-v4.igg　16 块　row_1_flux_1_M:6x93x73 ...]  (G4-5)
总体：PASS
```

### 6.5 v4 六件套 sha256

| 文件 | 字节 | sha256 |
|---|---:|---|
| `mesh-v4.trb` | 36,042 | `2a13265c87fb4adb5be099b98f38e6f1e52d034549756ed99004b4b8165862b1` |
| `mesh-v4.igg` | 459,893 | `2314a3453b1b366507df4e75624cc9d13195e10a16facb87dcc7af60a0328efa` |
| `mesh-v4.cgns` | 49,987,584 | `8bc261e619735b8219bd8a98e83d0179c4d6fcf5a21a8f34754c46b0d11a765a` |
| `mesh-v4.bcs` | 15,981 | `13fa2cfb6856cce7a732446a5628aee382f010697c9c472d54b66f1552fe7893` |
| `mesh-v4.config` | 13,326 | `865c667e9eddb23d8dfd19df01da3eb748886f8dcfae858bf616b25582077b6e` |
| `mesh-v4.qualityReport` | 4,462 | `824b2164b1cfcfe9499a947241d0104f51e4132ef3f2eb62c56b417eb179dd52` |
| `mesh-v4.geomTurbo` | 353,777 | `c4cc6340c8b0a6bb5719ab6263f67bcef85991f8ca033fac00e79a399a597ed7` |

> 注：`mesh-v4.geomTurbo` 与 `mesh-v3.geomTurbo` **哈希相同** —— 几何是同一套（v11），
> 变的只有网格密度。这本身是一条一致性证据。

### 6.6 v3 vs v4 并排

| | v3（as-built） | **v4（优化后）** | v2（对照，v8 几何） |
|---|---:|---:|---:|
| 叶顶流向点 | 97 | **101** | 97 |
| 点数 | 1,573,124 | 1,596,448 | 1,779,880 |
| 最小偏斜角 | 14.896° ⚠ | **16.496°** ✓ | 16.406° |
| 最大膨胀率 | 2.2528 | 2.3496 | 1.7729（展向） |
| 负单元 | 0 | 0 | 0 |
| 块数 | 16 | 16 | 16 |
| 内置审计 issues | 1 warn | **0** | — |

**v4 的质量已回到 v2 的水平（16.496° vs 16.406°），而几何是新的。**

### 6.7 登记

```
[added] G4 03-mesh/v4/mesh-v4.igg sha256=2314a3453b1b (459893 B)
[added] G4 03-mesh/v4/mesh-v4.qualityReport sha256=824b2164b1cf (4462 B)
$ python tools/gate_check.py audit --case cases/DF90-001  -> [OK] 合同与代码一致，无漂移
$ python tools/case_ledger.py verify --case cases/DF90-001 -> 校验 61 个产物：全部通过
```

---

## 7. 没做 / 卡住的

- 没有 git add / commit（按任务书要求留给上游）
- 没有改任何闸门/比对口径
- 叶尖间隙的**设计意图**（0.5 mm 还是 2 mm）**没定** —— 那是用户判断，不是执行层能定的。
  本轮的网格用的是参数表的 **0.0005**，对照组 0.002 只在 `%TEMP%` 里验证口径关系后已清理。
- y+ 与网格无关性**都没做** —— 那需要 CFD 证据，不是几何网格质量能回答的。

## 7. 复现命令

```powershell
# 1) 只生成脚本（不启动 AutoGrid）
python C:\Users\Administrator\.agents\skills\numeca-autogrid-meshing\scripts\build_autogrid_mesh.py \
    cases/DF90-001/_automation/g4/mesh-v3.request.json --prepare-only

# 2) 真跑
python C:\Users\Administrator\.agents\skills\numeca-autogrid-meshing\scripts\build_autogrid_mesh.py \
    cases/DF90-001/_automation/g4/mesh-v3.request.json
```

作业配置 `cases/DF90-001/_automation/g4/mesh-v3.request.json`（`config_sha256 = a8076d8d358b9b1b...`）
记载了模式 `new-project`、两排的 `row_type` / `rotation_speed_rpm` / `tip_gap` / `spanwise_layers`，
以及 `mesh: {accuracy: medium, grid_levels: 3, first_cell_height_m: 1e-5}`。