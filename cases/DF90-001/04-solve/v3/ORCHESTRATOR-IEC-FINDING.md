# 编排层亲自动手的结果（2026-09-20 05:xx）

> 六个执行者全部因**上下文耗尽 / 委托深度上限 3**交回。编排层亲自接手这一步。
> **这份文件里的一切都是编排层实测的。**

---

## 一、源 `.iec` 找到了（这是前几棒都没做成的第一件事）

`D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v8\fine\v8-optimized\v8-optimized.iec`
（24,382.70 KB，601,935 行，**57 个 computation 段**）

**案例内一个 `.iec` 都没有** —— 所以必须从 `Ducted-Fan` 取。

### 结构（实测）

```
    1| NUMECA_PROJECT_FILE   VERSION 1610
    2| PROJECT_TYPE  STRUCTURED
    3| COMPUTATION_NAME n05000_p101325     <- 项目级：当前工况名
    5| GRID_FILE   D:\...\v8\mesh\mesh-v2\mesh-v2.igg
   13| LAST_USED_COMPUTATION_INDEX    56
   16| ******* START COMPUTATION 1 SECTION  *******
   18|   NI_BEGIN computation
   20|     NAME     n05000_p101325           <- 段内用 NAME，不是 COMPUTATION_NAME！
```

**⚠ 关键：段内的工况名键是 `NAME`，不是 `COMPUTATION_NAME`。**
前几棒按 `COMPUTATION_NAME` 找段内名字，全部落空（57 段全报 `(none)`）。

**`n05000_p101325` 在第 1 段 —— 即 `finebatch -index 1`。**

## 二、`.iec` 已产出并改绑（编排层实测）

```
cases/DF90-001/04-solve/v3/mesh-v4.iec
  字节   24,365,931
  sha256 8eadeb1ace762991318b4721218e4ecdea408da82583efa3bad9120950ccedac
```

改绑了一行：
```
旧  GRID_FILE   D:\Project\Research\Ducted-Fan\run\90kg-duct-fan-v8\mesh\mesh-v2\mesh-v2.igg
新  GRID_FILE   D:\Project\Research\turtbo-agent\cases\DF90-001\03-mesh\v4\mesh-v4.igg
```

**依据**：skill 自带脚本 `numeca-fine-solver\scripts\build_multispeed_iec.py` 就是**把 `.iec` 当纯文本、
用正则改网格路径/工况名/索引**的（第 315/328/335/340 行）。所以**改 `.iec` 是被认可的做法**。

> ⚠ skill 禁止的是「文本替换**旧 `.run`** 的网格声明」，**不是 `.iec`**。这两件事必须分清。

## 三、⚠ 下一棒必须解决的：56 行残留

`mesh-v4.iec` 里**还有 56 行指向 `Ducted-Fan`**，全部是 `INITIAL_SOLUTION_FILE`：

```
INITIAL_SOLUTION_FILE  D:/Project/Research/Ducted-Fan/run/90kg-duct-fan-v8/fine/v8-optimized/v8-optimized_n05000_p101325/v8-op...
INITIAL_SOLUTION_FILE  .../v8-optimized_n05000_p101107/v8-op...
... 共 56 行
```

**这些是 56 个工况各自的重启动文件路径。**

**要查清两件**：
1. **第 1 段（`n05000_p101325`）自己有没有 `INITIAL_SOLUTION_FILE`** ——
   如果有，新 `.run` 会**从 v8 的解重启动**，而 v8 是**另一套几何/叶片**，那是错的。**必须清掉或改指。**
2. 其余 55 段的残留要不要清 —— `finebatch -index 1` 只物化第 1 段，理论上不影响，
   但**第 14 条要求 `.iec` 顶层与 `.run` 顶层一致**，保险起见应一并处理或明确记录为什么可以不动。

## 四、下一棒怎么做（命令已明确）

**1. 先解决上面那 56 行**（至少第 1 段那个）

**2. 建第 15 条要求的原生布局**：
```
04-solve/v3/
  mesh-v4.iec                              <- 已产出 ✓
  mesh-v4_n05000_p101325/                  <- 待建
      mesh-v4_n05000_p101325.run           <- 待物化
```

**3. 物化 `.run`**：
```
finebatch -project cases/DF90-001/04-solve/v3/mesh-v4.iec -index 1 \
          -mesh cases/DF90-001/03-mesh/v4/mesh-v4.igg \
          -computation cases/DF90-001/04-solve/v3/mesh-v4_n05000_p101325/mesh-v4_n05000_p101325.run
```

**4. 逐块核对 16 块**（块名 + IMAX/JMAX/KMAX），grep 零 `Ducted-Fan` 残留

**5. 起求解器只跑几十步**（验证标准，不是「启动没报错」）：
```
euranusx86_64.exe "<run>" -steering "<steering>" -niversion 161 -seq -batch   （stdout 重定向到 .std）
```
- `.std` 要**跑过 `BLOCK NUMBER 3`**，不再报 `!ZONE HAVE NOT THE SAME SIZE`
- **出现 `.res` 与 `.xmf`**
- **残差开始下降**

⚠ 求解器**按 `GRID_FILE` 换扩展名要同名 `.cgns`** —— 只搬 `.igg` 会死在 `CANNOT OPEN CGNS FILE`
（`03-mesh/v4/mesh-v4.cgns` 48 MB，已在）

## 五、编排层没做的

- **没跑 `finebatch`** —— 上下文已耗尽
- **没起求解器**
- 没 git add / commit

## 六、这一夜的教训（写给下一轮）

**委托深度上限是 3。** 今夜的链走到了 7 层，每一层转包一次、烧一次上下文，
最后卡在深度上限上，G5 第 2 棒连跑六棒都没交出来。

**正确形态**：任务切到每一棒**一层之内就能做完**，执行者**带完整任务书直接干、不转包**。
G5 第 1 棒（`.iec` 块签名）就是这么成功的，第 2 棒之后全败在转包上。