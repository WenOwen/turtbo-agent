# G5 第 1 棒报告：建 `.iec`

> 执行者：本会话（05:0x）。**只做第 1 步，没往下做。**
> **实测** —— 下面是真跑出来的，不是转述。

---

## 一、结论：`.iec` 建成了，块签名 16/16 全对齐

**但 `.iec` 不是"一个文件"，是一个工程包。**

`save_project("<...>\mesh-v4.iec")` 写出的是 6 个同前缀文件，**没有裸的 `mesh-v4.iec`**：

| 文件 | 字节数 | sha256 |
|---|---:|---|
| `mesh-v4.iec.bcs` | 15,981 | `13fa2cfb6856cce7a732446a5628aee382f010697c9c472d54b66f1552fe7893` |
| `mesh-v4.iec.cgns` | 49,987,584 | `6568f5fe1095b9c08cdbdf14da58818cdeadc33086956d06dbdb9bd626de40bc` |
| `mesh-v4.iec.config` | 13,326 | `865c667e9eddb23d8dfd19df01da3eb748886f8dcfae858bf616b25582077b6e` |
| `mesh-v4.iec.geom` | 1,622,509 | `2f204b4c04816f25871a60d99e2d30c5a282bd49f81a36d6232e4fdb919ba2a7` |
| `mesh-v4.iec.igg` | 459,883 | `a53e5a602bb8b1c9941d5b29917ce5bc6b801cba54b6a1ff998233be3411ab42` |
| `mesh-v4.iec.xmt_txt` | 1,701 | `b8eead58f6f40ce9a8c43c624a06213a14f0836dbf7e6998c1e775944fa7b3df` |

路径：`cases/DF90-001/04-solve/v3/n05000_p101325/`

> ⚠ **给下一棒的提醒**：任务书原话是「`.iec` 文件存在，给出字节数与 sha256」——
> 这个说法不成立。`.iec` 在 IGG 的 `save_project` 里是**工程名前缀**，
> 物化 `.run` 时要用哪个前缀文件、还是整个包，**下一棒得自己确认**（我没往下做）。

## 二、块签名对照（`.iec.igg` vs 源 `mesh-v4.igg`）

用 `tools/gate_check.py` 的 `igg_block_signature()` 解析两份 `.igg`：

```
1   row_1_flux_1_Main_Blade_do   6x93x73    6x93x73    OK
2   row_1_flux_1_Main_Blade_ou   6x17x73    6x17x73    OK
3   row_1_flux_1_Main_Blade_up   6x93x73    6x93x73    OK
4   row_1_flux_1_Main_Blade_in   6x17x73    6x17x73    OK
5   row_1_flux_1_Main_Blade_sk   6x17x73    6x17x73    OK
6   row_1_flux_1_Main_Blade_up   6x17x73    6x17x73    OK
7   row_1_flux_1_Main_Blade_do   6x17x73    6x17x73    OK
8   row_1_flux_1_Main_Blade_sh   6x17x17    6x17x17    OK
9   row_1_flux_1_Main_Blade_sh   6x17x17    6x17x17    OK
10  row_2_flux_1_Main_Blade_do   6x49x57    6x49x57    OK
11  row_2_flux_1_Main_Blade_ou   6x17x57    6x17x57    OK
12  row_2_flux_1_Main_Blade_up   6x49x57    6x49x57    OK
13  row_2_flux_1_Main_Blade_in   6x17x57    6x17x57    OK
14  row_2_flux_1_Main_Blade_sk   6x17x57    6x17x57    OK
15  row_2_flux_1_Main_Blade_up   6x17x57    6x17x57    OK
16  row_2_flux_1_Main_Blade_do   6x17x57    6x17x57    OK

VERDICT: ALL_MATCH
```

**16 块，块名与 `IMAX/JMAX/KMAX` 逐块一致。** 点数合计 1,596,448（与 G4 的 v4 网格一致）。

## 三、用的命令（可复现）

```
D:\NUMECA_SOFTWARE\fine161\bin64\iggx86_64.exe -batch -script <脚本> -print
```

脚本（纯 ASCII，IGG 是 **Python 2.7**）：

```python
igg_script_version(2.1)
import os
SRC = r"...\03-mesh\v4\mesh-v4.igg"
DST = r"...\04-solve\v3\n05000_p101325\mesh-v4.iec"
if not os.path.exists(SRC): raise RuntimeError("source not found: " + SRC)
if os.path.exists(DST): raise RuntimeError("refusing to overwrite: " + DST)
open_igg_project(SRC)
print("BLOCKS=%d" % num_of_blocks())
save_project(DST)
print("SAVED=" + DST)
```

**API 出处**：`numeca-igg-skills/references/igg-cli.md:38` ——
「原生保存/打开 | `save_project(path)`、`open_igg_project(path)`」

## 四、踩到的坑（下一棒别再踩）

1. **IGG 的脚本是 Python 2.7**。第一版带中文注释，直接死在：
   `SyntaxError: Non-ASCII character '\xe7' in file ... but no encoding declared`。
   **脚本必须纯 ASCII**（或加 `# -*- coding: utf-8 -*-`）。
2. **`block(i)` 没有 `.name()` 也没有 `.dimensions()`** —— 试过都报 `AttributeError`。
   块签名**不要靠 IGG API 打印**，用 `tools/gate_check.py` 的 `igg_block_signature()` 解析 `.igg` 更省事。
3. **`save_project` 的产物是包不是文件**（见第一节）。
4. **`exit code 0` 不代表成功** —— 第一版失败时也是 `exit=0`。
   必须看日志尾部 / 产物是否存在。

## 五、没做的

- **没有往下做第 2 棒**（物化 `.run`）—— 按任务书要求切碎收尾
- 没有 git add / commit（上游做）
- 没有改任何闸门或比对口径
- 没有碰 `01-scheme/*`、`02-geometry/*`、`03-mesh/*`、`04-solve/v1 v2`

## 六、给下一棒的直接输入

- **源网格**：`03-mesh/v4/mesh-v4.igg`（16 块，1,596,448 点）
- **新建的 `.iec` 包**：`04-solve/v3/n05000_p101325/mesh-v4.iec.*`（6 个文件，哈希见第一节）
- **块签名已验证 16/16 全对齐**
- **下一步**：由这个 `.iec` + `mesh-v4.igg` **物化基准 `.run`**（skill 第 95-97 行），
  再跑 `audit_iec_run_sync.ps1` 硬审计；**不许复用旧 `.run`、不许只替换 `GRID_FILE`**

## 七、日志与脚本位置

- IGG 日志：`04-solve/v3/_iec_build.log`
- 构建脚本：`tools/_g5_iec_build.py`
- 校验脚本：`tools/_g5_iec_verify2.py`