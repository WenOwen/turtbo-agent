# 布局发现：`.iec` 是真实文件，我们第 1 棒的产物可能是错的

> 2026-09-20 05:xx，由编排层读 `numeca-fine-solver/SKILL.md` 得出。
> **这份文件是为了防止这个发现随会话丢失。**

## 一、`.iec` 是真实文件，不是前缀

`C:\Users\Administrator\.agents\skills\numeca-fine-solver\SKILL.md`：

- **第 52 行（第 15 条）**：「若工程为 `<root>/<project>.iec`，其中 computation 名为 `<name>`，
  则所有 `.run/.res/.cgns/.mf/.xmf/.log/.std/.steering` 必须落在 `<root>/<project>_<name>/`」
- **第 98 行**：`finebatch -project <旧或来源.iec> -index <旧工况索引> -mesh <新.igg> -computation <工程目录>/<IEC文件干>_<工况名>/<IEC文件干>_<工况名>.run`
- **第 45 条**：`.iec` 是 FINE 工程内 computation 清单的**规范来源**；计算目录和独立 `.run` **不会自动回写 `.iec`**
- **第 12 条**：一个唯一网格必须对应一个独立 `.iec`；网格身份由 `.igg` 路径 + SHA256 + 块签名共同确定

## 二、由此推出的两个结论

**1. 正确的布局应当是**：

```
04-solve/v3/
  mesh-v4.iec                      <- 工程文件（单个）
  mesh-v4_n05000_p101325/          <- 算例目录
      mesh-v4_n05000_p101325.run
```

**我们现在的布局是错的** —— 6 个 `mesh-v4.iec.*` 文件直接躺在 `04-solve/v3/n05000_p101325/` 下，
**且没有裸 `.iec`**。

**2. 第 1 棒的 `save_project("mesh-v4.iec")` 大概把 `.iec` 当成了名字后缀**，
于是写出 `mesh-v4.iec.bcs` / `.cgns` / `.config` / `.geom` / `.igg` / `.xmt_txt`。
**也就是说：那次调用产的可能是「IGG 工程包」，不是 FINE 的 `.iec` 工程文件。**

⚠ **这不影响块签名验证的结论**（16 块 ALL_MATCH 仍然成立 —— 那验的是 `.igg` 拓扑，
与它装在哪个包里无关）。**但"建好了 FINE 能用的 `.iec`"这个结论要打问号。**

## 二之二、决定性证据：`.iec` 是**单文本文件**

`numeca-fine-solver\scripts\build_multispeed_iec.py` 的实证（这个脚本是 skill 自带的）：

```
2:   """Build a multi-speed FINE/Turbo IEC project from one audited computation."""
23:  r"(?ms)^\*+\s*START COMPUTATION\s+(\d+)\s+SECTION.*?"
144: r"(?m)^(\*+\s*START COMPUTATION\s+)\d+(\s+SECTION)"
315: source_text = read(args.source_project)          <- 当纯文本读
328: r"(?m)^(COMPUTATION_NAME\s+)\S+"                 <- 正则改计算名
335: lambda match: match.group(1) + str(args.mesh.resolve())   <- 正则改网格路径
340: r"(?m)^(LAST_USED_COMPUTATION_INDEX\s+)\d+"       <- 正则改工况索引
```

**结论**：`.iec` 是一个**纯文本文件**，由 `*...START COMPUTATION <n> SECTION` 分块，
含 `COMPUTATION_NAME` / `LAST_USED_COMPUTATION_INDEX` / 网格路径等字段。

**两条推论：**

1. **第 1 棒的 `save_project("mesh-v4.iec")` 产出的 6 个 `.iec.*` 不是 `.iec` 文件。**
   它是 IGG 的工程包。**「FINE 能用的 `.iec`」还没建出来。**
2. **skill 自带脚本就是靠正则改 `.iec` 的**（改网格路径、计算名、工况索引）——
   所以**文本编辑 `.iec` 是被 skill 认可的**。
   （skill 禁止的是「文本替换**旧 `.run`** 的网格声明」，不是 `.iec`。两件事要分清。）
   
## 二之三、正确的做法（推定，待实测）

1. **找一份源 `.iec`** —— v2 的（`04-solve/v2/` 下找）或 `Ducted-Fan` 里的 v7/v8 的
2. **物化 `.run`**：
   `finebatch -project <源.iec> -index <旧工况索引> -mesh 03-mesh/v4/mesh-v4.igg -computation <...>/mesh-v4_n05000_p101325/mesh-v4_n05000_p101325.run`
3. 或者用 `build_multispeed_iec.py` 的同一套手法：读源 `.iec`、正则改网格路径与计算名、写出新 `.iec`
4. **逐块核对 16 块**、grep 零 `Ducted-Fan` 残留
5. **起求解器只跑几十步验证**（标准：`.std` 跑过 `BLOCK NUMBER 3`、不再报 ZONE/SIZE 错、出现 `.res` 与 `.xmf`、残差开始降）

## 三、还要查什么

1. `C:\Users\Administrator\.agents\skills\numeca-igg-skills\`（尤其中文/CLI 参考）
2. `numeca-fine-solver` 的 `references/fine_automation_evidence.md`、`windows_v7_solver_handoff.md`
3. **`numeca-fine-solver\scripts\build_multispeed_iec.py`** —— 它生成 `.iec`，**最直接的线索**
4. `scripts\replace_iec_atomically.ps1`、`scripts\audit_iec_run_sync.ps1`

**判据**：找到一个调用/脚本，能产出**单个 `.iec` 文件**（而不是一堆 `.iec.*`）。

## 四、如果查不出单个 `.iec` 文件

**如实说，并写清查到了什么。** 别编。
第 1 棒的 `mesh-v4.iec.igg` 块签名确实验过了（16/16 ALL_MATCH），这是真的；
「它是 FINE 能用的 `.iec`」这个推论要分开看。