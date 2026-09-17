# turbo-flow 参考配置（可直接粘贴）

> 本文件是 G2 适配器的**已验证配置**，不是通用模板。
> 换机器/换工况时必须重新做 A/B，不要把这里的数值当普适参数。

## 已验证项目 JSON（attempt-3 骨架）

```json
{
  "schema_version": "1.0",
  "name": "<CASE-ID> ducted fan <rpm>rpm design point",
  "description": "涵道风扇 G2 对标算例。不是试验验证。",
  "fluid": {
    "name": "dry_air",
    "gas_constant": 287.05287,
    "gamma": 1.4,
    "heat_capacity_model": "temperature_dependent"
  },
  "inlet": {
    "total_pressure_pa": 101325.0,
    "total_temperature_k": 288.15,
    "mass_flow_kg_s": 15.09343,
    "absolute_flow_angle_deg": 0.0,
    "total_pressure_profile": [],
    "total_temperature_profile": [],
    "swirl_profile": []
  },
  "shaft": { "rpm": 6100.0 },
  "annulus": {
    "strategy": "custom",
    "inlet_hub_radius_m": 0.103457,
    "inlet_tip_radius_m": 0.300,
    "length_m": 0.180135,
    "hub_curve": [
      {"x": 0,        "r": 0.103457},
      {"x": 0.023915, "r": 0.103457},
      {"x": 0.074194, "r": 0.113681},
      {"x": 0.098407, "r": 0.115980},
      {"x": 0.176808, "r": 0.125168},
      {"x": 0.180135, "r": 0.125500}
    ],
    "shroud_curve": [{"x": 0, "r": 0.300}, {"x": 0.180135, "r": 0.300}],
    "inlet_blockage": 0.0,
    "outlet_blockage": 0.0
  },
  "design": {
    "mass_flow_kg_s": 15.09343,
    "total_pressure_ratio": 1.041818,
    "stage_count": 1,
    "target_efficiency_tt": 0.8931,
    "flow_coefficient": 0.3864,
    "loading_coefficient": 0.1041,
    "reaction": 0.5,
    "exit_swirl_deg": 0.0,
    "stage_work_weights": [],
    "auto_stage_count": false,
    "stage_reactions": [],
    "stage_flow_coefficients": []
  },
  "rows": [
    {"id": "R1", "row_type": "rotor", "stage": 1, "x_m": 0.049,
     "blade_count": 9, "chord_m": 0.090, "solidity": 0.639, "aspect_ratio": 2.0,
     "metal_angle_in_deg": 71.918, "metal_angle_out_deg": 56.144},
    {"id": "S1", "row_type": "stator", "stage": 1, "x_m": 0.1376,
     "blade_count": 11, "chord_m": 0.090, "solidity": 0.70, "aspect_ratio": 2.0,
     "metal_angle_in_deg": 56.144, "metal_angle_out_deg": 0.0}
  ],
  "vortex_law": "free",
  "numerics": {
    "spanwise_points": 17, "streamwise_points": 61, "max_iterations": 120,
    "mass_tolerance": 0.001, "energy_tolerance": 0.00001,
    "streamline_tolerance": 0.00001, "relaxation": 0.35, "momentum_tolerance": 0.001
  },
  "metadata": {}
}
```

## 对标目标 JSON

```json
{
  "source": "<必须写清基线出处，不允许无出处的数字>",
  "rpm": 6100.0,
  "inlet_total_pressure_pa": 101325.0,
  "inlet_total_temperature_k": 288.15,
  "mass_flow_kg_s": 15.09343,
  "total_pressure_ratio": 1.041818,
  "efficiency_tt": 0.8931,
  "power_w": 57695.871,
  "torque_nm": 90.32,
  "tip_radius_m": 0.300,
  "row_count": 2,
  "tol_efficiency_abs": 0.02,
  "tol_power_rel": 0.05,
  "tol_torque_rel": 0.05
}
```

## 命名与目录

```
01-scheme/v1/
  inputs/
    turbo-flow-attempt3.json      <- 生效配置（显式 rows + custom annulus）
    benchmark-targets.json        <- 对标目标（带 source）
  turbo-flow-attempt3/
    result.json                   <- 求解器原始结果（证据，不删）
    designed_project.json
  流道尺寸表.csv
  叶片几何参数表.csv
  通流计算结果表.csv
  benchmark_gate.json
  benchmark_gate.md
```

失败/被否的 attempt 目录**保留不删**，它们是对标结论的一部分。
