"""模块 2 CLI 入口：网表 -> 拓扑识别 -> 参数约减 -> 交付物。

用法（工作目录 contest/）：
    python -m src.topology --netlist fixtures/real/OPA_loopgain.netlist --outdir outputs

产出（对齐赛题 6.2 与教程 11.1 的交付物清单）：
    topology_analysis.json   拓扑模块识别结果（含依据与决策日志）
    variables_before.csv     约减前变量清单
    variables_after.csv      约减后变量清单（器件/参数/类型/边界）
    netlist_reduced.cdl      约减后的网表
    reduction_summary.md     约减报告（给技术报告直接引用）
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from netlist_parser import parse_netlist
    from topology_analyzer import analyze_topology
    from param_reduction import reduce_parameters
else:
    from netlist_parser import parse_netlist
    from topology_analyzer import analyze_topology
    from param_reduction import reduce_parameters


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print("已写出: %s" % path)


def _csv(path: str, rows: list, header: list) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print("已写出: %s（%d 行）" % (path, len(rows)))


def format_param_value(value, param: str) -> str:
    """按 PDK 习惯把数值格式化成带 SI 后缀的字符串（38u / 1.2p / 4）。

    网表里的尺寸单位是米，PDK 参数文件习惯用 um/p 之类的后缀。
    """
    if value is None:
        return ""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if param in ("m", "seg"):          # 整数参数
        return str(int(round(v)))
    for suffix, scale in (("u", 1e-6), ("n", 1e-9), ("p", 1e-12), ("f", 1e-15)):
        if abs(v) >= scale:
            q = v / scale
            s = ("%.6f" % q).rstrip("0").rstrip(".")
            return s + suffix
    return "%.6g" % v


def build_param_value_rows(red: dict) -> list:
    """构造赛题要求的『变量=初始值』清单（教程 12.4 的 `M1_w=36u,M1_L=2u` 形式）。"""
    rows = []
    for v in red["optimization_variables"]:
        rows.append([
            v["name"],
            format_param_value(v.get("init"), v["param"]),
            v["instance"],
            v["param"],
            v["kind"],
            "" if v["bounds"] is None else format_param_value(v["bounds"][0], v["param"]),
            "" if v["bounds"] is None else format_param_value(v["bounds"][1], v["param"]),
            v["unit"],
        ])
    return rows


def build_pdk_param_file(red: dict) -> str:
    """生成 PDK 参数文件行（`变量=值`），**值缺失时留空并注明需从 extractedcdfVal_0.txt 取**。"""
    lines = []
    for v in red["optimization_variables"]:
        val = format_param_value(v.get("init"), v["param"])
        if not val:
            lines.append("%s=" % v["name"])
        else:
            lines.append("%s=%s" % (v["name"], val))
    return "\n".join(lines) + "\n"


def render_summary(net: dict, topo: dict, red: dict) -> str:
    s = topo["stats"]
    lines = []
    lines.append("# 模块 2 报告：拓扑模块识别与参数约减\n")
    lines.append("> 由 `python -m src.topology` 自动生成，可直接引用进技术报告。\n")

    lines.append("## 1. 输入")
    lines.append("")
    lines.append("| 项 | 值 |")
    lines.append("|---|---|")
    lines.append("| 网表 | `%s` |" % os.path.basename(net.get("source", "?")))
    lines.append("| 子电路 | `%s` |" % s["subckt"])
    lines.append("| 对外端口 | %s |" % ", ".join(s["ports"]))
    lines.append("| 器件总数 | %d（MOS %d） |" % (s["n_instances"], s["n_mos"]))
    lines.append("| 自动分段折叠 | %d 条链 → 逻辑器件 %d 个 |"
                 % (s["n_segmented_collapsed"], s["n_instances_collapsed"]))

    lines.append("\n## 2. 识别到的拓扑模块\n")
    lines.append("| ID | 类型 | 器件 | 置信度 |")
    lines.append("|---|---|---|---|")
    for m in topo["modules"]:
        lines.append("| %s | %s | %s | %d |"
                     % (m["id"], m["type"], ", ".join(m["devices"][:8])
                        + ("…" if len(m["devices"]) > 8 else ""), m["confidence"]))

    lines.append("\n### 2.1 判定依据（为何识别为该模块）\n")
    for m in topo["modules"]:
        lines.append("- **%s（%s）**：%s" % (m["id"], m["type"], m["evidence"]))

    lines.append("\n## 3. 参数约减\n")
    lines.append("| 阶段 | 变量数 |")
    lines.append("|---|---|")
    lines.append("| 原始网表（器件级，未折叠分段） | %d |" % red["variable_count_raw"])
    lines.append("| 折叠自动分段后 | %d |" % red["variable_count_before"])
    lines.append("| **约减后** | **%d** |" % red["variable_count_after"])
    lines.append("| 约减比例 | **%.1f%%** |" % (red["reduction_ratio"] * 100))

    lines.append("\n### 3.1 变量统计\n")
    st = red["variable_stats"]
    lines.append("- 按参数：" + ", ".join("%s=%d" % (k, v) for k, v in st["by_param"].items()))
    lines.append("- 按器件类型：" + ", ".join("%s=%d" % (k, v)
                                              for k, v in st["by_instance_kind"].items()))
    lines.append("- 整数变量 %d 个（m / seg，优化时需取整），连续变量 %d 个"
                 % (st["n_integer"], st["n_continuous"]))
    lines.append("- 尺寸绑定组 %d 组" % st["n_groups"])

    lines.append("\n### 3.2 约减决策链（为何删除/绑定某变量）\n")
    for d in red["decision_log"]:
        lines.append("- **%s** → %s" % (d["step"], d["effect"]))
        lines.append("  - 理由：%s" % d["reason"])

    if red["removed"]["redundant_variables"]:
        lines.append("\n### 3.3 冗余变量映射（删除的变量指向哪个基准变量）\n")
        lines.append("| 被删除变量 | 映射到 | 理由 |")
        lines.append("|---|---|---|")
        for r in red["removed"]["redundant_variables"]:
            lines.append("| `%s` | `%s` | %s |" % (r["name"], r["mapped_to"], r["reason"]))

    if topo.get("warnings"):
        lines.append("\n## 4. 需要人工确认的点\n")
        for w in topo["warnings"]:
            lines.append("- ⚠️ %s" % w)

    return "\n".join(lines) + "\n"


def emit_deliverables(net: dict, topo: dict, red: dict, out: str) -> dict:
    """产出模块 2 全部交付物，返回 {"文件角色": "路径"} 映射。

    被 CLI 与智能体工具（emit_topology_report）共用，保证两条路径产物一致。
    """
    files = {}

    # 1) 拓扑识别结果
    p = os.path.join(out, "topology_analysis.json")
    _write(p, json.dumps({"stats": topo["stats"], "modules": topo["modules"],
                          "decision_log": topo["decision_log"],
                          "device_roles": topo["device_roles"],
                          "warnings": topo["warnings"]},
                         ensure_ascii=False, indent=2))
    files["topology_analysis"] = p

    # 2) 约减前后变量清单（表格形式）
    before_rows = []
    for dev, varmap in sorted(topo["var_map"].items()):
        for vname in sorted(varmap):
            before_rows.append([dev, vname])
    p = os.path.join(out, "variables_before.csv")
    _csv(p, before_rows, ["instance", "variable"])
    files["variables_before"] = p

    after_rows = []
    for v in red["optimization_variables"]:
        after_rows.append([v["instance"], v.get("instance_kind", ""), v["param"], v["name"],
                           v["kind"],
                           "" if v["bounds"] is None else "%g" % v["bounds"][0],
                           "" if v["bounds"] is None else "%g" % v["bounds"][1],
                           v["unit"], v["note"]])
    p = os.path.join(out, "variables_after.csv")
    _csv(p, after_rows,
         ["instance", "device_kind", "param", "variable", "var_type",
          "lower", "upper", "unit", "note"])
    files["variables_after"] = p

    # 3) 约减后网表
    p = os.path.join(out, "netlist_reduced.cdl")
    _write(p, red["reduced_netlist"])
    files["netlist_reduced"] = p

    # 3.1) 赛题 6.2 第3项：**变量=初始值** 形式 CSV（教程 12.4：M1_w=36u,M1_L=2u）
    pv_rows = build_param_value_rows(red)
    p = os.path.join(out, "variables_after_param_value.csv")
    _csv(p, pv_rows,
         ["variable", "value", "instance", "param", "var_type", "lower", "upper", "unit"])
    files["variables_param_value_csv"] = p

    # 3.2) PDK 参数文件（变量=值，一行一个）
    p = os.path.join(out, "params_variables.txt")
    _write(p, build_pdk_param_file(red))
    files["params_variables"] = p

    # 4) 约减报告（技术报告可直接引用）
    p = os.path.join(out, "reduction_summary.md")
    _write(p, render_summary(net, topo, red))
    files["reduction_summary"] = p

    return files


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="模块 2：拓扑识别与参数约减")
    ap.add_argument("--netlist", required=True, help="Spectre 网表路径")
    ap.add_argument("--outdir", default="outputs", help="输出目录")
    ap.add_argument("--subckt", help="只分析指定子电路（默认第一个）")
    args = ap.parse_args(argv)

    net = parse_netlist(args.netlist)
    if not net["subckts"]:
        print("❌ 网表里没有 subckt", file=sys.stderr)
        return 1
    topo = analyze_topology(net, args.subckt)
    red = reduce_parameters(net, topo, args.subckt)

    emit_deliverables(net, topo, red, args.outdir)

    print("\n=== 摘要 ===")
    print("识别模块 : %s" % json.dumps(topo["stats"]["by_type"], ensure_ascii=False))
    print("变量约减 : %d -> %d（%.1f%%）"
          % (red["variable_count_before"], red["variable_count_after"],
             red["reduction_ratio"] * 100))
    n_missing = sum(1 for v in red["optimization_variables"]
                    if not format_param_value(v.get("init"), v["param"]))
    if n_missing:
        print("⚠️ 有 %d 个变量的初始值缺失（网表里只有变量名，实际初值需从服务器上的 "
              "extractedcdfVal_0.txt / case1_params_0.txt 取）" % n_missing)
    for w in topo.get("warnings", []):
        print("⚠️ %s" % w)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
