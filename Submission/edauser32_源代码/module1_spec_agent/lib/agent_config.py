"""智能体配置加载（赛题要求：报告需含"配置文件"）。

配置文件是纯 JSON，便于提交与评审。查找顺序：
  1. 命令行 --config 指定
  2. 环境变量 AGENT_CONFIG
  3. 默认 config/agent_config.json
"""
from __future__ import annotations

import copy
import json
import os
from typing import Any, Dict

DEFAULT_CONFIG: Dict[str, Any] = {
    "agent": {
        "name": "EDA-Spec-Agent",
        "version": "1.0",
        "max_steps": 12,
        "verbose": True,
    },
    "llm": {
        "provider": "qwen",
        "model": "Qwen3.8-Max",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key_env": ["QWEN_API_KEY", "DASHSCOPE_API_KEY"],
        "temperature": 0,
        "timeout_s": 60,
        "max_retries": 2,
        "json_mode": True,
    },
    "tools": {
        "enabled": [
            "normalize_metric_unit",
            "validate_spec_schema",
            "check_grading_gates",
            "lookup_device_bounds",
            "emit_structured_spec",
            "parse_netlist",
            "detect_topology_modules",
            "reduce_parameters",
            "emit_topology_report",
        ],
    },
    "policy": {
        "require_llm": False,
        "fallback_to_rules": True,
        "halt_on_schema_invalid": True,
    },
    "thresholds": {
        "dc_gain_db": 40.0,
        "phase_margin_deg": 50.0,
        "gain_margin_db": -10.0,
        "i_opa_ma": 3.0,
    },
    "paths": {
        "output_dir": "outputs",
        "log_dir": "outputs/logs",
        "prompt_dir": "prompts",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str | None = None) -> Dict[str, Any]:
    """加载配置；文件不存在时用默认配置（不报错，保证离线可跑）。"""
    candidates = []
    if path:
        candidates.append(path)
    if os.environ.get("AGENT_CONFIG"):
        candidates.append(os.environ["AGENT_CONFIG"])
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates.append(os.path.join(here, "config", "agent_config.json"))

    for c in candidates:
        if c and os.path.isfile(c):
            with open(c, encoding="utf-8") as f:
                user = json.load(f)
            cfg = _deep_merge(DEFAULT_CONFIG, user)
            cfg["_config_path"] = os.path.abspath(c)
            return cfg

    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg["_config_path"] = None
    return cfg


def resolve_api_key(cfg: Dict[str, Any]) -> str | None:
    """按配置里的环境变量名顺序找 API Key。"""
    names = cfg.get("llm", {}).get("api_key_env") or []
    if isinstance(names, str):
        names = [names]
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    # 也允许直接写在配置里（不推荐，仅便于本地调试）
    return cfg.get("llm", {}).get("api_key")


def public_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """导出配置时：抹掉 API Key、去掉内部字段（下划线开头的键）。

    产出物要是"干净的配置文件"，不能带 `_config_path` 这类运行时痕迹。
    """
    out = copy.deepcopy(cfg)
    if isinstance(out.get("llm"), dict):
        if out["llm"].get("api_key"):
            out["llm"]["api_key"] = "***REDACTED***"
    for k in [k for k in out if k.startswith("_")]:
        out.pop(k, None)
    return out
