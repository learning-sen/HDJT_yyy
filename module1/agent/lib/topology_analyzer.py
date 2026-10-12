"""模块 2-②  拓扑模块识别。

方法（对齐《PyAether 教程》第 11.2 节【官】）：
  **基于连接关系的图分析**，规则只看结构、不看名字。
  红线：隐藏电路（Hidden）也参与评分，禁止硬编码器件名（如写死"NM15 是输出管"）。

识别的模块类型：
  current_mirror  电流镜      : 同型 MOS 栅极同网 + 源极同网，其中一个二极管连接
  input_pair      差分输入对  : 同型 MOS 源极同网，栅极分别为 VINP/VINN
  active_load     有源负载    : 作为负载使用的电流镜/二极管连接器件
  matching_pair   匹配器件    : 同 model、同尺寸参数、连接结构对称的器件对
  dummy           Dummy 器件  : 全部端子接同一网（或命名含 dummy），不参与电路功能
  cmfb            共模反馈    : 出现 outaverage/vcmfb 类节点，或检测两路输出的电阻分压网络
  bias_branch     偏置支路    : 由偏置端口驱动的参考支路
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from netlist_parser import mos_terminal

# 端口/网名启发（仅作**辅助**证据，不作为唯一判据）
INPUT_PORT_RE = re.compile(r"VINP|VINN|INP|INN|VIP|VIM", re.I)
OUTPUT_PORT_RE = re.compile(r"VOUTP|VOUTN|OUTP|OUTN|VOP|VON", re.I)
BIAS_RE = re.compile(r"IREF|IBIAS|VREF|VB|VBIAS|VCM", re.I)
CMFB_RE = re.compile(r"outaverage|vcmfb|vcm|cmfb|outavg", re.I)
DUMMY_NAME_RE = re.compile(r"dummy|dmy|_dm|^D", re.I)
POWER_RE = re.compile(r"^(VDD|VDDA|VSS|GND|GNDA|0|SUB)$", re.I)
# Cadence/Aether 自动分段器件后缀（同一物理器件被拆成多段串联）
SEG_SUFFIX_RE = re.compile(r"^(?P<base>.+?)_(?P<idx>\d+)_res_gen$", re.I)


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _moses(instances: List[dict]) -> List[dict]:
    return [i for i in instances if i["kind"] == "mos"]


def _polarity(inst: dict) -> str:
    """由模型名与实例名前缀判极性（结构判据的输入之一）。"""
    model = (inst.get("model") or "").lower()
    name = inst["name"].upper()
    if "pmos" in model or "p_mos" in model or "pfet" in model:
        return "pmos"
    if "nmos" in model or "n_mos" in model or "nfet" in model:
        return "nmos"
    if name.startswith("PM"):
        return "pmos"
    if name.startswith("NM"):
        return "nmos"
    return "unknown"


def _size_signature(inst: dict) -> Tuple:
    """尺寸签名：参数值相同则视为可匹配（值可能是变量名，用变量名比较就是结构等价）。"""
    p = inst.get("params", {})
    return (inst.get("model"), p.get("l"), p.get("w"), p.get("m"), p.get("multi"))


def _drain(inst): return mos_terminal(inst, "d")
def _gate(inst): return mos_terminal(inst, "g")
def _source(inst): return mos_terminal(inst, "s")
def _bulk(inst): return mos_terminal(inst, "b")


def _is_diode_connected(inst: dict) -> bool:
    """栅漏短接（二极管连接）。"""
    return _gate(inst) is not None and _gate(inst) == _drain(inst)


def _is_all_terminals_same(inst: dict) -> bool:
    nets = [n for n in inst["nodes"] if n is not None]
    return len(nets) > 0 and len(set(nets)) == 1


def _all_terminals_dangling(inst: dict, known_nets: set) -> bool:
    """所有端子都接到"未在其他任何器件出现过的网"（悬空）。"""
    nets = [n for n in inst["nodes"] if n is not None]
    return bool(nets) and all(n not in known_nets for n in nets)


def _dev(inst: dict) -> dict:
    return {
        "name": inst["name"],
        "kind": inst["kind"],
        "model": inst.get("model"),
        "polarity": _polarity(inst) if inst["kind"] == "mos" else "-",
        "nodes": inst["nodes"],
        "variables": [v["name"] for v in inst.get("variables", [])],
    }


# ---------------------------------------------------------------------------
# 预处理：把自动分段器件折叠成一个"逻辑器件"
# ---------------------------------------------------------------------------

def collapse_segmented(instances: List[dict]) -> Tuple[List[dict], List[dict]]:
    """把 `R3` + `R3_2_res_gen` ... 折叠成**一个**逻辑器件。

    为什么必须先折叠：分段是工具自动生成的实现细节（一段串联电阻被拆成 11 个），
    若不折叠会出现两类错误：
      - 拓扑分析看到 11 个"器件"，匹配对判定会把相邻段误配成 matching_pair；
      - 变量数被虚高 10 倍，参数约减的收益也算不准。

    折叠后：
      - 返回的新器件名用链的**基准名**（有 `R3` 就用 `R3`，否则取名字最短的段）
      - 节点的两个端点取整条链的两个"外部端点"
      - 保留 base / segments 字段，便于在报告里说明折叠了哪些器件
    """
    chains: Dict[str, List[dict]] = {}
    plain: List[dict] = []
    for inst in instances:
        m = SEG_SUFFIX_RE.match(inst["name"])
        if m:
            chains.setdefault(m.group("base"), []).append(inst)
        else:
            plain.append(inst)

    collapsed: List[dict] = []
    for base, segs in sorted(chains.items()):
        byname = {i["name"]: i for i in segs}
        head = next((i for i in plain if i["name"] == base), None)
        all_seg = ([head] if head else []) + segs
        # 统计每个网在段器件里出现的次数，只出现 1 次的网是链的端点
        cnt: Dict[str, int] = {}
        for s in all_seg:
            for n in s["nodes"]:
                if n:
                    cnt[n] = cnt.get(n, 0) + 1
        endpoints = sorted([n for n, c in cnt.items() if c == 1])
        if len(endpoints) < 2:
            # 环或退化结构：按出现顺序取首尾
            seq = []
            for s in all_seg:
                for n in s["nodes"]:
                    if n and n not in seq:
                        seq.append(n)
            endpoints = [seq[0], seq[-1]] if len(seq) >= 2 else seq
        rep = head if head else min(all_seg, key=lambda i: (len(i["name"]), i["name"]))
        merged = dict(rep)
        merged["nodes"] = endpoints[:2] if len(endpoints) >= 2 else rep["nodes"]
        merged["kind"] = rep["kind"]
        merged["segmented"] = True
        merged["segments"] = [s["name"] for s in all_seg]
        merged["base_device"] = base
        merged["segment_count"] = len(segs)
        collapsed.append(merged)

    return plain + collapsed, collapsed


# ---------------------------------------------------------------------------
# 各模块识别规则
# ---------------------------------------------------------------------------

def _find_current_mirrors(moses: List[dict], log: list) -> List[dict]:
    """电流镜：同型 MOS，栅极同网 + 源极同网；栅漏短接者为参考管。"""
    out = []
    buckets: Dict[Tuple, List[dict]] = {}
    for m in moses:
        if _gate(m) is None or _source(m) is None:
            continue
        buckets.setdefault((_polarity(m), _gate(m), _source(m)), []).append(m)

    idx = 0
    for (pol, gate, src), group in sorted(buckets.items(), key=lambda kv: str(kv[0])):
        if len(group) < 2 or gate is None or src is None:
            continue
        # 参考管：组内二极管连接的；没有则取第一个
        refs = [g for g in group if _is_diode_connected(g)]
        ref = refs[0] if refs else group[0]
        others = [g for g in group if g is not ref]
        idx += 1
        rules = ["同型(%s)" % pol, "栅极同接 %s" % gate, "源极同接 %s" % src]
        if refs:
            rules.append("%s 栅漏短接 -> 参考管" % ref["name"])
        else:
            rules.append("组内无二极管连接，取 %s 为参考管" % ref["name"])
        out.append({
            "id": "CM%d" % idx,
            "type": "current_mirror",
            "devices": [g["name"] for g in ([ref] + others)],
            "reference_device": ref["name"],
            "mirrored_devices": [g["name"] for g in others],
            "polarity": pol,
            "shared_gate_net": gate,
            "shared_source_net": src,
            "confidence": 3 if refs else 2,
            "evidence": "；".join(rules),
            "notes": "",
        })
        log.append({
            "rule": "current_mirror",
            "targets": [g["name"] for g in group],
            "reason": "；".join(rules),
        })
    return out


def _find_input_pairs(moses: List[dict], log: list, warnings: list) -> List[dict]:
    """差分输入对：同型 MOS 源极同网，栅极分别是差分输入端口。

    判定严格性（对齐教程 11.2 的"结构优先、但要小心过拟合"）：
      1) **只有栅极接输入端口（VINP/VINN）的才判为 input_pair**；
      2) 栅极接两个独立信号网但源极同网的，记为"候选差分对"进 warnings，
         不占 input_pair 名额（避免把 CMFB 误差放大器误判成主输入对）。
    """
    out = []
    warnings_local = []
    buckets: Dict[Tuple, List[dict]] = {}
    for m in moses:
        if _source(m) is None:
            continue
        buckets.setdefault((_polarity(m), _source(m)), []).append(m)

    idx = 0
    for (pol, src), group in sorted(buckets.items(), key=lambda kv: str(kv[0])):
        if len(group) < 2:
            continue
        pair = None
        for a in group:
            for b in group:
                if a is b:
                    continue
                ga, gb = _gate(a), _gate(b)
                if ga and gb and ga != gb and INPUT_PORT_RE.search(ga) and INPUT_PORT_RE.search(gb):
                    pair = (a, b)
                    break
            if pair:
                break
        if pair is None:
            # 退一步：同型、源极同网、栅极独立且漏极不同 -> 记为候选，不判正式输入对
            for a in group:
                for b in group:
                    if a is b:
                        continue
                    if _gate(a) and _gate(b) and _gate(a) != _gate(b) and _drain(a) != _drain(b):
                        warnings_local.append(
                            "候选差分对 %s/%s（源极同网 %s，栅极 %s/%s）未接输入端口，"
                            "不判为 input_pair；若为次级的差分单元请在报告中说明"
                            % (a["name"], b["name"], src, _gate(a), _gate(b)))
                        break
                if warnings_local and warnings_local[-1].startswith("候选差分对 %s/" % a["name"]):
                    break
            continue

        idx += 1
        a, b = pair
        out.append({
            "id": "IP%d" % idx,
            "type": "input_pair",
            "devices": [a["name"], b["name"]],
            "polarity": pol,
            "shared_source_net": src,
            "gate_nets": [_gate(a), _gate(b)],
            "gate_nets_are_input_ports": True,
            "confidence": 3,
            "evidence": "；".join([
                "同型(%s)" % pol,
                "源极同接 %s（尾节点）" % src,
                "栅极分别接输入端口 %s / %s" % (_gate(a), _gate(b)),
                "漏极分别接 %s / %s" % (_drain(a), _drain(b)),
            ]),
            "notes": "",
        })
        log.append({
            "rule": "input_pair",
            "targets": [a["name"], b["name"]],
            "reason": "栅极接输入端口 %s/%s 且源极同网 %s -> 差分输入对"
                      % (_gate(a), _gate(b), src),
        })
    warnings.extend(warnings_local)
    return out


def _find_active_loads(mirrors: List[dict], pairs: List[dict], by_name: Dict[str, dict],
                       log: list) -> List[dict]:
    """有源负载：电流镜/二极管连接器件，其漏极接在输入对管漏极上（承担负载）。"""
    out = []
    pair_drains = set()
    pair_devices = set()
    for p in pairs:
        for d in p["devices"]:
            pair_devices.add(d)
            inst = by_name.get(d)
            if inst:
                dn = _drain(inst)
                if dn:
                    pair_drains.add(dn)

    idx = 0
    for cm in mirrors:
        loads = []
        for name in cm["devices"]:
            if name in pair_devices:
                continue
            inst = by_name.get(name)
            if inst and _drain(inst) in pair_drains:
                loads.append(name)
        if not loads:
            continue
        idx += 1
        out.append({
            "id": "AL%d" % idx,
            "type": "active_load",
            "devices": loads,
            "source_mirror": cm["id"],
            "connection_net": sorted({_drain(by_name[n]) for n in loads if by_name.get(n)}),
            "confidence": 2,
            "evidence": "；".join([
                "电流镜 %s 的器件" % cm["id"],
                "漏极接在输入对管漏极节点 %s 上" % sorted(pair_drains),
                "以有源器件替代电阻作负载，提高增益",
            ]),
            "notes": "",
        })
        log.append({
            "rule": "active_load",
            "targets": loads,
            "reason": "漏极接输入对管漏极 -> 承担负载功能",
        })
    return out


def _is_power(n: Optional[str]) -> bool:
    return n is not None and bool(POWER_RE.match(n))


def _is_port(n: Optional[str], ports: set) -> bool:
    return n is not None and n in ports


def _node_role(n: Optional[str], ports: set) -> str:
    """节点角色标签（用于结构指纹）。

    关键：**差分端口必须角色化**。若把 VINP/VINN 原样保留，两颗输入对管的
    结构指纹就会不同（一个含 VINP、一个含 VINN），导致配不上对。
    规则：
      - 电源/地：保留真实名（VDDA/VSS 不可互换）
      - 差分输入端口：VINP/VINN、INP/INN -> 统一为 'IN*'
      - 差分输出端口：VOUTP/VOUTN       -> 统一为 'OUT*'
      - 偏置端口（IREF/VCM/...）         -> 保留真实名
      - 其他内部节点                     -> 'N'
    """
    if n is None or n == "":
        return "NC"
    if _is_power(n):
        return n
    if INPUT_PORT_RE.search(n):
        return "IN*"
    if OUTPUT_PORT_RE.search(n):
        return "OUT*"
    if BIAS_RE.search(n):
        return n
    if _is_port(n, ports):
        return n
    return "N"


def _structure_fingerprint(inst: dict, ports: set) -> Tuple:
    """器件的**结构指纹**：同指纹 = 连接结构等价（与图上编号无关）。

    这是匹配器件判定的正确基础。**不能**用"尺寸参数值相等"来判——
    因为参数化后每个器件的尺寸都是独立变量（NM8_l vs NM9_l），永远配不上。
    正确判据 = 同 model + 同固定参数（multi）+ 连接结构等价。
    """
    kind = inst["kind"]
    model = inst.get("model")
    multi = inst.get("params", {}).get("multi") or inst.get("params", {}).get("m")
    if kind == "mos":
        struct = (
            tuple(sorted([_node_role(_drain(inst), ports), _node_role(_gate(inst), ports),
                          _node_role(_source(inst), ports), _node_role(_bulk(inst), ports)])),
            _is_diode_connected(inst),
        )
    else:
        struct = tuple(sorted(_node_role(n, ports) for n in inst["nodes"]))
    return (kind, model, multi) + struct


def _allowed_pairs(mirrors: List[dict], pairs: List[dict]) -> set:
    """由已识别的镜像组/输入对生成"允许配对"的器件对集合。

    为什么需要：结构等价的管子可能属于**不同支路**（如 PM0/PM1/PM4 属 net6 镜像、
    PM5/PM6 属 net5 镜像，四者结构相同）。若只按结构配对，会跨镜错配。
    尺寸绑定的正确前提是"这两个器件本来就在同一支路/同一差分对里"。
    """
    allowed = set()
    for m in mirrors + pairs:
        devs = m.get("devices", [])
        for i, a in enumerate(devs):
            for b in devs[i + 1:]:
                allowed.add(tuple(sorted((a, b))))
    return allowed


def _matching_candidates(instances: List[dict], ports: set,
                         allowed: Optional[set] = None) -> List[dict]:
    """在"同结构"的候选里分**连通簇**，再在簇内配对。

    为什么要分簇：同结构的管子可能来自不同电路支路。
    例：PM0/PM1/PM4 是 net6 电流镜，PM5/PM6 是 net5 电流镜，四者结构相同；
    若只按结构分组，可能把 PM0 与 PM5 跨镜配成一对（错）。
    正确做法：把"结构等价 + 源极同网 + 栅极同网"的器件聚成一簇（= 一条镜像支路），
    再在簇内的镜像管之间做尺寸绑定。
    """
    buckets: Dict[Tuple, List[dict]] = {}
    for inst in instances:
        if inst["kind"] not in ("mos", "res", "cap"):
            continue
        if len(inst["nodes"]) < 2:
            continue
        buckets.setdefault(_structure_fingerprint(inst, ports), []).append(inst)

    out: List[dict] = []
    for key, group in buckets.items():
        if len(group) < 2:
            continue                      # 关键修复：绝对不要自己跟自己配对
        kind = key[0]
        # 按名字去重（防止同一器件重复进池）
        pool = sorted({i["name"]: i for i in group}.values(), key=lambda i: i["name"])

        if kind == "mos":
            # --- 连通簇：源极同网 && 栅极同网 ---
            clusters: Dict[Tuple, List[dict]] = {}
            for m in pool:
                clusters.setdefault((_source(m), _gate(m)), []).append(m)
            used = set()
            for (src, gate), cl in sorted(clusters.items(), key=lambda kv: str(kv[0])):
                cl = [m for m in cl if m["name"] not in used]
                if len(cl) < 2:
                    continue
                # 星型绑定：第一个为基准管，其余镜像管都绑定到它（每个器件只归组一次）
                base, rest = cl[0], cl[1:]
                used.add(base["name"])
                for other in rest:
                    if allowed is not None and tuple(sorted((base["name"], other["name"]))) not in allowed:
                        continue
                    used.add(other["name"])
                    out.append({
                        "a": base, "b": other, "kind": kind,
                        "case": "same_branch",
                        "detail": "同一支路（源极同接 %s、栅极同接 %s）" % (src, gate),
                        "members_all": [i["name"] for i in cl],
                    })

            # --- 差分两臂：源极同网、栅极不同（且组内也只有这两个同结构器件）---
            by_src: Dict[Optional[str], List[dict]] = {}
            for m in pool:
                if m["name"] in used:
                    continue
                by_src.setdefault(_source(m), []).append(m)
            for src, grp in sorted(by_src.items(), key=lambda kv: str(kv[0])):
                if src is None or len(grp) != 2:      # 只处理干净的两臂结构
                    continue
                a, b = grp
                if _gate(a) == _gate(b):
                    continue
                if allowed is not None and tuple(sorted((a["name"], b["name"]))) not in allowed:
                    continue          # 不同支路的同结构管子，不配对
                used.add(a["name"])
                used.add(b["name"])
                out.append({
                    "a": a, "b": b, "kind": kind,
                    "case": "differential_arms",
                    "detail": "源极同接 %s 的差分两臂，栅极分别接 %s / %s"
                              % (src, _gate(a), _gate(b)),
                    "members_all": [a["name"], b["name"]],
                })
        else:
            # 两端器件：结构等价 + 共享节点 + **各自还有另一个端点**
            used = set()
            for i, a in enumerate(pool):
                if a["name"] in used:
                    continue
                for b in pool[i + 1:]:
                    if b["name"] in used or b["name"] == a["name"]:
                        continue
                    shared = [n for n in a["nodes"] if n and n in b["nodes"]]
                    if not shared:
                        continue
                    a_other = [n for n in a["nodes"] if n not in shared]
                    b_other = [n for n in b["nodes"] if n not in shared]
                    if not a_other or not b_other:
                        continue          # 两端接同一网的器件不参与匹配
                    if a_other == b_other:
                        continue          # 完全相同的两端连接 = 并联，不是对称对
                    used.add(a["name"])
                    used.add(b["name"])
                    out.append({
                        "a": a, "b": b, "kind": kind,
                        "case": "shared_node",
                        "detail": "同 model 且共享节点 %s，另一端分别接 %s / %s"
                                  % (shared, a_other, b_other),
                        "members_all": [x["name"] for x in pool],
                    })
                    break
    return out


def _find_matching_pairs(instances: List[dict], ports: set, log: list,
                         allowed: Optional[set] = None) -> List[dict]:
    """匹配器件：把"结构等价 + 同 model + 同 multi + 同一支路"的器件配对。"""
    out = []
    for idx, cand in enumerate(_matching_candidates(instances, ports, allowed), 1):
        a, b = cand["a"], cand["b"]
        why = "同 model(%s)、同 multi(%s)、%s" % (
            a.get("model"), a.get("params", {}).get("multi"), cand["detail"])
        out.append({
            "id": "MP%d" % idx,
            "type": "matching_pair",
            "devices": [a["name"], b["name"]],
            "kind": cand["kind"],
            "polarity": _polarity(a) if cand["kind"] == "mos" else "-",
            "match_rule": cand["case"],
            "group_members": cand["members_all"],
            "group_size": len(cand["members_all"]),
            "confidence": 3 if cand["case"] == "same_source" else 2,
            "evidence": "；".join([
                why,
                "-> 版图匹配要求尺寸绑定，共享同一组变量（只保留一个基准变量）",
            ]),
            "notes": "",
        })
        log.append({
            "rule": "matching_pair",
            "targets": [a["name"], b["name"]],
            "reason": why + " -> 尺寸绑定，只保留一组变量",
        })
    return out


def _find_dummies(instances: List[dict], all_nets: set, log: list,
                  warnings: list) -> Tuple[List[dict], List[dict]]:
    """Dummy 器件 / 两端短接器件，**分开判定**（这是赛题网表里的真实陷阱）。

    真 Dummy（应剔除变量）：
      - MOS 全端子接同一网（如 MD1 四端全接 VDD）；或
      - 所有端子所连的网都没出现在别的器件上（悬空）；或
      - 命名含 dummy/DMY 且有上述特征之一

    两端短接器件（**保留**，不是 dummy）：
      - R/C 两端接同一网在版图里常见：电容=寄生/去耦，电阻=参考电阻
      - 若把它当 dummy 删掉会**误删真实器件的变量**，因此在报告里单独列出
    """
    dummies, tied = [], []
    idx = 0
    tidx = 0
    for inst in instances:
        reasons = []
        if _is_all_terminals_same(inst):
            if inst["kind"] == "mos":
                reasons.append("MOS 全部端子都接在同一网 %s（不可能正常工作）"
                               % inst["nodes"][0])
            else:
                tidx += 1
                tied.append({
                    "id": "TIE%d" % tidx,
                    "type": "two_terminal_shorted",
                    "devices": [inst["name"]],
                    "kind": inst["kind"],
                    "net": inst["nodes"][0],
                    "confidence": 2,
                    "evidence": "两端器件 %s 的两个端子都接在 %s 上 -> 电气上短路；"
                                "版图里常见于寄生/去耦电容或参考电阻，**保留其变量**，"
                                "但需在报告中说明为何保留" % (inst["name"], inst["nodes"][0]),
                    "notes": "不是 Dummy，不应删除",
                })
                warnings.append(
                    "%s 两端接同一网（%s）：按『真实器件』保留变量，请在报告说明其作用"
                    % (inst["name"], inst["nodes"][0]))
                continue
        if len(inst["nodes"]) >= 2 and _all_terminals_dangling(inst, all_nets):
            reasons.append("所有端子所连的网均未出现在其他器件上（悬空）")
        if DUMMY_NAME_RE.search(inst["name"]) and reasons:
            reasons.append("命名也符合 Dummy 特征")
        if not reasons:
            continue
        idx += 1
        dummies.append({
            "id": "DM%d" % idx,
            "type": "dummy",
            "devices": [inst["name"]],
            "kind": inst["kind"],
            "confidence": 3 if len(reasons) > 1 else 2,
            "evidence": "；".join(reasons) + " -> 不参与电路功能，可剔除其优化变量",
            "notes": "",
        })
        log.append({
            "rule": "dummy",
            "targets": [inst["name"]],
            "reason": reasons[0] + " -> 剔除其全部优化变量",
        })
    return dummies, tied


def _find_cmfb(instances: List[dict], all_nets: set, log: list) -> List[dict]:
    """共模反馈：出现 outaverage/vcmfb 类节点，或存在检测两路输出的电阻分压网络。"""
    out = []
    cmfb_nets = sorted(n for n in all_nets if CMFB_RE.search(n))
    if not cmfb_nets:
        return out

    # 找出接到这些节点上的器件
    members = []
    for inst in instances:
        if any(n in cmfb_nets for n in inst["nodes"]):
            members.append(inst["name"])

    # 检测电阻分压网络：两个同 model 电阻，各自接一个输出端，另一端共接
    res = [i for i in instances if i["kind"] == "res"]
    divider = []
    for i, a in enumerate(res):
        for b in res[i + 1:]:
            if a.get("model") != b.get("model"):
                continue
            na, nb = set(n for n in a["nodes"] if n), set(n for n in b["nodes"] if n)
            shared = na & nb
            outs_a = [n for n in na if OUTPUT_PORT_RE.search(n)]
            outs_b = [n for n in nb if OUTPUT_PORT_RE.search(n)]
            if shared and outs_a and outs_b:
                divider.append((a["name"], b["name"], sorted(shared)[0], outs_a[0], outs_b[0]))

    evidence = ["检测到共模相关节点: %s" % cmfb_nets]
    if divider:
        a, b, mid, oa, ob = divider[0]
        evidence.append("电阻分压网络 %s/%s：从 %s 与 %s 取平均到 %s" % (a, b, oa, ob, mid))
    evidence.append("涉及器件 %d 个：%s" % (len(members), members[:12]))
    evidence.append("作用：稳定全差分输出的共模电平")

    out.append({
        "id": "CMFB1",
        "type": "cmfb",
        "devices": members,
        "cmfb_nets": cmfb_nets,
        "sense_divider": divider,
        "confidence": 3 if divider else 2,
        "evidence": "；".join(evidence),
        "notes": "",
    })
    log.append({
        "rule": "cmfb",
        "targets": cmfb_nets,
        "reason": "存在共模检测节点/分压网络，判为共模反馈结构",
    })
    return out


def _find_bias_branches(instances: List[dict], all_nets: set, log: list) -> List[dict]:
    """偏置支路：由偏置端口（IREF/IBIAS/VREF...）直接驱动的器件。"""
    bias_nets = sorted(n for n in all_nets if BIAS_RE.search(n))
    devices = []
    for inst in instances:
        gates = [_gate(inst)] if inst["kind"] == "mos" else []
        for n in inst["nodes"]:
            if n in bias_nets and (n in gates or inst["kind"] in ("isrc", "vsrc")):
                devices.append(inst["name"])
                break
    if not devices and not bias_nets:
        return []
    log.append({
        "rule": "bias_branch",
        "targets": devices or bias_nets,
        "reason": "由偏置端口 %s 驱动" % bias_nets,
    })
    return [{
        "id": "BIAS1",
        "type": "bias_branch",
        "devices": sorted(set(devices)),
        "bias_nets": bias_nets,
        "confidence": 2,
        "evidence": "偏置节点 %s 直接驱动 %d 个器件（栅极或独立源），构成参考偏置支路"
                    % (bias_nets, len(set(devices))),
        "notes": "",
    }]


def _find_segmented(instances: List[dict], log: list) -> List[dict]:
    """自动分段器件归并：`R3` + `R3_2_res_gen` ... 实为**同一个物理器件的多段串联**。

    这是赛题网表里真实存在的结构，若不归并会被当成十几个独立器件/变量。
    """
    groups: Dict[str, List[dict]] = {}
    for inst in instances:
        m = SEG_SUFFIX_RE.match(inst["name"])
        if m:
            groups.setdefault(m.group("base"), []).append(inst)

    out = []
    idx = 0
    by_name = {i["name"]: i for i in instances}
    for base, segs in sorted(groups.items()):
        head = by_name.get(base)
        members = ([head] if head else []) + [s for s in segs]
        idx += 1
        out.append({
            "id": "SEG%d" % idx,
            "type": "segmented_device",
            "devices": [m["name"] for m in members],
            "base_device": base if head else None,
            "segment_count": len(segs),
            "confidence": 3,
            "evidence": "；".join([
                "器件 %s 被自动拆分为 %d 段串联（后缀 _<n>_res_gen）" % (base, len(segs)),
                "参数完全相同（同一物理器件的分段实现）",
                "-> 应视为**一个**器件，只保留一组变量",
            ]),
            "notes": "",
        })
        log.append({
            "rule": "segmented_device",
            "targets": [m["name"] for m in members],
            "reason": "同一物理器件被拆成 %d 段，只保留一组变量" % len(segs),
        })
    return out


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def analyze_topology(net: dict, subckt_name: Optional[str] = None) -> dict:
    """对网表做拓扑模块识别。

    返回结构见 ../CONTRACTS.md 第 2.3 节。
    """
    from netlist_parser import find_subckt

    if subckt_name:
        sc = find_subckt(net, subckt_name)
        if sc is None:
            raise ValueError("找不到 subckt: %s" % subckt_name)
    else:
        if not net.get("subckts"):
            raise ValueError("网表里没有 subckt")
        sc = net["subckts"][0]

    instances = sc["instances"]

    log: List[dict] = []
    warnings: List[str] = []

    # ---- 预处理：先把自动分段器件折叠成一个逻辑器件 ----
    analysis_set, collapsed = collapse_segmented(instances)
    if collapsed:
        for c in collapsed:
            log.append({
                "rule": "collapse_segmented",
                "targets": c["segments"],
                "reason": "自动分段器件 %s 共 %d 段折叠为 1 个逻辑器件（2 个外部端点 %s）"
                          % (c["name"], c["segment_count"], c["nodes"]),
            })

    moses = _moses(analysis_set)
    by_name = {i["name"]: i for i in analysis_set}

    # 统计所有"被使用过"的网（用于判悬空）—— 用折叠前的全集，更准确
    net_count: Dict[str, int] = {}
    for inst in instances:
        for n in inst["nodes"]:
            if n:
                net_count[n] = net_count.get(n, 0) + 1
    all_nets = set(net_count)
    # 出现 >= 2 次的网才算"参与连接"
    known_nets = {n for n, c in net_count.items() if c >= 2}

    mirrors = _find_current_mirrors(moses, log)
    pairs = _find_input_pairs(moses, log, warnings)
    loads = _find_active_loads(mirrors, pairs, by_name, log)
    matches = _find_matching_pairs(analysis_set, set(sc["ports"]), log,
                                   _allowed_pairs(mirrors, pairs))
    dummies, tied = _find_dummies(analysis_set, known_nets, log, warnings)
    cmfb = _find_cmfb(analysis_set, all_nets, log)
    bias = _find_bias_branches(analysis_set, all_nets, log)
    segs = _find_segmented(instances, log)

    modules = mirrors + pairs + loads + matches + dummies + tied + cmfb + bias + segs

    # 器件角色反查
    device_roles: Dict[str, List[str]] = {}
    for m in modules:
        for d in m["devices"]:
            device_roles.setdefault(d, []).append(m["type"])

    # 变量映射（约减前：每个器件一组变量）
    var_map: Dict[str, Dict[str, str]] = {}
    for inst in analysis_set:
        for v in inst.get("variables", []):
            var_map.setdefault(inst["name"], {})[v["name"]] = v["name"]

    by_type: Dict[str, int] = {}
    for m in modules:
        by_type[m["type"]] = by_type.get(m["type"], 0) + 1

    stats = {
        "subckt": sc["name"],
        "ports": sc["ports"],
        "n_instances": len(instances),
        "n_instances_collapsed": len(analysis_set),
        "n_segmented_collapsed": len(collapsed),
        "n_mos": len(moses),
        "by_kind": {k: sum(1 for i in analysis_set if i["kind"] == k)
                    for k in sorted({i["kind"] for i in analysis_set})},
        "by_type": dict(sorted(by_type.items())),
        "n_variables_before": sum(len(i.get("variables", [])) for i in analysis_set),
        "n_variables_raw": sum(len(i.get("variables", [])) for i in instances),
        "n_nets": len(all_nets),
        "vdd_nets": sorted(n for n in all_nets if POWER_RE.search(n)),
    }

    return {
        "modules": modules,
        "stats": stats,
        "device_roles": {k: sorted(set(v)) for k, v in sorted(device_roles.items())},
        "var_map": var_map,
        "decision_log": log,
        "warnings": warnings,
    }
