# G4 执行层记录 —— 03-mesh/v4（单因素优化后的 v11 网格）

> 这是 v4 的一手记录。**完整背景、叶尖间隙实验、口径结论见 `../v3/G4-REPORT.md`**（那一份覆盖 v3 与 v4）。
> 本文件只记 v4 自身的实测数据与复现方式。

## 1. 它是什么

**v3 的 as-built 网格最小偏斜角 14.896°，低于本项目 15.0° 验收线。**
根因不是网格坏了，是**叶片换了**（v11 的金属角与 v8 不同），网格还没跟上。

v4 = 在 v3 的基础上做**单因素优化**：只把 row 1 的 `streamwise_blade_upper_points` 从 **97 改成 101**，
其余（流道、几何、叶尖间隙 0.0005、73/57 层、首层高度 1e-5、转速 6100/0）全部不变。

**选 101 的依据**：单因素扫描里（97 / 101 / 105 / 109 / 113），101 是**满足 ≥16° 的最低代价点** ——
点数 +1.48%、最大膨胀率 2.3496。这与 `numeca-autogrid-meshing/references/v7_mesh_optimization.md`
里那条已验证的经验一致（「Select 101 for the lowest tested cost satisfying the target」）。

## 2. 六件套 + geomTurbo（实测 sha256）

| 文件 | 字节 | sha256 |
|---|---:|---|
| `mesh-v4.trb` | 36,042 | `2a13265c87fb4adb5be099b98f38e6f1e52d034549756ed99004b4b8165862b1` |
| `mesh-v4.igg` | 459,893 | `2314a3453b1b366507df4e75624cc9d13195e10a16facb87dcc7af60a0328efa` |
| `mesh-v4.cgns` | 49,987,584 | `8bc261e619735b8219bd8a98e83d0179c4d6fcf5a21a8f34754c46b0d11a765a` |
| `mesh-v4.bcs` | 15,981 | `13fa2cfb6856cce7a732446a5628aee382f010697c9c472d54b66f1552fe7893` |
| `mesh-v4.config` | 13,326 | `865c667e9eddb23d8dfd19df01da3eb748886f8dcfae858bf616b25582077b6e` |
| `mesh-v4.qualityReport` | 4,462 | `824b2164b1cfcfe9499a947241d0104f51e4132ef3f2eb62c56b417eb179dd52` |
| `mesh-v4.geomTurbo` | 353,777 | `c4cc6340c8b0a6bb5719ab6263f67bcef85991f8ca033fac00e79a399a597ed7` |

> `mesh-v4.geomTurbo` 与 `mesh-v3.geomTurbo` **哈希相同** —— 几何是同一套（v11），变的只有网格密度。
> 这本身是一条一致性证据：优化没有偷偷改几何。

## 3. 质量（实测，来自 `mesh-v4.audit.json`）

```
points    = 1596448
min_skew  = 16.496        <- 目标 >=16 达成（v3 是 14.896）
max_exp   = 2.3496        <- 验收上限 3
validity  = OK  (No Overlapping Cells Generated)
neg_ok    = True
issues    = []            <- 内置审计零 issue（v3 有一条 low_skewness warn）
tip_gap   = True 0.0005
streamwise_upper = 101
块数      = 16（与 v3 / v2 同拓扑）
```

## 4. G4 闸门（实测）

```
$ python tools/gate_check.py mesh --case cases/DF90-001 --version v4 --no-log

第 5 步检查（G4）：通过
  通过 5 / 注意 0 / 没通过 0 / 还查不了 0
  v 网格文件存在  [stem=mesh-v4 suffixes=.bcs,.cgns,.config,.igg,.info,.qualityReport,.trb]  (G4-1)
  v 关键文件齐全  [missing=[]　外部索引满足=[]]  (G4-2)
  v 质量报告非空  [4462 bytes]  (G4-3)
  v 负单元 = 0  [reported=0]  (G4-4)
  v 块签名已记录  [mesh-v4.igg　16 块　row_1_flux_1_M:6x93x73 row_1_flux_1_M:6x17x73 row_1_flux_1_M:6x93x73]  (G4-5)
总体：PASS
```

## 5. 登记与自查

```
$ python tools/case_ledger.py add --case cases/DF90-001 --stage G4 --kind mesh \
    --path "03-mesh/v4/mesh-v4.igg" --version v4 --verdict PASS \
    --from "02-geometry/v11/autoblade/R1_13span/R1.geomTurbo" \
    --criteria "单因素优化 streamwise_blade_upper_points 97->101；最小偏斜角 14.896->16.496 度；16 块；负单元 0；issues 空"
[added] G4 03-mesh/v4/mesh-v4.igg sha256=2314a3453b1b (459893 B)

$ python tools/case_ledger.py add ... --path "03-mesh/v4/mesh-v4.qualityReport" --from "03-mesh/v4/mesh-v4.igg"
[added] G4 03-mesh/v4/mesh-v4.qualityReport sha256=824b2164b1cf (4462 B)

$ python tools/gate_check.py audit --case cases/DF90-001    -> [OK] 合同与代码一致，无漂移
$ python tools/case_ledger.py verify --case cases/DF90-001   -> 校验 61 个产物：全部通过
```

## 6. 复现命令

```powershell
python C:\Users\Administrator\.agents\skills\numeca-autogrid-meshing\scripts\build_autogrid_mesh.py \
    cases/DF90-001/_automation/g4/mesh-v4.request.json
```

作业配置：`cases/DF90-001/_automation/g4/mesh-v4.request.json`
（`mode: new-project`；两排显式给 `row_type` / `rotation_speed_rpm` / `tip_gap`；
`rows[0].mesh.streamwise_blade_upper_points = 101`；`tip_gap_width_m = 0.0005`；
`mesh: {accuracy: medium, grid_levels: 3, first_cell_height_m: 1e-5}`）。

**全部路径都在案例目录内，零 `Ducted-Fan` 引用。**

## 7. 边界

- 这是**几何网格质量**的结论。**网格无关性与 y+ 都没有证据** —— 那要 CFD，不是网格质量能回答的。
- 叶尖间隙用的是参数表的 **0.0005**。它的**设计意图**（0.5 vs v7 的 2 mm）**未定**，属用户判断。
- 没有 git add / commit（留给上游）。没有改任何闸门/比对口径。