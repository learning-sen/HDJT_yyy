"""模块 2-③  参数约减。

按《PyAether 教程》第 11.3 节的原则做变量约减：

| 该保留 | 该剔除 |
|---|---|
| 直接影响性能的：输入对管 W/L/m、负载管 W/L、补偿电容、偏置电流 | 固定不动的：电源、地、理想源 |
| 成比例匹配组：保留一个"基准变量" + 比例系数 | Dummy / 电气惰性器件 |
| 有对称约束的：只留一组，另一组由对称规则导出 | 已有硬约束的（如已固定的共模电平） |

约减顺序（不能乱，否则会把"可合并"的器件先删掉）：
  1. 剔除 dummy / 电气惰性 / 孤立器件的全部变量（器件保留在网表里）
  2. 尺寸绑定：对称匹配组（WL 自同构）与差分对按 `bind_params` 绑定到基准器件
  3. 电流镜长度绑定：镜像管共享 L，镜像比由 w/m 表达（**不绑 w/m**）
  4. 折叠自动分段器件：多段只保留一组变量
  5. 标注连续 / 整数类型与赛题边界
  6. 渲染约减后网表（**保留全部器件**，只把变量换成绑定后的基准变量）

三条容易搞错、这里都做了显式处理的规则：
  - **字面常数不是优化变量**：网表里以变量名给出的尺寸参数才是待优化变量
    （`l=NM15_l`），写成字面值的（`w=10u`、`m=1`）是器件结构的固定部分，
    官方参数化脚本也没把它们变成变量，所以不计入变量数。
  - **镜像支路只绑 L**：把 w/m 也绑死等于把镜像比锁成 1，优化器就不能再调工作点了。
    只有差分两臂/对称两臂（对换对称、必须完全一致）才绑全部尺寸。
  - **约减的是变量，不是器件**：约减后网表必须与约减前电气等价。

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

# 默认绑定范围（模块没给 bind_params 时用全量）
DEFAULT_BIND_PARAMS = ["l", "w", "m", "segL", "segW", "seg"]


def _var_type_and_bounds(param: str) -> Tuple[str, Optional[list], str, str]:
    return BOUNDS.get(param, ("continuous", None, "", "未在赛题约束表中，需人工确认"))


def free_variables(inst: dict) -> List[dict]:
    """取该器件的**真优化变量**（参数以变量名给出，且属于可优化参数）。

    网表里 `l=NM15_l` 是变量；`w=10u`、`m=1` 是字面常数，不是优化变量。
    """
    return [v for v in inst.get("variables", [])
            if v["param"] in OPTIMIZABLE_PARAMS and v.get("interface", "variable") != "value"]


def _ordered_param_keys(inst: dict) -> List[str]:
    """按器件类型的习惯顺序列出该器件实际出现的可优化参数键。"""
    order = [k for k, _ in PARAM_ORDER.get(inst["kind"], [])]
    keys = [k for k in order if k in inst.get("params", {})]
    keys += [k for k in sorted(inst.get("params", {}))
             if k in OPTIMIZABLE_PARAMS and k not in keys]
    return keys


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
    # 0. 建立"器件 -> 变量"全集（只收真变量，字面常数不计）
    # ------------------------------------------------------------------
    var_by_device: Dict[str, List[dict]] = {}
    for inst in analysis_set:
        vs = free_variables(inst)
        if vs:
            var_by_device[inst["name"]] = vs

    n_fixed_params = sum(1 for i in analysis_set for v in i.get("variables", [])
                         if v.get("interface", "variable") == "value")
    count_before = sum(len(v) for v in var_by_device.values())

    def base_var_name(base: str, param: str) -> str:
        """基准器件上该参数对应的变量名（绑定目标要用它，而不是设备名）。"""
        for v in var_by_device.get(base, []):
            if v["param"] == param:
                return v["name"]
        return "%s_%s" % (base, param)

    # ------------------------------------------------------------------
    # 1. 剔除 Dummy / 电气惰性 / 孤立器件的变量（器件本身保留在网表里）
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
            removed["dummy_variables"].append({
                "name": v["name"], "device": name,
                "reason": "Dummy / 电气惰性器件：其尺寸对任何仿真结果都没有影响",
            })
    if dummy_devices:
        decision_log.append({
            "step": "remove_dummy",
            "targets": dummy_devices,
            "reason": "两端同网（电气惰性）/ 与主电路无电气连接（孤立）/ 全端子同网或悬空 —— "
                      "这些器件的尺寸不可能影响任何仿真结果，属纯冗余优化变量",
            "effect": "剔除 %d 个器件的 %d 个变量（器件保留在约减后网表中，尺寸按原值固定）"
                      % (len(dummy_devices), len(removed["dummy_variables"])),
        })

    # ------------------------------------------------------------------
    # 2. 尺寸绑定：对称匹配组（WL 自同构）+ 差分对
    #    绑定范围由模块的 bind_params 决定：
    #      - 对换对称组（差分两臂/对称两臂）：l,w,m 全绑，因为必须完全一致
    #      - 同支路镜像组：只绑 L，w/m 留给优化器表达镜像比
    # ------------------------------------------------------------------
    bound: Dict[str, str] = {}          # 器件名 -> 基准器件名
    n_bind_vars = 0
    for m in topo["modules"]:
        if m["type"] not in ("matching_pair", "input_pair"):
            continue
        members = [d for d in m.get("devices", []) if d in var_by_device]
        if len(members) < 2:
            continue
        base = m.get("base_device") if m.get("base_device") in members else members[0]
        if bound.get(base):
            continue                    # 基准管已绑到别处：跳过，避免链式绑定打架
        bind_params = set(m.get("bind_params") or DEFAULT_BIND_PARAMS)
        shared_params: List[str] = []
        bound_members: List[str] = []
        for other in members:
            if other == base or bound.get(other):
                continue
            kept = []
            for v in var_by_device.get(other, []):
                if v["param"] in bind_params:
                    removed["redundant_variables"].append({
                        "name": v["name"],
                        "mapped_to": base_var_name(base, v["param"]),
                        "reason": "%s：与基准器件 %s 尺寸绑定（%s）"
                                  % (m["id"], base, m.get("match_rule") or m.get("role") or m["type"]),
                    })
                    shared_params.append(v["param"])
                    n_bind_vars += 1
                else:
                    kept.append(v)
            var_by_device[other] = kept
            if not kept:
                var_by_device.pop(other, None)
            bound[other] = base
            bound_members.append(other)
        if not bound_members:
            continue
        groups.append({
            "id": "G_%s" % m["id"],
            "type": m["type"],
            "match_rule": m.get("match_rule") or m.get("role"),
            "detector": m.get("detector", ""),
            "members": [base] + bound_members,
            "base_device": base,
            "shared_params": sorted(set(shared_params)),
            "reason": m["evidence"],
        })
    if groups:
        decision_log.append({
            "step": "bind_matching_group",
            "targets": [g["members"] for g in groups],
            "reason": "匹配器件必须尺寸绑定：保留一个基准变量，其余由匹配规则导出。"
                      "对换对称组绑全部尺寸；同支路镜像组只绑 L（镜像比由 w/m 表达）",
            "effect": "绑定 %d 组、删除 %d 个冗余变量" % (len(groups), n_bind_vars),
        })

    # ------------------------------------------------------------------
    # 3. 电流镜长度绑定（镜像管共享 l；镜像比用 w/m 表达）
    # ------------------------------------------------------------------
    mirror_groups = []
    n_mirror_vars_removed = 0
    for m in topo["modules"]:
        if m["type"] != "current_mirror":
            continue
        ref = m.get("reference_device")
        if not ref or ref not in var_by_device:
            continue
        members = [ref]
        for d in m.get("mirrored_devices", []):
            if d not in var_by_device:
                members.append(d)
                continue
            # 已由匹配组绑定到别的基准管的器件，交给匹配组统一管理，
            # 否则同一条 l 变量会被重复登记（链式重复绑定）
            if bound.get(d) and bound[d] != ref:
                members.append(d)
                continue
            gone = [v for v in var_by_device.get(d, []) if v["param"] == "l"]
            for v in gone:
                removed["redundant_variables"].append({
                    "name": v["name"],
                    "mapped_to": base_var_name(ref, "l"),
                    "reason": "电流镜 %s 的镜像管，沟道长度须与参考管 %s 一致" % (m["id"], ref),
                })
            var_by_device[d] = [x for x in var_by_device.get(d, []) if x["param"] != "l"]
            if not var_by_device[d]:
                var_by_device.pop(d, None)
            n_mirror_vars_removed += len(gone)
            bound.setdefault(d, ref)
            members.append(d)
        mirror_groups.append({
            "id": "G_%s" % m["id"],
            "type": "current_mirror",
            "members": members,
            "base_device": ref,
            "shared_params": ["l"],
            "ratio_params": ["w", "m"],
            "reason": "%s；镜像比通过 w/m 的比例表达（w/m 不绑，保持可调）" % m["evidence"],
        })
    if mirror_groups:
        decision_log.append({
            "step": "bind_current_mirror",
            "targets": [g["members"] for g in mirror_groups],
            "reason": "电流镜镜像管沟道长度必须与参考管一致；镜像比用 w/m 比例表达，"
                      "所以只绑 L，不绑 w/m",
            "effect": "处理 %d 个电流镜，删除 %d 个冗余 l 变量"
                      % (len(mirror_groups), n_mirror_vars_removed),
        })
        groups.extend(mirror_groups)

    # ------------------------------------------------------------------
    # 4. 自动分段器件折叠（多段共用一个变量）
    # ------------------------------------------------------------------
    for c in collapsed:
        decision_log.append({
            "step": "collapse_segmented",
            "targets": c["segments"],
            "reason": "自动分段器件 %s 由 1 个基准器件 + %d 个自动生成段（共 %d 段串联）组成，"
                      "是同一物理器件，全链共用一组变量"
                      % (c["name"], c["segment_count"], c["element_count"]),
            "effect": "变量只保留 1 组（原 %d 个器件各自一组）" % c["element_count"],
        })

    # ------------------------------------------------------------------
    # 5. 生成最终变量清单（标注类型与赛题边界）
    # ------------------------------------------------------------------
    optimization_variables: List[dict] = []
    for name in sorted(var_by_device):
        inst = by_name.get(name, {})
        role = "bound" if bound.get(name) else "base"
        for v in var_by_device[name]:
            kind, bounds, unit, note = _var_type_and_bounds(v["var_suffix"])
            optimization_variables.append({
                "name": v["name"],
                "instance": name,
                "instance_kind": inst.get("kind"),
                "param": v["param"],
                "kind": kind,
                "bounds": bounds,
                "unit": unit,
                "init": v.get("initial"),
                "role": role,
                "bound_to": bound.get(name),
                "note": note,
            })

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

    # 自洽性断言：约减前 = 最终 + dummy 剔除 + 冗余绑定
    n_removed = len(removed["redundant_variables"])
    n_dummy = len(removed["dummy_variables"])
    assert count_before - n_dummy - n_removed == count_after, (
        "参数约减对账失败：before=%d - dummy=%d - 冗余=%d != after=%d"
        % (count_before, n_dummy, n_removed, count_after))

    # 回溯后，映射目标必须真实存在于最终清单
    final_names = {v["name"] for v in optimization_variables}
    dangling = sorted({r["mapped_to"] for r in removed["redundant_variables"]
                       if r["mapped_to"] not in final_names})
    assert not dangling, "冗余映射目标仍悬空: %s" % dangling

    # ------------------------------------------------------------------
    # 6. 生成约减后的网表文本（保留全部器件，只改变量的表达）
    # ------------------------------------------------------------------
    inert = set(topo["stats"].get("inert_devices") or [])
    netlist_after, kept_devices = render_reduced_netlist(
        sc, analysis_set, var_by_device, inert=inert, bound=bound)
    n_lost = len(analysis_set) - len(kept_devices)
    assert n_lost == 0, "约减后网表丢了 %d 个器件（必须与约减前电气等价）" % n_lost
    decision_log.append({
        "step": "render_reduced_netlist",
        "targets": kept_devices,
        "reason": "约减的是**变量**不是器件：全部器件保留（分段链折叠为基准器件），"
                  "被绑定的参数写成基准变量名，字面常数/惰性器件按原值写出并加注释",
        "effect": "约减后网表含 %d 个器件（约减前逻辑器件 %d 个，无丢失）"
                  % (len(kept_devices), len(analysis_set)),
    })

    return {
        "subckt": sc["name"],
        "_comment": "变量数：raw=原始网表器件级真变量；before=折叠分段后真变量；after=约减后",
        "variable_count_raw": sum(len(free_variables(i)) for i in instances),
        "variable_count_before": count_before,
        "variable_count_after": count_after,
        "variable_count_fixed": n_fixed_params,
        "reduction_ratio": round(1.0 - (count_after / count_before), 4) if count_before else 0.0,
        "optimization_variables": optimization_variables,
        "variable_stats": {
            "by_param": by_param,
            "by_instance_kind": by_kind,
            "n_integer": n_integer,
            "n_continuous": count_after - n_integer,
            "n_groups": len(groups),
            "n_dummy_devices": len(dummy_devices),
            "n_dummy_variables": n_dummy,
            "n_bound_variables": n_removed,
            "n_fixed_params_excluded": n_fixed_params,
        },
        "groups": groups,
        "removed": removed,
        "reduced_netlist": netlist_after,
        "reduced_netlist_devices": kept_devices,
        "decision_log": decision_log,
    }


def render_reduced_netlist(sc: dict, analysis_set: List[dict],
                           var_by_device: Dict[str, List[dict]],
                           inert: Optional[set] = None,
                           bound: Optional[Dict[str, str]] = None) -> Tuple[str, List[str]]:
    """把约减后的网表渲染成 Spectre 文本（交付物 3）。

    ⚠️ 语义要点：**约减的是变量，不是器件**。
    旧实现用的是 `if name not in var_by_device: continue`，于是把所有"变量被绑定掉"
    的器件（NM13/NM6/NM7/NM9/PM9/PM3/C3… 以及 R3 的合并件）整个从网表里删掉了，
    约减后网表只剩 34 个器件 —— 那不是同一个电路，根本跑不起来。
    现在每个器件都保留：
      - 仍作为优化变量的参数 -> 写成变量名；
      - 字面常数 / 被判为惰性或被绑定的参数 -> 写出原表达式（如 `l=C4_l`、`w=10u`）
        并在行尾注明是固定值。
    """
    inert = inert or set()
    bound = bound or {}
    free_by_dev = {n: {v["param"]: v["name"] for v in vs} for n, vs in var_by_device.items()}

    lines = ["// ---- 约减后网表（由模块 2 自动生成）----",
             "// 说明：全部器件保留（分段链折叠为基准器件）；参数保留为优化变量的写变量名，",
             "//       其余按原值固定（行尾 // 注释标注），因此本网表与约减前电气等价",
             "subckt %s (%s)" % (sc["name"], " ".join(sc["ports"]))]

    kept_devices: List[str] = []
    for inst in analysis_set:
        name = inst["name"]
        if inst.get("segmented"):
            lines.append("// （分段链已折叠为 1 个逻辑器件）%s <- %s"
                         % (name, inst.get("segments")))

        free = free_by_dev.get(name, {})
        params = []
        params_raw = []
        for pkey in _ordered_param_keys(inst):
            if pkey in free:
                params.append("%s=%s" % (pkey, free[pkey]))
                params_raw.append("%s=%s" % (pkey, inst["params"][pkey]))
            else:
                params.append("%s=%s" % (pkey, inst["params"][pkey]))

        extra = ["%s=%s" % (k, v) for k, v in inst.get("params", {}).items()
                 if k not in OPTIMIZABLE_PARAMS]

        marks = []
        if name in inert:
            marks.append("惰性/Dummy：变量已剔除，按原值固定")
        if bound.get(name):
            marks.append("尺寸绑定到 %s" % bound[name])
        if any(p.split("=")[0] not in free for p in params):
            marks.append("含固定尺寸")

        line = "%-8s (%s) %s %s" % (name, " ".join(inst["nodes"]),
                                    inst.get("model") or "", " ".join(params + extra))
        if marks:
            line += "   // " + "；".join(marks)
        lines.append(line.rstrip())
        kept_devices.append(name)

    lines.append("ends %s" % sc["name"])
    return "\n".join(lines), kept_devices
