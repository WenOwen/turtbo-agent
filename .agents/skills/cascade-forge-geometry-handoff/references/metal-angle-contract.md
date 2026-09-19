# 金属角约定：turbo-flow ↔ AutoBlade（实测确认 2026-09-20）

> 这份文件回答一个问题：**一维方案给出的金属角，能不能直接写成 AutoBlade 的 `CAMBER_BETA`？**
> 答案分两半：**能直通**（约定相同），**但不够**（一维给不出展向分布）。

---

## 1. 结论先说

| 问题 | 答案 | 证据 |
|---|---|---|
| 参考方向一样吗 | **一样** —— 都是从**轴向**量起（不是从切向） | 见 §3 证据 1 / 2 |
| 符号一样吗 | **一样**（转子进口都负、静子进口都正） | 见 §3 证据 3 |
| 需要 `90 − x` 之类的换算吗 | **不需要** | 同上 |
| 那 v8 的叶片能由 v3 的三表导出吗 | **不能** | 见 §4 |
| 缺的是什么 | **展向分布** —— 一维平均线只给中径一个值 | 见 §5 |

---

## 2. 两边各自的定义（带出处）

### turbo-flow 侧

```
losses.py:10-11
    def flow_angle_deg(meridional_velocity_m_s, tangential_velocity_m_s):
        return math.degrees(math.atan2(tangential_velocity_m_s,
                                      max(1e-12, meridional_velocity_m_s)))

meanline.py:412-416
    angle1 = flow_angle_deg(before.meridional_velocity_m_s,
                            before.tangential_velocity_m_s - u1)
    angle2 = flow_angle_deg(state.meridional_velocity_m_s,
                            state.tangential_velocity_m_s - u2)
    deviation = -math.copysign(abs(row["deviation_base_deg"]), angle2 - angle1)
    row["metal_angle_in_deg"]  = max(-85, min(85, angle1))
    row["metal_angle_out_deg"] = max(-85, min(85, angle2 - deviation))
```

- **从轴向量起**：`atan2(Wθ, Vm)` —— 分子是切向分量，分母是子午（轴向）分量
- 转子 `Wθ = Cθ − U`（相对系）；静子 `U = 0`，`Wθ = Cθ`（绝对系）
- **出口要减 `deviation`**（默认 `deviation_base_deg = 2.0`，见 `models.py:153`）；进口不减
- 上下限 ±85°：`models.py:145-146` 的 `Field(ge=-85.0, le=85.0)` —— 这个区间本身就说明是**相对轴向**
  （相对切向的角度会落在 ±90 附近，不会用 ±85 截断）

### AutoBlade 侧

来自全局 skill `numeca-autoblade-geometry`：

- `references/autoblade_project_contract.md:42-44`
  ```
  安装角      -> S#_CAMBER_GAMMA
  前缘金属角  -> S#_CAMBER_BETA1
  尾缘金属角  -> S#_CAMBER_BETA2
  ```
- `SKILL.md:35` —— 金属角写在**公共周向坐标**里；符号要靠 `.axx`（转子比 `wu`、静子比 `cu`）
  或显式 `周向方向因子` 恢复
- `SKILL.md:51` / `autoblade_project_contract.md:196` —— **来源不明时必须停下来问**，
  不得按叶排名称、角度正负外观或经验默认判断

**文档只说了"公共周向坐标"，没说参考方向是轴向还是切向。** 所以只能用几何实测来定 —— 见 §3。

---

## 3. 三条实测证据（这才是判据）

### 证据 1：`.par` 的 `CAMBER_GAMMA` 与几何实测安装角逐截面吻合

拿 `02-geometry/v8/autoblade/R1_13span/R1.par` 的 `S#_CAMBER_GAMMA`，
与从同目录 `R1.geomTurbo` 反算的截面安装角（`geom_view.section_metrics` 的 `stagger_deg`）对比：

| 截面 | GAMMA(.par) | 几何实测 | 差 |
|---|---|---|---|
| S1（叶根） | −42.2972 | −42.9114 | 0.6143 |
| S7（中） | −66.2019 | −66.2833 | 0.0814 |
| S13（叶尖） | −74.2925 | −74.2925 | **−0.0000** |

R2 静子同样：S1 差 −0.5934，S13 差 **0.0000**。

**残差沿展向单调衰减到 0** —— 这是反算方法的截断误差（我用吸力面首尾点估弦、用截面平均半径解开周向），
**不是约定差**。约定差会是常数，或者差 90°、或者反号。
**结论：`GAMMA` 是从轴向量起的，与 `geom_view` 同一个 (z, s) 坐标系。**

### 证据 2：`BETA1/BETA2` 与几何反算的中弧线前后缘切线角同定义

用 `tools/geom_check.py` 的 `geom_metal_angles()`（中弧线 = 吸力面与压力面同序号点中点，取两端切线）：

| 叶排 | 量 | 叶根差 | 叶尖差 |
|---|---|---|---|
| R1 转子 | BETA1 | 2.94 | −0.01 |
| R1 转子 | BETA2 | −2.19 | 0.04 |
| R2 静子 | BETA1 | −1.10 | 0.01 |
| R2 静子 | BETA2 | **0.02** | −0.05 |

**同样是沿展向单调衰减**。R2 的 BETA2 几乎处处吻合（最大 0.05°）。
**结论：`BETA1/BETA2` 就是中弧线前后缘切线角，与 `GAMMA` 同一坐标系 —— 从轴向。**

### 证据 3：用 turbo-flow 的公式重算 v3 的表，对得上

`tools/metal_angle_convert.py` 拿 `01-scheme/v3/turbo-flow-v3/result.json` 的站位，
在**各自站位的中径**上重算（进口中径算 β1、出口中径算 β2），与 `叶片几何参数表.csv` 比：

| 叶排 | 量 | 表里 | 重算 | 差 |
|---|---|---|---|---|
| R1 转子 | BETA1 | −68.276 | −68.679 | −0.403 |
| R1 转子 | BETA2 | −60.531 | **−60.531** | **−0.000** |
| S1 静子 | BETA1 | 32.223 | 33.408 | +1.185 |
| S1 静子 | BETA2 | −2.433 | −2.000 | +0.433 |

**R1 的 BETA2 精确到 0.000°** —— 公式（含 `− deviation`）完全对上。
其余三个的 0.4°–1.2° 残差是 turbo-flow **内部使用值**与它**reported 站位**之间的差
（reported 的是设计收敛后的值，内部用的是迭代中途的值），**不是约定差**。

---

## 4. 那为什么 v8 的叶片不是从 v3 导出的

**因为它们本来就不是一条线。**

`_automation/v8/v8_build_par.py` 的文档字符串第一行就写着：

> `v8 / main builder: v7 5-section AutoBlade model -> v8 13-section model.`
> `Changes applied (nothing else is touched):`
> `1. BLADE SECTION COUNT 5 -> 13 ... the five SECTION blocks are replaced by thirteen,`
> `   whose 33+ stored parameters are sampled from a shape-preserving (PCHIP) interpolant`
> `   through the v7 values in span.`

也就是说：**v8 的 `.par` 是把 v7 的 AutoBlade 工程从 5 截面插值到 13 截面做出来的**，
脚本只改了三件事（截面数、轮毂型线、弯掠），**叶片角度整个继承自 v7**。
而 v7 的 AutoBlade 工程来自 AxSTREAM（`.axx`）。

| | 叶片的来源 |
|---|---|
| `01-scheme/v3` 的金属角 | **turbo-flow** 的一维平均线 |
| `02-geometry/v8`（及 v9）的 `CAMBER_BETA` | **v7 的 AutoBlade** ← AxSTREAM |

**两条独立来源，从来没有互相推导过。** 所以数值对不上是应该的，不是谁错了。

---

## 5. 那缺的是什么：展向分布

`01-scheme/v3/turbo-flow-v3/result.json` 里：

```
"metal_angle_in_profile":  [],
"metal_angle_out_profile": [],
```

**全是空数组**（`models.py:147-148` 定义、`analysis.py:98-99` 直接赋空）。
turbo-flow 的一维平均线本来就是**一根流管**，只给中径一个值。

所以：**"每排一个角"不是转换时丢了信息，而是上游本来就只有这一个数。**

从一维到几何，展向律是**设计选择**，不是数据。`tools/metal_angle_convert.py` 把它显式化：

```powershell
python tools/metal_angle_convert.py --case cases/DF90-001 --scheme v3 --row R1
python tools/metal_angle_convert.py --case cases/DF90-001 --scheme v3 --row R1 --law linear --json
```

| `--law` | 含义 | 什么时候用 |
|---|---|---|
| `free` | 自由涡 `r·Cθ = const` | **默认** —— 本项目 `vortex_law: free` |
| `linear` | 线性 `Cθ ∝ r` | 对照 |
| `constant` | 等环量 `Cθ = const` | 对照 |

它输出的假设都写在返回值的 `assumptions` 里，**不许当成数据用**：
- `Vm` 沿展向取常数（圆柱面假设）
- 展向律是设计选择
- `CAMBER_GAMMA` 用 `(β1+β2)/2` 近似 —— 中弧线弯曲时它不是严格解
- `deviation` 固定 2.0°

---

## 6. 对 G3 判据的影响

- **G3-9「由参数表导出」**：现在 v9 只有**流道**能从 v3 导出（逐点偏差 0.0061 mm），
  **叶片不能**。这一条仍然只能说"部分成立"，不许宣称完整。
- **G3-5「几何与参数表一致」**：`S1 出口金属角` 那条 FAIL 是**真差异**（v8 的 −17.34° vs v3 的 −2.43°），
  不是换算错误。要消掉它，得**真的按 v3 重做叶片**（用上面的展向律展开 + 重建 AutoBlade 工程），
  而不是改比对口径。
- **下一步**：用 `metal_angle_convert.py` 的输出重出一版 `.par`，让叶片也来自 v3。
  但要注意 §3 证据 3 那 0.4°–1.2° 的残差 —— 它来自 turbo-flow 内部值与 reported 站位的差，
  换了输入就会变，**不要把残差当成需要"修正"的量去凑**。

---

## 7. 一句话

**约定是同一个约定，换算就是直通；对不上的原因是血缘不同，不是角度口径不同。**

相关：`SKILL.md` 的「输出前自查清单」G3-9；`tools/metal_angle_convert.py`；
`tools/geom_check.py` 的 `geom_metal_angles()`。