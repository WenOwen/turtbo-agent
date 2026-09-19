# G5 第 4 棒 —— 编排层亲自做（depth 3，无法再转包）

> 2026-09-20 05:3x。**目的**：上游轮次随时断，这份文件保证状态可接。

## 结论先说：**求解器跑起来了，finebatch 的 "NOT CONSISTENT" 警告不是致命的**

```
Rotor/Stator Pre-processing completed
ROTOR/STATOR PRE-PROCESSING COMPLETED ON GRID 3
Computed Rotor-Stator FNMB data written for grid level 222
PREPARING DATA FOR TURBULENCE
TURBULENT DATA: DONE  66.13%        <- 正在初始化
```

**已经过了转静交界面预处理** —— 那正是 BLOCK 3 失败会卡住的地方。`.res` 已出现。

## 两条被推翻的假设

**① `.iec` 不是 IGG 产物。** 我先试了「IGG 新开工程 -> 另存 `.iec`」：

```python
igg_script_version(2.1)
open_igg_project(r'...\03-mesh\v4\mesh-v4.igg')   # OPENED, blocks = 16  <- 读到了 16 块
save_project(r'...\04-solve\v3\mesh-v4.iec')
```

IGG 把 `mesh-v4.iec` 当**基名**，写出 `mesh-v4.iec.igg` + `.bcs` + `.cgns` + `.config` + `.geom` + `.xmt_txt`。
**`.iec` 是 NUMECA 工程文件**（`NUMECA_PROJECT_FILE VERSION 1610` + computation 段）。
它的生成器是 **FINE 的 GUI**（`finex86_64.exe`）—— **批处理做不了**。

**② v8 的 `.iec` 确实带块名**（`SELECT-STRING` 命中 `row_1_flux_1_Main_Blade_downStream` @ 行 8026），
所以上一棒「拓扑不一致」的判断方向是对的 —— **但那个检查比 euranus 的实际需要严**。

## 实际用的东西（可复现）

```
.run      cases/DF90-001/04-solve/v3/mesh-v4_n05000_p101325/mesh-v4_n05000_p101325.run   262.10 KB
.steering 同目录  4.70 KB   （存在但没用上）
启动      euranusx86_64.exe "<run>" -niversion 161 -seq -batch  > probe.std
```

**注意**：这条命令**没有 `-steering`**，也跑起来了。`.steering` 只是监视量配置，不是必需 ——
这与 `numeca-fine-solver` skill 里记的不完全一致，**值得回填 skill**。

## 还没做（留给下一棒）

- 跑完 + 收敛判定 —— `tools/convergence_check.py`
- **静推力三列 + `A_out` 交叉核验** —— `tools/thrust_closure.py`
- **G5-6 锚点对照** —— `tools/anchor_check.py`
- `gate_check solve` / `case_ledger.py add` / `audit`
- **零残留 grep**：`.run` 里 `Ducted-Fan` 有没有残留（这一棒没查）
- **`.run` 的块签名与 v4 网格逐块对照**（这一棒只查到「名字同族」）

## 要转告下游的

- `mesh-v4.iec`（v8 那个 56 段工程）里 **56 行 `Ducted-Fan` 残留全在第 2..56 段**，
  **第 1 段零残留** ✓ —— **扫点阶段必须先清掉那 56 行**，否则那些段会从 v8 的解重启动
- `mesh-v4.WRONG-topology.iec`（23.8 MB）**留着当证据，别删**
- `mesh-v4.iec.igg` / `.bcs` / `.cgns` / `.config` / `.geom` / `.xmt_txt` 是 IGG 那次实验的**副产物**
  （`mesh-v4.iec` 被当基名了），**不是本算例用的网格**，别混淆
- 后台跑着的求解器：`probe.std` 在 `04-solve/v3/mesh-v4_n05000_p101325/` 下

## 纪律

- **没有 git add / commit**（留给上游）
- 没有改 `gate_check.py` / `geom_check.py` 任何比对口径
- **没有编造任何数字**