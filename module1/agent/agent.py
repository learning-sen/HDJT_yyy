#!/usr/bin/env python
"""智能体入口（可独立运行）。

这是赛题要求的智能体源码入口 `agent/agent.py`。实现拆在 `lib/` 下：
    lib/agent_runtime.py    智能体运行时（工具注册表 + ReAct 决策循环 + CoT 日志）
    lib/spec_agent.py       模块 1 智能体：自然语言 -> Spec JSON
    lib/topology_agent.py   模块 2 智能体：网表 -> 拓扑识别 + 参数约减
    lib/llm_client.py       Qwen3.8-Max 客户端（APIKey 调用）
    lib/agent_config.py     配置文件加载
    lib/*.py                确定性工具实现（解析/识别/约减等）

用法：
    export QWEN_API_KEY=sk-xxx          # Linux/macOS
    set QWEN_API_KEY=sk-xxx             # Windows

    python agent.py spec      --input requirement.txt --out spec_case1.json
    python agent.py topology  --netlist OPA_loopgain.netlist --outdir output
    python agent.py self-test
    python agent.py dump-config --out agent_config_used.json
"""
import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "lib"))

from agent_config import load_config, public_config          # noqa: E402
from spec_agent import run_spec_agent, SPEC_AGENT_SYSTEM_PROMPT      # noqa: E402
from topology_agent import run_topology_agent, TOPOLOGY_AGENT_SYSTEM_PROMPT  # noqa: E402
import spec_schema as ss                                     # noqa: E402


def _write(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print("已写出: %s" % path)


def _save_trace(res, outdir, tag):
    """保存推理链：JSONL（赛题格式 trace_*.jsonl）+ MD（报告用）。"""
    os.makedirs(outdir, exist_ok=True)
    meta = res["reasoning"].get("meta", {})
    jl = os.path.join(outdir, "trace_%s.jsonl" % tag)
    with open(jl, "w", encoding="utf-8") as f:
        for s in res["reasoning"]["steps"]:
            import time
            rec = {"trace_id": "%s-%s" % (tag, time.strftime("%Y%m%d-%H%M%S")),
                   "agent": meta.get("agent"), "model": meta.get("model"),
                   "used_llm": meta.get("used_llm")}
            rec.update(s)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print("已写出: %s" % jl)


def cmd_spec(args, cfg):
    text = args.text
    if args.input:
        text = open(args.input, encoding="utf-8").read()
    res = run_spec_agent(text, cfg)
    if res["answer"] is None:
        print("智能体未产出结果", file=sys.stderr)
        return 1
    payload = ss.to_submission(res["answer"]) if args.variant == "submit" else res["answer"]
    _write(args.out or "spec_case1.json", json.dumps(payload, ensure_ascii=False, indent=2))
    _save_trace(res, args.trace_dir or "output", "spec")
    return 0


def cmd_topology(args, cfg):
    res = run_topology_agent(args.netlist, cfg, subckt=args.subckt or "",
                             outdir=args.outdir)
    _save_trace(res, args.trace_dir or "output", "topology")
    return 0


def cmd_dump_config(args, cfg):
    _write(args.out or "agent_config_used.json",
           json.dumps(public_config(cfg), ensure_ascii=False, indent=2))
    return 0


def cmd_self_test(args, cfg):
    r1 = run_spec_agent("设计全差分运放，增益不得低于40dB，面积尽可能小", cfg)
    print("模块1 智能体：约束 %d 条 / 目标 %d 条 / 推理链 %d 步"
          % (len(r1["answer"]["constraints"]), len(r1["answer"]["objectives"]),
             r1["reasoning"]["total_steps"]))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="EDA 模拟电路智能设计智能体")
    ap.add_argument("--config", default=os.path.join(_HERE, "config.json"))
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("spec", help="模块1：自然语言 -> Spec JSON")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--input")
    g.add_argument("--text")
    s.add_argument("--out", default="spec_case1.json")
    s.add_argument("--variant", choices=["submit", "full"], default="submit")
    s.add_argument("--trace-dir", default="output")
    s.set_defaults(func=cmd_spec)

    t = sub.add_parser("topology", help="模块2：网表 -> 识别 + 约减")
    t.add_argument("--netlist", required=True)
    t.add_argument("--outdir", default="output")
    t.add_argument("--subckt")
    t.add_argument("--trace-dir", default="output")
    t.set_defaults(func=cmd_topology)

    d = sub.add_parser("dump-config")
    d.add_argument("--out", default="agent_config_used.json")
    d.set_defaults(func=cmd_dump_config)

    st = sub.add_parser("self-test")
    st.set_defaults(func=cmd_self_test)

    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    return args.func(args, cfg)


if __name__ == "__main__":
    raise SystemExit(main())
