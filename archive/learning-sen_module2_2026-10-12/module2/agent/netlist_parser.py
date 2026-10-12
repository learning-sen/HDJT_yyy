# -*- coding: utf-8 -*-
"""
模块二 · 第 1 层：确定性网表解析器（不调用大模型）

职责：把 Spectre 网表文本变成结构化对象 —— 子电路、端口、器件、端子、参数、变量。
这一层的输出必须 100% 可复现：网表里写了什么，就解析出什么，不允许"猜"。

解析难点（本 PDK 网表的真实情况）：
1. 器件语句跨行，续行以 `+` 开头，必须先拼成一整行再解析；
2. 注释有 `//`（整行或行内）和 `*`（整行）两种；
3. MOS 的 ad/as/pd/ps/nrd/nrs/sa/sb 是**派生参数表达式**，
   里面也含变量名（如 PM3_fw），但它们是**因变量**，不是优化变量；
4. 真正可优化的只有尺寸参数（w/l/m/segL/segW/...），
   且只有"值是裸标识符"的才叫变量（w=10u 是常量）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# ---------- 常量表 ----------

# PDK 模型名 -> 逻辑器件类型
MODEL_KIND = {
    "n_mos_a": "nmos",
    "p_mos_a": "pmos",
    "res_n_poly": "res",
    "res_p_poly": "res",
    "cap_mim": "cap",
}

# 只有这些参数是"尺寸参数"，才有资格成为优化变量
SIZE_PARAMS = ("w", "l", "m", "multi", "seg", "segL", "segW", "r", "c", "nf", "fw")

# MOS 的端口顺序（Spectre：D G S B）
MOS_NETS = ("d", "g", "s", "b")
# 两端器件的端口顺序（R / C）
TWO_NETS = ("p", "n")

# 值是裸标识符才算变量；含数字/运算符/括号的都是常量或表达式
IDENT_RE = re.compile(r"^[A-Za-z_]\w*$")
# 器件语句：NAME (net1 net2 ...) model param=value ...
DEVICE_RE = re.compile(r"^(\S+)\s*\(([^)]*)\)\s*(\S+)\s*(.*)$")
# 参数：key=value（value 取到下一个空白）
PARAM_RE = re.compile(r"([A-Za-z_]\w*)\s*=\s*(\S+)")
SUBCKT_RE = re.compile(r"^subckt\s+(\S+)\s*\(([^)]*)\)", re.I)
ENDS_RE = re.compile(r"^ends\b", re.I)


# ---------- 数据结构 ----------

@dataclass
class Device:
    """一个器件实例。"""
    name: str
    nets: tuple[str, ...]
    model: str
    params: dict[str, str] = field(default_factory=dict)
    line_no: int = 0
    raw: str = ""

    @property
    def kind(self) -> str:
        return MODEL_KIND.get(self.model.lower(), "unknown")

    @property
    def net_map(self) -> dict[str, str]:
        """端口名 -> 网名，MOS 用 d/g/s/b，两端器件用 p/n。"""
        keys = MOS_NETS if self.kind in ("nmos", "pmos") else TWO_NETS
        return dict(zip(keys, self.nets))

    @property
    def size_params(self) -> dict[str, str]:
        return {k: v for k, v in self.params.items() if k in SIZE_PARAMS}

    @property
    def variables(self) -> dict[str, str]:
        """尺寸参数里"值是裸标识符"的 -> 优化变量。返回 {参数名: 变量名}。"""
        out = {}
        for k, v in self.size_params.items():
            if IDENT_RE.match(v):
                out[k] = v
        return out

    @property
    def var_names(self) -> list[str]:
        return sorted(self.variables.values())

    def is_diode_connected(self) -> bool:
        """栅极与漏极同网 = 二极管接法（电流镜的参考管）。"""
        if self.kind not in ("nmos", "pmos"):
            return False
        m = self.net_map
        return m.get("g") == m.get("d")

    def is_two_terminal_shorted(self) -> bool:
        """两端器件两个端子接同一网 = 电气上悬空无用（Dummy 的典型特征）。"""
        return len(self.nets) == 2 and self.nets[0] == self.nets[1]

    def size_suffix_set(self) -> frozenset:
        return frozenset(self.size_params.keys())


@dataclass
class Circuit:
    subckt: str
    ports: list[str]
    devices: list[Device]
    top_devices: list[Device] = field(default_factory=list)
    source: str = ""

    def by_name(self, name: str) -> Device | None:
        for d in self.devices:
            if d.name == name:
                return d
        return None

    @property
    def all_variables(self) -> list[str]:
        """原始变量清单（去重、排序）。"""
        seen = []
        for d in self.devices:
            for v in d.var_names:
                if v not in seen:
                    seen.append(v)
        return seen


# ---------- 解析 ----------

def _strip_comments(text: str) -> list[str]:
    """去掉整行注释（// 与 * 开头）与行内 // 注释。"""
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("//") or s.startswith("*"):
            continue
        if "//" in s:
            s = s.split("//", 1)[0].strip()
            if not s:
                continue
        out.append(s)
    return out


def _join_continuations(lines: list[str]) -> list[tuple[int, str]]:
    """把以 `+` 开头的续行拼到上一行；返回 (起始行号, 完整语句)。"""
    joined: list[tuple[int, str]] = []
    for i, s in enumerate(lines, start=1):
        if s.startswith("+") and joined:
            no, prev = joined[-1]
            joined[-1] = (no, prev + " " + s[1:].strip())
        else:
            joined.append((i, s))
    return joined


def parse_netlist(path: str | Path) -> Circuit:
    """解析网表文件，返回 Circuit。只取第一个 subckt 作为 DUT。"""
    p = Path(path)
    raw_lines = _strip_comments(p.read_text(encoding="utf-8", errors="replace"))
    stmts = _join_continuations(raw_lines)

    subckt, ports = "", []
    devices: list[Device] = []
    top_devices: list[Device] = []
    inside = False

    for no, s in stmts:
        m = SUBCKT_RE.match(s)
        if m:
            subckt = m.group(1)
            ports = m.group(2).split()
            inside = True
            continue
        if ENDS_RE.match(s):
            inside = False
            continue
        if s.lower().startswith("parameters"):   # 裸关键字，跳过
            continue

        dm = DEVICE_RE.match(s)
        if not dm:
            continue
        name, nets, model, tail = dm.groups()
        params = dict(PARAM_RE.findall(tail))
        dev = Device(name=name, nets=tuple(nets.split()), model=model,
                     params=params, line_no=no, raw=s)
        if inside:
            devices.append(dev)
        else:
            top_devices.append(dev)

    return Circuit(subckt=subckt, ports=ports, devices=devices,
                   top_devices=top_devices, source=str(p))


# ---------- 自测 ----------

if __name__ == "__main__":
    import sys

    default = (Path(__file__).resolve().parents[2] / "extracted" / "赛题数据本身"
               / "netlist" / "OPA_loopgain.netlist")
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else default
    c = parse_netlist(target)

    print(f"文件      : {c.source}")
    print(f"子电路    : {c.subckt}({', '.join(c.ports)})")
    print(f"内部器件  : {len(c.devices)}   顶层器件: {len(c.top_devices)}")
    print("-" * 72)
    for d in c.devices:
        print(f"{d.name:<6} {d.kind:<5} {d.model:<12} "
              f"{str(d.nets):<34} 变量={d.var_names}")
    print("-" * 72)
    print(f"原始变量总数: {len(c.all_variables)}")
    dummies = [d.name for d in c.devices if d.is_two_terminal_shorted()]
    diodes = [d.name for d in c.devices if d.is_diode_connected()]
    print(f"Dummy(两端同网): {dummies}")
    print(f"二极管接法    : {diodes}")
