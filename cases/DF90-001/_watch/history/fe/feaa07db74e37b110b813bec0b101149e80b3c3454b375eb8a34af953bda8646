# 案例经验记录 | DF90-001

> 条目格式见 .agents/skills/turbomachinery-case-ledger/SKILL.md。
> 满足晋升三条件之一时，改写为可执行判据进入 skill 的 references/contracts.md。

## 2026-09-17 | 交付文档的"首个振荡背压"有两种状态口径，审计脚本不能只匹配 rejected

- 来源：实测发现（回放审计 v7 时 R-8 首次报 FAIL）
- 现象：CFD-DELIVERY.md 的「已验收最高背压 / 首个振荡背压」表在 4500、5500 rpm 对应
  rejected/persistent_flow_oscillation，但 5000 rpm 的 103525 Pa 在 sweep_summary.csv 里是
  stopped/user_stop（README-CFD.md 记载该点在持续振荡时由用户要求正常保存停止，
  末 3000 步流量 8.540–8.893 kg/s、各 500 步窗口相对极差约 4.04%、振幅不衰减）。
- 合同：审计「振荡侧边界」时，判据必须是**「高于最高验收背压的第一个未验收点」**，
  而不是只匹配 state == "rejected"；同时必须保留该点的 state 与 reason，以便区分
  「机器按策略自动拒绝」与「人干预停止」。
- 证据：cases/DF90-001/_replay/v7/replay_audit.json#R-8；
  Ducted-Fan/run/90kg-duct-fan-v7/fine/v7-optimized/sweep_summary.csv
- 适用边界：凡交付物用自然语言描述「边界」而非直接给状态码的场合。
  **不得据此认为两个状态等价**——rejected 是策略判定，stopped 是人为干预，审计语义不同。
- 晋升状态：已晋升 -> ducted-fan-contracts.md#C-011（并修正 gates.md G5 失败出口的错误状态组合）

## 2026-09-17 | turbo-flow 默认配置会静默改掉被需求锁死的桨盘直径

- 来源：实测发现（G2 对标 A/B 三组）
- 现象：用 turbo-flow 跑涵道风扇工况时，若 annulus.strategy 保持默认的 constant_mean，
  工具按「总状态定尺寸」重算整个流道——输入机匣半径 0.300 m 被改成 0.3486 m，
  轮毂半径 0.103457 被改成 0.0495。这直接违反 requirements.yaml 里锁定的 D=0.600 m。
- 合同：给 turbo-flow 的 annulus 必须显式用 strategy=custom 并给出 hub_curve/shroud_curve
  （两条曲线都须从 x=0 覆盖到 x>=length_m，且 x 单调递增）。
- 证据：cases/DF90-001/01-scheme/v1/benchmark_gate.json；attempt-1 与 attempt-3 的 result.json
- 适用边界：任何「需求锁定了几何尺寸」而一维工具自带尺寸估算逻辑的场合。
  这是一个**通用陷阱**：工具不会报错，只会给出一个看起来合理的错误答案。
- 晋升状态：已晋升 -> ducted-fan-1d-scheme/SKILL.md#两条硬要求A

## 2026-09-17 | turbo-flow 留空 rows 会自动生成三排默认几何

- 来源：实测发现
- 现象：rows: [] + stage_count=1 时，工具自动生成 IGV + R1 + OGV 三排，
  叶片数 36/34/37、弦长 0.04/0.045/0.045、稠度 1.15/1.2/1.3 全是默认值。
  与需求「转子 + 静子两排」不符，且 OGV 扩散因子 0.978（限值 0.6）、de Haller 0.377（限值 0.72）。
- 合同：rows 必须显式给出，不能用自动生成；x_m 必须落在 [0, annulus.length_m] 内。
- 证据：attempt-1/attempt-2 的 metadata.generated_rows 与 constraints
- 适用边界：任何「工具能自动补全缺失拓扑」的场合。**自动补全出的默认值不是设计值。**
- 晋升状态：已晋升 -> ducted-fan-1d-scheme/SKILL.md#两条硬要求B

## 2026-09-17 | flow_coefficient 的桨尖口径与中径口径差 1.49 倍

- 来源：实测发现（B-7 WARN 归因）
- 现象：按桨尖定义算出的 phi_tip = Va/U_tip = 0.2581 输入后，
  工具报告的 flow_coefficient_target 是 0.3864。比值 1.4971 ≈ r_tip/r_mean = 0.300/0.2017 = 1.4871。
- 合同：给 turbo-flow 的 flow_coefficient 必须用中径口径；
  换算 phi_mean = phi_tip * (r_tip / r_mean)。
- 证据：cases/DF90-001/01-scheme/v1/turbo-flow-attempt3/result.json#constraints
- 适用边界：**无量纲系数必须先确认定义半径**（桨尖 / 中径 / 轮毂）。
  这类差异不会被求解器当成错误，只会让可行性判据误报。
- 晋升状态：已晋升 -> ducted-fan-1d-scheme/SKILL.md#口径陷阱C

## 2026-09-18 | finebatch `-index` 是零基，传一基位置会静默物化下一个工况

- 来源：实测发现（G5 物化锚点时踩到）
- 现象：按"IEC 第 1 个 computation"传 `-index 1`，finebatch 把**第 2 个** computation
  （4500 rpm、重启动自锚点）写进了我指定的 `..._n05000_p101325.run`；文件名、大小、
  `Output file(s) successfully written` 全部正常，只有内容错位。
- 合同：`finebatch -index` 取零基位置；物化后必须逐项核对最终 `.run` 的转速、
  出口静压、重启动开关与来源是否等于 IEC 登记项，不得只看文件名或日志成功行。
- 证据：cases/DF90-001/LOG.md#2026-09-18T22:14（v8 求解布置）+ run/90kg-duct-fan-v8/automation/materialize_runs.py
- 适用边界：NUMECA FINE 16.1 `finebatch`；其他 NUMECA 批处理工具的 index 基准需另行实测，不得类推。
- 晋升状态：已晋升 -> numeca-fine-solver/references/multispeed_characteristic_scan.md#6.5

## 2026-09-18 | 冷启动工况不能被写成"从空的路径重启动"

- 来源：实测发现（构建 IEC 与扫描审计各踩一次）
- 现象：计划里 `restart_from` 为空表示冷启动，但构建脚本对所有工况一律写
  `START_FROM_INITIAL_SOLUTION_FILE yes` + 空 `INITIAL_SOLUTION_FILE`；
  同时构建审计与扫描审计都把该工况判为不合格。
- 合同：冷启动写 `START_FROM_INITIAL_SOLUTION_FILE no` + `INITIAL_SOLUTION_FILE unknown`，
  审计把"空 restart"与 `unknown` 视为等价。
- 证据：cases/DF90-001/LOG.md#2026-09-18T22:17；`build_multispeed_iec.py` 与
  `audit_characteristic_scan.py` 已按此修正
- 适用边界：仅适用于计划中显式留空的冷启动点；有路径的重启动点仍必须校验文件存在与依赖顺序。
- 晋升状态：已晋升 -> numeca-fine-solver/references/multispeed_characteristic_scan.md#6.6

## 2026-09-18 | `.par` 文本手术：字段正则跨行会静默改坏参数块

- 来源：实测发现（v8 13 截面重建，叶片扭转整段丢失）
- 现象：用 `VALUE\s{2,}` 改字段时 `\s` 匹配了换行，把 `QUANTITY_TYPE  VALUE` 的下一行
  `UNCERTAIN FALSE` 整行吃掉；AutoBlade 不报错，但重建出的叶片全部截面同一安装角（无扭转）。
- 合同：字段分隔一律 `[ \t]{2,}`，行内容一律 `[^\n]*`；改完必须做"骨架比对"
  （清空数值载荷后逐行相等）再调用 AutoBlade。
- 证据：cases/DF90-001/LOG.md#2026-09-18T22:19（G3 v8 几何）；v8 重建脚本
- 适用边界：所有 AutoBlade/FINE 文本工程的字段级改写；含 `VALUE` 结尾的枚举行是主要触发点。
- 晋升状态：已晋升 -> numeca-autoblade-geometry/references/par_rebuild_pitfalls.md#1.1

## 2026-09-18 | `NUMBER_OF_PARAMETERS` 必须按"任意父容器"统计

- 来源：实测发现
- 现象：只对字面 `PARAMETERS` 容器计数，`SSPS_PARAMETERS`/`CT_PARAMETERS` 被写成 `+0`；
  AutoBlade 把空块当默认值处理，同样表现为叶型被静默替换。
- 合同：维护 `NI_BEGIN/NI_END` 栈，遇到 `NI_BEGIN PARAMETER` 就给直接父容器 +1，
  不判断父容器叫什么；回写后再做骨架比对。
- 证据：cases/DF90-001/LOG.md#2026-09-18T22:19
- 适用边界：AutoBlade `.par`；其他 NUMECA 工程的容器命名规则需另行确认。
- 晋升状态：已晋升 -> numeca-autoblade-geometry/references/par_rebuild_pitfalls.md#1.2

## 2026-09-18 | `.par` 里的 `REVERSE_THETA` 不等于交付 `.geomTurbo` 实际用的值

- 来源：实测发现（v8 转静方向门禁）
- 现象：v7 `R1.par` 存 `REVERSE_THETA +1`，但用它原样重跑导出的转子是**镜像**的；
  只有 `0` 才能复现 v7 交付的 `R1.geomTurbo`。照抄该值会让转静同向，物理上错误。
- 合同：导向前必须用未改动的源 `.par` 重跑一次，比对接头件转子/静子的切向缠绕方向；
  `.par` 里存"真正能复现交付件"的值并写进交付说明。
- 证据：cases/DF90-001/LOG.md#2026-09-18T22:19；`run/90kg-duct-fan-v8/automation/v8_winding_check.py` 输出
- 适用边界：任何从既有 AutoBlade 工程延续的导出；仅凭参数文件不能证明交付件的方向。
- 晋升状态：已晋升 -> numeca-autoblade-geometry/references/par_rebuild_pitfalls.md#5

## 2026-09-18 | `new-project` 之后是质量重置，旧候选值不可套用

- 来源：实测发现
- 现象：流道变化后用 `new-project` 重建，层数/第一层高度/间隙/转速全部照抄，
  最小偏斜角仍从 v7 基线的 11.65° 掉到 9.45°；同一组候选值 97 点在新几何上给 16.406°。
- 合同：`new-project` 后必须重跑单因素扫描（从质量报告最差 block 出发），
  把首轮合格结果当作新基线；已验证候选值只在同一几何上可复现。
- 证据：cases/DF90-001/LOG.md#2026-09-18T22:19（G4）
- 适用边界：AutoGrid 16.1 `new-project`；`template-replace` 不适用此条（几何未变）。
- 晋升状态：已晋升 -> numeca-autogrid-meshing/SKILL.md#new-project 之后的质量重置

## 2026-09-18 | skill 脚本在 GBK 控制台打印中文审计会非零退出

- 来源：实测发现
- 现象：`optimize_existing_mesh.py` 在产物与优化记录**全部写完之后**抛
  `UnicodeEncodeError: 'gbk' codec can't encode character`，退出码 1。
- 合同：调用前设 `PYTHONIOENCODING=utf-8` 或重定向 stdout；出现该异常时先检查
  版本目录与审计 JSON 是否齐全，不要直接判任务失败或重跑。
- 证据：cases/DF90-001/LOG.md#2026-09-18T22:19（G4 的 mesh-v2 优化记录完整）
- 适用边界：中文 Windows + 该 skill 系列脚本；Linux/UTF-8 控制台不触发。
- 晋升状态：已晋升 -> numeca-autogrid-meshing/SKILL.md#脚本输出的编码坑

## 2026-09-18 | AutoBlade 导出的叶型截面点是直角坐标，不是 (r, θ, z)

- 来源：实测发现
- 现象：直接拿第 1 列当半径，会得出"叶片埋在轮毂里"的错误结论；
  `hypot(x, y)` 才等于端壁曲线在对应轴向位置的半径（实测吻合到 1.4 µm）。
- 合同：读 GeomTurbo 叶型前先用轮毂截面自证坐标系；不要跨模板族假定列含义。
- 证据：cases/DF90-001/LOG.md#2026-09-18T22:19（G3）
- 适用边界：AutoBlade 16.1 GeomTurbo；AutoGrid 输出的 GeomTurbo 已由审计器核对端壁哈希。
- 晋升状态：已晋升 -> numeca-autoblade-geometry/references/par_rebuild_pitfalls.md#4
