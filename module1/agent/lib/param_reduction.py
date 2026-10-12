"""模块 2-③  参数约减。

按《PyAether 教程》第 11.3 节的原则做变量约减：

| 该保留 | 该剔除 |
|---|---|
| 直接影响性能的：输入对管 W/L/m、负载管 W/L、补偿电容、偏置电流 | 固定不动的：电源、地、理想源 |
| 成比例匹配组：保留一个"基准变量" + 比例系数 | Dummy 器件 |
| 有对称约束的：只留一组，另一组由对称规则导出 | 已有硬约束的（如已固定的共模电平） |

约减顺序（不能乱，否则会把"可合并"的器件先删掉）：
  1. 剔除 dummy / 悬空器件的全部变量
  2. 匹配器件尺寸绑定：同组共享一组变量（其余变量登记为冗余映射）
  3. 电流镜比例绑定：镜像管共享（镜像比用 m 表达）
  4. 折叠自动分段器件：多段只保留一组变量
  5. 标注连续 / 整数类型与赛题边界

输出交付物（对齐赛题 6.2 与教程 11.1）：
  1. 拓扑模块识别结果
  2. 约减后的变量个数 + 变量统计列表
  3. 约减后的网表
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from netlist_parser import PARAM_ORDER

# 赛题器件取值范围（教程 12.3【官】）
BOUNDS = {
    "l": ("continuous", [0.13e-6, 10e-6], "m", "晶体管长度 L：0.13μm – 10μm"),
    "fw": ("continuous", [0.13e-6, 20e-6], "m", "晶体管宽度 W(fw)：0.13μm – 20μm"),
    "w": ("continuous", [0.13e-6, 20e-6], "m", "晶体管/电容宽度：0.13μm – 20μm"),
    "m": ("integer", [1, 20], "", "Multiplier m：1..20（整数）"),
    "seg": ("integer", [1, 20], "", "电阻 Segment：1..20（整数）"),
    "segL": ("continuous", [0.13e-6, 20e-6], "m", "电阻段长 segL：0.13μm – 20μm"),
    "segW": ("continuous", [0.13e-6, 20e-6], "m", "电阻段宽 segW：0.13μm – 20μm"),
}

# 只保留这些参数的变量（其余如 ad/as/pd/ps/nrd/nrs 是版图派生量，不独立优化）
OPTIMIZABLE_PARAMS = {"l", "w", "m", "segL", "segW", "seg"}


def _var_type_and_bounds(param: str) -> Tuple[str, Optional[list], str, str]:
    return BOUNDS.get(param, ("continuous", None, "", "未在赛题约束表中，需人工确认"))


def reduce_parameters(net: dict, topo: dict, subckt_name: Optional[str] = None) -> dict:
    """执行参数约减。返回结构见 ../CONTRACTS.md 第 2.4 节。"""
    from netlist_parser import find_subckt
    from topology_analyzer import collapse_segmented

    if subckt_name:
        sc = find_subckt(net, subckt_name)
    else:
        sc = net["subckts"][0] if net.get("subckts") else None
    if sc is None:
        raise ValueError("网表里没有可用的 subckt")

    instances = sc["instances"]
    analysis_set, collapsed = collapse_segmented(instances)
    by_name = {i["name"]: i for i in analysis_set}

    decision_log: List[dict] = []
    groups: List[dict] = []
    removed: Dict[str, list] = {"dummy_variables": [], "redundant_variables": [],
                               "dummy_devices": [], "floating_devices": []}

    # ------------------------------------------------------------------
    # 0. 先建立"器件 -> 变量"全集（这是变量数的基线）
    # ------------------------------------------------------------------
    var_by_device: Dict[str, List[dict]] = {}
    for inst in analysis_set:
        vs = [v for v in inst.get("variables", []) if v["param"] in OPTIMIZABLE_PARAMS]
        if vs:
            var_by_device[inst["name"]] = vs
    count_before = sum(len(v) for v in var_by_device.values())

    # ------------------------------------------------------------------
    # 1. 剔除 dummy / 悬空器件
    # ------------------------------------------------------------------
    dummy_devices = []
    for m in topo["modules"]:
        if m["type"] == "dummy":
            dummy_devices.extend(m["devices"])
    dummy_devices = sorted(set(dummy_devices))

    for name in dummy_devices:
        vs = var_by_device.pop(name, [])
        removed["dummy_devices"].append(name)
        for v in vs:
            removed["dummy_variables"].append({"name": v["name"], "device": name,
                                               "reason": "Dummy 器件，不参与电路功能"})
    if dummy_devices:
        decision_log.append({
            "step": "remove_dummy",
            "targets": dummy_devices,
            "reason": "全端子接同一网/悬空的 Dummy 器件，剔除其全部优化变量",
            "effect": "删除 %d 个器件、%d 个变量"
                      % (len(dummy_devices), len(removed["dummy_variables"])),
        })

    # ------------------------------------------------------------------
    # 2. 匹配器件尺寸绑定（matching_pair 优先）
    # ------------------------------------------------------------------
    bound: Dict[str, str] = {}          # 器件名 -> 基准器件名
    for m in topo["modules"]:
        if m["type"] != "matching_pair":
            continue
        a, b = m["devices"][0], m["devices"][1]
        if a not in var_by_device or b not in var_by_device:
            continue
        # 已绑定过就跳过
        if bound.get(a) or bound.get(b):
            continue
        bound[b] = a
        shared = []
        for va in var_by_device[a]:
            vb = next((v for v in var_by_device[b] if v["param"] == va["param"]), None)
            if vb is None:
                continue
            shared.append(va["param"])
            removed["redundant_variables"].append({
                "name": vb["name"],
                "mapped_to": va["name"],
                "reason": "与 %s 为匹配对（%s），尺寸必须绑定" % (a, m["match_rule"]),
            })
        var_by_device.pop(b, None)
        groups.append({
            "id": "G_%s" % m["id"],
            "type": "matching_pair",
            "members": [a, b],
            "base_device": a,
            "shared_params": shared,
            "reason": m["evidence"],
        })
    if groups:
        decision_log.append({
            "step": "bind_matching_pair",
            "targets": [g["members"] for g in groups],
            "reason": "匹配器件必须尺寸绑定：保留一个基准变量，另一器件由匹配规则导出",
            "effect": "绑定 %d 组，删除 %d 个冗余变量"
                      % (len(groups), len(removed["redundant_variables"])),
        })

    # ------------------------------------------------------------------
    # 3. 电流镜比例绑定（镜像管共享 l；镜像比用 w/m 表达）
    # ------------------------------------------------------------------
    mirror_groups = []
    n_mirror_vars_removed = 0
    for m in topo["modules"]:
        if m["type"] != "current_mirror":
            continue
        ref = m.get("reference_device")
        mirrors = [d for d in m.get("mirrored_devices", []) if d in var_by_device]
        if not ref or ref not in var_by_device or not mirrors:
            continue
        bound_members = []
        for d in mirrors:
            # 已由匹配对绑定到**别的**基准管的器件，交给匹配对统一管理，
            # 否则会出现同一条 l 变量被重复登记（链式重复绑定）
            if bound.get(d) and bound[d] != ref:
                bound_members.append(d)
                continue
            gone = [v for v in var_by_device.get(d, []) if v["param"] == "l"]
            for v in gone:
                removed["redundant_variables"].append({
                    "name": v["name"],
                    "mapped_to": "%s_l" % ref,
                    "reason": "电流镜 %s 的镜像管，沟道长度须与参考管 %s 一致" % (m["id"], ref),
                })
            var_by_device[d] = [x for x in var_by_device.get(d, []) if x["param"] != "l"]
            n_mirror_vars_removed += len(gone)
            bound_members.append(d)
        mirror_groups.append({
            "id": "G_%s" % m["id"],
            "type": "current_mirror",
            "members": [ref] + mirrors,
            "base_device": ref,
            "shared_params": ["l"],
            "ratio_params": ["w", "m"],
            "reason": "%s；镜像比通过 w/m 的比例表达" % m["evidence"],
        })
    if mirror_groups:
        decision_log.append({
            "step": "bind_current_mirror",
            "targets": [g["members"] for g in mirror_groups],
            "reason": "电流镜镜像管沟道长度必须与参考管一致；镜像比用 w/m 比例表达",
            "effect": "处理 %d 个电流镜，删除 %d 个冗余 l 变量"
                      % (len(mirror_groups), n_mirror_vars_removed),
        })
        groups.extend(mirror_groups)

    # ------------------------------------------------------------------
    # 4. 自动分段器件折叠（多段共用一个变量）
    # ------------------------------------------------------------------
    for c in collapsed:
        seg_vars = c["segments"]
        decision_log.append({
            "step": "collapse_segmented",
            "targets": seg_vars,
            "reason": "自动分段器件 %s（%d 段）是同一物理器件，全链共用一组变量"
                      % (c["name"], c["segment_count"]),
            "effect": "变量只保留 1 组（原 %d 个器件各自一组）" % len(seg_vars),
        })

    # ------------------------------------------------------------------
    # 5. 生成最终变量清单（标注类型与赛题边界）
    # ------------------------------------------------------------------
    optimization_variables: List[dict] = []
    for name in sorted(var_by_device):
        inst = by_name.get(name, {})
        for v in var_by_device[name]:
            kind, bounds, unit, note = _var_type_and_bounds(v["var_suffix"])
            # 变量名里的后缀用于取边界（MOS 的 w -> fw）
            item = {
                "name": v["name"],
                "instance": name,
                "instance_kind": inst.get("kind"),
                "param": v["param"],
                "kind": kind,
                "bounds": bounds,
                "unit": unit,
                "init": v.get("initial"),
                "note": note,
            }
            optimization_variables.append(item)

    # 变量统计
    by_param: Dict[str, int] = {}
    for v in optimization_variables:
        by_param[v["param"]] = by_param.get(v["param"], 0) + 1
    n_integer = sum(1 for v in optimization_variables if v["kind"] == "integer")
    by_kind: Dict[str, int] = {}
    for v in optimization_variables:
        by_kind[v["instance_kind"]] = by_kind.get(v["instance_kind"], 0) + 1

    count_after = len(optimization_variables)

    # ---- 把冗余映射回溯到"等价类根变量"，消除两跳链 ----
    # 例：NM13_l -> NM12_l，而 NM12_l 自己又被删（-> NM2_l）。
    # 若不做回溯，NM13_l 的映射目标在最终清单里不存在，下游回写会找不到变量。
    direct = {r["name"]: r["mapped_to"] for r in removed["redundant_variables"]}

    def resolve(v: str) -> str:
        seen = set()
        while v in direct and v not in seen:
            seen.add(v)
            v = direct[v]
        return v

    for r in removed["redundant_variables"]:
        root = resolve(r["mapped_to"])
        if root != r["mapped_to"]:
            r["mapped_via"] = r["mapped_to"]
            r["mapped_to"] = root

    # 自洽性断言：最终枚举结果必须等于"约减前 - 被删除的冗余变量数"
    n_removed = len(removed["redundant_variables"])
    assert count_before - n_removed == count_after, (
        "参数约减对账失败：before=%d - 冗余=%d != after=%d"
        % (count_before, n_removed, count_after))

    # 回溯后，映射目标必须真实存在于最终清单
    final_names = {v["name"] for v in optimization_variables}
    dangling = sorted({r["mapped_to"] for r in removed["redundant_variables"]
                       if r["mapped_to"] not in final_names})
    assert not dangling, "冗余映射目标仍悬空: %s" % dangling

    # ------------------------------------------------------------------
    # 6. 生成约减后的网表文本（交付物）
    # ------------------------------------------------------------------
    netlist_after, kept_devices = render_reduced_netlist(sc, analysis_set, var_by_device)
    decision_log.append({
        "step": "render_reduced_netlist",
        "targets": kept_devices,
        "reason": "只保留参与优化的器件（已折叠分段、已剔除 dummy），并写出其变量",
        "effect": "约减后网表含 %d 个器件" % len(kept_devices),
    })

    return {
        "subckt": sc["name"],
        "_comment": "变量数：raw=原始网表器件级变量；before=折叠分段后；after=约减后",
        "variable_count_raw": sum(len(i.get("variables", [])) for i in instances),
        "variable_count_before": count_before,
        "variable_count_after": count_after,
        "reduction_ratio": round(1.0 - (count_after / count_before), 4) if count_before else 0.0,
        "optimization_variables": optimization_variables,
        "variable_stats": {
            "by_param": by_param,
            "by_instance_kind": by_kind,
            "n_integer": n_integer,
            "n_continuous": count_after - n_integer,
            "n_groups": len(groups),
        },
        "groups": groups,
        "removed": removed,
        "reduced_netlist": netlist_after,
        "decision_log": decision_log,
    }


def render_reduced_netlist(sc: dict, analysis_set: List[dict],
                           var_by_device: Dict[str, List[dict]]) -> Tuple[str, List[str]]:
    """把约减后的网表渲染成 Spectre 文本（交付物 3）。"""
    lines = ["// ---- 约减后网表（由模块 2 自动生成）----",
             "// 说明：已折叠自动分段器件、已剔除 Dummy；变量名沿用官方 <实例名>_<参数> 规则",
             "subckt %s (%s)" % (sc["name"], " ".join(sc["ports"]))]

    keep = set(var_by_device)
    kept_devices: List[str] = []
    for inst in analysis_set:
        name = inst["name"]
        if name not in keep and not inst.get("segmented"):
            continue
        if name in keep:
            params = []
            for v in var_by_device[name]:
                params.append("%s=%s" % (v["param"], v["name"]))
            # 保留非优化但必需的参数（model/multi 等）
            extra = []
            for k, val in inst.get("params", {}).items():
                if k in OPTIMIZABLE_PARAMS:
                    continue
                extra.append("%s=%s" % (k, val))
            lines.append("%-8s (%s) %s %s"
                         % (name, " ".join(inst["nodes"]), inst.get("model") or "",
                            " ".join(params + extra)))
            kept_devices.append(name)
        elif inst.get("segmented"):
            lines.append("// （已折叠）%s <- %s" % (name, inst.get("segments")))
    lines.append("ends %s" % sc["name"])
    return "\n".join(lines), kept_devices
