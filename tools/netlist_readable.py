#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 Spectre 网表变成人可读的表格（Markdown + CSV）。

赛题网表的真实痛点：一个 MOS 器件后面跟着 10 行 `+ad=...+as=...` 的版图寄生参数
续行，看着像乱码，而真正有信息的只有每个器件那一行的前几个字段。
本脚本按"一行一个器件"重新排版，并把网表解析结果、拓扑识别结果、优化变量
一起挂到表里，方便人读，也方便写进技术报告。

用法（工作区根目录）：
    python tools/netlist_readable.py
    python tools/netlist_readable.py --netlist "extracted/赛题数据本身/netlist/OPA_loopgain.netlist" \
                                     --outdir module1/agent/output

产出：
    netlist_readable.md   人看的可读视图（概览 / 器件总表 / 功能模块 / 网表连接 / 折叠说明）
    netlist_devices.csv   机器读的器件清单（Excel 可直接打开）
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LIB = os.path.join(ROOT, "module1", "agent", "lib")
if LIB not in sys.path:
    sys.path.insert(0, LIB)

from netlist_parser import (                                    # noqa: E402
    parse_netlist, find_subckt, mos_terminal, PARAM_ORDER,
)
from topology_analyzer import (                                 # noqa: E402
    analyze_topology, collapse_segmented, _polarity, _multi_of,
    _is_diode_connected,
)

DEFAULT_NETLIST = os.path.join(ROOT, "extracted", "赛题数据本身",
                               "netlist", "OPA_loopgain.netlist")

MOS_TERMS = [("d", "漏"), ("g", "栅"), ("s", "源"), ("b", "衬底")]


def natkey(s: str):
    """自然排序：NM2 < NM10（而不是字典序 NM10 < NM2）。"""
    return [(0, int(t)) if t.isdigit() else (1, t.lower())
            for t in re.split(r"(\d+)", str(s)) if t]


def is_free(v: dict) -> bool:
    return v.get("param") in {"l", "w", "m", "segL", "segW", "seg"} \
        and v.get("interface", "variable") != "value"


def dev_cells(inst: dict) -> dict:
    """把一个器件整理成一行可读字段。"""
    kind = inst["kind"]
    nodes = inst["nodes"]
    p = inst.get("params", {})

    cells = {
        "name": inst["name"],
        "kind": kind,
        "polarity": _polarity(inst) if kind == "mos" else "-",
        "model": inst.get("model") or "",
        "multi": "" if _multi_of(inst) is None else str(_multi_of(inst)),
        "segmented": "是" if inst.get("segmented") else "",
        "elements": inst.get("element_count", ""),
        "diode": "是" if (kind == "mos" and _is_diode_connected(inst)) else "",
    }
    if kind == "mos":
        for key, _label in MOS_TERMS:
            cells[key] = mos_terminal(inst, key) or ""
    else:
        cells["d"] = nodes[0] if len(nodes) > 0 else ""
        cells["g"] = ""
        cells["s"] = nodes[1] if len(nodes) > 1 else ""
        cells["b"] = ""

    # 尺寸参数：变量名原样保留（这才是优化变量），并区分"变量 / 固定值"
    free_n = fixed_n = 0
    for key, _suffix in PARAM_ORDER.get(kind, []):
        if key not in p:
            cells[key] = ""
            continue
        expr = p[key]
        if re.fullmatch(r"[A-Za-z_]\w*", expr):
            cells[key] = expr + "（变量）"
            free_n += 1
        else:
            cells[key] = expr + "（固定）"
            fixed_n += 1
    cells["n_free"] = free_n
    cells["n_fixed"] = fixed_n
    cells["continued"] = inst.get("continued_lines", 0)
    return cells


def build_readable(net: dict, subckt_name: str | None, src: str) -> tuple[str, list]:
    sc = find_subckt(net, subckt_name) if subckt_name else (
        net["subckts"][0] if net["subckts"] else None)
    if sc is None:
        raise SystemExit("网表里找不到可用的 subckt")

    topo = analyze_topology(net, sc["name"])
    stats = topo["stats"]

    # 逻辑器件（分段链已折叠）——这才是"一器件一行"的正确粒度
    analysis_set, collapsed = collapse_segmented(sc["instances"])
    by_name = {i["name"]: i for i in analysis_set}

    # 器件 -> 所属功能模块 ID
    mod_of: dict[str, list] = {}
    for m in topo["modules"]:
        for d in m["devices"]:
            mod_of.setdefault(d, []).append(m["id"])
    mod_type = {m["id"]: m["type"] for m in topo["modules"]}

    rows = []
    for inst in analysis_set:
        c = dev_cells(inst)
        c["modules"] = ",".join(mod_of.get(inst["name"], []))
        c["module_types"] = ",".join(sorted({mod_type[x] for x in mod_of.get(inst["name"], [])}))
        rows.append(c)

    moses = [r for r in rows if r["kind"] == "mos"]
    moses.sort(key=lambda r: (0 if r["polarity"] == "nmos" else 1, natkey(r["name"])))
    others = [r for r in rows if r["kind"] != "mos"]
    others.sort(key=lambda r: (r["kind"], natkey(r["name"])))
    rows = moses + others

    # 网表连接关系（网 -> 器件.端子）
    netmap: dict[str, list] = {}
    for inst in analysis_set:
        for key, _label in MOS_TERMS if inst["kind"] == "mos" else [("d", ""), ("s", "")]:
            term = mos_terminal(inst, key) if inst["kind"] == "mos" else (
                inst["nodes"][0 if key == "d" else 1] if len(inst["nodes"]) > (0 if key == "d" else 1) else None)
            if term:
                netmap.setdefault(term, []).append("%s.%s" % (inst["name"], key))

    L = []
    A = L.append
    A("# 网表可读化：`%s`" % os.path.basename(src))
    A("")
    A("> 由 `tools/netlist_readable.py` 自动生成。原网表里每个 MOS 后面跟着 10 行")
    A("> `+ad=... / +as=... / +nrd=...` 版图寄生参数续行，本视图把它们折叠成计数，")
    A("> 只保留真正有信息量的字段：**器件 / 端子 / 尺寸参数 / 所属功能模块**。")
    A("")

    A("## 1. 一眼看懂")
    A("")
    A("| 项 | 值 |")
    A("|---|---|")
    A("| 子电路 | `%s` |" % stats["subckt"])
    A("| 对外端口 | %s |" % ", ".join("`%s`" % p for p in stats["ports"]))
    A("| 原始器件数 | %d（MOS %d） |" % (stats["n_instances"], stats["n_mos"]))
    A("| 折叠分段后逻辑器件 | %d（%d 条分段链被折叠） |"
      % (stats["n_instances_collapsed"], stats["n_segmented_collapsed"]))
    A("| 优化变量（真变量） | %d 个；另有 %d 个字面常数尺寸不计入 |"
      % (stats["n_variables_before"], stats["n_fixed_params"]))
    A("| 电气惰性/Dummy 器件 | %s |"
      % (", ".join("`%s`" % x for x in stats.get("inert_devices") or []) or "无"))
    A("| testbench 器件 | %d 个（在 subckt 之外，见文末） |" % len(net["footer"]))
    A("")

    pairs = [m for m in topo["modules"] if m["type"] == "input_pair"]
    mirrors = [m for m in topo["modules"] if m["type"] == "current_mirror"]
    loads = [m for m in topo["modules"] if m["type"] == "active_load"]
    if pairs:
        main = next((m for m in pairs if m.get("role") == "main"), pairs[0])
        load_devs = ", ".join("`%s`" % d for m in loads for d in m["devices"])
        A("**信号通路**：差分输入对 `%s`（%s，尾节点 `%s`），漏极分别接有源负载 %s。"
          % ("`/`".join(main["devices"]), main["polarity"],
             main.get("shared_source_net"), load_devs or "（未识别到）"))
        A("输出节点经共模取样网络回到共模反馈（见 `CMFB1`）。")
        A("")
    if mirrors:
        A("**偏置通路**：%d 组电流镜 —— %s。"
          % (len(mirrors),
             "；".join("%s（参考管 `%s`，镜像管 %s）"
                       % (m["id"], m.get("reference_device"),
                          ", ".join("`%s`" % d for d in m.get("mirrored_devices", [])))
                       for m in mirrors)))
        A("")

    A("## 2. 器件总表（一行一个器件）")
    A("")
    A("说明：`l/w/m` 列里标 **（变量）** 的是待优化变量，标 **（固定）** 的是字面常数；")
    A("`续行` 列是该器件被折叠掉的 `+...` 版图参数行数；`模块` 列见第 3 节。")
    A("**电阻/电容是两端器件**，表中「漏」列=端点1、「源」列=端点2（两端无极性）。")
    A("")
    A("| 器件 | 类型 | 极性 | 模型 | 漏 | 栅 | 源 | 衬底 | multi | l | w/fw | m | segL | segW | 变量/固定 | 续行 | 模块 |")
    A("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")

    def cell(v):
        return str(v).replace("|", "\\|")

    for r in rows:
        A("| `%s` | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %d/%d | %s | %s |"
          % (cell(r["name"]), cell(r["kind"]), cell(r["polarity"]), cell(r["model"]),
             cell(r["d"]), cell(r["g"]), cell(r["s"]), cell(r["b"]), cell(r["multi"]),
             cell(r.get("l", "")), cell(r.get("w", "")), cell(r.get("m", "")),
             cell(r.get("segL", "")), cell(r.get("segW", "")),
             r["n_free"], r["n_fixed"], r["continued"] or "", cell(r["modules"])))
    A("")

    A("## 3. 按功能模块看")
    A("")
    A("| 模块 | 类型 | 器件 |")
    A("|---|---|---|")
    for m in sorted(topo["modules"], key=lambda x: (x["type"], natkey(x["id"]))):
        A("| `%s` | %s | %s |" % (m["id"], m["type"],
                                  ", ".join("`%s`" % d for d in m["devices"][:12])
                                  + ("…" if len(m["devices"]) > 12 else "")))
    A("")
    A("> 每个模块的**判定依据**（为何这样识别）保存在 `topology_analysis.json` 的 `modules[].evidence`。")
    A("")

    if collapsed:
        A("## 4. 被折叠的自动分段器件")
        A("")
        A("Cadence/Aether 会把一个长电阻拆成多段串联，网表里表现为 `R0` + `R0_2_res_gen` …。")
        A("它们是**同一个物理器件**，本视图已折叠成一行，只保留一组变量。")
        A("")
        A("| 基准器件 | 链上段数 | 链上器件（含基准） |")
        A("|---|---|---|")
        for c in collapsed:
            A("| `%s` | %d | %s |" % (c["name"], c.get("element_count", c["segment_count"]),
                                      ", ".join("`%s`" % s for s in c["segments"])))
        A("")

    A("## 5. 网表连接清单（网 → 器件.端子）")
    A("")
    A("| 网名 | 连接的器件端子 |")
    A("|---|---|")
    for n in sorted(netmap, key=natkey):
        A("| `%s` | %s |" % (n, ", ".join("%s.%s" % (t.split(".")[0], t.split(".")[1])
                                          for t in sorted(netmap[n], key=natkey))))
    A("")

    if net["footer"]:
        A("## 6. subckt 之外的 testbench 器件")
        A("")
        A("| 器件 | 类型 | 端子 | 参数 |")
        A("|---|---|---|---|")
        for inst in net["footer"]:
            A("| `%s` | %s | %s | %s |"
              % (inst["name"], inst["kind"], " ".join(inst["nodes"]),
                 " ".join("%s=%s" % (k, v) for k, v in inst.get("params", {}).items())))
        A("")

    if topo.get("warnings"):
        A("## 7. 需要人工确认的点")
        A("")
        for w in topo["warnings"]:
            A("- ⚠️ %s" % w)
        A("")

    md = "\n".join(L)

    # ---- CSV ----
    csv_rows = []
    for r in rows:
        csv_rows.append({
            "instance": r["name"], "kind": r["kind"], "polarity": r["polarity"],
            "model": r["model"], "multi": r["multi"],
            "d": r["d"], "g": r["g"], "s": r["s"], "b": r["b"],
            "l": r.get("l", ""), "w": r.get("w", ""), "m": r.get("m", ""),
            "segL": r.get("segL", ""), "segW": r.get("segW", ""),
            "n_free_vars": r["n_free"], "n_fixed_params": r["n_fixed"],
            "folded_layout_lines": r["continued"], "segmented": r["segmented"],
            "diode_connected": r["diode"], "modules": r["modules"],
        })
    return md, csv_rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="把 Spectre 网表变成人可读的表格")
    ap.add_argument("--netlist", default=DEFAULT_NETLIST, help="网表路径")
    ap.add_argument("--outdir", default=os.path.join(ROOT, "module1", "agent", "output"))
    ap.add_argument("--subckt", default=None, help="只分析指定子电路（默认第一个）")
    args = ap.parse_args(argv)

    if not os.path.exists(args.netlist):
        print("找不到网表: %s" % args.netlist, file=sys.stderr)
        return 1

    net = parse_netlist(args.netlist)
    md, rows = build_readable(net, args.subckt, args.netlist)

    os.makedirs(args.outdir, exist_ok=True)
    md_path = os.path.join(args.outdir, "netlist_readable.md")
    csv_path = os.path.join(args.outdir, "netlist_devices.csv")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print("已写出: %s（%d 行 Markdown）" % (md_path, md.count("\n") + 1))
    print("已写出: %s（%d 个器件）" % (csv_path, len(rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
