"""模块 1 智能体：自然语言 Spec 解析（Spec Agent）。

赛题原文：模块1 = "自然语言 Spec 解析（**智能体**）"，本地部署，LLM 用 Qwen3.8-Max。

智能体行为（LLM 决策）：
    System Prompt（角色 + 工具说明 + 四要素约束 + 单位归一化规则）
      → 模型决定调哪个工具（或直接产出 JSON）
      → 工具执行（规则解析 / 单位归一 / schema 校验 / 打分门槛核对 / 产出）
      → 观察结果后继续决策，直到 finalize

工具集（9 个中的 5 个属模块 1）：
    normalize_metric_unit  指标名与单位归一化（把口语文案映射成规范名 + 规范单位）
    parse_requirement      规则解析需求文本 -> 候选 Spec（确定性）
    validate_spec_schema   按教程 10.2 四要素校验
    check_grading_gates    核对赛题 6.3 打分门槛是否齐全
    lookup_device_bounds   器件取值范围（供模块 3 用）
    emit_structured_spec   finalize：产出最终 Spec
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from agent_runtime import AgentDefinition, AgentRuntime, ToolRegistry
import spec_schema as ss
from spec_parser import (parse_spec, validate_spec, check_spec_completeness,
                          normalize_unit, METRIC_ALIASES, DEFAULT_UNIT, _find_metrics_all)
import grading_rules as gr


# ---------------------------------------------------------------------------
# System Prompt（赛题要求：报告需展示 SystemPrompt）
# ---------------------------------------------------------------------------

SPEC_AGENT_SYSTEM_PROMPT = """你是「模拟电路 Spec 解析智能体」，运行在本地，负责把用户的自然语言性能需求
变成下游优化器可用的结构化 Spec。

【你的身份与目标】
你是模拟集成电路设计专家，熟悉全差分运放、共模反馈（CMFB）、米勒补偿、折叠共源共栅。
你的目标不是"写一段解释"，而是**调用工具**完成解析、校验并产出 JSON。

【可用工具与调用顺序建议】
1. parse_requirement(text)      —— 先拿到确定性解析结果作为基线（不要凭空编造指标）
2. normalize_metric_unit(...)   —— 遇到口语化指标名/单位时用它归一化
3. validate_spec_schema(spec)   —— 校验四要素（硬约束项/优化目标/指标单位/目标优先级）
4. check_grading_gates(spec)    —— 核对赛题打分门槛 PM/GM/I_OPA/DC_Gain 是否齐全
5. lookup_device_bounds()       —— 取器件取值范围（传给模块 3）
6. emit_structured_spec(spec)   —— 产出最终 Spec 并结束

【输出规范 —— 必须严格遵守】
最终 Spec 结构（教程 10.3 官方结构）：
{
  "design_type": "...",
  "constraints": [{"name": "...", "op": ">=|<=|>|<|==", "value": 数值, "unit": "...", "type": "hard", "priority": 整数}],
  "objectives":  [{"name": "...", "direction": "maximize|minimize", "unit": "...", "priority": 整数}],
  "pvt_condition": "all_corners",
  "worst_case": true
}

指标名只能取：DC_Gain, UGB, Phase_Margin, Gain_Margin, I_OPA, Area, Slew_Rate, Power,
Output_Swing, Input_CM_Range, CMRR, PSRR, Noise, Offset

【四要素（缺一类扣 1 分）】
1. 硬约束项 constraints  2. 优化目标 objectives  3. 指标单位 unit  4. 目标优先级 priority

【单位归一化规则】
- 电流 → mA（1A=1000mA，1uA=0.001mA）
- 频率 → MHz（1GHz=1000MHz，1kHz=0.001MHz）
- 增益/裕度 → dB；角度 → deg；长度 → um；面积 → um^2

【语义规则】
- "不低于/不少于/至少/≥/不得低于" → op ">="
- "不超过/不高于/不大于/≤" → op "<="
- "尽可能大/越大越好/最大化/高增益" → direction "maximize"
- "尽可能小/越小越好/最小化/低功耗" → direction "minimize"
- **增益裕度归一到负值域**：GM <= -10dB
- 阈值型描述是硬约束；方向型描述是优化目标；同一指标可以两者都有
- 需求若未写 PVT，按赛题要求默认 pvt_condition="all_corners"、worst_case=true
- 赛题打分门槛（PM>=50°、GM<=-10dB、I_OPA<=3mA、DC_Gain>=40dB）**必须出现在 constraints 里**，
  即使用户没写也要补上（不满足该项直接 0 分）

【行为约束】
- 不要输出与 JSON 无关的长篇解释；优先调用工具。
- 工具返回的确定性结果优先采信；你的补充必须与工具结果一致。
- 完成后必须调用 emit_structured_spec 结束。
"""

SPEC_USER_TEMPLATE = """请解析下面这条自然语言性能需求，产出结构化 Spec：

需求原文：
{requirement_text}

要求：
1. 调用 parse_requirement 拿到基线解析结果
2. 调用 validate_spec_schema 与 check_grading_gates 核对
3. 补齐赛题打分门槛（PM/GM/I_OPA/DC_Gain）
4. 用 emit_structured_spec 产出最终 Spec
"""


# ---------------------------------------------------------------------------
# 工具实现
# ---------------------------------------------------------------------------

def build_spec_tools(cfg: Dict[str, Any]) -> ToolRegistry:
    reg = ToolRegistry(enabled=cfg.get("tools", {}).get("enabled"))

    @reg.register(
        "parse_requirement",
        "对自然语言需求做确定性解析，得到候选 Spec（规则引擎，可离线运行）",
        {"type": "object", "properties": {"text": {"type": "string"}},
         "required": ["text"]})
    def _parse_requirement(text: str, ctx=None):
        spec = parse_spec(text)
        state = (ctx or {}).setdefault("_state", {})
        state["spec"] = spec
        return {
            "design_type": spec["design_type"],
            "constraints": len(spec["constraints"]),
            "objectives": len(spec["objectives"]),
            "n_reasoning_steps": len(spec.get("reasoning_trace", [])),
            "unparsed_fragments": spec["meta"].get("unparsed_fragments", []),
        }

    @reg.register(
        "normalize_metric_unit",
        "把口语化指标名/单位归一化为规范指标名与规范单位",
        {"type": "object", "properties": {"metric_text": {"type": "string"},
                                          "value": {"type": "number"},
                                          "unit": {"type": "string"}},
         "required": ["metric_text"]})
    def _normalize_metric_unit(metric_text: str, value: float = 0.0, unit: str = "", ctx=None):
        hits = _find_metrics_all(metric_text)
        if not hits:
            return {"found": False, "metric_text": metric_text,
                    "hint": "未命中规范指标；可用指标见 config 中的指标表"}
        metric = hits[0][0]
        v, u = normalize_unit(float(value or 0.0), unit, metric)
        return {"found": True, "metric": metric, "official_name": ss.official_name(metric),
                "value": v, "unit": u or DEFAULT_UNIT.get(metric, "")}

    @reg.register(
        "validate_spec_schema",
        "按教程 10.2 校验四要素（硬约束项/优化目标/指标单位/目标优先级）",
        {"type": "object", "properties": {"spec": {"type": "object"}},
         "required": ["spec"]})
    def _validate_spec_schema(spec: dict, ctx=None):
        ok, errs = validate_spec(spec)
        comp = check_spec_completeness(spec)
        return {"valid": ok, "errors": errs, "completeness": comp}

    @reg.register(
        "check_grading_gates",
        "核对赛题 6.3 打分门槛 PM/GM/I_OPA/DC_Gain 是否都在 constraints 里",
        {"type": "object", "properties": {"spec": {"type": "object"}},
         "required": ["spec"]})
    def _check_grading_gates(spec: dict, ctx=None):
        cons = spec.get("constraints") or []
        names = {str(c.get("name", "")).lower().replace("_", "") for c in cons}
        missing = []
        for gate in ss.GRADING_HARD_GATES + [ss.DC_GAIN_FLOOR]:
            if ss.official_name(gate["metric"]).lower().replace("_", "") not in names:
                missing.append(ss.official_name(gate["metric"]))
        return {"all_present": not missing, "missing_gates": missing,
                "gate_count": len(cons)}

    @reg.register(
        "lookup_device_bounds",
        "查询赛题规定的器件取值范围（晶体管/电阻/电容），供尺寸优化使用",
        {"type": "object", "properties": {}})
    def _lookup_device_bounds(ctx=None):
        return {"device_bounds": gr.DEVICE_BOUNDS,
                "area_formula": gr.AREA_FORMULA,
                "scoring_baseline": {k: gr.SCORING_BASELINE[k]
                                     for k in ("ugb_base_hz", "area_base", "time_base_s")}}

    @reg.register(
        "emit_structured_spec",
        "产出最终结构化 Spec（提交版：只含教程 10.3 官方结构）",
        {"type": "object", "properties": {
            "spec": {"type": "object"},
            "variant": {"type": "string", "enum": ["submit", "full"]}},
         "required": ["spec"]})
    def _emit_structured_spec(spec: dict, variant: str = "full", ctx=None):
        payload = ss.to_submission(spec) if variant == "submit" else spec
        state = (ctx or {}).setdefault("_state", {})
        state["final_spec"] = payload
        return payload

    return reg


# ---------------------------------------------------------------------------
# Fallback 计划（无 LLM 时的确定性路径，工具集完全一致）
# ---------------------------------------------------------------------------

def spec_fallback_plan(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    text = ctx.get("requirement_text", "")
    return [
        {"tool": "parse_requirement", "args": {"text": text},
         "thought": "先用规则引擎做确定性解析，得到可核对的基线 Spec"},
        {"tool": "validate_spec_schema",
         "args": {"__from_state__": "spec", "__target__": "spec"},
         "thought": "校验四要素是否齐全（缺一类扣 1 分）"},
        {"tool": "check_grading_gates",
         "args": {"__from_state__": "spec", "__target__": "spec"},
         "thought": "核对赛题打分门槛 PM/GM/I_OPA/DC_Gain 是否齐备"},
        {"tool": "lookup_device_bounds", "args": {},
         "thought": "取器件取值范围与打分基线，供下游模块使用"},
        {"tool": "emit_structured_spec",
         "args": {"__from_state__": "spec", "__target__": "spec"},
         "thought": "产出最终 Spec"},
    ]


# ---------------------------------------------------------------------------
# 对外入口
# ---------------------------------------------------------------------------

def build_spec_agent(cfg: Dict[str, Any]) -> AgentDefinition:
    return AgentDefinition(
        name=cfg.get("agent", {}).get("name", "EDA-Spec-Agent"),
        system_prompt=SPEC_AGENT_SYSTEM_PROMPT,
        user_prompt_template=SPEC_USER_TEMPLATE,
        registry=build_spec_tools(cfg),
        finalize_tool="emit_structured_spec",
        fallback_plan=spec_fallback_plan,
    )


def run_spec_agent(requirement_text: str, cfg: Dict[str, Any],
                   llm: Any = None) -> Dict[str, Any]:
    """运行模块 1 智能体，返回 {answer, reasoning}。"""
    defn = build_spec_agent(cfg)
    rt = AgentRuntime(defn, cfg, llm=llm,
                      verbose=cfg.get("agent", {}).get("verbose", True))
    return rt.run({"requirement_text": requirement_text})
