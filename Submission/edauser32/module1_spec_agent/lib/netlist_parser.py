"""模块 2-①  Spectre 网表解析器。

输入：赛题真实网表（Spectre 格式，`subckt` / `ends` 结构）
输出：结构化 dict，供拓扑识别与参数约减使用。

处理的格式特征（全部来自真实网表 OPA_loopgain.netlist 的实测）：
  1. `//` 行注释、空行
  2. `subckt NAME (n1 n2 ...)` ... `ends NAME`
  3. `+` 续行：器件 master card 之后的多行版图寄生参数表达式
     （ad/as/pd/ps/nrd/nrs/sa/sb/sca/scb/scc/trise/option_vop/isoring）
  4. 参数写法：`l=NM15_l w=NM15_fw multi=1 m=NM15_m`（值可能是变量名或数字，
     版图参数还可能是含 `? :` 与括号的表达式）
  5. 器件首字母：M=MOS / R=电阻 / C=电容 / V=电压源 / I=电流源 / E=VCVS
  6. MOS 端子顺序 d g s b；电阻/电容为两端器件
  7. 自动分段的电阻/电容：`R3` + `R3_2_res_gen` ...（同一器件被拆成多段串联）
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# SI 后缀 -> 倍率（注意 'm' = milli，需与 'meg' 区分，长匹配优先）
SI_SUFFIX = [
    ("meg", 1e6), ("mil", 25.4e-6),
    ("t", 1e12), ("g", 1e9), ("k", 1e3),
    ("m", 1e-3), ("u", 1e-6), ("n", 1e-9), ("p", 1e-12), ("f", 1e-15), ("a", 1e-18),
]
# 几何参数的默认单位是米（网表里 l/w 的数值如 1u 表示 1 微米）
LENGTH_PARAMS = {"l", "w", "fw", "segL", "segW", "le", "we"}

# 版图寄生参数：这些是 master card 的续行，**不是**独立优化变量
LAYOUT_PARAMS = {"ad", "as", "pd", "ps", "nrd", "nrs", "sa", "sb", "sca", "scb", "scc",
                 "trise", "option_vop", "isoring", "multi"}

# 每类器件的参数名（用于生成变量名 <inst>_<param>）
# 注意 MOS：网表里参数名是 `w`，但官方参数化脚本生成的变量名是 `<inst>_fw`
# （教程 8.3：【官】NM15_fw ← NM15 的 finger width），所以这里用 (参数键, 变量后缀) 对
PARAM_ORDER = {
    "mos": [("l", "l"), ("w", "fw"), ("m", "m")],
    "res": [("segL", "segL"), ("segW", "segW"), ("seg", "seg")],
    "cap": [("l", "l"), ("w", "w"), ("m", "m")],
}


def parse_number(tok: str) -> Optional[float]:
    """解析带 SI 后缀的数值：'10u' -> 1e-05；'2k' -> 2000；'1.2p' -> 1.2e-12。

    纯数字直接返回；无法解析返回 None。
    """
    tok = tok.strip().strip("'\"")
    m = re.fullmatch(r"([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)([A-Za-z]*)", tok)
    if not m:
        return None
    val = float(m.group(1))
    suffix = m.group(2).lower()
    if not suffix:
        return val
    for s, factor in SI_SUFFIX:
        if suffix == s:
            return val * factor
    return None


def is_number(tok: str) -> bool:
    return parse_number(tok) is not None


def _split_kv(text: str) -> List[Tuple[str, str]]:
    """把 'l=NM15_l w=NM15_fw multi=1' 拆成 [(l, NM15_l), (w, NM15_fw), (multi, 1)]。

    值可能是含空格/括号/问号的表达式，因此按"下一个 key=" 的位置切分。
    """
    out: List[Tuple[str, str]] = []
    # 找所有形如 key= 的位置（key 由字母数字下划线组成）
    marks = [(m.start(), m.group(1), m.end()) for m in
             re.finditer(r"(?:^|\s)([A-Za-z_]\w*)\s*=", text)]
    for i, (start, key, valstart) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        out.append((key, text[valstart:end].strip()))
    return out


def _split_master_and_continuations(master_rest: str, conts: List[str]) -> List[str]:
    """把 master card 尾部与续行拆成"一条条完整的 key=value 文本"。

    Spectre 里每个 `+` 续行本身是**完整的 key=value**（值为可能含 `?:` 和括号的表达式），
    例如：
        NM15 (...) n_mos_a l=NM15_l w=NM15_fw multi=1 m=NM15_m
        +ad=(NM15_fw<300n)?(...):(...)
        +as=(...):(...)
    所以**不能**按"括号总平衡"去截断 —— 第一行 `ad=...` 括号就平衡了，
    会导致后面 8 行续行全部丢失（实测 NM15 只剩 ad 一个版图参数）。

    正确做法：
      1. 先扫 master 部分，把它切成"完整的 kv"和"未闭合的尾巴"、
         以及"未闭合尾巴的后续续行"（跨行的单个 kv）
      2. 其余续行每条各算一个 kv
    """
    pieces: List[str] = []
    buf = master_rest.strip()

    def depth(s: str) -> int:
        d = 0
        for ch in s:
            if ch == "(":
                d += 1
            elif ch == ")":
                d -= 1
        return d

    if depth(buf) > 0:
        # master 上有未闭合的表达式 -> 用续行补全
        for line in conts:
            buf += " " + line
            if depth(buf) <= 0:
                break
        pieces.append(buf.strip())
        used = len([1 for _ in conts])  # 保守：其余续行仍全部解析
    elif buf:
        pieces.append(buf)

    # 每条续行都是独立的 kv（即使 master 上已有完整 kv）
    for line in conts:
        line = line.strip()
        if not line:
            continue
        if pieces and not pieces[-1].endswith(line) and depth(pieces[-1]) > 0:
            pieces[-1] += " " + line
            continue
        pieces.append(line)
    return pieces


def parse_netlist(path: Optional[str] = None, *, text: Optional[str] = None) -> dict:
    """解析 Spectre 网表，返回结构化结果。

    参数
    ----
    path : 网表文件路径
    text : 或直接给网表文本（二选一）
    """
    if text is None:
        if path is None:
            raise ValueError("必须提供 path 或 text")
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()

    lines = text.splitlines()
    warnings: List[str] = []
    subckts: List[dict] = []
    cur: Optional[dict] = None
    footer: List[str] = []      # subckt 之外的内容（testbench 器件等）

    i = 0
    n = len(lines)
    while i < n:
        raw = lines[i]
        i += 1
        line = raw.strip()
        if not line:
            continue
        if line.startswith("//") or line.startswith("*"):
            continue                       # 注释
        if line.startswith("simulator") or line.startswith("global"):
            continue                       # 仿真器指令

        low = line.lower()
        if low.startswith("subckt"):
            m = re.match(r"subckt\s+(\S+)\s*\((.*?)\)", line, re.I)
            if not m:
                warnings.append("无法解析 subckt 定义: %s" % line)
                continue
            cur = {
                "name": m.group(1),
                "ports": m.group(2).split(),
                "instances": [],
                "fixed_params": {},
            }
            # `parameters` 声明行（可选）
            if i < n and lines[i].strip().lower().startswith("parameters"):
                i += 1
            continue
        if low.startswith("ends"):
            if cur:
                subckts.append(cur)
                cur = None
            continue
        if low.startswith("parameters"):
            continue

        # ---- 收集续行 ----
        conts: List[str] = []
        while i < n:
            nxt = lines[i].lstrip()
            if nxt.startswith("+"):
                conts.append(nxt[1:].strip())
                i += 1
            else:
                break

        target = cur["instances"] if cur else footer
        inst = _parse_instance(line, conts, warnings)
        if inst:
            target.append(inst)
        elif line:
            warnings.append("无法解析的行: %s" % line[:80])

    if cur:
        subckts.append(cur)

    return {
        "source": path or "<text>",
        "subckts": subckts,
        "footer": footer,
        "warnings": warnings,
    }


def _infer_kind(name: str) -> str:
    """由实例名推断器件类型。

    兼容两种命名体系：
      - 标准 SPICE：M/R/C/D/Q/L/X 开头
      - Cadence/Aether 导出常见：**NM/PM** 前缀表示 N/P 型 MOS（如 NM15、PM0）
        —— 只看首字母会把 NM15 判成 unknown 而丢掉整颗管子。
    """
    up = name.upper()
    if up.startswith(("NM", "PM")) and len(up) > 2 and (up[2].isdigit() or up[2] == "_"):
        return "mos"
    first = up[0] if up else ""
    return {"M": "mos", "R": "res", "C": "cap", "D": "diode", "Q": "bjt",
            "I": "isrc", "V": "vsrc", "E": "vcvs", "X": "subckt"}.get(first, "unknown")


def _parse_instance(master: str, conts: List[str], warnings: List[str]) -> Optional[dict]:
    """解析一条器件 master card + 续行。"""
    # 优先匹配带括号的写法：`NM15 (d g s b) n_mos_a l=... w=...`
    m = re.match(r"([A-Za-z_]\w*)\s*\((.*?)\)\s*(.*)$", master)
    if m:
        name = m.group(1)
        nodes = m.group(2).split()
        rest = m.group(3)
    else:
        # 兼容无括号写法：`R6 net1 net2 model k=v ...`
        m2 = re.match(r"([A-Za-z_]\w*)\s+(\S+)\s+(\S+)\s*(.*)$", master)
        if not m2:
            return None
        name = m2.group(1)
        nodes = [m2.group(2), m2.group(3)]
        rest = m2.group(4)

    kind = _infer_kind(name)
    if kind == "unknown":
        return None

    # 第三段是模型名（MOS/电阻/电容/二极管/BJT 都有模型名）
    model = None
    body = rest
    if kind in ("mos", "res", "cap", "diode", "bjt"):
        mm = re.match(r"([A-Za-z_][\w.]*)\s+(.*)$", rest.strip())
        if mm and "=" not in mm.group(1):
            model = mm.group(1)
            body = mm.group(2)

    # 把 master 尾部与续行拆成一条条完整的 key=value 文本
    pieces = _split_master_and_continuations(body, conts)
    kvs: List[Tuple[str, str]] = []
    for piece in pieces:
        kvs.extend(_split_kv(piece))

    params: Dict[str, str] = {}
    params_numeric: Dict[str, float] = {}
    param_ifaces: Dict[str, str] = {}     # 参数 -> 来源（value / variable / expression）
    layout_params: Dict[str, str] = {}
    for key, val in kvs:
        if key in LAYOUT_PARAMS and key != "multi":
            layout_params[key] = val
            continue
        # 精简版键名：segL/segW -> 保留原名
        params[key] = val
        num = parse_number(val)
        if num is not None:
            # 长度类参数且无单位后缀时，按微米*1e-6 处理（网表惯例：l=1u 已是 SI）
            params_numeric[key] = num
            param_ifaces[key] = "value"
        elif re.fullmatch(r"[A-Za-z_]\w*", val):
            param_ifaces[key] = "variable"
        else:
            param_ifaces[key] = "expression"

    # 生成该器件的优化变量名（<inst>_<变量后缀>），只对几何/倍数参数
    order = PARAM_ORDER.get(kind, [])
    variables: List[dict] = []
    for pkey, vsuffix in order:
        if pkey not in params:
            continue
        variables.append({
            "name": "%s_%s" % (name, vsuffix),
            "param": pkey,               # 网表里的参数键
            "var_suffix": vsuffix,       # 官方变量名后缀（MOS 的 w -> fw）
            "expr": params[pkey],
            "initial": params_numeric.get(pkey),
            "interface": param_ifaces.get(pkey, "value"),
        })

    return {
        "name": name,
        "kind": kind,
        "model": model,
        "nodes": nodes,
        "params": params,
        "params_numeric": params_numeric,
        "param_interfaces": param_ifaces,
        "layout_params": layout_params,
        "variables": variables,
        "raw": master.strip(),
        "continued_lines": len(conts),
    }


# ---------------------------------------------------------------------------
# 便捷查询
# ---------------------------------------------------------------------------

def all_instances(net: dict) -> List[dict]:
    out = []
    for sc in net.get("subckts", []):
        out.extend(sc["instances"])
    out.extend(net.get("footer", []))
    return out


def find_subckt(net: dict, name: str) -> Optional[dict]:
    for sc in net.get("subckts", []):
        if sc["name"] == name:
            return sc
    return None


def mos_terminal(inst: dict, which: str) -> Optional[str]:
    """取 MOS 的某个端子网名：d/g/s/b（越界返回 None）。"""
    idx = {"d": 0, "g": 1, "s": 2, "b": 3}.get(which)
    if idx is None or idx >= len(inst["nodes"]):
        return None
    return inst["nodes"][idx]
