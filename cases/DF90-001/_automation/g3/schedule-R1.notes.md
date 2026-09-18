# DF90-001 R1 的 SectionSchedule 来源说明

由 tools/g3_schedule.py 从 01-scheme 的两张表生成。**哪些是原生、哪些是推算，必须分清：**

| 字段 | 来源 |
|---|---|
| blade_count = 9 | 原生，来自参数表「叶片数」 |
| chord_m = 0.090000 | 原生，来自参数表「弦长」；**沿展向取常数** |
| stagger_deg = -68.392 | 参数表给的是**进口金属角**，这里当作安装角用 —— 两者不是一回事（金属角是中弧线切线角，安装角是前后缘连线角）。这是本转换的**已知近似**，不是等价。 |
| radius_m | 推算：由流道尺寸表在 z=0.0490 处插值得 hub=0.107774 / shroud=0.300000，再按余弦展向律分配 |
| span_fraction | 推算：余弦展向律，13 个截面 |
| geometry_id | geo_test_123 —— 由 --geometry-id 传入，工具不猜。早先留空占位是错的：空 id 会让 schedule 通过 schema 校验、然后在 build_blade 第一步 KeyError |
| axial_offset_m / lean_m / sweep_m | 参数表里没有，取 0 |

**为什么截面数不是 1：** 参数表一个叶排只有一行，而 SectionSchedule 要求 >=2 个截面。
沿展向展开是必须的一步，展开律是一个工程选择，不是从数据里读出来的。
