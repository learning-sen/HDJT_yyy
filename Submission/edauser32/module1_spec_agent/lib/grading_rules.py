"""官方评分规则常量（来自 run_score.sh / 赛题 PDF 6.3 的原文数值）。

这些是**打分器的真实基线**，解析 Spec 时用于生成 derived_constraints，
并作为人工核对评分的唯一依据。修改前必须对照 run_score.sh 原文。
"""

# run_score.sh 中 setup_parameters() 为 case1 设定的基线
SCORING_BASELINE = {
    "source": "run_score.sh setup_parameters() + 赛题 PDF 6.3",
    "case": "eda_2026_case_1",
    "ae_lib": "2026_EDA_case1",
    "ae_cell": "OPA",
    "ae_view": "schematic",
    "mde_cell": "OPA_loopgain",
    "mde_view": "spe_state1_Corner",
    "input_param_file": "case1_params_0.txt",
    "best_param_file": "2026_EDA_case1_best_params.txt",
    "ugb_base_hz": 200000000.0,   # 2e8 = 200 MHz
    "area_base": 8000.0,
    "time_base_s": 7200.0,        # 2 小时
    "time_limit_s": 10800,        # 3 小时（超时强杀）
    "cpu_affinity": "1-10",
}

# 硬门槛（所有 PVT 均需满足），来自 PDF 6.3(2)
HARD_GATES = [
    {"metric": "phase_margin", "op": ">=", "value": 50.0, "unit": "deg", "points": 10},
    {"metric": "gain_margin", "op": "<=", "value": -10.0, "unit": "dB", "points": 10},
    {"metric": "i_opa", "op": "<=", "value": 3.0, "unit": "mA", "points": 10},
]

# 优化目标（PDF 6.3(3)）
OPTIMIZATION_TARGETS = [
    {"metric": "dc_gain", "direction": "maximize", "floor": 40.0, "unit": "dB", "points": 10,
     "note": "所有 PVT 最坏情况; <40dB 本项记 0 分"},
    {"metric": "ugb", "direction": "maximize", "unit": "MHz", "points": 15},
    {"metric": "area", "direction": "minimize", "unit": "um^2", "points": 15},
]

# 面积口径（PDF 6.3 注）
AREA_FORMULA = {
    "transistor": "fw * L * m * 1.5",
    "capacitor": "W * L * 1",
    "resistor": "W * L * 2",
}

# 器件取值范围（PDF 附件 2）
DEVICE_BOUNDS = {
    "transistor_width_um": [0.13, 20.0],
    "transistor_length_um": [0.13, 10.0],
    "multiplier_m": [1, 20],
    "resistor_seg": [1, 20],
    "capacitor_l_um": [0.13, 20.0],
}

# PVT 覆盖要求（PDF 6.2(5)）
PVT_REQUIREMENT = {
    "model_corners": ["TT", "FF", "SS"],
    "temperatures_c": [-40, 27, 125],
    "supply_tolerance_pct": 10,
    "supply_nominal_v": 1.8,
}
