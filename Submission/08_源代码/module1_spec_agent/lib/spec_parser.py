"""模块 1：自然语言 Spec → 结构化 JSON。

契约见 ../CONTRACTS.md 第 1 节。核心设计：

1. **规则引擎为主**：离线可跑、无第三方依赖、结果可解释（技术报告要写"为何这样解析"）。
2. **LLM 为可选增强**：`use_llm=True` 时若环境变量齐全且客户端可用，才调用；
   任何失败都回退规则解析，绝不抛异常（打分器可能在无网络环境跑）。
3. **单位归一化**：所有输出统一到规范单位（dB / MHz / deg / mA / um^2）。
4. **不丢信息**：解析不了的内容进 `meta.unparsed_fragments` 或 `ambiguities`。

规范指标名见 CONTRACTS.md 第 0 节。
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import grading_rules as gr
import spec_schema as ss

# ---------------------------------------------------------------------------
# 规范指标表：别名按"长优先"排序，避免 "增益带宽积" 被 "增益" 抢先匹配
# ---------------------------------------------------------------------------

METRIC_ALIASES: Dict[str, List[str]] = {
    "dc_gain": ["直流增益", "开环增益", "dc增益", "dc gain", "gain_db", "增益", "dcgain"],
    "ugb": ["单位增益带宽", "增益带宽积", "unity gain bandwidth", "ugb", "gbw"],
    "phase_margin": ["相位裕度", "相位余量", "phase margin", "pm"],
    "gain_margin": ["增益裕度", "增益余量", "gain margin", "gm"],
    "i_opa": ["工作电流", "静态电流", "总电流", "i_opa", "iop"],
    "power": ["功耗", "power"],
    "slew_rate": ["压摆率", "slew rate", " sr "],
    "area": ["面积", "area"],
    "output_swing": ["输出摆幅", "output swing"],
    "input_cm_range": ["输入共模范围", "icmr"],
    "cmrr": ["共模抑制比", "cmrr"],
    "psrr": ["电源抑制比", "psrr"],
    "noise": ["噪声", "noise"],
    "offset": ["失调", "offset"],
    "transistor_width": ["晶体管宽度", "宽度"],
    "transistor_length": ["晶体管长度"],
}

# 追加官方指标名写法（如 "DC_Gain" / "DC Gain"），对齐教程 10.3 的 name 风格
for _m, _official in ss.METRIC_TO_OFFICIAL.items():
    METRIC_ALIASES.setdefault(_m, [])
    for _a in (_official.lower(), _official.lower().replace("_", " ")):
        if _a and _a not in METRIC_ALIASES[_m]:
            METRIC_ALIASES[_m].append(_a)

DEFAULT_UNIT = {
    "dc_gain": "dB",
    "ugb": "MHz",
    "phase_margin": "deg",
    "gain_margin": "dB",
    "i_opa": "mA",
    "power": "mW",
    "slew_rate": "V/us",
    "area": "um^2",
    "output_swing": "V",
    "input_cm_range": "V",
    "cmrr": "dB",
    "psrr": "dB",
    "noise": "nV/sqrt(Hz)",
    "offset": "mV",
    "transistor_width": "um",
    "transistor_length": "um",
}

# 单位 → (规范单位, 换算系数: 值 * 系数 = 规范值)
# 说明：'deg' 故意不放进正则（防止在英文单词里误匹配），仅当它作为独立 token 出现时，
# 由 _load_number_unit 的 token 检查分支处理。
UNIT_CONVERSION = {
    "a": ("mA", 1e3),
    "ma": ("mA", 1.0),
    "ua": ("mA", 1e-3),
    "µa": ("mA", 1e-3),
    "μa": ("mA", 1e-3),
    "na": ("mA", 1e-6),
    "hz": ("MHz", 1e-6),
    "khz": ("MHz", 1e-3),
    "mhz": ("MHz", 1.0),
    "ghz": ("MHz", 1e3),
    "db": ("dB", 1.0),
    "deg": ("deg", 1.0),
    "°": ("deg", 1.0),
    "度": ("deg", 1.0),
    "v": ("V", 1.0),
    "mv": ("mV", 1.0),
    "um": ("um", 1.0),
    "µm": ("um", 1.0),
    "μm": ("um", 1.0),
    "nm": ("um", 1e-3),
    "us": ("us", 1.0),
    "v/us": ("V/us", 1.0),
    "v/µs": ("V/us", 1.0),
    "mw": ("mW", 1.0),
    "uw": ("mW", 1e-3),
}

# 操作符：长优先
OP_PATTERNS: List[Tuple[str, str]] = [
    # "不得低于/不得超过" 这类否定式必须整词匹配，否则会误命中最长的"大于/小于"
    ("不得低于", ">="), ("不得少于", ">="), ("不得小于", ">="),
    ("不得高于", "<="), ("不得大于", "<="),
    ("不低于", ">="), ("不少于", ">="), ("不小于", ">="), ("至少", ">="),
    ("大于等于", ">="), ("≥", ">="), (">=", ">="),
    ("不高于", "<="), ("不超过", "<="), ("不大于", "<="), ("最多", "<="),
    ("小于等于", "<="), ("以下", "<="), ("以内", "<="), ("≤", "<="), ("<=", "<="),
    ("大于", ">"), (">", ">"),
    ("小于", "<"), ("<", "<"),
    ("等于", "=="), ("==", "=="),
]

MAXIMIZE_HINTS = ["尽可能大", "尽量大", "越大越好", "最大", "最大化", "尽可能高",
                  "尽量高", "越高越好", "增大", "提高", "提升", "增加", "变大",
                  "as large", "maximize"]
MINIMIZE_HINTS = ["尽可能小", "尽量小", "越小越好", "最小", "最小化", "尽可能低",
                  "尽量低", "越低越好", "减小", "减少", "降低", "缩小", "缩短", "节省",
                  "as small", "minimize"]
# 断句词：方向判断最多看到这里，避免"UGB尽量大，面积最小"里面积被误判成 maximize
CLAUSE_CUT = ["，", "。", "；", ";", ",", "、", "并", "且", "同时", "以及", "而"]


def _clip_clause(tail: str) -> str:
    """把片段从第一个断句词处截断（保留断句词前的部分）。"""
    cut = len(tail)
    for tok in CLAUSE_CUT:
        i = tail.find(tok)
        if 0 <= i < cut:
            cut = i
    return tail[:cut]

CIRCUIT_TYPES = [
    ("fully_differential_opamp", ["全差分运放", "全差分放大器", "全差分"]),
    ("single_ended_opamp", ["单端运放", "单端输出运放"]),
    ("two_stage_opamp", ["两级运放", "二级运放"]),
    ("folded_cascode_opamp", ["折叠共源共栅", "折叠cascode"]),
    ("telescopic_cascode_opamp", ["套筒式共源共栅", "套筒cascode"]),
    ("ota", ["ota", "跨导放大器"]),
    ("opamp", ["运放", "运算放大器", "opamp", "operational amplifier"]),
]

FEATURE_HINTS = {
    "common_mode_feedback": ["共模反馈", "cmfb"],
    "miller_compensation": ["米勒补偿", "miller"],
    "cascode": ["共源共栅", "cascode"],
}

# 一行内可出现的多个约束，用这些分隔符切块
# 注意：不要把单独一个"并"当分隔符——"并不低于"会被误切；"、"
# 也不切（"低功耗、高增益、大带宽"是并列形容词，不是约束）
SEGMENT_SPLITTERS = ["，", "。", "；", ";", ",", "、", "且", "并且", "同时", "以及",
                     " and ", "&", "\n"]

NUM_RE = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"
# 单位匹配的坑：
#  1) 单个汉字单位（度/米/安/瓦/秒）不能出现在汉字词内部，
#     否则"宽度"/"面积"里的"度"会被当成角度单位；
#  2) 单字母单位（A/V/W）不能出现在英文单词内部（如 "GAIN" 里的 A）。
_CJK = r"\u4e00-\u9fff"
_LATIN_LETTER = r"A-Za-z"
UNIT_RE = (
    "(?:"
    r"dB|db|DB|MHz|mhz|GHz|ghz|kHz|khz|Hz|hz|mA|uA|µA|μA|nA|"
    r"mV|mW|uW|um|µm|μm|nm|"
    "(?<![%s])度(?![%s])|(?<![%s])米(?![%s])|(?<![%s])安(?![%s])|"
    "(?<![%s])瓦(?![%s])|(?<![%s])秒(?![%s])|°|"
    r"V/us|V/µs|"
    "(?<![%s])A(?![%s])|(?<![%s])V(?![%s])|(?<![%s])W(?![%s])"
    ")" % (_CJK, _CJK, _CJK, _CJK, _CJK, _CJK, _CJK, _CJK, _CJK, _CJK,
           _LATIN_LETTER, _LATIN_LETTER, _LATIN_LETTER, _LATIN_LETTER,
           _LATIN_LETTER, _LATIN_LETTER)
)
PVT_HINTS = ["所有pvt", "全pvt", "所有 pvt", "各pvt", "全corner", "所有corner",
             "所有工艺角", "全工艺角", "所有场景", "全场景", "各种pvt", "any pvt", "all pvt"]


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------

def _load_number_unit(text: str) -> Optional[Tuple[float, str, str]]:
    """从文本中取第一个 数字+单位。返回 (归一化值, 规范单位, 原始片段)。

    若数字后紧跟的是独立单位 token（如 'deg'），也接受；否则按 token 猜单位。
    """
    m = re.search(r"(%s)\s*(%s)?" % (NUM_RE, UNIT_RE), text)
    if not m:
        return None
    value = float(m.group(1))
    raw_unit = (m.group(2) or "").strip()
    if raw_unit:
        key = raw_unit.lower()
        if key in UNIT_CONVERSION:
            canon, factor = UNIT_CONVERSION[key]
            return value * factor, canon, m.group(0)
        return value, raw_unit, m.group(0)

    # 数字后面没有可取的单位：看看是不是 "55deg" / "3mA" 这类被拆开的情况
    tail = text[m.end(1):m.end(1) + 6]
    tm = re.match(r"\s*([A-Za-z°/]+)", tail)
    if tm:
        key = tm.group(1).lower()
        if key in UNIT_CONVERSION:
            canon, factor = UNIT_CONVERSION[key]
            return value * factor, canon, m.group(0) + tm.group(0)
    return value, "", m.group(0)


def normalize_unit(value: float, unit: str, metric: str) -> Tuple[float, str]:
    """把 (值, 单位) 归一化到该指标的规范单位。"""
    if not unit:
        return value, DEFAULT_UNIT.get(metric, "")
    key = unit.lower()
    if key in UNIT_CONVERSION:
        canon, factor = UNIT_CONVERSION[key]
        return value * factor, canon
    return value, DEFAULT_UNIT.get(metric, unit)


def _find_metrics_all(text: str) -> List[Tuple[str, str]]:
    """返回该片段命中的**所有** (规范指标名, 别名)，按别名长度倒序去重。

    必须返回全部：一句话里可能并列出现多个指标，例如
    "最大化单位增益带宽并把面积做到最小" —— 只取最长匹配会丢掉"面积"。
    """
    low = text.lower()
    hits = []
    for metric, aliases in METRIC_ALIASES.items():
        best_alias = None
        for alias in aliases:
            a = alias.lower()
            if a in low and (best_alias is None or len(a) > len(best_alias)):
                best_alias = alias
        if best_alias:
            hits.append((len(best_alias), metric, best_alias))
    hits.sort(key=lambda x: -x[0])

    out: List[Tuple[str, str]] = []
    covered: List[Tuple[int, int]] = []
    seen: set = set()
    for length, metric, alias in hits:
        if metric in seen:      # 一个指标只保留最长的那个别名，避免重复判定
            continue
        a = alias.lower()
        spans = []
        start = 0
        while True:
            i = low.find(a, start)
            if i < 0:
                break
            spans.append((i, i + len(a)))
            start = i + len(a)
        # 若该别名的所有出现位置都已被更长的别名覆盖，则跳过（如"增益"被"单位增益带宽"覆盖）
        fresh = [s for s in spans if not any(s[0] >= c[0] and s[1] <= c[1] for c in covered)]
        if not fresh:
            continue
        covered.extend(fresh)
        seen.add(metric)
        out.append((metric, alias))
    return out


def _collocation_hits(seg: str, existing: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """中文固定搭配兜底：如"大带宽"、"低功耗"这类没有标准别名、也没有数字的写法。

    只返回尚未命中的指标，避免与别名匹配重复。
    """
    have = {m for m, _ in existing}
    out = []
    low = seg.lower()
    for token, metric, _direction in COLLOCATION_RULES:
        if metric in have:
            continue
        idx = low.find(token.lower())
        if idx < 0:
            continue
        have.add(metric)
        out.append((metric, token))
    return out


def _parse_metric_context(seg: str, metric: str, alias: str,
                          fallback_dir: Optional[str]):
    """按**该指标在句中的局部位置**判定 (方向, 操作符, 数字+单位)。

    这是本模块最关键的一处设计：一句话里可能并列多个指标，
    数字/操作符/方向词必须就近判定，不能整段共用。
    例："在满足上述条件的前提下最大化单位增益带宽并把面积做到最小"
        -> UGB 附近有"最大化"，面积附近有"最小"（无数字、无操作符）
    """
    low = seg.lower()
    idx = low.find(alias.lower())
    window = _clip_clause(seg[idx + len(alias):]) if idx >= 0 else _clip_clause(seg)

    direction = _direction(window) or fallback_dir
    op_hit = _find_op(window)
    num = _load_number_unit(window) if op_hit else None
    if num is None:
        tail = seg[idx + len(alias):] if idx >= 0 else seg
        num = _load_number_unit(tail)
    return direction, op_hit, num


def _find_op(text: str) -> Optional[Tuple[str, str]]:
    for token, op in OP_PATTERNS:
        if token in text or token.lower() in text.lower():
            return op, token
    return None


def _direction(text: str) -> Optional[str]:
    low = text.lower()
    for h in MAXIMIZE_HINTS:
        if h in low:
            return "maximize"
    for h in MINIMIZE_HINTS:
        if h in low:
            return "minimize"
    return None


def _local_direction(seg: str, alias: str, fallback: Optional[str]) -> Optional[str]:
    """按"指标别名附近的子句"判定 optimize 方向。

    例："最大化单位增益带宽并把面积做到最小" 里 UGB 附近是"最大化"、
    面积附近是"最小"—— 整段共用一个方向会把面积判错。
    """
    i = seg.lower().find(alias.lower())
    if i < 0:
        return fallback
    tail = _clip_clause(seg[i + len(alias):])
    local = _direction(tail)
    return local if local else fallback


# 中文"形容词 + 指标"的固定搭配：这类片段没有数字也没有常见的方向词，
# 但确实是优化需求。若不显式登记会被静默丢掉（=报告里说不清"为何保留/丢弃"）。
COLLOCATION_RULES = [
    ("高增益", "dc_gain", "maximize"),
    ("大增益", "dc_gain", "maximize"),
    ("增益大", "dc_gain", "maximize"),
    ("高带宽", "ugb", "maximize"),
    ("大带宽", "ugb", "maximize"),
    ("宽带宽", "ugb", "maximize"),
    ("带宽大", "ugb", "maximize"),
    ("低功耗", "power", "minimize"),
    ("小功耗", "power", "minimize"),
    ("低电流", "i_opa", "minimize"),
    ("小面积", "area", "minimize"),
    ("面积小", "area", "minimize"),
    ("高相位裕度", "phase_margin", "maximize"),
]


def _collocation_direction(seg: str, metric: str) -> Optional[str]:
    """按固定搭配判断方向（无数字、无方向词时的兜底）。"""
    for token, m, direction in COLLOCATION_RULES:
        if token in seg and m == metric:
            return direction
    return None


def _is_pvt_scoped(text: str) -> bool:
    low = text.lower().replace(" ", "")
    return any(h.replace(" ", "") in low for h in PVT_HINTS)


def _segment(text: str) -> List[str]:
    parts = [text]
    for sep in SEGMENT_SPLITTERS:
        new = []
        for p in parts:
            new.extend(p.split(sep))
        parts = new
    return [p.strip() for p in parts if p.strip()]


def _dedup(items: List[dict], keys: Tuple[str, ...]) -> List[dict]:
    seen = set()
    out = []
    for it in items:
        k = tuple(it.get(k) for k in keys)
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


# ---------------------------------------------------------------------------
# 主解析
# ---------------------------------------------------------------------------

def parse_spec(text: str, use_llm: bool = False, llm_client: Any = None) -> dict:
    """把自然语言性能规格解析为结构化 Spec（JSON 友好）。

    参数
    ----
    text : 自然语言输入（中文/英文混排均可）
    use_llm : 为 True 时尝试用 LLM 增强；失败/不可用则回退规则解析
    llm_client : 可选，需提供 .complete_json(prompt) -> dict 接口
    """
    if not isinstance(text, str):
        raise TypeError("text 必须是字符串")

    warnings: List[str] = []
    method = "rule"

    # ---- 1. 规则解析 ----
    spec = _rule_parse(text, warnings)

    # ---- 2. LLM 增强（可选，失败回退） ----
    if use_llm:
        merged, llm_note = _try_llm(text, spec, llm_client)
        if merged is not None:
            spec = merged
            method = "rule+llm"
        else:
            warnings.append(llm_note)

    spec["meta"]["parse_method"] = method
    spec["meta"]["warnings"] = warnings
    return spec


def _rule_parse(text: str, warnings: List[str]) -> dict:
    """规则解析主流程：输出对齐教程第 10 节官方 schema，并生成推理链日志。"""
    design_type, design_raw, features = _parse_design_target(text)
    constraints: List[dict] = []
    objectives: List[dict] = []
    unparsed: List[str] = []
    ambiguities: List[dict] = []
    trace: List[dict] = []

    step = [0]

    def log(stage: str, rule: str, evidence: str, result: dict) -> None:
        step[0] += 1
        trace.append({
            "step": step[0],
            "stage": stage,      # 解析阶段：segment / constraint / objective / pvt / derived
            "evidence": evidence,  # 命中的原文片段
            "rule": rule,        # 触发的规则（为人可读的说明）
            "result": result,    # 落到 JSON 的哪个字段
        })

    if design_raw:
        log("design_type", "匹配电路类型关键词 '%s'" % design_raw,
            design_raw, {"design_type": design_type, "features": features})

    for seg in _segment(text):
        metric_hits = _find_metrics_all(seg)
        metric_hits = metric_hits + _collocation_hits(seg, metric_hits)
        if not metric_hits:
            # 解析不了的片段必须登记，不能静默丢弃
            unparsed.append(seg)
            log("segment", "未命中任何指标别名，登记为未解析片段", seg, {"unparsed": seg})
            continue
        pvt = _is_pvt_scoped(seg)
        fallback_dir = _direction(seg)
        log("segment", "切分片段，命中指标 %s" % [m for m, _ in metric_hits], seg,
            {"segment": seg})

        for metric, alias in metric_hits:
            # 按该指标的局部位置判定方向/操作符/数字（不整段共用）
            direction, op_hit, num = _parse_metric_context(seg, metric, alias, fallback_dir)

            if num and op_hit:
                value, unit, raw_num = num
                value, unit = _fix_gain_margin(metric, value, unit)
                op = op_hit[0]
                item = {
                    "id": "",  # 稍后统一编号
                    "name": ss.official_name(metric),
                    "metric": metric,          # 内部规范名，供下游模块使用
                    "op": op,
                    "value": round(value, 10),
                    "unit": unit or DEFAULT_UNIT.get(metric, ""),
                    "type": "hard",
                    "priority": ss.get_constraint_priority(metric),
                    "raw": seg,
                    "scope": "all_pvt" if pvt else "nominal",
                    "origin": "spec_text",
                }
                constraints.append(item)
                log("constraint",
                    "数值 + 操作符 -> 硬约束（别名 '%s'，操作符 '%s'）" % (alias, op_hit[1]),
                    seg, {"name": item["name"], "op": op, "value": item["value"],
                          "unit": item["unit"], "type": "hard"})
            else:
                # 优化目标：方向按**该指标附近**的子句判定，不能整段共用
                source = "方向词"
                if direction is None:
                    direction = _collocation_direction(seg, metric)
                    source = "固定搭配"
                if direction:
                    unit = (num[1] if num else "") or DEFAULT_UNIT.get(metric, "")
                    item = {
                        "id": "",
                        "name": ss.official_name(metric),
                        "metric": metric,
                        "direction": direction,
                        "unit": unit,
                        "type": "soft",
                        "priority": ss.get_objective_priority(metric),
                        "raw": seg,
                        "weight": 0.0,  # 稍后归一化
                    }
                    objectives.append(item)
                    log("objective",
                        "%s命中 -> 优化目标（别名 '%s'，方向 '%s'）" % (source, alias, direction),
                        seg, {"name": item["name"], "direction": direction,
                              "priority": item["priority"]})
                elif num:
                    # 有数值但没操作符 → 登记为歧义，不丢
                    value, unit, raw_num = num
                    value, unit = _fix_gain_margin(metric, value, unit)
                    ambiguities.append({
                        "item": metric,
                        "issue": "该片段有数值但缺少明确的比较关系（如'不低于/不超过'）",
                        "raw": seg,
                        "assumed": {"op": "<=", "value": value,
                                    "unit": unit or DEFAULT_UNIT.get(metric, "")},
                    })
                    item = {
                        "id": "",
                        "name": ss.official_name(metric),
                        "metric": metric,
                        "op": "<=",
                        "value": round(value, 10),
                        "unit": unit or DEFAULT_UNIT.get(metric, ""),
                        "type": "hard",
                        "priority": ss.get_constraint_priority(metric),
                        "raw": seg,
                        "scope": "all_pvt" if pvt else "nominal",
                        "origin": "spec_text",
                    }
                    constraints.append(item)
                    log("constraint",
                        "有数值但无操作符 -> 按 '不超过' 保守建为硬约束，并登记歧义",
                        seg, {"name": item["name"], "op": "<=", "value": item["value"]})

    # ---- 补齐打分门槛：直接写进 constraints，保证"每个被判分的指标都显式在案" ----
    present_metrics = {c["metric"] for c in constraints}
    for gate in ss.GRADING_HARD_GATES + [ss.DC_GAIN_FLOOR]:
        if gate["metric"] in present_metrics:
            continue
        item = {
            "id": "",
            "name": ss.official_name(gate["metric"]),
            "metric": gate["metric"],
            "op": gate["op"],
            "value": float(gate["value"]),
            "unit": gate["unit"],
            "type": "hard",
            "priority": ss.get_constraint_priority(gate["metric"]),
            "raw": "(赛题打分门槛) %s %s %s %s"
                   % (ss.official_name(gate["metric"]), gate["op"], gate["value"], gate["unit"]),
            "scope": "all_pvt" if gate is not ss.DC_GAIN_FLOOR else "nominal",
            "origin": "grading_rule",
            "reason": gate["reason"],
            "points": gate["points"],
        }
        constraints.append(item)
        present_metrics.add(gate["metric"])
        log("constraint",
            "用户需求未给出该指标 -> 按赛题 6.3 打分门槛补为硬约束（不满足该项直接 0 分）",
            item["raw"], {"name": item["name"], "op": item["op"],
                          "value": item["value"], "unit": item["unit"],
                          "origin": "grading_rule"})

    constraints = _dedup(constraints, ("name", "op", "value"))
    objectives = _dedup(objectives, ("name", "direction"))


    for i, c in enumerate(constraints, 1):
        c["id"] = "C%d" % i
    for i, o in enumerate(objectives, 1):
        o["id"] = "O%d" % i

    # 同一指标既有硬约束又有优化目标时 **两者都保留**（教程 10.3 官方示例即如此：
    # DC_Gain 同时在 constraints 与 objectives 里）。硬约束是下限，目标是继续往好里优化。
    # 只做一件事：标注该目标的阈值来自哪条硬约束，便于报告解释。
    cons_by_metric = {}
    for c in constraints:
        cons_by_metric.setdefault(c["metric"], []).append(c)
    for o in objectives:
        related = cons_by_metric.get(o["metric"])
        if related:
            o["supports_constraint"] = related[0]["id"]
            log("objective",
                "与硬约束 %s（%s %s %s）同指标 -> 保留目标并标注支撑关系（硬约束是下限，目标继续优化）"
                % (related[0]["id"], related[0]["name"], related[0]["op"], related[0]["value"]),
                o["raw"], {"objective": o["name"],
                           "supports_constraint": related[0]["id"]})

    if objectives:
        w = round(1.0 / len(objectives), 4)
        for o in objectives:
            o["weight"] = w

    pvt_condition, pvt_detail = _parse_pvt(text, constraints)
    log("pvt", "按关键词与约束 scope 判定 PVT 覆盖", pvt_detail["evidence"] or "默认 nominal",
        {"pvt_condition": pvt_condition, "worst_case": pvt_detail["worst_case"]})

    derived = _build_grading_audit(constraints)
    if derived:
        log("grading_audit", "把赛题 6.3 打分门槛整理成审核表（指向 constraints 里的对应条目）",
            "spec_schema.GRADING_HARD_GATES / DC_GAIN_FLOOR",
            {"grading_audit": [d["name"] for d in derived]})

    spec = {
        "spec_version": "1.2",
        # ---- 官方 schema（教程 10.3）----
        "design_type": design_type,
        "constraints": constraints,
        "objectives": objectives,
        "pvt_condition": pvt_condition,
        "worst_case": pvt_detail["worst_case"],
        # ---- 内部扩展字段（不改官方四要素，供模块 2/3 与报告使用）----
        "source_text": text,
        "grading_audit": derived,
        "pvt_scope": pvt_detail,
        "design_variables_hint": dict(gr.DEVICE_BOUNDS),
        "areas": dict(gr.AREA_FORMULA),
        "ambiguities": ambiguities,
        "reasoning_trace": trace,
        "meta": {
            "parse_method": "rule",
            "warnings": warnings,
            "unparsed_fragments": unparsed,
            "design_type_raw": design_raw,
            "features": features,
        },
    }
    return spec


def _fix_gain_margin(metric: str, value: float, unit: str) -> Tuple[float, str]:
    """增益裕度惯用正值表述（如"增益裕度不低于10dB"）→ 归一到负值域。

    赛题打分口径是 GM <= -10dB，若文本给的是正数（罕见但可能出现），
    取负号以保证与打分器同一口径。
    """
    if metric == "gain_margin" and value > 0:
        return -abs(value), unit
    return value, unit


def _parse_design_target(text: str) -> Tuple[str, str, List[str]]:
    """识别 design_type（教程 10.3 的 fully_differential_opamp_with_cmfb 风格）。"""
    low = text.lower()
    design_type = "unknown"
    raw = ""
    for canon, aliases in ss.DESIGN_TYPE_RULES:
        for a in aliases:
            if a.lower() in low:
                design_type, raw = canon, a
                break
        if design_type != "unknown":
            break
    features = []
    for feat, hints in FEATURE_HINTS.items():
        if any(h in low for h in hints):
            features.append(feat)
    return design_type, raw, features


def _parse_pvt(text: str, constraints: List[dict]) -> Tuple[str, dict]:
    """返回 (pvt_condition, pvt_scope 详情)。

    pvt_condition 取值对齐教程：'all_corners' / 'nominal'。
    """
    declared = _is_pvt_scoped(text)
    scoped = any(c.get("scope") == "all_pvt" for c in constraints)
    evidence = [c["raw"] for c in constraints if c.get("scope") == "all_pvt"]
    if declared:
        evidence = list(dict.fromkeys(evidence + ["需求文本声明覆盖 PVT 全场景"]))

    all_corners = bool(declared or scoped)
    if not all_corners:
        # 赛题兜底：打分门槛（PM/GM/I_OPA）本身要求"所有 PVT 均需满足"，
        # 且教程第 9 节明确"性能指标一律取所有 PVT 下最坏的那个值"。
        # 因此即使需求原文没写 PVT，也必须按全 corner 最坏情况处理，否则优化只用 TYP 会被扣分。
        all_corners = True
        evidence.append(
            "需求原文未声明 PVT；按赛题 6.3 门槛与教程 2.7/第 9 节，"
            "指标一律取所有 PVT 最坏情况（策略：worst_case=true）")

    detail = {
        "all_pvt": all_corners,
        "corners": list(gr.PVT_REQUIREMENT["model_corners"]),
        "temperatures_c": list(gr.PVT_REQUIREMENT["temperatures_c"]),
        "supply_nominal_v": gr.PVT_REQUIREMENT["supply_nominal_v"],
        "supply_tolerance_pct": gr.PVT_REQUIREMENT["supply_tolerance_pct"],
        "worst_case": all_corners,
        "evidence": evidence,
        "declared_in_text": bool(declared),
    }
    return ("all_corners" if all_corners else "nominal"), detail


def _build_grading_audit(constraints: List[dict]) -> List[dict]:
    """把赛题 6.3 打分门槛整理成审核表。

    每条门槛在 `constraints` 里都有对应条目（可能来自用户文本，也可能是我们按门槛补的），
    这里只做"指引"，避免同一约束在两处重复出现造成口径不一致。
    """
    by_metric = {}
    for c in constraints:
        by_metric.setdefault(c["metric"], c)

    out = []
    for gate in ss.GRADING_HARD_GATES + [ss.DC_GAIN_FLOOR]:
        c = by_metric.get(gate["metric"])
        if not c:
            continue
        out.append({
            "name": c["name"],
            "constraint_id": c["id"],
            "op": c["op"],
            "value": c["value"],
            "unit": c["unit"],
            "type": "hard",
            "scope": c.get("scope", "nominal"),
            "origin": c.get("origin", "spec_text"),
            "reason": gate["reason"],
            "points": gate["points"],
            "source": "赛题 6.3 打分门槛",
        })
    return out


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------

VALID_OPS = {">=", "<=", ">", "<", "=="}
VALID_DIRECTIONS = {"maximize", "minimize"}


def validate_spec(spec: dict) -> Tuple[bool, List[str]]:
    """校验 Spec 是否满足教程 10.2 的四要素要求。

    四要素 = constraints（硬约束项）/ objectives（优化目标）/
             unit（指标单位）/ priority（目标优先级）
    """
    errs: List[str] = []

    if not isinstance(spec, dict):
        return False, ["spec 不是 dict"]

    for key in ("spec_version", "design_type", "constraints", "objectives",
                "pvt_condition", "worst_case", "grading_audit", "pvt_scope",
                "reasoning_trace", "ambiguities", "meta"):
        if key not in spec:
            errs.append("缺少顶层字段: %s（应遵循教程 10.3 的官方结构）" % key)
    if errs:
        return False, errs

    if not spec["constraints"]:
        errs.append("constraints 为空：至少要解析出一条硬约束")
    # 注意：objectives 为空只算"不完整"，不算致命错误 —— 需求可能只给硬指标，
    # 优化目标由打分基线补齐。详见 check_spec_completeness()。

    for c in spec["constraints"]:
        for f in ("id", "name", "metric", "op", "value", "unit", "type", "priority", "raw"):
            if f not in c:
                errs.append("约束 %s 缺少字段 %s（教程要求含 name/op/value/unit/type）"
                            % (c.get("id", "?"), f))
        if c.get("op") not in VALID_OPS:
            errs.append("约束 %s 的 op 非法: %r" % (c.get("id"), c.get("op")))
        if not isinstance(c.get("value"), (int, float)):
            errs.append("约束 %s 的 value 非数值: %r" % (c.get("id"), c.get("value")))
        if not c.get("unit"):
            errs.append("约束 %s 缺少单位 unit（评分要求：缺一类扣 1 分）" % c.get("id"))
        if c.get("type") not in ("hard", "soft"):
            errs.append("约束 %s 的 type 非法: %r" % (c.get("id"), c.get("type")))
        if not isinstance(c.get("priority"), int):
            errs.append("约束 %s 缺少整数 priority" % c.get("id"))

    for o in spec["objectives"]:
        for f in ("id", "name", "metric", "direction", "unit", "type", "priority", "raw"):
            if f not in o:
                errs.append("目标 %s 缺少字段 %s（教程要求含 name/direction/priority）"
                            % (o.get("id", "?"), f))
        if o.get("direction") not in VALID_DIRECTIONS:
            errs.append("目标 %s 的 direction 非法: %r" % (o.get("id"), o.get("direction")))
        if not o.get("unit"):
            errs.append("目标 %s 缺少单位 unit" % o.get("id"))
        if not isinstance(o.get("priority"), int):
            errs.append("目标 %s 缺少整数 priority（评分要求目标优先级）" % o.get("id"))

    known = set(METRIC_ALIASES.keys())
    for item in spec["constraints"] + spec["objectives"]:
        if item.get("metric") not in known:
            errs.append("未知规范指标名: %r" % item.get("metric"))
        if item.get("name") != ss.official_name(item.get("metric")):
            errs.append("指标 %s 的官方名不规范: %r（应为 %r）"
                        % (item.get("metric"), item.get("name"),
                           ss.official_name(item.get("metric"))))

    if spec["pvt_condition"] not in ("all_corners", "nominal"):
        errs.append("pvt_condition 非法: %r" % spec["pvt_condition"])
    if not isinstance(spec["worst_case"], bool):
        errs.append("worst_case 必须是布尔值")
    if not isinstance(spec["reasoning_trace"], list) or not spec["reasoning_trace"]:
        errs.append("reasoning_trace 为空：技术报告要求展示每一步决策依据（教程 10.4）")

    return (len(errs) == 0), errs


def parse_and_validate(text: str, use_llm: bool = False, llm_client: Any = None) -> dict:
    """解析并附带校验结果。返回结构含 spec / valid / errors / completeness。"""
    spec = parse_spec(text, use_llm=use_llm, llm_client=llm_client)
    valid, errors = validate_spec(spec)
    return {"spec": spec, "valid": valid, "errors": errors,
            "completeness": check_spec_completeness(spec)}


def check_spec_completeness(spec: dict) -> dict:
    """按教程 10.2 的口径检查四要素是否齐全（**每缺一类扣 1 分**）。

    四要素：
      1. 硬约束项 constraints
      2. 优化目标 objectives
      3. 指标单位 unit（约束与目标都要有）
      4. 目标优先级 priority（约束与目标都要有）

    注意：打分门槛会被自动补进 constraints，所以 constraints 永不为空；
    因此还要单独检查"**到底从需求原文里解析出了几条**"，避免空输入也报 complete。
    """
    cons = spec.get("constraints", []) or []
    objs = spec.get("objectives", []) or []
    missing = []
    if not cons:
        missing.append("硬约束项")
    if not objs:
        missing.append("优化目标")
    for c in cons:
        if not c.get("unit"):
            missing.append("约束 %s 的指标单位" % c.get("id"))
        if not isinstance(c.get("priority"), int):
            missing.append("约束 %s 的目标优先级" % c.get("id"))
    for o in objs:
        if not o.get("unit"):
            missing.append("目标 %s 的指标单位" % o.get("id"))
        if not isinstance(o.get("priority"), int):
            missing.append("目标 %s 的目标优先级" % o.get("id"))

    parsed_from_text = (
        sum(1 for c in cons if c.get("origin", "spec_text") == "spec_text")
        + len(objs)
    )
    if parsed_from_text == 0:
        missing.append("需求原文中未解析出任何指标（只有自动补的打分门槛）")

    missing = list(dict.fromkeys(missing))
    return {
        "complete": len(missing) == 0,
        "missing_items": missing,
        "hard_constraint_count": len(cons),
        "objective_count": len(objs),
        "constraints_from_text": sum(1 for c in cons
                                     if c.get("origin", "spec_text") == "spec_text"),
        "constraints_from_grading": sum(1 for c in cons if c.get("origin") == "grading_rule"),
        "grading_gate_count": len(spec.get("grading_audit", []) or []),
        "reasoning_steps": len(spec.get("reasoning_trace", []) or []),
    }


# ---------------------------------------------------------------------------
# 可选 LLM 增强
# ---------------------------------------------------------------------------

LLM_ENV_HINT = ("需要设置环境变量 QWEN_API_KEY（可选 QWEN_BASE_URL / QWEN_MODEL）"
                "并安装 requests，且 llm_client 或 use_llm=True")


def _try_llm(text: str, baseline: dict, llm_client: Any) -> Tuple[Optional[dict], str]:
    """尝试 LLM 增强。任何异常都返回 (None, 说明)，由调用方回退。"""
    client = llm_client
    if client is None:
        client = _build_env_client()
        if client is None:
            return None, "LLM 不可用（%s），已回退规则解析" % LLM_ENV_HINT

    try:
        prompt = _build_prompt(text)
        data = client.complete_json(prompt)
        if not isinstance(data, dict):
            return None, "LLM 返回非 dict，已回退规则解析"
        return _merge_llm(baseline, data), "已启用 LLM 增强"
    except Exception as exc:  # 网络/解析/配额等任何问题都回退
        return None, "LLM 调用失败(%s: %s)，已回退规则解析" % (type(exc).__name__, exc)


def _build_prompt(text: str) -> str:
    """按教程 10.4 要求构造：系统提示词 + 只要 JSON + 单位归一化约束。"""
    return ss.SYSTEM_PROMPT + "\n\n【用户需求】\n" + text


def _merge_llm(baseline: dict, data: dict) -> dict:
    """LLM 结果与规则结果合并：规则已解析出的硬约束优先保留，LLM 补充缺失项。

    兼容两种 LLM 返回形状：
      - 教程官方结构：{"constraints": [{"name","op","value","unit","type"}...]}
      - 早期结构：{"hard_constraints": [{"metric","op","value","unit"}...]}
    """
    spec = json.loads(json.dumps(baseline))  # deep copy
    known = set(METRIC_ALIASES.keys())

    def to_metric(item):
        """从 name / metric 字段还原内部规范名。"""
        raw = item.get("metric") or item.get("name") or ""
        key = str(raw).strip()
        if key in known:
            return key
        low = key.lower()
        if low in ss.OFFICIAL_TO_METRIC:
            return ss.OFFICIAL_TO_METRIC[low]
        # 官方名大小写不敏感匹配
        for official, metric in ss.OFFICIAL_TO_METRIC.items():
            if official.lower() == low.replace("_", ""):
                return metric
        # 再退一步：走别名表
        hit = _find_metrics_all(key)
        return hit[0][0] if hit else None

    raw_constraints = (data.get("constraints") or data.get("hard_constraints") or [])
    for item in raw_constraints:
        metric = to_metric(item)
        if metric not in known:
            continue
        value = item.get("value")
        if not isinstance(value, (int, float)):
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        value, unit = normalize_unit(value, item.get("unit", ""), metric)
        value, unit = _fix_gain_margin(metric, value, unit)
        item_type = item.get("type")
        spec["constraints"].append({
            "id": "",
            "name": ss.official_name(metric),
            "metric": metric,
            "op": item.get("op") if item.get("op") in VALID_OPS else "<=",
            "value": round(value, 10),
            "unit": unit or DEFAULT_UNIT.get(metric, ""),
            "type": item_type if item_type in ("hard", "soft") else "hard",
            "priority": int(item.get("priority") or ss.get_constraint_priority(metric)),
            "raw": "(LLM) " + str(item.get("raw", "")),
            "scope": item.get("scope", "nominal"),
        })

    for item in data.get("objectives", []) or []:
        metric = to_metric(item)
        if metric not in known:
            continue
        direction = item.get("direction")
        if direction not in VALID_DIRECTIONS:
            continue
        spec["objectives"].append({
            "id": "",
            "name": ss.official_name(metric),
            "metric": metric,
            "direction": direction,
            "unit": item.get("unit") or DEFAULT_UNIT.get(metric, ""),
            "type": "soft",
            "priority": int(item.get("priority") or ss.get_objective_priority(metric)),
            "raw": "(LLM) " + str(item.get("raw", "")),
            "weight": 0.0,
        })

    spec["constraints"] = _dedup(spec["constraints"], ("name", "op", "value"))
    spec["objectives"] = _dedup(spec["objectives"], ("name", "direction"))
    # 同指标允许同时出现在 constraints 与 objectives（教程 10.3 官方示例如此）
    cons_by_metric = {}
    for c in spec["constraints"]:
        cons_by_metric.setdefault(c["metric"], []).append(c)
    for o in spec["objectives"]:
        related = cons_by_metric.get(o["metric"])
        if related:
            o["supports_constraint"] = related[0]["id"]

    for i, c in enumerate(spec["constraints"], 1):
        c["id"] = "C%d" % i
    for i, o in enumerate(spec["objectives"], 1):
        o["id"] = "O%d" % i
    if spec["objectives"]:
        w = round(1.0 / len(spec["objectives"]), 4)
        for o in spec["objectives"]:
            o["weight"] = w

    spec["grading_audit"] = _build_grading_audit(spec["constraints"])
    pvt_condition, pvt_detail = _parse_pvt(spec["source_text"], spec["constraints"])
    spec["pvt_condition"] = pvt_condition
    spec["pvt_scope"] = pvt_detail
    spec["worst_case"] = pvt_detail["worst_case"]

    n = len(spec.get("reasoning_trace", []))
    spec.setdefault("reasoning_trace", []).append({
        "step": n + 1,
        "stage": "llm_merge",
        "evidence": "LLM 补充解析",
        "rule": "LLM 结果与规则结果合并：规则已解析项优先保留，LLM 只补缺失项",
        "result": {"constraints": [c["name"] for c in spec["constraints"]],
                   "objectives": [o["name"] for o in spec["objectives"]]},
    })
    return spec


class OpenAICompatClient:
    """极简 OpenAI 兼容客户端（适配 Qwen 等 /chat/completions 接口）。

    仅在 use_llm=True 且环境变量齐全时会被构造；不引入硬依赖。
    """

    def __init__(self, api_key: str, base_url: str, model: str, timeout: float = 60.0):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def complete_json(self, prompt: str) -> dict:
        import requests  # 局部导入，保证无 requests 时不影响规则解析

        resp = requests.post(
            "%s/chat/completions" % self.base_url,
            headers={"Authorization": "Bearer %s" % self.api_key,
                     "Content-Type": "application/json"},
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return json.loads(_strip_code_fence(content))


def _strip_code_fence(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s


def _build_env_client() -> Optional[OpenAICompatClient]:
    api_key = os.environ.get("QWEN_API_KEY") or os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        return None
    base = os.environ.get("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    model = os.environ.get("QWEN_MODEL", "qwen-max")
    try:
        return OpenAICompatClient(api_key, base, model)
    except Exception:
        return None
