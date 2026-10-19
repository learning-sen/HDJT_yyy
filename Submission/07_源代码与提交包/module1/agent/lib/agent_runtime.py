"""智能体运行时：工具注册表 + ReAct 决策循环 + 推理链（Chain-of-Thought）日志。

架构（对应赛题"智能体"要求）：

    ┌─────────────────────────── AgentRuntime ───────────────────────────┐
    │  System Prompt（角色 + 工具说明 + 输出约束）                        │
    │        ↓                                                            │
    │  LLM 决策（Qwen3.8-Max，function calling）                          │
    │        ↓ 选择工具 + 参数                                            │
    │  工具执行（确定性 Python 函数）                                      │
    │        ↓ 观察结果                                                   │
    │  回填对话，循环（直到调用 finalize 工具或达到 max_steps）             │
    │        ↓                                                            │
    │  CoT 日志（每步 thought / action / observation / decision）          │
    └────────────────────────────────────────────────────────────────────┘

无 API Key 时：不改变流程，只把"LLM 决策"替换为**确定性工具计划**
（`fallback_plan()`），并在推理链里如实记录这一步是 fallback。
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# 工具定义
# ---------------------------------------------------------------------------

@dataclass
class Tool:
    name: str
    description: str
    parameters: Dict[str, Any]                 # JSON Schema
    func: Callable[..., Any]

    def to_openai_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """注册与调用工具；调用异常不会中断智能体，而是作为 observation 返回。"""

    def __init__(self, enabled: Optional[List[str]] = None):
        self._tools: Dict[str, Tool] = {}
        self.enabled = set(enabled) if enabled else None
        self.call_log: List[Dict[str, Any]] = []

    def register(self, name: str, description: str, parameters: Dict[str, Any]):
        def deco(fn):
            self._tools[name] = Tool(name, description, parameters, fn)
            return fn
        return deco

    def register_tool(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    @property
    def names(self) -> List[str]:
        names = list(self._tools)
        if self.enabled is not None:
            names = [n for n in names if n in self.enabled]
        return sorted(names)

    def schemas(self) -> List[Dict[str, Any]]:
        return [self._tools[n].to_openai_schema() for n in self.names]

    def has(self, name: str) -> bool:
        return name in self._tools and (self.enabled is None or name in self.enabled)

    def call(self, name: str, args: Dict[str, Any]) -> Any:
        if not self.has(name):
            raise KeyError("工具未注册或未启用: %s（可用: %s）" % (name, self.names))
        t0 = time.time()
        try:
            result = self._tools[name].func(**args)
            ok, err = True, None
        except Exception as e:
            result, ok, err = None, False, "%s: %s" % (type(e).__name__, e)
        self.call_log.append({"tool": name, "args": args, "ok": ok, "error": err,
                              "elapsed_ms": round((time.time() - t0) * 1000, 1)})
        if not ok:
            raise RuntimeError(err)
        return result


# ---------------------------------------------------------------------------
# 推理链（CoT）日志
# ---------------------------------------------------------------------------

class ReasoningLog:
    """逐步记录智能体的决策依据。赛题/教程都要求报告展示"每一步决策依据"。"""

    def __init__(self):
        self.steps: List[Dict[str, Any]] = []
        self._t0 = time.time()

    def add(self, thought: str, action: str, action_input: Any = None,
            observation: Any = None, decision: str = "", source: str = "") -> Dict[str, Any]:
        step = {
            "step": len(self.steps) + 1,
            "thought": thought,
            "action": action,
            "action_input": action_input,
            "observation": _shorten(observation),
            "decision": decision or ("继续" if action != "finalize" else "完成"),
            "source": source or "agent",
            "elapsed_s": round(time.time() - self._t0, 3),
        }
        self.steps.append(step)
        return step

    def finalize(self, answer_summary: str) -> None:
        self.add(thought="所有必要工具已执行完毕，产出最终结果",
                 action="finalize", observation=answer_summary,
                 decision="完成", source="agent")

    def to_dict(self, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {
            "meta": meta or {},
            "total_steps": len(self.steps),
            "steps": self.steps,
        }

    def save(self, path: str, meta: Optional[Dict[str, Any]] = None) -> str:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(meta), f, ensure_ascii=False, indent=2)
        return path

    # -- JSONL：赛题要求的推理链日志格式（trace_*.jsonl）----------------
    def to_jsonl(self, meta: Optional[Dict[str, Any]] = None,
                 trace_id: Optional[str] = None) -> str:
        """把推理链导成 JSONL（每行一个 JSON，逐步可流式解析）。

        每行结构（在 step 字段基础上补 trace 元信息，便于多次运行合并分析）：
            {"trace_id","agent","model","used_llm","step","thought","action",
             "action_input","observation","decision","source","elapsed_s","ts"}
        """
        meta = meta or {}
        tid = trace_id or "%s-%s" % (meta.get("agent", "agent"),
                                     time.strftime("%Y%m%d-%H%M%S"))
        t0 = time.time()
        lines = []
        for s in self.steps:
            rec = {
                "trace_id": tid,
                "agent": meta.get("agent"),
                "model": meta.get("model"),
                "used_llm": meta.get("used_llm"),
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "wall_elapsed_s": round(t0 - self._t0, 3),
            }
            rec.update(s)
            lines.append(json.dumps(rec, ensure_ascii=False))
        return "\n".join(lines) + ("\n" if lines else "")

    def save_jsonl(self, path: str, meta: Optional[Dict[str, Any]] = None,
                   trace_id: Optional[str] = None) -> str:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_jsonl(meta, trace_id))
        return path

    def render_text(self) -> str:
        """人读版推理链（技术报告可直接粘贴）。"""
        out = []
        for s in self.steps:
            out.append("[步骤 %d | %s] %s" % (s["step"], s["source"], s["thought"]))
            out.append("   → 动作: %s" % s["action"])
            if s["action_input"] not in (None, {}, ""):
                out.append("   → 输入: %s" % _shorten(s["action_input"], 300))
            if s["observation"] not in (None, "", {}):
                out.append("   → 观察: %s" % _shorten(s["observation"], 400))
            out.append("   → 决策: %s" % s["decision"])
            out.append("")
        return "\n".join(out)


def _shorten(obj: Any, limit: int = 600) -> Any:
    """把 observation 截断，避免日志爆炸（保留可读性）。"""
    if obj is None:
        return None
    if isinstance(obj, (int, float, bool)):
        return obj
    if isinstance(obj, str):
        return obj if len(obj) <= limit else obj[:limit] + "…(%d 字)" % len(obj)
    try:
        s = json.dumps(obj, ensure_ascii=False)
    except Exception:
        s = str(obj)
    if len(s) <= limit:
        return obj
    return s[:limit] + "…(truncated)"


# ---------------------------------------------------------------------------
# 智能体定义与运行时
# ---------------------------------------------------------------------------

@dataclass
class AgentDefinition:
    name: str
    system_prompt: str
    user_prompt_template: str
    registry: ToolRegistry
    finalize_tool: str = "finalize"
    fallback_plan: Callable[[Dict[str, Any]], List[Dict[str, Any]]] = field(
        default_factory=lambda: (lambda ctx: []))


class AgentRuntime:
    """ReAct 风格智能体主循环。"""

    def __init__(self, definition: AgentDefinition, cfg: Dict[str, Any],
                 llm: Any = None, verbose: bool = True):
        self.defn = definition
        self.cfg = cfg
        self.log = ReasoningLog()
        self.verbose = verbose
        self.final_answer: Optional[dict] = None
        self.used_llm = False
        if llm is None:
            from llm_client import LLMClient
            llm = LLMClient(cfg)
        self.llm = llm
        self.max_steps = int(cfg.get("agent", {}).get("max_steps", 12))

    # -- 主循环 ---------------------------------------------------------
    def run(self, ctx: Dict[str, Any]) -> dict:
        """ctx 是任务上下文（如 {"requirement_text": ...}），工具之间通过它共享状态。"""
        ctx.setdefault("_state", {})
        self.log.add(
            thought="接收任务，准备解析输入并规划执行步骤",
            action="receive_task",
            action_input={k: v for k, v in ctx.items() if not k.startswith("_")},
            observation="任务已接收",
            decision="进入智能体决策循环",
            source="agent",
        )

        if self.llm.available:
            self.used_llm = True
            self._run_llm_loop(ctx)
        else:
            self.log.add(
                thought="LLM 不可用（%s），按下线策略回退到确定性工具链"
                        % getattr(self.llm, "unavailable_reason", lambda: "unknown")(),
                action="llm_unavailable",
                observation="将以确定性工具计划完成同一套工具调用",
                decision="执行 fallback 计划（工具与产物不变）",
                source="fallback",
            )
            self._run_fallback(ctx)

        if self.final_answer is None:
            self.log.add(thought="循环结束但仍无最终产物",
                         action="finalize", observation="未产出",
                         decision="异常结束", source="agent")
        return {
            "answer": self.final_answer,
            "reasoning": self.log.to_dict({
                "agent": self.defn.name,
                "model": getattr(self.llm, "model", "scripted"),
                "used_llm": self.used_llm,
                "max_steps": self.max_steps,
            }),
        }

    # -- LLM 驱动 -------------------------------------------------------
    def _run_llm_loop(self, ctx: Dict[str, Any]) -> None:
        messages = [
            {"role": "system", "content": self.defn.system_prompt},
            {"role": "user", "content": self.defn.user_prompt_template.format(**ctx)},
        ]
        tool_schemas = self.defn.registry.schemas()

        for _ in range(self.max_steps):
            resp = self.llm.chat(messages, tools=tool_schemas)
            if not resp.ok:
                self.log.add(thought="LLM 调用失败", action="llm_error",
                             observation=resp.error,
                             decision="回退到确定性工具链", source="fallback")
                self._run_fallback(ctx, skip_done=True)
                return

            # 情况一：模型直接给出工具调用
            if resp.tool_calls:
                messages.append({"role": "assistant", "content": resp.content or "",
                                 "tool_calls": resp.tool_calls})
                for tc in resp.tool_calls:
                    name = tc.get("function", {}).get("name", "")
                    raw_args = tc.get("function", {}).get("arguments") or "{}"
                    try:
                        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    except Exception:
                        args = {}
                    if self._dispatch(name, args, ctx, thought=resp.content or "(模型选择调用工具)"):
                        return
                continue

            # 情况二：模型只输出 JSON（不调工具）-> 当作候选 Spec
            text = resp.content or ""
            maybe = _extract_json(text)
            if maybe is not None:
                self.log.add(thought="模型直接输出结构化结果，交由校验工具核对",
                             action="llm_structured_output",
                             action_input=_shorten(maybe, 400),
                             observation="已接收，进入校验",
                             decision="调用校验与门槛检查工具", source="llm")
                self.defn.registry.call("check_grading_gates",
                                        {"spec": maybe, "ctx": ctx})
                self.final_answer = maybe
                self.log.finalize("LLM 直接输出通过校验，作为最终 Spec")
                return

            self.log.add(thought="模型既未调用工具也未给出 JSON，追问下一步",
                         action="llm_no_action", observation=_shorten(text, 200),
                         decision="继续循环", source="llm")
            messages.append({"role": "assistant", "content": text})
            messages.append({"role": "user",
                             "content": "请调用合适的工具继续，或输出最终 JSON。"})

        self.log.add(thought="达到最大步数仍未完成", action="max_steps_reached",
                     observation="max_steps=%d" % self.max_steps,
                     decision="用确定性工具链补齐", source="fallback")
        self._run_fallback(ctx, skip_done=True)

    # -- 确定性回退 -----------------------------------------------------
    def _run_fallback(self, ctx: Dict[str, Any], skip_done: bool = False) -> None:
        plan = self.defn.fallback_plan(ctx)
        self.log.add(thought="确定性工具计划（不依赖 LLM）",
                     action="fallback_plan",
                     action_input=[p["tool"] for p in plan],
                     observation="共 %d 步工具调用" % len(plan),
                     decision="逐步执行", source="fallback")
        for item in plan:
            if self._dispatch(item["tool"], item.get("args", {}), ctx,
                              thought=item.get("thought", "(确定性策略)"),
                              source="fallback"):
                return

    # -- 工具派发 -------------------------------------------------------
    def _dispatch(self, name: str, args: Dict[str, Any], ctx: Dict[str, Any],
                  thought: str = "", source: str = "llm") -> bool:
        """执行一个工具调用。返回 True 表示已产出最终结果、可以结束。"""
        args = self._resolve_args(args or {}, ctx)
        args.setdefault("ctx", ctx)
        try:
            obs = self.defn.registry.call(name, args)
        except Exception as e:
            self.log.add(thought=thought, action=name, action_input=args,
                         observation="工具执行失败: %s" % e,
                         decision="跳过该步，继续", source=source)
            return False

        if name == self.defn.finalize_tool:
            self.final_answer = obs
            self.log.add(thought=thought, action=name, action_input=_shorten(args),
                         observation=_shorten(obs), decision="完成", source=source)
            return True

        self.log.add(thought=thought, action=name, action_input=_shorten(args),
                     observation=obs, decision="继续", source=source)
        return False

    @staticmethod
    def _resolve_args(args: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        """支持从上下文状态串联工具。

        两种写法：
          {"__from_state__": "spec", "__target__": "spec"}
              -> 调用时传 spec=ctx["_state"]["spec"]
          {"netlist_path": "@netlist_path"}
              -> 字符串开头为 '@' 时，从 ctx（非 _state）取同名键

        这样确定性计划可以把"前一个工具的输出"喂给"后一个工具的指定参数"，
        而不必把大对象写进日志。
        """
        state = ctx.get("_state", {})
        out: Dict[str, Any] = {}
        for k, v in args.items():
            if k == "__from_state__":
                target = args.get("__target__") or v
                if v in state:
                    out[target] = state[v]
                continue
            if k == "__target__":
                continue
            if isinstance(v, str) and v.startswith("@") and v[1:] in ctx:
                out[k] = ctx[v[1:]]
                continue
            out[k] = v
        return out


def _extract_json(text: str) -> Optional[dict]:
    """从文本里抽出第一个完整 JSON 对象。"""
    if not text:
        return None
    text = re.sub(r"^```[a-zA-Z]*\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except Exception:
                    return None
    return None
