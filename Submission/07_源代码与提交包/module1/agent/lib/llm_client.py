"""LLM 客户端：对接赛题指定模型 Qwen3.8-Max（APIKey 调用）。

设计要点：
  1. 只依赖标准库 urllib（避免离线环境缺 requests）
  2. 支持 function calling（tool calls）—— 智能体靠它决定"下一步调哪个工具"
  3. 无 API Key / 调用失败时返回 available=False，由 agent 回退确定性工具链，
     **但这一步本身也会记进推理链**（保证 CoT 日志完整）
  4. 绝不把 API Key 打进日志或交付物
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


class LLMClient:
    """OpenAI 兼容 /chat/completions 客户端（Qwen 走 dashscope compatible-mode）。"""

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        llm = cfg.get("llm", {})
        self.model = llm.get("model", "Qwen3.8-Max")
        self.base_url = (llm.get("base_url") or "").rstrip("/")
        self.temperature = llm.get("temperature", 0)
        self.timeout = llm.get("timeout_s", 60)
        self.max_retries = llm.get("max_retries", 2)
        self.json_mode = llm.get("json_mode", True)
        self.api_key = self._resolve_key()
        self.last_error: Optional[str] = None

    # -- 可用性 ---------------------------------------------------------
    def _resolve_key(self) -> Optional[str]:
        from agent_config import resolve_api_key
        return resolve_api_key(self.cfg)

    @property
    def available(self) -> bool:
        return bool(self.api_key) and bool(self.base_url)

    def unavailable_reason(self) -> str:
        if not self.api_key:
            names = self.cfg.get("llm", {}).get("api_key_env", [])
            return "未检测到 API Key（应设置环境变量 %s）" % (
                " 或 ".join(names) if names else "QWEN_API_KEY")
        if not self.base_url:
            return "未配置 base_url"
        return ""

    # -- 调用 -----------------------------------------------------------
    def chat(self, messages: List[Dict[str, Any]],
             tools: Optional[List[Dict[str, Any]]] = None,
             response_format: Optional[Dict[str, str]] = None) -> LLMResponse:
        """一次对话调用。任何异常都封装进 LLMResponse.error，不向上抛。"""
        if not self.available:
            return LLMResponse(error=self.unavailable_reason())

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if response_format:
            payload["response_format"] = response_format
        elif self.json_mode and not tools:
            payload["response_format"] = {"type": "json_object"}

        last_err = None
        for attempt in range(self.max_retries + 1):
            try:
                req = urllib.request.Request(
                    "%s/chat/completions" % self.base_url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": "Bearer %s" % self.api_key,
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                msg = (data.get("choices") or [{}])[0].get("message", {})
                return LLMResponse(
                    content=msg.get("content") or "",
                    tool_calls=msg.get("tool_calls") or [],
                    raw=data,
                )
            except urllib.error.HTTPError as e:
                body = ""
                try:
                    body = e.read().decode("utf-8")[:300]
                except Exception:
                    pass
                last_err = "HTTP %s: %s" % (e.code, body)
            except Exception as e:                       # 网络/超时/解析
                last_err = "%s: %s" % (type(e).__name__, e)
            if attempt < self.max_retries:
                time.sleep(1.0 * (attempt + 1))
        self.last_error = last_err
        return LLMResponse(error=last_err)

    def chat_json(self, system_prompt: str, user_prompt: str) -> Tuple[Optional[dict], LLMResponse]:
        """要求模型只输出 JSON，返回 (解析后的 dict 或 None, 原始响应)。"""
        resp = self.chat(
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": user_prompt}],
            response_format={"type": "json_object"},
        )
        if not resp.ok:
            return None, resp
        try:
            from spec_parser import _strip_code_fence
            return json.loads(_strip_code_fence(resp.content)), resp
        except Exception as e:
            resp.error = "返回内容不是合法 JSON: %s" % e
            return None, resp


# ---------------------------------------------------------------------------
# 测试/离线用：可编程的假客户端
# ---------------------------------------------------------------------------

class ScriptedLLM:
    """按脚本依次返回预设响应，用于**离线回归测试**智能体主循环。

    脚本元素可以是：
      - {"content": "...", "tool_calls": [...]}   -> 当作一次 LLM 响应
      - {"content": "..."}                        -> 纯文本响应
    """

    def __init__(self, script: List[Dict[str, Any]]):
        self.script = list(script)
        self.calls: List[List[Dict[str, Any]]] = []
        self.model = "ScriptedLLM"

    @property
    def available(self) -> bool:
        return True

    def unavailable_reason(self) -> str:
        return ""

    def chat(self, messages, tools=None, response_format=None) -> LLMResponse:
        self.calls.append(messages)
        if not self.script:
            return LLMResponse(error="脚本已用尽")
        item = self.script.pop(0)
        return LLMResponse(content=item.get("content", ""),
                           tool_calls=item.get("tool_calls", []) or [])

    def chat_json(self, system_prompt, user_prompt):
        resp = self.chat([{"role": "system", "content": system_prompt},
                          {"role": "user", "content": user_prompt}])
        if not resp.ok:
            return None, resp
        try:
            return json.loads(resp.content), resp
        except Exception as e:
            resp.error = "非合法 JSON: %s" % e
            return None, resp
