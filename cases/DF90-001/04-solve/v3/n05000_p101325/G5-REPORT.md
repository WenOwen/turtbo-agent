# G5 报告（编排层亲跑，2026-09-20 04:4x）

> 执行者：**编排层自己**（子 agent 深度已到 3，不能再转包）。
> 本文件里所有内容都是**实测**，无转述。

---

## 一、算例布置：**成功**

`04-solve/v3/n05000_p101325/`

- 用 `tools/setup_n05000.py`（我给它加了 `--mesh` 参数，原来硬编码 `03-mesh/v2/mesh-v2.igg`）
- GRID_FILE 改绑：`Ducted-Fan\...\mesh-v2.igg` -> **`cases/DF90-001/03-mesh/v4/mesh-v4.igg`**（替换 1 次）
- `.steering` 的 NAME 也改绑
- **零残留**：`leftover_source_refs: []`（grep `Ducted-Fan` / `v8-optimized` 都是 0）
- 网格哈希：原 `433150fa56c18eca…` -> 新 `2314a3453b1b3665…`，**`identical: false`**
  这是**预期的** —— 叶片换了（v11 按 v4 参数表重做），网格必须跟着换，不是纯路径变化
- `setup.json` 已落盘

## 二、求解：**启动后立刻死了，而且是个真问题**

命令（含已知的三个坑的规避）：
```
euranusx86_64.exe "<run>" -steering "<steering>" -niversion 161 -seq -batch > <stem>.std 2>&1
```

- 进程退出，**exit code = 0（euranus 失败也返回 0，退出码不是成功信号）**
- `.std` 8.2 KB，停在 `BLOCK NUMBER 3`；`.log` 63.1 KB
- **没有** `.res` / `.xmf` / 输出 `.cgns`

### 根因（`.log` 尾部原文）

```
!ZONE HAVE NOT THE SAME SIZE
!CGNS SIZE max I,J,K 49 57 13
!IGG  SIZE max I,J,K 105 57 1
```

**`.run` 里声明的网格块结构与新的 `mesh-v4` 对不上。**

### 这意味着什么（重要）

**换网格不只是改 `GRID_FILE` 路径。**
`n05000_p101325.run` 是从 v8 的算例逐字节改绑来的，它内部**记着 `mesh-v2` 的块拓扑**
（`mesh-v2`：1,779,880 点；`mesh-v4`：1,596,448 点 —— **点数不同，拓扑就不同**）。
所以求解器一读到网格就发现尺寸不符，直接退出。

**这一条推翻了我原本的假设**（"改绑网格 = 改 GRID_FILE"）。v2 算例当年能成，是因为它换的
`mesh-v2` 与原始网格**逐字节相同**（`identical: true`）—— 那是纯路径变化。
**而 v11 的网格是新的，拓扑变了，`.run` 必须重新生成，不能只改路径。**

## 三、下一步该做什么（我没做完，如实说）

**要让 `.run` 与 `mesh-v4` 对齐。** 可选路径：

1. **用 FINE 的批处理从网格重建 `.run`** —— `finebatchx86_64.exe` 能从 `.iec`/网格建工程。
   先查 `numeca-fine-solver` skill 里有没有现成配方
2. **走 IGG/CFView 重新导入网格并另存 `.iec`**，再由 `.iec` 生成 `.run`
3. 查 `.run` 里网格声明的具体字段（块数 / 每块 IMAX/JMAX/KMAX），
   **用 `mesh-v4` 的实际块签名替换**（`03-mesh/v4/mesh-v4.audit.json` 里有 16 块的签名；
   同理 `tools/gate_check.py` 的 `igg_block_signature()` 能从 `.igg` 直接解析）

**我倾向第 3 条** —— 它是纯文本替换，最可控，且我们已经有块签名解析器。
但**必须是块数、顺序、每块尺寸全对**，否则会得到静默错误的解。

## 四、`A_out` 交叉核验 / 静推力闭合 / G5-6：**都还没做**

求解没跑起来，所以：
- 静推力三列（`static_thrust_n` / `momentum_thrust_n` / `pressure_thrust_n`）**没有**
- `A_out` 交叉核验**没有**
- `G5-6` 锚点对照**没有**
- `gate_check solve` **没跑**

## 五、没做的与没改的

- **没有 git add / commit**
- 没有改 `gate_check.py` / `geom_check.py` 的任何比对口径
- 叶子间隙 0.002 对照组**没跑**

## 六、这一棒唯一的产出

1. `tools/setup_n05000.py` 加了 `--mesh` 参数（原来是硬编码）——**这条改动应该保留并提交**
2. `04-solve/v3/n05000_p101325/` 的 `setup.json`（布置取证）
3. **本报告 + 上面那条根因** —— 这是今夜最值钱的一条：
   **"换网格"不等于"改 GRID_FILE"，拓扑变了就必须重建 `.run`。**