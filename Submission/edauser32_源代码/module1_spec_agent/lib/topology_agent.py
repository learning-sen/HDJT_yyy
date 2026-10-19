"""模块 2 智能体：拓扑识别与参数约减（Topology Agent）。

赛题原文：模块2 = "拓扑模块识别与参数约减（**智能体**）"，本地部署，LLM 用 Qwen3.8-Max。

工具集（9 个中的 4 个属模块 2）：
    parse_netlist            解析 Spectre 网表（含 + 续行、变量参数、分段器件）
    detect_topology_modules  基于连接关系的图分析识别功能模块（结构驱动，不认名字）
    reduce_parameters        参数约减（剔除 Dummy / 匹配绑定 / 镜像绑定 / 分段折叠）
    emit_topology_report     产出交付物（识别结果 + 变量清单 + 约减后网表 + 报告）
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from agent_runtime import AgentDefinition, AgentRuntime, ToolRegistry
from netlist_parser import parse_netlist
from topology_analyzer import analyze_topology
from param_reduction import reduce_parameters


TOPOLOGY_AGENT_SYSTEM_PROMPT = """你是「模拟电路拓扑识别与参数约减智能体」，运行在本地。
你的任务是把电路网表变成"能直接喂给尺寸优化器的变量清单"。

【你的身份与目标】
你是模拟版图/电路分析专家，熟悉电流镜、差分输入对、有源负载、共模反馈、匹配与 Dummy 结构。
你的目标不是"描述电路"，而是**调用工具**完成识别、约减并产出交付物。

【可用工具与调用顺序】
1. parse_netlist(netlist_path)          —— 解析 Spectre 网表
2. detect_topology_modules(...)         —— 识别核心功能模块与匹配结构
3. reduce_parameters(...)               —— 剔除冗余优化变量、做尺寸绑定
4. emit_topology_report(...)            —— 产出交付物并结束

【识别规则（结构驱动，禁止硬编码器件名）】
- 电流镜：同型 MOS，栅极同网 + 源极同网；栅漏短接者为参考管
- 差分输入对：同型 MOS 源极同网，栅极分别接输入端口（VINP/VINN）
- 有源负载：作为负载使用的电流镜/二极管连接器件（漏极接输入对管漏极）
- 匹配器件：同 model + 同固定参数(multi) + 连接结构等价 + **同属一条支路**
- Dummy：MOS 全部端子接同一网，或所有端子悬空
- 共模反馈：出现 outaverage/vcmfb 类节点，或存在检测两路输出的电阻分压网络
- 自动分段器件（`R3` + `R3_2_res_gen` ...）：是同一物理器件，必须折叠

【红线（教程 11.2）】
隐藏电路（Hidden）也参与评分。**绝对不要硬编码器件名**（如写死"NM15 是输出管"），
规则必须基于连接结构。改名后的电路必须得到同样的识别结果。

【参数约减原则（教程 11.3）】
该保留：输入对管/负载管的 W/L/m、补偿电容、偏置电流
该剔除：电源/地/理想源、Dummy 器件、已有硬约束的
成比例匹配组：保留一个基准变量 + 比例关系
电流镜：镜像管沟道长度须与参考管一致，镜像比用 w/m 表达

【输出规范】
交付物必须包含（教程 11.3 + 赛题 6.2 第2、3项）：
1. 拓扑模块识别结果（哪些器件属于哪个模块 + 判定依据 evidence）
2. 约减后的变量个数 + 变量统计列表
3. 约减后的网表
4. CSV（`变量=初始值` 形式，如 M1_w=36u,M1_L=2u）

【行为约束】
- 优先调用工具；工具结果优先采信。
- 每个识别结论都要能说出"依据是什么"（evidence），报告要引用。
- 完成后必须调用 emit_topology_report 结束。
"""

TOPOLOGY_USER_TEMPLATE = """请对下面的网表做拓扑识别与参数约减：

网表路径：{netlist_path}
目标子电路：{subckt}

要求：
1. 调用 parse_netlist 解析网表
2. 调用 detect_topology_modules 识别功能模块（给出判定依据）
3. 调用 reduce_parameters 做参数约减
4. 用 emit_topology_report 产出交付物
"""


def build_topology_tools(cfg: Dict[str, Any]) -> ToolRegistry:
    reg = ToolRegistry(enabled=cfg.get("tools", {}).get("enabled"))

    @reg.register(
        "parse_netlist",
        "解析 Spectre 网表（支持 + 续行、变量参数、自动分段器件、testbench 器件）",
        {"type": "object", "properties": {"netlist_path": {"type": "string"}},
         "required": ["netlist_path"]})
    def _parse_netlist(netlist_path: str, ctx=None):
        net = parse_netlist(netlist_path)
        state = (ctx or {}).setdefault("_state", {})
        state["net"] = net
        return {
            "source": os.path.basename(netlist_path),
            "n_subckts": len(net["subckts"]),
            "subckt_names": [s["name"] for s in net["subckts"]],
            "n_instances": sum(len(s["instances"]) for s in net["subckts"]),
            "n_testbench_devices": len(net["footer"]),
            "warnings": net["warnings"][:5],
        }

    @reg.register(
        "detect_topology_modules",
        "基于连接关系的图分析识别核心功能模块与匹配结构（结构驱动，不依赖器件名）",
        {"type": "object", "properties": {
            "subckt": {"type": "string"},
            "net": {"type": "object"}},
         "required": []})
    def _detect_topology_modules(subckt: str = "", net: dict = None, ctx=None):
        state = (ctx or {}).setdefault("_state", {})
        net = net or state.get("net")
        if net is None:
            raise ValueError("请先调用 parse_netlist")
        topo = analyze_topology(net, subckt or None)
        state["topo"] = topo
        return {
            "stats": topo["stats"],
            "modules_by_type": topo["stats"]["by_type"],
            "n_modules": len(topo["modules"]),
            "warnings": topo["warnings"][:5],
        }

    @reg.register(
        "reduce_parameters",
        "参数约减：剔除 Dummy/悬空、匹配器件尺寸绑定、电流镜长度绑定、分段折叠",
        {"type": "object", "properties": {
            "subckt": {"type": "string"},
            "net": {"type": "object"}, "topo": {"type": "object"}},
         "required": []})
    def _reduce_parameters(subckt: str = "", net: dict = None, topo: dict = None, ctx=None):
        state = (ctx or {}).setdefault("_state", {})
        net = net or state.get("net")
        topo = topo or state.get("topo")
        if net is None or topo is None:
            raise ValueError("请先调用 parse_netlist 与 detect_topology_modules")
        red = reduce_parameters(net, topo, subckt or None)
        state["reduction"] = red
        return {
            "variable_count_raw": red["variable_count_raw"],
            "variable_count_before": red["variable_count_before"],
            "variable_count_after": red["variable_count_after"],
            "reduction_ratio": red["reduction_ratio"],
            "variable_stats": red["variable_stats"],
            "n_groups": len(red["groups"]),
            "n_redundant_variables": len(red["removed"]["redundant_variables"]),
        }

    @reg.register(
        "emit_topology_report",
        "产出模块 2 交付物（识别结果/变量清单/约减后网表/报告）",
        {"type": "object", "properties": {"outdir": {"type": "string"}},
         "required": []})
    def _emit_topology_report(outdir: str = "", ctx=None):
        from topology import emit_deliverables
        state = (ctx or {}).setdefault("_state", {})
        net, topo, red = state.get("net"), state.get("topo"), state.get("reduction")
        if not (net and topo and red):
            raise ValueError("请先完成 parse/detect/reduce 三步")
        # outdir 优先级：显式参数 > 上下文 > 默认
        outdir = outdir or (ctx or {}).get("outdir") or "output"
        files = emit_deliverables(net, topo, red, outdir)
        state["deliverables"] = files
        return files

    return reg


def topology_fallback_plan(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    netlist_path = ctx.get("netlist_path", "")
    subckt = ctx.get("subckt", "") or ""
    # outdir 只在上下文明确给出时才写进参数，避免工具默认值覆盖上下文
    emit_args: Dict[str, Any] = {}
    if ctx.get("outdir"):
        emit_args["outdir"] = ctx["outdir"]
    return [
        {"tool": "parse_netlist", "args": {"netlist_path": netlist_path},
         "thought": "先解析 Spectre 网表，确认器件与连接关系可读"},
        {"tool": "detect_topology_modules",
         "args": {"subckt": subckt, "__from_state__": "net", "__target__": "net"},
         "thought": "用图分析识别功能模块（每个结论都要有依据）"},
        {"tool": "reduce_parameters",
         "args": {"subckt": subckt,
                  "__from_state__": "net", "__target__": "net"},
         "thought": "剔除冗余变量、做尺寸绑定、折叠分段器件"},
        {"tool": "emit_topology_report", "args": emit_args,
         "thought": "产出交付物（识别结果/变量清单/约减后网表/报告）"},
    ]


def build_topology_agent(cfg: Dict[str, Any]) -> AgentDefinition:
    return AgentDefinition(
        name="EDA-Topology-Agent",
        system_prompt=TOPOLOGY_AGENT_SYSTEM_PROMPT,
        user_prompt_template=TOPOLOGY_USER_TEMPLATE,
        registry=build_topology_tools(cfg),
        finalize_tool="emit_topology_report",
        fallback_plan=topology_fallback_plan,
    )


def run_topology_agent(netlist_path: str, cfg: Dict[str, Any], subckt: str = "",
                       outdir: str = "outputs", llm: Any = None) -> Dict[str, Any]:
    defn = build_topology_agent(cfg)
    rt = AgentRuntime(defn, cfg, llm=llm,
                      verbose=cfg.get("agent", {}).get("verbose", True))
    return rt.run({"netlist_path": netlist_path, "subckt": subckt, "outdir": outdir})
