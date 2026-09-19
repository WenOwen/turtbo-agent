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