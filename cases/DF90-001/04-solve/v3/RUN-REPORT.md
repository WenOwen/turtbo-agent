# G5 第 2 棒：`.run` 物化 —— 走到哪、卡在哪

> 执行者：编排层（本会话）。**上游明令「自己动手，不要转包」**，我照办了。
> 写这份文件的原因：**上游轮次随时断，写进文件的半成品比转包一圈什么都没落地有价值。**
> 时间：2026-09-20 04:5x。**本棒未完成，卡点见第五节。**

---

## 一、现状（实测）

`cases/DF90-001/04-solve/v3/n05000_p101325/`：

| 文件 | KB | 时间 | 说明 |
|---|---:|---|---|
| `mesh-v4.iec.bcs` | 15.6 | 04:44 | 第 1 棒产出的工程包 |
| `mesh-v4.iec.cgns` | 48816.0 | 04:44 | 同上 |
| `mesh-v4.iec.config` | 13.0 | 04:44 | 同上 |
| `mesh-v4.iec.geom` | 1584.5 | 04:44 | 同上 |
| `mesh-v4.iec.igg` | 449.1 | 04:44 | 同上（块签名 16/16 已验）|
| `mesh-v4.iec.xmt_txt` | 1.7 | 04:44 | 同上 |
| `n05000_p101325.run` | **262.10** | **04:33** | ⚠ **还是旧的** |
| `n05000_p101325.steering` | 4.7 | 04:33 | 旧的 |
| `n05000_p101325.std` | 8.2 | 04:33 | 旧试跑的日志（死在 BLOCK 3）|
| `n05000_p101325.log` | 63.1 | 04:33 | |
| `setup.json` | 3.2 | 04:33 | |

**关键对照**：`04-solve/v2/n05000_p101325/n05000_p101325.run` 也是 **262.10 KB** ——
**两份 `/run` 同尺寸，说明 v3 的 `.run` 就是 v2 那份，块拓扑还是旧的。**

## 二、卡点（上游已查清，我复核了症状）

直接拿旧 `.run` 跑会死在：

```
.std 停在 BLOCK NUMBER 3
  !ZONE HAVE NOT THE SAME SIZE
  !CGNS SIZE max I,J,K  49 57 13
  !IGG  SIZE max I,J,K 105 57  1
```

**而且 exit code 0** —— 这是这个项目里第三次踩到「NUMECA 不拿退出码当信号」
（前两次：IGG 的 `exit=0` 但失败；euranus 失败也返回 0）。

## 三、我找到的正解（skill 第 98 行，原文）

```
finebatch -project <旧或来源.iec> -index <旧工况索引> -mesh <新.igg> \
  -computation <工程目录>/<IEC文件干>_<工况名>/<IEC文件干>_<工况名>.run
```

出处：`C:\Users\Administrator\.agents\skills\numeca-fine-solver\SKILL.md:98`。

配套的硬规矩（同 skill）：
- **第 11 条**：禁止复用旧 `.run` 或只替换 `GRID_FILE`；必须用新 `.igg` 重新物化，逐块核对名称与 `IMAX/JMAX/KMAX`
- **第 12 条**：一个唯一网格必须对应一个独立 `.iec` 工程；网格身份由规范化 `.igg` 路径 + SHA256 + 块签名共同确定
- **第 15 条**：**FINE computation 必须使用 ICE 原生同级目录合同** ——
  若工程为 `<root>/<project>.iec`、computation 名为 `<name>`，
  则所有 `.run/.res/.cgns/...` 必须在 `<root>/<project>_<name>/<project>_<name>.*`

**验证标准**（上游定的，我认同）：**不是「启动没报错」**，而是
① `.std` 跑过 `BLOCK NUMBER 3` 且不再报 ZONE/SIZE 错；② 出现 `.res` 与 `.xmf`；③ 残差开始下降。

## 四、我做到哪一步

1. ✅ 复核了现状（第一节的表，全是实测）
2. ✅ 复核了 `setup.json` 里的工况：**静压 101325 Pa、转速 523.598775571636 rad/s（= 5000 rpm）**，
   来源标注为「原始算例目录的 `boundary_audit.json`（实测）」
3. ✅ 找到了物化的正解命令（第三节）
4. ❌ **没有执行 `finebatch`** —— 卡在第五节那个问题上
5. ❌ 没有逐块核对、没有 grep 残留、没有起求解器试跑

## 五、⚠ 卡在哪（这是个真问题，不是我没时间）

**`finebatch -project` 要一个 `.iec` 工程文件，而目录里没有裸的 `mesh-v4.iec`。**

第 1 棒的 `save_project("<...>/mesh-v4.iec")` 写出的是 **6 个同前缀文件**
（`.iec.bcs` / `.iec.cgns` / `.iec.config` / `.iec.geom` / `.iec.igg` / `.iec.xmt_txt`），
**没有裸的 `mesh-v4.iec`**。第 1 棒的报告里已经把这条标为「任务书说法不成立」并留给下一棒确认 ——
**现在我确认了它的后果：`-project` 没有东西可指。**

同时，这 6 个文件**直接躺在 `04-solve/v3/n05000_p101325/` 下**，
而 skill 第 15 条要求的是 `<root>/<project>_<name>/<project>_<name>.*` 的原生同级目录合同。
**当前布局不符合第 15 条。**

**所以有两个可能**（我没能验证是哪个）：
- (a) `mesh-v4.iec` 这个工程文件本该由 IGG 一起写出，但没写成功（或写到了别处）
- (b) FINE 的工程文件就是那 6 个的某一个，`-project` 该指向它 —— 但 skill 没写清

## 六、下一棒该从哪接

1. **先解决「`.iec` 工程文件在哪」**：
   - 去 `C:\Users\Administrator\.agents\skills\numeca-autogrid-meshing\` 和
     `numeca-igg-skills` 里找 `save_project` 的正确用法 / 工程文件命名
   - 或者在 IGG 里 `save_project` 之后**列出目录看它到底写了什么**（第 1 棒可能漏看了）
   - **确认后再走 `finebatch -project ... -index ... -mesh ... -computation ...`**
2. **顺带确认目录布局**：按 skill 第 15 条，物化前可能要先建
   `<root>/<project>_<name>/` 的原生同级目录
3. 物化后按第三节的验证标准试跑（可只跑几十步）

## 七、我没做的

- **没有 git add / commit**（上游做）
- **没有改 `gate_check.py` / `geom_check.py` 的比对口径**
- **没有碰** `01-scheme/*`、`02-geometry/*`、`03-mesh/*`、`04-solve/v1 v2`
- 没有起求解器（因为 `.run` 还没物化出来）
- **没有转包**（上游明令，我照办）

## 八、一句实话

**这一棒我做到「找到正解 + 定位到真卡点」就断了，`finebatch` 一次都没跑。**
卡点不是「没时间」，是 `-project` 指向的 `.iec` 工程文件不存在 —— 这是第 1 棒留下的悬念
（它当时就标了「下一棒得自己确认」），我确认了它的后果，但没解决它。

**下一步最省力的路径是从第六节第 1 条接**：先搞清 `save_project` 到底该写出什么。

---

# 追加（05:0x–05:1x，第 2 棒实际执行这一层）

> 上一节把卡点定在「`.iec` 工程文件不存在」。**我复核后：卡点不成立 —— 文件在。**
> 下面全是我亲手跑出来的，不是转述。

## 九、先纠正上一节的一个判断

上一节在 `04-solve/v3/n05000_p101325/` 里找裸 `.iec`，没找到。**但工程文件在上一层：**

```
cases/DF90-001/04-solve/v3/mesh-v4.iec      24,365,931 B
```

**它存在。** 上一节的卡点（「`-project` 没有东西可指」）**不成立**。

## 十、`finebatch` 的参数是**位置式**的，不是 flag

实测 `finebatchx86_64.exe --help` 原文：

```
finebatch usage:
         first  argument => input project file (extension .iec)
         second argument => input mesh file (extension .igg)
         third  argument => output computation file (extension .run)
         fourth argument => COMMON (or bin) directory path
         fifth  argument => input computation index (optional)
```

**所以第三节抄的那条 `-project / -index / -mesh / -computation` 写法是错的**，
`finebatch` 不认这些 flag。正确形式（我实际跑的）：

```
finebatchx86_64.exe <iec> <igg> <run> "D:\NUMECA_SOFTWARE\fine161\bin" 1
```

## 十一、56 行残留：**第 1 段零残留** ✓（附带一条警告）

**这个 `.iec` 是 56 段的多算例工程**：

```
第 3 行   COMPUTATION_NAME n05000_p101325
第 13 行  LAST_USED_COMPUTATION_INDEX    56
段边界：第 1 段 = 行 16..10575；第 2 段起于 10576
```

**56 行 `Ducted-Fan` 的行号：最小 10612，最大 591412** —— 全部在第 2..56 段。
**第 1 段（行 16..10575）里 `Ducted-Fan` 零命中。**

第 1 段自己的重启动设置（行 50/52 逐行读出）：
```
START_FROM_INITIAL_SOLUTION_FILE no
INITIAL_SOLUTION_FILE            unknown        <- 值是 "unknown"，不是真路径
```
**第 1 段不会从 v8 的解重启动** ✓

⚠ **警告留给下游**：第 2..56 段那 56 行 `INITIAL_SOLUTION_FILE` 指向 `Ducted-Fan`，
**那些段若被物化会从 v8 的解重启动** —— 而 v8 是另一套几何/叶片，与 v11 不是同一台机器。
**本棒只物化 `index 1`，不受影响；但扫点阶段必须先清掉那 56 行。**

> 我自己一度搞混：`Select-String 'INITIAL_SOLUTION_FILE'` 会同时命中 `START_FROM_INITIAL_SOLUTION_FILE`，
> 所以我一开始以为第 1 段第 50/52 行就是残留。**判别残留必须直接 grep `Ducted-Fan`，不要 grep 字段名。**

## 十二、`finebatch` 实际跑了，**失败** —— 原因未查明

**报错（两种布局都试了，一模一样）：**

```
ERROR:  File: D:\Project\Research\turtbo-agent\cases\DF90-001\03-mesh\v4\ does not exist! STOP !
NIFineBatch::merge_mesh, ERROR: Cannot find the mesh file: 'unknownmesh-v4.igg'
NIFineBatch::merge_mesh, ERROR: IGG file not correct! STOP
exit=0        <- 失败也返回 0，这是本项目第三次踩到 "NUMECA 退出码不是信号"
```

**试过的两种输出布局（都失败）：**
1. `04-solve/v3/n05000_p101325/mesh-v4_n05000_p101325.run`
2. `04-solve/v3/mesh-v4_n05000_p101325/mesh-v4_n05000_p101325.run`（**skill 第 15 条的原生同级目录合同**）

**→ 布局不是原因。**

**已实测排除的：**
- 文件确实在：`cases/DF90-001/03-mesh/v4/mesh-v4.igg` = **459,893 B**，`Test-Path` True
- `.iec` 的 `GRID_FILE`（第 5 行）指对了那个绝对路径
- 输出目录已建、工作路径纯 ASCII

**未查明的、给下一棒的线索（按可能性排序）：**
1. **`'unknownmesh-v4.igg'` 这个拼法最可疑** —— `unknown` 前缀像是从
   `.iec` 第 6/8 行 `RELATIVE_GRID_FILE undefined` / `RELATIVE_TRB_FILE undefined` 取的。
   **finebatch 可能要求 `RELATIVE_GRID_FILE` 有值。** 试试把它填成 `mesh-v4.igg` 或相对路径。
2. `.iec` 第 7/9 行是 `TRB_FILE \usr\unknown` / `GEOMETRY_FILE \usr\unknown` ——
   **第 2 个位置参数给的 `.igg` 可能不够，也许要 `.trb`**（`03-mesh/v4/mesh-v4.trb` 在，35.1 KB）
3. **最有力的旁证**：v2 当年的 `.run` **不是在案例目录里物化的**
   （`04-solve/v2/` 下没有 `.iec`，`boundary_audit.json` 的 `run` 指向 `Ducted-Fan\...`）——
   **当年是在 `Ducted-Fan` 树里、用那边的 `.iec` 物化的。**
   本棒只改了 `GRID_FILE`，**可能不够** —— 也许 `TRB_FILE` / `RELATIVE_*` 也要一起改绑。

## 十三、这一棒做到哪、没做什么

**做到了：** 复核「`.iec` 存在」（推翻上一节卡点）· 查清 `finebatch` 位置式参数 ·
**查清 56 行残留全在第 2..56 段、第 1 段干净** · 实际跑了 `finebatch` 两次、拿到真报错 · 排除布局因素

**没做到：** `.run` 没物化出来 · 因此 16 块对照 / 零残留 grep / 试跑都没做

**没做：** 没有 git add/commit · **没有转包**（一层内做完）· 没改任何比对口径 · **没编造任何数字**

## 十四、下一棒从哪接（一句话）

**从第十二节的线索 1 接**：打开 `mesh-v4.iec`，把第 6 行 `RELATIVE_GRID_FILE undefined`
改成有效值（或把第 7 行 `TRB_FILE` 指向 `03-mesh/v4/mesh-v4.trb`），再跑一次同样的 `finebatch` 位置式命令。