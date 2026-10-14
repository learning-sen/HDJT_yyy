# -*- coding: utf-8 -*-
"""
模块二 · 第 2 层：拓扑模块识别 + 参数约减（确定性规则，不调用大模型）

设计原则：**结构判定必须可复现，大模型只负责"讲道理"**。
本文件给出结论（哪些是电流镜、哪些是匹配管、删掉哪些变量），
agent.py 再让大模型基于这些事实生成"为什么这么做"的说明文字。

==================================================================
2026-10-14 修正说明（初版有 4 处问题，全部已修，并有自检断言兜底）
==================================================================
F1 关系分离：初版用一个 σ 同时承担"图对称"和"工艺匹配"两种语义。
   CMFB 差分对（PM12/PM8）的栅极是 outaverage 与 VCM —— 这是**匹配**要求
   （误差放大器输入对必须一致），**不是**图对称（VCM 是基准输入、outaverage
   是取样节点，二者不可互换）。它被当成 σ 的种子后强制 σ(VCM)=outaverage；
   再经 NM11↔NM10 这一对强制 σ(net5)=vcmfb（net5 上挂着二极管接法的 PM5，
   vcmfb 上没有对应器件），于是 PM5/PM6/PM2/PM3/R0/R3/C2/C3 在 σ 下都找不到
   镜像对象 —— σ 已经不是自同构了，而初版的冲突检测器却报"无冲突"
   （因为 `find_pair` 对"两端本来就相同的端子"直接跳过，绕过了冲突检查）。
   修正：**对称**走"自同构"（σ + 全局校验）；**匹配**走"局部支路对应"
   （只要求在两条臂内部一致，不要求全局成立）。
F2 σ 全局校验：任何器件在 σ 下必须有镜像对象，否则拒绝该配对并逐对回退。
F3 电流镜判据补强：桶键补 model（原来只分 nmos/pmos，不同型号会被并成一组）；
   无二极管参考管的组改判 common_gate_pair，不再写"复制参考电流"；
   短接/悬空 MOS 不参与；补 references / confidence 字段。
F4 配对可追溯：每一对都登记 relation（symmetry / differential / arm_match），
   报告里能看出"这一对凭什么成立"。

识别用的证据链（全部来自网表本身，不依赖器件命名）：
  E1 端口/网表事实：端子连接、器件 model、参数取值
  E2 电气判据：二极管接法、两端同网、共栅共源
  E3 对称（自同构）：差分端口对换下的图自同构 —— WL 颜色细化 + 全局校验
  E4 匹配（局部支路）：由差分对出发，沿两臂对应网做结构对应（只局部成立）
  E5 功能网络：CMFB 取样网络（电阻割点）、尾电流、输出级

参数约减规则：
  R1 Dummy（两端同网/短接）      -> 尺寸参数移出优化变量（固定）
  R2 同名变量（串联分段）        -> 天然共享，归入同一组
  R3 对称对（自同构 σ）          -> 共享全部尺寸（w/l/m/segL/segW）
  R4 匹配对（差分对/支路对应）    -> 共享全部尺寸（两侧必须完全一致，含 m）
  R5 电流镜组（同型号/同栅/同源） -> 共享 w/l；比值由 m 承担，m 逐管保留
  注：m（Multiplier）与 seg 是**整数比值旋钮**，除 R3/R4 的严格匹配对外不合并。
"""
from __future__ import annotations

import re

from netlist_parser import Circuit, Device, IDENT_RE

# 参与合并的尺寸参数（不含 m / multi —— 它们是比值旋钮）
MERGE_PARAMS = ("w", "l", "segL", "segW", "r", "c")

# 严格匹配对（对称对 / 差分对 / 支路对应）必须**完全一致**，包括 m：
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


def _roles(d: Device):
    """端子在连接图里的角色标签：MOS 用 d/g/s/b，两端器件统一 't'。

    两端器件的两个端子电气等价、网表书写顺序任意
    （`C2 (outaverage VOUTP)` 与 `C3 (VOUTN outaverage)` 就是反着写的），
    所以不能拿"第几个端子"当角色，否则会把一对本来对应的器件判成不同结构。
    """
    if d.kind in ("nmos", "pmos"):
        return ("d", "g", "s", "b")[:len(d.nets)]
    return ("t",) * len(d.nets)


def _multi_key(d: Device):
    return d.params.get("multi", d.params.get("m"))


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


# ---------- E3：图对称（WL 颜色细化 + 全局自同构校验） ----------

def _diff_port_pairs(ports) -> list:
    """端口名里的差分对：末位 P/N 成对（VINP/VINN、VOUTP/VOUTN、INP/INN...）。

    只按命名规则识别、不写死具体端口名，隐藏电路换名字也适用。
    """
    pset = {p for p in ports if p}
    out = []
    for p in sorted(pset):
        if p[-1] not in "PpNn":
            continue
        sib = p[:-1] + ("N" if p[-1] in "Pp" else "P")
        if sib in pset and sib != p and p < sib:
            out.append((p, sib))
    return out


def _net_role(n: str, ports, diff_prefix: dict) -> str:
    """网的初色：差分端口对折叠成同一角色，电源地保留真实名，内部网统一 'N'。"""
    if n is None or n == "":
        return "NC"
    if n.lower() in RAILS:
        return n.lower()
    if n in diff_prefix:
        return "DIFF:" + diff_prefix[n]
    if n in ports:
        return n
    return "N"


def _canon(values) -> dict:
    m: dict = {}
    for v in values:
        if v not in m:
            m[v] = len(m)
    return m


def wl_colors(c: Circuit):
    """Weisfeiler-Lehman 颜色细化：给"器件—网"二部图算稳定颜色。

    同色 = 在该图的自同构下**可能**互换。这是识别"图对称器件"的正确基础：
      - 只看尺寸参数值不行：参数化后每个器件尺寸都是独立变量名，永远不同；
      - 只看"同 model + 同 multi"会跨支路误配（PM0 与 PM5 都是 p_mos_a/multi=1
        的二极管接法管子，却分属两条不同镜像支路）。
    颜色细化会把"周围连接结构不同"的器件自动分开，而真正对称的两只会保持同色。
    """
    devs = list(c.devices)
    nets = sorted({n for d in devs for n in d.nets})
    diff_prefix = {}
    for p, q in _diff_port_pairs(c.ports):
        diff_prefix[p] = p[:-1]
        diff_prefix[q] = p[:-1]
    ports = set(c.ports)

    net_color: dict = {n: _net_role(n, ports, diff_prefix) for n in nets}
    dev_color: dict = {}
    for _ in range(16):
        dsig = {}
        for d in devs:
            cols = [net_color[n] for n in d.nets]
            if d.kind not in ("nmos", "pmos"):
                cols = sorted(cols)          # 两端器件端子无序
            dsig[d.name] = (d.model, _multi_key(d), tuple(cols))
        cm = _canon(dsig.values())
        dev_color = {k: cm[v] for k, v in dsig.items()}

        nsig = {}
        for n in nets:
            nsig[n] = tuple(sorted((dev_color[d.name], r)
                                   for d in devs for r, x in zip(_roles(d), d.nets) if x == n))
        cm2 = _canon(nsig.values())
        new = {n: cm2[v] for n, v in nsig.items()}
        if new == net_color:
            break
        net_color = new
    return dev_color, net_color


def _align(a: Device, b: Device, sigma: dict):
    """求两只"互为镜像"器件的端子对应；不相容返回 None。

    MOS 是四端有向器件，按位置对应；两端器件的两个端子可互换，两种对应都试，
    取与当前 σ 相容的一种；两种都相容且派生的映射不同则视为歧义（返回 None）。
    """
    cands = [list(zip(a.nets, b.nets))]
    if len(a.nets) == 2 and len(b.nets) == 2:
        cands.append(list(zip(a.nets, b.nets[::-1])))
    good = []
    for pr in cands:
        ok = True
        for x, y in pr:
            if x == y:
                continue
            if sigma.get(x, y) != y or sigma.get(y, x) != x:
                ok = False
                break
        if ok:
            good.append(pr)
    if not good:
        return None
    if len(good) > 1:
        m1 = {x: y for x, y in good[0] if x != y}
        m2 = {x: y for x, y in good[1] if x != y}
        if m1 != m2:
            return None
    return good[0]


def _verify_sigma(c: Circuit, sigma: dict, pairs: list):
    """全局自同构校验：除配对器件外，每个器件在 σ 下都必须保持不变。

    返回 (是否通过, 找不到镜像对象的器件列表)。
    """
    images = {}
    for a, b in pairs:
        images[a.name] = b.name
        images[b.name] = a.name

    missing = []
    for d in c.devices:
        if d.name in images:
            continue
        imgs = {tuple(sigma.get(n, n) for n in pr) for pr in _orderings(d)}
        if tuple(d.nets) in imgs:                     # 自身在 σ 下不变
            continue
        hit = None
        for e in c.devices:
            if e.name == d.name or not _same_style(d, e):
                continue
            if tuple(e.nets) in imgs:
                hit = e.name
                break
        if hit is None:
            missing.append(d.name)
    return (not missing), missing


def _rebuild_sigma(c: Circuit, pairs: list) -> dict:
    sigma: dict = {}
    for p, q in _diff_port_pairs(c.ports):
        sigma[p] = q
        sigma[q] = p
    for d in c.devices:
        for n in d.nets:
            if n.lower() in RAILS:
                sigma.setdefault(n, n)
    for a, b in pairs:
        al = _align(a, b, sigma)
        if al is None:
            return sigma
        for x, y in al:
            if x != y:
                sigma[x] = y
                sigma[y] = x
    return sigma


def _solve_symmetry(c: Circuit, cands: list, banned: set):
    """在"禁用若干配对"的约束下，用**不动点迭代**求解 σ。

    为什么必须迭代而不是一遍扫过：候选对的端子对应是否唯一，取决于 σ 已经知道多少。
    以共模取样电阻链为例，链首那对（R3↔R0_10）在早期处理时"两种端子对应都说得通"，
    会被判为歧义；只有先接受靠输出端口锚定的那一对，链上的对应才逐段唯一。
    所以：先接受当前唯一可判的，再回头重试之前歧义的，直到不再前进。
    """
    sigma = _rebuild_sigma(c, [])
    pairs: list = []
    paired: set = set()
    pending = [p for p in cands
               if tuple(sorted((p[0].name, p[1].name))) not in banned]
    skipped: list = []
    while pending:
        progressed = False
        rest = []
        for a, b in pending:
            if a.name in paired or b.name in paired:
                continue
            al = _align(a, b, sigma)
            if al is None:
                rest.append((a, b))
                continue
            for x, y in al:
                if x != y:
                    sigma[x] = y
                    sigma[y] = x
            pairs.append((a, b))
            paired.update((a.name, b.name))
            progressed = True
        if not progressed:
            skipped = [(a.name, b.name, "端子对应存在歧义或与已建立的 σ 冲突")
                       for a, b in rest]
            break
        pending = rest
    return pairs, sigma, skipped


def find_symmetry_pairs(c: Circuit) -> dict:
    """E3：找**真正的图对称**器件对（差分端口对换下的自同构）。

    ① WL 颜色细化；② 只取颜色类恰为 2 的对；③ 不动点迭代建立 σ；
    ④ **全局校验**（每个器件都必须有镜像对象），不通过就把卷入冲突的配对拉黑重解。
    宁可少认，不可错认。
    """
    devs = list(c.devices)
    dev_color, _ = wl_colors(c)
    classes: dict = {}
    for d in devs:
        classes.setdefault(dev_color[d.name], []).append(d)
    ordered = sorted(classes.items(), key=lambda kv: str(kv[0]))
    cands = [(m[0], m[1]) for _, m in ordered if len(m) == 2]
    # 颜色类 >2 的（多重对称）：本引擎只处理两两对称，保守跳过并登记，供人工确认
    multifold = [sorted(x.name for x in m) for _, m in ordered if len(m) > 2]

    banned: set = set()
    pairs, sigma, skipped = _solve_symmetry(c, cands, banned)
    rejected = list(skipped)
    for _ in range(6):
        ok, missing = _verify_sigma(c, sigma, pairs)
        if ok:
            break
        ms = set(missing)
        newban = {tuple(sorted((a.name, b.name))) for a, b in pairs
                  if ms & (set(a.nets) | set(b.nets))}
        if not newban and pairs:
            a, b = pairs[-1]
            newban = {tuple(sorted((a.name, b.name)))}
        if not newban:
            break
        for a, b in pairs:
            if tuple(sorted((a.name, b.name))) in newban:
                rejected.append((a.name, b.name,
                                 "全局自同构校验失败：%d 个器件找不到镜像对象" % len(missing)))
        banned |= newban
        pairs, sigma, skipped = _solve_symmetry(c, cands, banned)
        rejected = list(skipped) + rejected

    ok, missing = _verify_sigma(c, sigma, pairs)
    return {"pairs": pairs, "sigma": sigma, "verified": ok,
            "missing_images": missing, "rejected": rejected,
            "multifold_classes": multifold}


# ---------- E4：工艺匹配（差分对 + 局部支路对应） ----------

def find_differential_pairs(c: Circuit, mos: list, dummy_names: set) -> list:
    """差分对：同款 MOS、**共尾节点**（非电源地）、栅极互不相同且漏极互不相同，
    且该尾节点下这一尺寸档**恰好两只**。

    为什么要求"恰好两只"：同一条尾节点上可能挂着 3 只以上同款管子（如输出支路），
    此时配对不唯一，宁可不判、交给人工确认。
    "主输入对"的判据是两栅同属一对差分端口（按端口名 P/N 成对识别）。
    """
    diff_pref = {}
    for p, q in _diff_port_pairs(c.ports):
        diff_pref[p] = p[:-1]
        diff_pref[q] = p[:-1]
    out = []
    buckets: dict = {}
    for d in mos:
        if d.name in dummy_names:
            continue
        src = d.net_map.get("s")
        if not src or src.lower() in RAILS:
            continue
        buckets.setdefault((src, d.model, _multi_key(d)), []).append(d)
    for (src, model, multi), members in sorted(buckets.items(), key=lambda kv: str(kv[0])):
        if len(members) != 2:
            continue
        a, b = members
        ma, mb = a.net_map, b.net_map
        if ma["g"] == mb["g"] or ma["d"] == mb["d"]:
            continue
        pref_a, pref_b = diff_pref.get(ma["g"]), diff_pref.get(mb["g"])
        is_main = bool(pref_a and pref_b and pref_a == pref_b)
        out.append({"a": a, "b": b, "tail": src,
                    "role": "main" if is_main else "auxiliary",
                    "gates": [ma["g"], mb["g"]]})
    return out


def arm_match(c: Circuit, seeds: list, already: set, dummy_names: set):
    """E4：由匹配对出发，沿"两臂对应网"做**局部**结构对应。

    与 σ（全局自同构）的区别：
      · σ 要求整个网表一致 —— 因此"VCM 对 outaverage"这种匹配关系不可能成立；
      · 本函数只要求在两条臂内部一致，走出臂的范围就停。
    典型收获：CMFB 误差放大器两侧的镜像负载与共源共栅
      （PM12↔PM8 是差分对 -> net52↔net3 -> NM13↔NM12、NM11↔NM10）。
      由此得到的 net5↔vcmfb **只在臂内成立**，不会外溢到 PM5/PM6/PM2/PM3
      —— 这正是"匹配"与"对称"必须分开的原因。
    配对不唯一时保守跳过（宁少不错）。
    """
    corr: dict = {}

    def consistent(x, y):
        if x == y:
            return True
        if x in corr and corr[x] != y:
            return False
        if y in corr and corr[y] != x:
            return False
        return True

    def put(x, y):
        if not consistent(x, y):
            return False
        if x != y:
            corr[x] = y
            corr[y] = x
        return True

    devs = list(c.devices)
    paired = set(already)
    pairs: list = []
    work: list = []
    for s in seeds:
        a, b = s["a"], s["b"]
        if a.kind in ("nmos", "pmos"):
            put(a.net_map["d"], b.net_map["d"])
            work.append((a.net_map["d"], b.net_map["d"]))

    guard = 0
    while work and guard < 128:
        guard += 1
        na, nb = work.pop(0)
        for role in ("d", "g", "s", "t"):
            left = [d for d in devs
                    if d.name not in dummy_names and d.name not in paired
                    and any(r == role and x == na for r, x in zip(_roles(d), d.nets))]
            right = [d for d in devs
                     if d.name not in dummy_names and d.name not in paired
                     and any(r == role and x == nb for r, x in zip(_roles(d), d.nets))]
            if len(left) != 1 or len(right) != 1:
                continue                      # 不唯一 -> 保守跳过
            x, y = left[0], right[0]
            if not _same_style(x, y):
                continue
            # 端子重复模式必须一致：二极管接法（d==g）只能对应二极管接法。
            # 否则会把 PM5(net5,net5,...) 与 PM6(vcmfb,net5,...) 误配成同位器件。
            if len(set(x.nets)) != len(set(y.nets)):
                continue
            options = [list(zip(x.nets, y.nets))]
            if len(x.nets) == 2 and len(y.nets) == 2:
                options.append(list(zip(x.nets, y.nets[::-1])))
            chosen = None
            for opt in options:
                if all(consistent(xn, yn) for xn, yn in opt):
                    chosen = opt
                    break
            if chosen is None:
                continue
            for xn, yn in chosen:
                put(xn, yn)
            pairs.append((x, y, corr.get(na, na), corr.get(nb, nb)))
            paired.update((x.name, y.name))
            for xn, yn in chosen:
                if xn != yn and (xn, yn) not in work and (yn, xn) not in work:
                    work.append((xn, yn))
    return pairs, corr


# ---------- 主分析 ----------

def analyze(c: Circuit) -> dict:
    devs = c.devices
    mos = [d for d in devs if d.kind in ("nmos", "pmos")]
    twoterm = [d for d in devs if d.kind in ("res", "cap")]

    # ================= E2：基础电气判据 =================
    # 两端同网（R/C）以及全端子同网的 MOS 都算 Dummy：电气上构不成通路。
    dummies = [d for d in devs
               if d.is_two_terminal_shorted() or len(set(d.nets)) == 1]
    dummy_names = {d.name for d in dummies}
    diode = [d for d in mos if d.is_diode_connected() and d.name not in dummy_names]

    # ================= E5-1：CMFB 取样网络（电阻图割点） =================
    res_adj: dict = {}
    res_devs = [d for d in twoterm if d.kind == "res" and d.name not in dummy_names]
    for d in res_devs:
        res_adj.setdefault(d.nets[0], set()).add(d.nets[1])
        res_adj.setdefault(d.nets[1], set()).add(d.nets[0])

    def res_reach(start: str, blocked=None) -> set:
        seen, stack = {start}, [start]
        while stack:
            for nb in res_adj.get(stack.pop(), ()):
                if nb == blocked or nb in seen:
                    continue
                seen.add(nb)
                stack.append(nb)
        return seen

    cap_nets = set()
    for d in twoterm:
        if d.kind == "cap" and d.name not in dummy_names:
            cap_nets.update(d.nets)
    out_ports = [p for p in c.ports if p.lower() not in RAILS and p in cap_nets]
    out_pair = tuple(out_ports[:2]) if len(out_ports) >= 2 else None

    res_dev_names = {d.name for d in res_devs}
    nonres_nets: dict = {}
    for d in devs:
        if d.name in res_dev_names or d.name in dummy_names:
            continue
        for n in d.nets:
            nonres_nets.setdefault(n, []).append(d.name)

    cm_sense = None
    if out_pair:
        a, b = out_pair
        candidates = [n for n in res_reach(a)
                      if n != b and n.lower() not in RAILS
                      and b not in res_reach(a, blocked=n)
                      and nonres_nets.get(n)]
        if len(candidates) == 1:
            cm_sense = candidates[0]

    # ================= E3：图对称（自同构） =================
    sym = find_symmetry_pairs(c)
    pairing = [(a.name, b.name) for a, b in sym["pairs"]]
    paired_names = {n for p in pairing for n in p}

    # ================= E4：工艺匹配（差分对 + 局部支路对应） =================
    diff_pairs = find_differential_pairs(c, mos, dummy_names)
    match_pairs: list = []                 # (a, b, relation, why)
    for dp in diff_pairs:
        a, b = dp["a"], dp["b"]
        rel = "differential/%s" % dp["role"]
        why = "共尾节点 %s、栅极 %s/%s" % (dp["tail"], dp["gates"][0], dp["gates"][1])
        if a.name in paired_names and b.name in paired_names:
            rel += "+symmetry"
            why += "（同时通过 σ 自同构校验）"
        match_pairs.append((a, b, rel, why))
        paired_names.update((a.name, b.name))

    arm_pairs, _corr = arm_match(c, diff_pairs, paired_names, dummy_names)
    for x, y, na, nb in arm_pairs:
        match_pairs.append((x, y, "arm_match",
                            "两臂对应网 %s↔%s 上的同位器件" % (na, nb)))

    # ================= E2：电流镜组（同类型 + 同栅 + 同源） =================
    mirror_groups: list = []
    buckets: dict = {}
    for d in mos:
        if d.name in dummy_names:
            continue
        m = d.net_map
        buckets.setdefault((d.kind, d.model, m["g"], m["s"]), []).append(d)
    for (kind, model, gate, src), members in sorted(buckets.items(), key=lambda kv: str(kv[0])):
        if len(members) < 2:
            continue
        refs = [x for x in members if x.is_diode_connected()]
        ref = refs[0].name if refs else None
        if ref:
            mtype, conf = "current_mirror", (3 if len(refs) == 1 else 2)
            ev = (f"{kind}({model}) 管栅极同为 {gate}、源极同为 {src}，共 {len(members)} 管；"
                  f"其中 {ref} 栅漏短接，是参考管；其余各管按 (W/L·m) 之比复制参考电流")
            zh = ("NMOS" if kind == "nmos" else "PMOS") + " 电流镜"
        else:
            mtype, conf = "common_gate_pair", 2
            ev = (f"{kind}({model}) 管栅极同为 {gate}、源极同为 {src}，共 {len(members)} 管；"
                  f"组内无二极管接法器件 -> 不是标准电流镜，栅压由 {gate} 外部确定，"
                  f"各管电流比 = (W/L·m) 之比；仍需尺寸匹配但**不能**称参考管")
            zh = ("NMOS" if kind == "nmos" else "PMOS") + " 共栅对（无参考管）"
        mirror_groups.append({
            "type": mtype, "name_zh": zh, "kind": kind, "model": model,
            "gate": gate, "source": src, "reference": ref,
            "references": [r.name for r in refs], "confidence": conf,
            "devices": [x.name for x in members], "evidence": ev,
        })

    # CMFB 误差放大器差分对（辅助差分对）
    cmfb_pair = None
    if cm_sense:
        for dp in diff_pairs:
            if cm_sense in dp["gates"]:
                cmfb_pair = (dp["a"], dp["b"])
                break

    # ================= 功能模块清单 =================
    modules: list = []
    if dummies:
        modules.append({
            "id": "D1", "type": "dummy", "name_zh": "Dummy 器件（电气无效）",
            "devices": [d.name for d in dummies],
            "evidence": "两端接同一节点或全端子同网：" + "、".join(
                f"{d.name}({','.join(d.nets)})" for d in dummies)
                + "。电气上不构成通路，对任何性能指标无贡献，其尺寸参数应从优化变量中剔除"
                  "（器件保留在网表中，否则仿真读不到初值）",
        })
    for i, g in enumerate(mirror_groups, 1):
        g["id"] = f"CM{i}"
        modules.append(g)
    for i, dp in enumerate(diff_pairs, 1):
        a, b = dp["a"], dp["b"]
        modules.append({
            "id": f"DP{i}", "type": "differential_pair",
            "name_zh": "输入差分对" if dp["role"] == "main" else "辅助差分对（误差放大器）",
            "devices": [a.name, b.name],
            "evidence": (f"{a.name}/{b.name} 同为 {a.model}、同 multi {_multi_key(a)}，"
                         f"源极共接 {dp['tail']}，栅极分别接 {dp['gates'][0]}/{dp['gates'][1]}；"
                         f"{'主输入对' if dp['role'] == 'main' else '非主输入（如共模反馈误差放大器输入）'}"
                         f"，两管必须严格匹配（失配直接恶化失调与 CMRR）"),
        })
    main_pair = next((dp for dp in diff_pairs if dp["role"] == "main"), None)
    if main_pair:
        tail_node = main_pair["tail"]
        pair_names = {main_pair["a"].name, main_pair["b"].name}
        tail = [d for d in mos if d.name not in dummy_names and d.name not in pair_names
                and any(x == tail_node for x in d.nets)]
        if tail:
            modules.append({
                "id": "T1", "type": "tail_current_source", "name_zh": "尾电流源",
                "devices": [d.name for d in tail],
                "evidence": (f"{tail[0].name} 的端子接在差分对公共源 {tail_node} 上，"
                             f"为输入对提供尾电流"),
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
        # 取样电阻链：端点落在"从两个输出出发的电阻可达网"里的电阻（按网判断，不是按器件名）
        reach = (res_reach(out_pair[0]) | res_reach(out_pair[1])) if out_pair else set()
        chain = [d for d in res_devs if any(n in reach for n in d.nets)]
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
            "id": "MB1", "type": "matching", "name_zh": "对称结构（自同构 σ，已全局校验）",
            "devices": sorted({n for p in pairing for n in p}, key=_natkey),
            "evidence": "由差分端口对换（VINP/VINN、VOUTP/VOUTN）建立网表自同构 σ："
                        "WL 颜色细化求候选，再**全局校验**每个器件都有镜像对象，"
                        "不通过则逐对回退；满足 σ(d1)=d2 的器件对结构严格对称，尺寸必须完全一致。"
                        "配对结果：" + "，".join(f"{a}={b}" for a, b in pairing),
        })
    if match_pairs:
        modules.append({
            "id": "MB2", "type": "matching", "name_zh": "工艺匹配结构（差分对 + 两臂对应）",
            "devices": sorted({n for a, b, _, _ in match_pairs for n in (a.name, b.name)},
                              key=_natkey),
            "evidence": "工艺匹配**不等于**图对称：差分对两侧栅极接的是不同信号"
                        "（例如共模反馈误差放大器的 VCM 与 outaverage），整体网表并不自同构。"
                        "所以这里用「差分对种子 + 两臂对应网的结构对应」单独识别，只在两条臂内部成立；"
                        "配对结果：" + "，".join(f"{a.name}={b.name}[{rel}]"
                                                for a, b, rel, _ in match_pairs),
        })

    # ================= 参数约减 =================
    uf = UnionFind()
    for d in devs:
        for p in d.variables:
            uf.find((d.name, p))
    prefer: dict = {}                      # 并查集根 -> 期望的规范器件名（可追溯）

    # R2：同名变量天然共享（电阻串联分段）
    var_shared: dict = {}
    for d in devs:
        for v in d.var_names:
            var_shared.setdefault(v, []).append(d.name)
    segment_groups = {v: ns for v, ns in var_shared.items() if len(ns) > 1}
    for v, names in segment_groups.items():
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

    # R3/R4：对称对与匹配对完全共享尺寸（含 m）
    pair_notes: dict = {}
    pair_relation: list = []
    strict_pairs = [(a.name, b.name, "symmetry") for a, b in sym["pairs"]]
    strict_pairs += [(a.name, b.name, rel) for a, b, rel, _ in match_pairs]
    seen_pairs: set = set()
    for a, b, rel in strict_pairs:
        key = tuple(sorted((a, b)))
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        da, db = c.by_name(a), c.by_name(b)
        if not da or not db:
            continue
        shared = []
        for p in PAIR_MERGE_PARAMS:
            if p in da.variables and p in db.variables:
                uf.union((da.name, p), (db.name, p))
                shared.append(p)
        pair_notes.setdefault(a, []).append(b)
        pair_notes.setdefault(b, []).append(a)
        pair_relation.append({"a": a, "b": b, "relation": rel, "shared": sorted(shared)})

    # R5：电流镜组内共享 w/l（比值由 m 承担，m 逐管保留）
    for g in mirror_groups:
        members = [m for m in (c.by_name(n) for n in g["devices"]) if m]
        for p in ("w", "l"):
            anchor = None
            if g.get("reference"):
                ref_d = c.by_name(g["reference"])
                if ref_d and p in ref_d.variables:
                    anchor = ref_d
            if anchor is None:
                anchor = next((m for m in members if p in m.variables), None)
            if not anchor:
                continue
            for m in members:
                if p in m.variables:
                    uf.union((anchor.name, p), (m.name, p))
            # 只有"真正有参考管"的镜像组才用参考管名当规范名；
            # 无参考管的共栅对保持自然序最小的器件名（避免凭空改名，便于与 PDK 初值文件对齐）
            if g.get("reference"):
                prefer[uf.find((anchor.name, p))] = anchor.name

    # 规范名：优先用基准器件/参考管的变量名（可追溯）
    groups: dict = {}
    for d in devs:
        if d.name in dummy_names:
            continue
        for p, v in d.variables.items():
            groups.setdefault(uf.find((d.name, p)), []).append((d.name, p, v))

    reduced: list = []
    rename: dict = {}
    for root, items in groups.items():
        names = sorted({v for _, _, v in items}, key=_natkey)
        pref = prefer.get(root)
        by_dev = sorted({n for n, _, _ in items}, key=lambda n: (_natkey(n), n))
        want_dev = pref or by_dev[0]
        cand = [v for n, _, v in items if n == want_dev]
        canon = cand[0] if cand else names[0]
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
                   "reason": "Dummy 器件（电气无效），尺寸不参与优化"}
                  for d in dummies for p, v in d.variables.items()]

    by_cat: dict = {}
    for r in reduced:
        k = "整数(m)" if r["kind"] == "integer" else r["param"]
        by_cat[k] = by_cat.get(k, 0) + 1

    # ================= 自检断言（防止"看起来对、实际不自洽"） =================
    assert sym["verified"], "σ 未通过全局自同构校验：%s" % sym["missing_images"]
    all_names = {d.name for d in devs}
    for a, b, _ in strict_pairs:
        assert a in all_names and b in all_names, "配对里出现不存在的器件 %s/%s" % (a, b)
    for m in mirror_groups:
        for n in m["devices"]:
            assert n in all_names, "电流镜组里出现不存在的器件 %s" % n
        if m["type"] == "current_mirror":
            assert m["reference"] in m["devices"], "电流镜缺少参考管"
    assert len({r["var"] for r in reduced}) == len(reduced), "约减后变量名有重复"

    return {
        "subckt": c.subckt, "ports": c.ports, "device_count": len(devs),
        "raw_variable_count": len(c.all_variables), "raw_variables": c.all_variables,
        "modules": modules, "mirror_groups": mirror_groups,
        "pairing": [{"a": a, "b": b} for a, b in pairing],
        "pairing_relation": pair_relation,
        "symmetry_verified": sym["verified"],
        "symmetry_missing_images": sym["missing_images"],
        "symmetry_rejected": [{"a": a, "b": b, "why": w} for a, b, w in sym["rejected"]],
        "multifold_classes": sym["multifold_classes"],
        "match_pairs": [{"a": a.name, "b": b.name, "relation": rel, "why": why}
                        for a, b, rel, why in match_pairs],
        "seeds": ["差分端口对换 " + "/".join("%s~%s" % (p, q)
                                            for p, q in _diff_port_pairs(c.ports))],
        "sigma_conflicts": [],
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
    merged_note: dict = {}
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
    L.append(f"// 原始优化变量 {res['raw_variable_count']}  ->  约减后 "
             f"{res['reduced_variable_count']}")
    L.append("//")
    L.append("// 【变量账目】重新解析本网表会数出 "
             f"{res['reduced_variable_count'] + len(res['fixed_variables'])} 个符号，其中：")
    L.append(f"//     优化变量 {res['reduced_variable_count']} 个  <- 交给优化算法"
             "（见 var_reduction.csv / param_list_reduced.txt）")
    L.append(f"//     固定符号 {len(res['fixed_variables'])} 个  <- Dummy 器件，电气无效，"
             "保留符号只为让仿真能读到初值，不参与优化")
    L.append("//")
    L.append("// 配对关系：对称对由自同构 σ 判定（已通过全局校验）；")
    L.append("//           匹配对由差分对/两臂对应判定（工艺匹配，**不是**图对称）")
    L.append("// 标记：[MERGED] 尺寸已与配对器件/镜像管合并为同一变量；")
    L.append("//       [DUMMY]  电气无效器件，尺寸不参与优化（保留符号供仿真读取初值）")
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
    print(f"σ 自同构校验    : {'通过' if r['symmetry_verified'] else '失败'}"
          f"   对称对 {len(r['pairing'])} 对，回退 {len(r['symmetry_rejected'])} 对")
    print(f"工艺匹配对      : {len(r['match_pairs'])} 对")
    print(f"Dummy           : {r['dummies']}")
    print(f"二极管接法      : {r['diode_connected']}")
    print(f"输出端口对      : {r['output_pair']}    共模检测点: {r['cm_sense_node']}")
    print("=" * 72)
    for m in r["modules"]:
        print(f"[{m['id']:<4}] {m['name_zh']}  ({m['type']})")
        print(f"       器件：{', '.join(m['devices'])}")
        print(f"       依据：{m['evidence']}")
        print()
    print("=" * 72)
    print("对称配对（σ，已全局校验）：")
    for p in r["pairing"]:
        print(f"   {p['a']:<8} = {p['b']}")
    print("工艺匹配对（差分/支路对应）：")
    for p in r["match_pairs"]:
        print(f"   {p['a']:<8} = {p['b']:<8} [{p['relation']}] {p['why']}")
    print("=" * 72)
    print("约减后变量清单：")
    for v in r["reduced_variables"]:
        tag = "整数" if v["kind"] == "integer" else "连续"
        src = f"   <- {','.join(v['merged_from'])}" if len(v["merged_from"]) > 1 else ""
        print(f"   {v['var']:<12} {tag}  {v['unit']:<5} {','.join(v['devices'])}{src}")
