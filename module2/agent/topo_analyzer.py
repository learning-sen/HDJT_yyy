# -*- coding: utf-8 -*-
"""
模块二 · 第 2 层：拓扑模块识别 + 参数约减（确定性规则，不调用大模型）

设计原则：**结构判定必须可复现，大模型只负责"讲道理"**。
本文件给出结论（哪些是电流镜、哪些是匹配管、删掉哪些变量），
agent.py 再让大模型基于这些事实生成"为什么这么做"的说明文字。

识别用的四条证据链（全部来自网表本身，不依赖器件命名）：
  E1 端口/网表事实：端子连接、器件 model、参数取值
  E2 电气判据：二极管接法、两端同网、共栅共源
  E3 镜像置换 σ 传播：从差分对/输出对/CMFB 差分对三个种子出发，
     求网表的镜像自同构 σ，满足 σ(d1)=d2 的器件对即严格对称的匹配器件
  E4 功能网络：CMFB 取样网络（电阻割点）、米勒补偿支路、偏置链

参数约减规则：
  R1 Dummy（两端同网）      -> 尺寸参数移出优化变量（固定）
  R2 同名变量（串联分段）    -> 天然共享，归入同一组
  R3 镜像对称对（σ 配对）    -> 共享 w/l（或 segL/segW、l）
  R4 电流镜组（共栅共源）    -> 参考管与镜像管共享 w/l，比值由 m 承担
  注：m（Multiplier）与 seg 是**整数比值旋钮**，不合并，逐管保留。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from netlist_parser import Circuit, Device, IDENT_RE

# 参与合并的尺寸参数（不含 m / multi —— 它们是比值旋钮）
MERGE_PARAMS = ("w", "l", "segL", "segW", "r", "c")

# 镜像对称对（σ 配对）必须**完全一致**，包括 m：
# 差分对/对称支路两侧的 multiplier 不等会直接破坏对称性、恶化失调与 CMRR。
# 注意这和"电流镜比值旋钮"是两回事：后者由 MERGE_PARAMS 控制，m 保持独立。
PAIR_MERGE_PARAMS = MERGE_PARAMS + ("m", "multi", "seg", "nf")

# 电源/地网络：不参与极性判定
RAILS = {"0", "gnd!", "gnda", "gnd", "vdda", "vdd", "vssa", "vss", "sub"}

INTEGER_PARAMS = {"m", "multi", "seg", "nf"}
UNIT_BY_PARAM = {"w": "m", "l": "m", "segL": "m", "segW": "m", "r": "Ohm",
                 "c": "F", "m": "-", "multi": "-", "seg": "-"}


# ---------- 小工具 ----------

def _natkey(s: str):
    """自然排序键：NM2 < NM13（字符串排序会把 NM13 排到 NM2 前面）。"""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def _const_params(d: Device) -> dict:
    """器件上"真正的常量参数"，用于判断两台器件是不是同一种画法。

    注意：MOS 的 ad/as/pd/ps/nrd/nrs/sa/sb 是**派生表达式**，
    里面嵌了本器件自己的变量名（如 NM6_fw），逐字比较会把所有 MOS 都判成不同款，
    所以这里把"值引用了本器件变量"的参数一律排除，只留纯常量
    （multi / sca / trise / option_vop ...）以及常量尺寸（如电容 w=30u、m=2）。
    """
    varnames = set(d.variables.values())
    out = {}
    for k, v in d.params.items():
        if IDENT_RE.match(v):          # 裸标识符 = 变量本身，跳过
            continue
        if any(re.search(r"\b" + re.escape(vn) + r"\b", v) for vn in varnames):
            continue                   # 派生表达式，跳过
        out[k] = v
    return out


def _same_style(a: Device, b: Device) -> bool:
    return (a.model == b.model
            and a.size_suffix_set() == b.size_suffix_set()
            and _const_params(a) == _const_params(b))


def _orderings(d: Device):
    """两端器件的两个端子顺序无关，允许交换。"""
    yield d.nets
    if len(d.nets) == 2:
        yield (d.nets[1], d.nets[0])


class UnionFind:
    def __init__(self):
        self.p: dict = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


# ---------- 主分析 ----------

def analyze(c: Circuit) -> dict:
    from netlist_parser import parse_netlist  # noqa: F401  (供外部 import 兼容)

    devs = c.devices
    mos = [d for d in devs if d.kind in ("nmos", "pmos")]
    twoterm = [d for d in devs if d.kind in ("res", "cap")]

    # ================= E2：基础电气判据 =================
    dummies = [d for d in devs if d.is_two_terminal_shorted()]
    dummy_names = {d.name for d in dummies}
    diode = [d for d in mos if d.is_diode_connected()]

    # ================= E4-1：CMFB 取样网络（电阻图割点） =================
    res_adj: dict[str, set[str]] = {}
    res_devs = [d for d in twoterm if d.kind == "res" and d.name not in dummy_names]
    for d in res_devs:
        res_adj.setdefault(d.nets[0], set()).add(d.nets[1])
        res_adj.setdefault(d.nets[1], set()).add(d.nets[0])

    def res_reach(start: str, blocked: str | None = None) -> set[str]:
        seen, stack = {start}, [start]
        while stack:
            for nb in res_adj.get(stack.pop(), ()):
                if nb == blocked or nb in seen:
                    continue
                seen.add(nb)
                stack.append(nb)
        return seen

    # 输出端口对：接了电容、且不是电源地的端口
    cap_nets = set()
    for d in twoterm:
        if d.kind == "cap" and d.name not in dummy_names:
            cap_nets.update(d.nets)
    out_ports = [p for p in c.ports if p.lower() not in RAILS and p in cap_nets]
    out_pair = tuple(out_ports[:2]) if len(out_ports) >= 2 else None

    # 共模检测点 = 电阻链上的交汇节点
    # 判据（两条同时满足）：
    #   ① 割点：去掉它之后，两个输出端口在纯电阻图上不再连通
    #   ② 有非电阻支路：该节点还接了电容或 MOS 栅极（否则只是电阻链中间的普通节点）
    # 只满足①的节点在"两条链串联"的结构里有十几个，必须靠②把它挑出来。
    res_dev_names = {d.name for d in res_devs}
    nonres_nets: dict[str, list[str]] = {}
    for d in devs:
        if d.name in res_dev_names or d.name in dummy_names:
            continue
        for n in d.nets:
            nonres_nets.setdefault(n, []).append(d.name)

    cm_sense = None
    candidates: list[str] = []
    if out_pair:
        a, b = out_pair
        candidates = [n for n in res_reach(a)
                      if n != b and n.lower() not in RAILS
                      and b not in res_reach(a, blocked=n)
                      and nonres_nets.get(n)]
        if len(candidates) == 1:
            cm_sense = candidates[0]

    # ================= 电流镜组（E2：同类型 + 同栅 + 同源） =================
    mirror_groups: list[dict] = []
    buckets: dict[tuple, list[Device]] = {}
    for d in mos:
        if d.name in dummy_names:
            continue
        m = d.net_map
        buckets.setdefault((d.kind, m["g"], m["s"]), []).append(d)
    for (kind, gate, src), members in buckets.items():
        if len(members) < 2:
            continue
        refs = [x for x in members if x.is_diode_connected()]
        mirror_groups.append({
            "type": "current_mirror",
            "name_zh": "NMOS 电流镜" if kind == "nmos" else "PMOS 电流镜",
            "kind": kind, "gate": gate, "source": src,
            "reference": refs[0].name if refs else None,
            "devices": [x.name for x in members],
            "evidence": (f"{kind} 管栅极同为 {gate}、源极同为 {src}，共 {len(members)} 管；"
                         + (f"其中 {refs[0].name} 栅漏短接，是参考管；" if refs else "无二极管接法参考管；")
                         + "其余各管复制参考电流，比值由 m 决定"),
        })

    # ================= 输入差分对（E1/E2） =================
    ports_lc = {p.lower() for p in c.ports}
    input_pair = None
    for i, a in enumerate(mos):
        for b in mos[i + 1:]:
            if a.kind != b.kind or a.name in dummy_names or b.name in dummy_names:
                continue
            ma, mb = a.net_map, b.net_map
            if ma["s"] != mb["s"] or ma["s"].lower() in RAILS:
                continue
            ga, gb = ma["g"], mb["g"]
            if ga == gb or ga.lower() not in ports_lc or gb.lower() not in ports_lc:
                continue
            input_pair = (a, b)
            break
        if input_pair:
            break

    # ================= E3：镜像置换 σ 传播 =================
    sigma: dict[str, str] = {}
    conflicts: list[str] = []

    def bind(x: str, y: str) -> bool:
        if x in sigma and sigma[x] != y:
            conflicts.append(f"{x} 已映射到 {sigma[x]}，又与 {y} 冲突")
            return False
        if y in sigma and sigma[y] != x:
            conflicts.append(f"{y} 已映射到 {sigma[y]}，又与 {x} 冲突")
            return False
        sigma[x] = y
        sigma[y] = x
        return True

    def smap(n: str) -> str:
        return sigma.get(n, n)

    def find_pair(d: Device, pool: list[Device], paired: set[str]):
        """找一个且仅一个镜像伙伴。
        判据：端子逐位对应，未登记的网作为新映射写入；
        且**至少有一对端子是已被 σ 锚定的差异**（防止把两个无关同型管配成对）。
        """
        hits = []
        for e in pool:
            if e.name == d.name or e.name in paired or e.name in dummy_names:
                continue
            if not _same_style(d, e):
                continue
            for nets_e in _orderings(e):
                # 重复端子模式必须一致：栅漏短接的自环结构只能映射到自环结构，
                # 否则 (net5,net5,VDDA,VDDA) 会与 (vcmfb,net5,VDDA,VDDA) 误配成对称对。
                if len(set(d.nets)) != len(set(nets_e)):
                    continue
                new, anchored, ok = [], 0, True
                for xn, yn in zip(d.nets, nets_e):
                    if xn == yn:
                        continue
                    if xn in sigma:
                        if sigma[xn] != yn:
                            ok = False
                            break
                        anchored += 1
                    elif yn in sigma:
                        if sigma[yn] != xn:
                            ok = False
                            break
                        anchored += 1
                    else:
                        new.append((xn, yn))
                if ok and anchored >= 1:
                    hits.append((e, new))
                    break
        return hits[0] if len(hits) == 1 else None

    pairing: list[tuple[str, str]] = []
    paired: set[str] = set()

    def seed(a: Device, b: Device, note: str):
        ma, mb = a.net_map, b.net_map
        for k in ma:
            if k in mb:
                bind(ma[k], mb[k])
        pairing.append((a.name, b.name))
        paired.update((a.name, b.name))
        return note

    seeds = []
    if input_pair:
        seed(*input_pair, "差分输入对")
        seeds.append("差分输入对 " + "/".join(x.name for x in input_pair))
    if out_pair:
        bind(out_pair[0], out_pair[1])
        seeds.append(f"输出端口对 {out_pair[0]}/{out_pair[1]}")

    # CMFB 差分对：共源、一栅为基准端口、另一栅为共模检测点
    cmfb_pair = None
    if cm_sense:
        for i, a in enumerate(mos):
            for b in mos[i + 1:]:
                if a.kind != b.kind or a.name in dummy_names or b.name in dummy_names:
                    continue
                ma, mb = a.net_map, b.net_map
                if ma["s"] != mb["s"] or ma["s"].lower() in RAILS:
                    continue
                gs = {ma["g"], mb["g"]}
                if cm_sense in gs and any(
                        g.lower() in ports_lc and g.lower() not in RAILS
                        for g in gs if g != cm_sense):
                    cmfb_pair = (a, b)
                    break
            if cmfb_pair:
                break
    if cmfb_pair:
        seed(*cmfb_pair, "CMFB 误差放大器差分对")
        seeds.append("CMFB 差分对 " + "/".join(x.name for x in cmfb_pair))

    # 迭代到不动点（MOS 与两端器件统一处理）
    for _ in range(len(devs) + 5):
        changed = False
        for pool in (mos, twoterm):
            for d in list(pool):
                if d.name in paired or d.name in dummy_names:
                    continue
                hit = find_pair(d, pool, paired)
                if not hit:
                    continue
                e, new = hit
                if all(bind(x, y) for x, y in new):
                    pairing.append((d.name, e.name))
                    paired.update((d.name, e.name))
                    changed = True
        if not changed:
            break

    # ================= 串联分段：共用同一组变量名 =================
    var_shared: dict[str, list[str]] = {}
    for d in devs:
        for v in d.var_names:
            var_shared.setdefault(v, []).append(d.name)
    segment_groups = {v: ns for v, ns in var_shared.items() if len(ns) > 1}

    # ================= 功能模块清单 =================
    modules: list[dict] = []
    if dummies:
        modules.append({
            "id": "D1", "type": "dummy", "name_zh": "Dummy 器件（两端短接）",
            "devices": [d.name for d in dummies],
            "evidence": "两端接同一节点：" + "、".join(
                f"{d.name}({d.nets[0]},{d.nets[1]})" for d in dummies)
                + "。电气上不构成通路，对任何性能指标无贡献，其尺寸参数应从优化变量中剔除",
        })
    for i, g in enumerate(mirror_groups, 1):
        g["id"] = f"CM{i}"
        modules.append(g)
    if input_pair:
        a, b = input_pair
        modules.append({
            "id": "IN1", "type": "input_pair", "name_zh": "输入差分对",
            "devices": [a.name, b.name],
            "evidence": (f"{a.name}/{b.name} 同型号 {a.model}，源极共接 {a.net_map['s']}，"
                         f"栅极分别接输入端口 {a.net_map['g']}/{b.net_map['g']}；"
                         f"构成差分输入对，两管必须严格匹配（失配直接恶化失调与 CMRR）"),
        })
        tail = [d for d in mos if d.name not in dummy_names
                and d.name not in (a.name, b.name) and a.net_map["s"] in d.nets]
        if tail:
            modules.append({
                "id": "T1", "type": "tail_current_source", "name_zh": "尾电流源",
                "devices": [x.name for x in tail],
                "evidence": f"{tail[0].name} 漏极接差分对公共源 {a.net_map['s']}，为输入对提供尾电流",
            })
    if out_pair:
        outs = [d for d in mos if d.name not in dummy_names and d.nets[0] in out_pair]
        if outs:
            modules.append({
                "id": "O1", "type": "output_stage", "name_zh": "输出级",
                "devices": [d.name for d in outs],
                "evidence": f"漏极直接驱动输出端口 {out_pair[0]}/{out_pair[1]}",
            })
    if cm_sense:
        net_devs = [d for d in devs if cm_sense in d.nets and d.name not in dummy_names]
        chain = [d for d in res_devs if d.name in
                 (res_reach(out_pair[0]) | res_reach(out_pair[1]))]
        modules.append({
            "id": "FB1", "type": "cmfb", "name_zh": "共模反馈网络（CMFB）",
            "devices": [d.name for d in net_devs],
            "evidence": (f"取样：从 {out_pair[0]}/{out_pair[1]} 各经一条纯电阻链在 "
                         f"{cm_sense} 汇合，{cm_sense} 是电阻图上分开两个输出的割点，"
                         f"链上共 {len(chain)} 段电阻；"
                         + (f"误差放大差分对 {cmfb_pair[0].name}/{cmfb_pair[1].name} 的栅极分别为 "
                            f"{cmfb_pair[0].net_map['g']}/{cmfb_pair[1].net_map['g']}；"
                            if cmfb_pair else "")
                         + f"与 {cm_sense} 直连的器件 {len(net_devs)} 个"),
        })
    if pairing:
        modules.append({
            "id": "MB1", "type": "matching", "name_zh": "匹配结构（镜像置换 σ）",
            "devices": sorted({n for p in pairing for n in p}, key=_natkey),
            "evidence": "由差分对/输出对/CMFB 差分对建立网表镜像置换 σ，"
                        "满足 σ(d1)=d2 的器件对结构严格对称 -> 尺寸必须一致；配对结果："
                        + "，".join(f"{a}={b}" for a, b in pairing),
        })

    # ================= 参数约减 =================
    uf = UnionFind()
    for d in devs:
        for p in d.variables:
            uf.find((d.name, p))
    # R2：同名变量天然共享（电阻分段）
    for v, names in var_shared.items():
        first = None
        for n in names:
            dd = c.by_name(n)
            if not dd:
                continue
            for p, vv in dd.variables.items():
                if vv != v:
                    continue
                key = (n, p)
                if first is None:
                    first = key
                else:
                    uf.union(first, key)
    # R3：镜像对称对完全共享尺寸（含 m）
    pair_notes: dict[str, list[str]] = {}
    for a, b in pairing:
        da, db = c.by_name(a), c.by_name(b)
        if not da or not db:
            continue
        for p in PAIR_MERGE_PARAMS:
            if p in da.variables and p in db.variables:
                uf.union((da.name, p), (db.name, p))
        pair_notes.setdefault(a, []).append(b)
        pair_notes.setdefault(b, []).append(a)
    # R4：电流镜组内共享 w/l
    for g in mirror_groups:
        members = [m for m in (c.by_name(n) for n in g["devices"]) if m]
        for p in ("w", "l"):
            anchor = next((m for m in members if p in m.variables), None)
            if not anchor:
                continue
            for m in members:
                if p in m.variables:
                    uf.union((anchor.name, p), (m.name, p))

    groups: dict[tuple, list[tuple]] = {}
    for d in devs:
        if d.name in dummy_names:
            continue
        for p, v in d.variables.items():
            groups.setdefault(uf.find((d.name, p)), []).append((d.name, p, v))

    reduced: list[dict] = []
    rename: dict[str, str] = {}
    for root, items in groups.items():
        names = sorted({v for _, _, v in items}, key=_natkey)
        canon = names[0]
        for _, _, v in items:
            rename[v] = canon
        reduced.append({
            "var": canon,
            "param": items[0][1],
            "devices": sorted({n for n, _, _ in items}, key=_natkey),
            "merged_from": names,
            "kind": "integer" if items[0][1] in INTEGER_PARAMS else "continuous",
            "unit": UNIT_BY_PARAM.get(items[0][1], "-"),
        })
    reduced.sort(key=lambda r: _natkey(r["var"]))

    fixed_vars = [{"var": v, "param": p, "device": d.name,
                   "reason": "Dummy 器件两端短接，对性能无影响"}
                  for d in dummies for p, v in d.variables.items()]

    by_cat: dict[str, int] = {}
    for r in reduced:
        k = "整数(m)" if r["kind"] == "integer" else r["param"]
        by_cat[k] = by_cat.get(k, 0) + 1

    return {
        "subckt": c.subckt, "ports": c.ports, "device_count": len(devs),
        "raw_variable_count": len(c.all_variables), "raw_variables": c.all_variables,
        "modules": modules, "mirror_groups": mirror_groups,
        "pairing": [{"a": a, "b": b} for a, b in pairing],
        "seeds": seeds, "sigma_conflicts": conflicts,
        "segment_groups": segment_groups,
        "dummies": [d.name for d in dummies],
        "diode_connected": [d.name for d in diode],
        "cm_sense_node": cm_sense,
        "output_pair": list(out_pair) if out_pair else [],
        "reduced_variable_count": len(reduced),
        "reduced_variables": reduced,
        "reduced_by_category": by_cat,
        "fixed_variables": fixed_vars,
        "rename_map": rename,
        "pair_notes": pair_notes,
    }


# ---------- 约减后网表输出 ----------

def emit_reduced_netlist(c: Circuit, res: dict) -> str:
    rename = res["rename_map"]
    dummy_names = set(res["dummies"])
    merged_note: dict[str, list[str]] = {}
    for r in res["reduced_variables"]:
        if len(r["devices"]) > 1:
            for n in r["devices"]:
                merged_note.setdefault(n, []).append(r["var"])

    pat = None
    if rename:
        pat = re.compile(r"\b(" + "|".join(
            re.escape(k) for k in sorted(rename, key=len, reverse=True)) + r")\b")

    def sub_tokens(t: str) -> str:
        return pat.sub(lambda m: rename[m.group(1)], t) if pat else t

    L = []
    L.append("// ==================================================================")
    L.append(f"// {c.subckt} —— 参数约减后网表（模块二自动生成，可直接用于后续仿真）")
    L.append(f"// 原始优化变量 {res['raw_variable_count']}  ->  约减后 {res['reduced_variable_count']}")
    L.append("//")
    L.append("// 【变量账目】重新解析本网表会数出 "
             f"{res['reduced_variable_count'] + len(res['fixed_variables'])} 个符号，其中：")
    L.append(f"//     优化变量 {res['reduced_variable_count']} 个  <- 交给优化算法"
             "（见 var_reduction.csv / param_list_reduced.txt）")
    L.append(f"//     固定符号 {len(res['fixed_variables'])} 个  <- Dummy 器件，电气无效，"
             "保留符号只为让仿真能读到初值，不参与优化")
    L.append("//")
    L.append("// 标记：[MERGED] 尺寸已与镜像对称器件合并为同一变量；")
    L.append("//       [DUMMY]  两端短接器件，尺寸不参与优化（保留符号供仿真读取初值）")
    L.append("// ==================================================================")
    L.append("")
    L.append("simulator lang = spectre")
    L.append("")
    L.append(f"subckt {c.subckt} ({' '.join(c.ports)})")
    L.append("parameters")
    for d in c.devices:
        body = " ".join(f"{k}={sub_tokens(v)}" for k, v in d.params.items())
        notes = []
        if d.name in dummy_names:
            notes.append("DUMMY")
        if merged_note.get(d.name):
            notes.append("MERGED:" + ",".join(sorted(set(merged_note[d.name]), key=_natkey)))
        tail = ("  // " + " ".join(notes)) if notes else ""
        L.append(f"{d.name} ({' '.join(d.nets)}) {d.model} {body}{tail}")
        L.append("")
    L.append(f"ends {c.subckt}")
    return "\n".join(L) + "\n"


# ---------- 自测 ----------

if __name__ == "__main__":
    import sys
    from pathlib import Path
    from netlist_parser import parse_netlist

    default = (Path(__file__).resolve().parents[2] / "extracted" / "赛题数据本身"
               / "netlist" / "OPA_loopgain.netlist")
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else default
    cir = parse_netlist(target)
    r = analyze(cir)

    print(f"子电路          : {r['subckt']}  网表器件 {r['device_count']} 个")
    print(f"原始优化变量    : {r['raw_variable_count']}")
    print(f"约减后优化变量  : {r['reduced_variable_count']}"
          f"   （约减 {r['raw_variable_count'] - r['reduced_variable_count']} 个，"
          f"{100 * (1 - r['reduced_variable_count'] / r['raw_variable_count']):.1f}%）")
    print(f"分类            : {r['reduced_by_category']}")
    print(f"σ 种子          : {r['seeds']}")
    print(f"Dummy           : {r['dummies']}")
    print(f"二极管接法      : {r['diode_connected']}")
    print(f"输出端口对      : {r['output_pair']}    共模检测点: {r['cm_sense_node']}")
    print(f"σ 冲突          : {r['sigma_conflicts'] or '无'}")
    print("=" * 72)
    for m in r["modules"]:
        print(f"[{m['id']:<4}] {m['name_zh']}  ({m['type']})")
        print(f"       器件：{', '.join(m['devices'])}")
        print(f"       依据：{m['evidence']}")
        print()
    print("=" * 72)
    print("镜像对称配对：")
    for p in r["pairing"]:
        print(f"   {p['a']:<8} = {p['b']}")
    print("=" * 72)
    print("约减后变量清单：")
    for v in r["reduced_variables"]:
        tag = "整数" if v["kind"] == "integer" else "连续"
        src = f"   <- {','.join(v['merged_from'])}" if len(v["merged_from"]) > 1 else ""
        print(f"   {v['var']:<12} {tag}  {v['unit']:<5} {','.join(v['devices'])}{src}")
