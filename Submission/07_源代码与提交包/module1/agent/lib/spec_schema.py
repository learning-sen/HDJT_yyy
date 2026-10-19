"""官方 Spec JSON schema（严格对齐《PyAether 系统学习教程（详细版）》第 10 节）。

教程原文第 10.2 节：JSON 必须包含四类信息，**每缺一类扣 1 分**：
    1. 硬约束项 constraints（必须满足的，如 PM ≥ 55°）
    2. 优化目标 objectives（越大越好 / 越小越好）
    3. 指标单位 unit（dB、MHz、度、mA、μm²…）
    4. 目标优先级 priority（哪个目标更重要）

教程第 10.3 节给出的建议结构（本模块的输出即按此结构）：

    {
      "design_type": "fully_differential_opamp_with_cmfb",
      "constraints": [
        {"name": "DC_Gain", "op": ">=", "value": 95, "unit": "dB", "type": "hard"},
        ...
      ],
      "objectives": [
        {"name": "DC_Gain", "direction": "maximize", "priority": 1},
        ...
      ],
      "pvt_condition": "all_corners",
      "worst_case": true
    }

内部规范名（dc_gain / ugb / ...）与官方名的映射也在此文件维护。
"""

from __future__ import annotations

from typing import Dict, List

# ---------------------------------------------------------------------------
# 内部规范名 <-> 官方指标名（教程 10.3 的 name 取值风格）
# ---------------------------------------------------------------------------

METRIC_TO_OFFICIAL: Dict[str, str] = {
    "dc_gain": "DC_Gain",
    "ugb": "UGB",
    "phase_margin": "Phase_Margin",
    "gain_margin": "Gain_Margin",
    "i_opa": "I_OPA",
    "power": "Power",
    "slew_rate": "Slew_Rate",
    "area": "Area",
    "output_swing": "Output_Swing",
    "input_cm_range": "Input_CM_Range",
    "cmrr": "CMRR",
    "psrr": "PSRR",
    "noise": "Noise",
    "offset": "Offset",
    "transistor_width": "Transistor_Width",
    "transistor_length": "Transistor_Length",
}

OFFICIAL_TO_METRIC: Dict[str, str] = {v: k for k, v in METRIC_TO_OFFICIAL.items()}

# 官方指标名（可作为解析输入别名，例如需求里直接写 "DC_Gain >= 95dB"）
OFFICIAL_ALIASES: List[str] = sorted(METRIC_TO_OFFICIAL.values(), key=len, reverse=True)

# ---------------------------------------------------------------------------
# 电路类型（design_type）
# ---------------------------------------------------------------------------

DESIGN_TYPE_RULES = [
    ("fully_differential_opamp_with_cmfb", ["共模反馈", "cmfb", "全差分运放", "全差分"]),
    ("fully_differential_opamp", ["全差分运放", "全差分放大器"]),
    ("single_ended_opamp", ["单端运放", "单端输出运放"]),
    ("two_stage_opamp", ["两级运放", "二级运放"]),
    ("folded_cascode_opamp", ["折叠共源共栅", "折叠cascode"]),
    ("telescopic_cascode_opamp", ["套筒式共源共栅", "套筒cascode"]),
    ("ota", ["ota", "跨导放大器"]),
    ("opamp", ["运放", "运算放大器", "opamp", "operational amplifier"]),
]

# ---------------------------------------------------------------------------
# 目标优先级（教程 10.3 示例：DC_Gain=1 > UGB=2 > Area=3）
# 数值越小越重要；用户若显式给了优先级则以其为准。
# ---------------------------------------------------------------------------

DEFAULT_OBJECTIVE_PRIORITY = {
    "dc_gain": 1,
    "ugb": 2,
    "area": 3,
    "power": 3,
    "slew_rate": 3,
    "phase_margin": 1,
    "gain_margin": 2,
    "i_opa": 2,
}
FALLBACK_OBJECTIVE_PRIORITY = 9

# 硬约束默认优先级（同为硬约束时按序，仅用于排序展示）
DEFAULT_CONSTRAINT_PRIORITY = {
    "phase_margin": 1,
    "gain_margin": 1,
    "i_opa": 1,
    "dc_gain": 2,
}
FALLBACK_CONSTRAINT_PRIORITY = 5

# ---------------------------------------------------------------------------
# 官方评分门槛（教程第 10 节 + 赛题 6.3）—— 用于派生硬约束
# ---------------------------------------------------------------------------

GRADING_HARD_GATES = [
    {"metric": "phase_margin", "op": ">=", "value": 50.0, "unit": "deg",
     "reason": "赛题 6.3 硬门槛：所有 PVT 均需满足，不满足该项直接记 0 分", "points": 10},
    {"metric": "gain_margin", "op": "<=", "value": -10.0, "unit": "dB",
     "reason": "赛题 6.3 硬门槛：所有 PVT 均需满足，不满足该项直接记 0 分", "points": 10},
    {"metric": "i_opa", "op": "<=", "value": 3.0, "unit": "mA",
     "reason": "赛题 6.3 硬门槛：所有 PVT 均需满足，不满足该项直接记 0 分", "points": 10},
]

DC_GAIN_FLOOR = {"metric": "dc_gain", "op": ">=", "value": 40.0, "unit": "dB",
                 "reason": "赛题 6.3：DC Gain < 40dB 本项记 0 分", "points": 10}

# ---------------------------------------------------------------------------
# 教程 10.4 要求的 System Prompt（技术报告要展示，故内置并可直接导出）
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """你是模拟集成电路设计专家，负责把用户的自然语言性能需求解析为严格的 JSON。

【角色设定】
- 你熟悉全差分运放、共模反馈（CMFB）、米勒补偿、折叠共源共栅等结构。
- 你熟悉运放核心指标：DC Gain(dB)、UGB(MHz)、Phase Margin(deg)、Gain Margin(dB)、
  I_OPA(mA)、Area(um^2)、Slew Rate(V/us)、Power(mW)。

【输出格式约束】
只输出一个 JSON 对象，不要任何解释文字、不要 markdown 代码块。结构固定为：
{
  "design_type": "<circuit type>",
  "constraints": [
    {"name": "<指标名>", "op": ">=|<=|>|<|==", "value": <数值>, "unit": "<单位>", "type": "hard"}
  ],
  "objectives": [
    {"name": "<指标名>", "direction": "maximize|minimize", "priority": <整数, 1 最重要>}
  ],
  "pvt_condition": "all_corners" | "nominal",
  "worst_case": true | false
}

【单位归一化规则（必须执行）】
- 电流统一 mA：1A=1000mA，1uA=0.001mA
- 频率统一 MHz：1GHz=1000MHz，1kHz=0.001MHz
- 增益/裕度统一 dB
- 角度统一 deg（"度"=deg）
- 电容/MOS 长度统一 um：1nm=0.001um
- 面积统一 um^2

【指标名规范】
只能取：DC_Gain, UGB, Phase_Margin, Gain_Margin, I_OPA, Area, Slew_Rate, Power,
Output_Swing, Input_CM_Range, CMRR, PSRR, Noise, Offset

【语义规则】
- "不低于/不少于/至少/≥" -> ">="；"不超过/不高于/不大于/≤" -> "<="
- "大于/超过" -> ">"；"小于" -> "<"
- "尽可能大/越大越好/最大化" -> direction "maximize"
- "尽可能小/越小越好/最小化" -> direction "minimize"
- 增益裕度归一到负值域：GM <= -10dB
- 出现"所有 PVT / 全 corner / 全场景" -> pvt_condition "all_corners"，worst_case true
- 阈值型描述（"不得低于 40dB"）是硬约束，不是优化目标；方向的描述才是优化目标
"""


def official_name(metric: str) -> str:
    """内部规范名 -> 官方指标名（未知则原样返回）。"""
    return METRIC_TO_OFFICIAL.get(metric, metric)


def get_constraint_priority(metric: str) -> int:
    return DEFAULT_CONSTRAINT_PRIORITY.get(metric, FALLBACK_CONSTRAINT_PRIORITY)


def get_objective_priority(metric: str) -> int:
    return DEFAULT_OBJECTIVE_PRIORITY.get(metric, FALLBACK_OBJECTIVE_PRIORITY)


# ---------------------------------------------------------------------------
# 提交版 schema（精简）
# ---------------------------------------------------------------------------

# 教程 10.3 的官方字段，**提交版只保留这些**
SUBMISSION_TOP_LEVEL = ("design_type", "constraints", "objectives",
                        "pvt_condition", "worst_case")


def to_submission(spec: dict) -> dict:
    """把完整 Spec 精简成"提交版"：只保留教程 10.3 的官方结构。

    精简原则（评测口径优先，报告素材另存）：
      保留：design_type / constraints / objectives / pvt_condition / worst_case
      保留：每条约束的 name/op/value/unit/type/priority
           每条目标的 name/direction/unit/priority
      删除：id / metric / raw / origin / scope 等实现细节
      删除：spec_version / source_text / grading_audit / pvt_scope /
            design_variables_hint / areas / ambiguities / reasoning_trace / meta
            （这些是审计与报告素材，放 *_full.json）

    注意：打分门槛（Phase_Margin/Gain_Margin/I_OPA/DC_Gain）必须保留在
    constraints 里 —— 它们是赛题硬性要求，不是可选信息。
    """
    cons = []
    for c in spec.get("constraints", []):
        item = {
            "name": c.get("name"),
            "op": c.get("op"),
            "value": c.get("value"),
            "unit": c.get("unit"),
            "type": c.get("type", "hard"),
        }
        if isinstance(c.get("priority"), int):
            item["priority"] = c["priority"]
        cons.append(item)

    objs = []
    for o in spec.get("objectives", []):
        item = {
            "name": o.get("name"),
            "direction": o.get("direction"),
        }
        if o.get("unit"):
            item["unit"] = o["unit"]
        if isinstance(o.get("priority"), int):
            item["priority"] = o["priority"]
        objs.append(item)

    return {
        "design_type": spec.get("design_type"),
        "constraints": cons,
        "objectives": objs,
        "pvt_condition": spec.get("pvt_condition"),
        "worst_case": spec.get("worst_case"),
    }
