# -*- coding: utf-8 -*-
"""
模块二 · 参数回写展开器（把"49 个自由变量"展开成"105 个原理图符号"）

为什么必须有这个脚本
--------------------
参数约减把 99 个原始符号压成 47 个自由变量（例：`NM2_fw` 代表
`NM2_fw|NM3_fw|NM6_fw|NM7_fw|NM8_fw|NM9_fw|NM12_fw|NM13_fw` 八个符号）。
但赛题流程里的 `--param_file` 是**整体替换** `extractcdfVal_0.txt` 的文件，
它作用于**原理图上的 CDF 参数** —— 原理图里仍然是全部 105 个符号。
如果只写 47 行，被合并掉的成员（如 `NM3_fw`）不会被更新，仍停在初值：

    ⇒ 你精心绑定成"完全一致"的镜像管，在仿真里尺寸并不相等，
    ⇒ 仿真结果和优化的不是同一个电路 —— 而且**不会报错**（静默失效）。

所以：**47 是搜索空间，105 是回写面**。本脚本负责把搜索结果展开到回写面，
并用三条断言把这件事钉死（而不是靠人记得）。

用法
----
    # 1) 查看/校验模板（不需要任何优化结果）
    python expand_params.py --check

    # 2) 展开：把优化器给出的自由变量值写成 105 行的回写文件
    python expand_params.py --values best_values.csv --out params_writeback.txt

    # 3) 带初值来源（extractcdfVal_0.txt）：给 Dummy 等固定符号填值
    python expand_params.py --values best_values.csv --init extractcdfVal_0.txt \
                            --out params_writeback.txt

`--values` 支持两种格式（自动识别）：
    * `变量=值` 每行一条        （如 param_list_reduced.txt 的格式，值可空）
    * CSV，含表头 `变量名,值` 或 `var,value`
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from netlist_parser import parse_netlist          # noqa: E402

DEFAULT_TEMPLATE = os.path.join(HERE, os.pardir, "params_writeback_template.txt")
DEFAULT_NETLIST = os.path.join(HERE, os.pardir, os.pardir, "extracted",
                               "赛题数据本身", "netlist", "OPA_loopgain.netlist")


def _natkey(s: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def load_template(path: str) -> dict:
    """读回写模板：返回 {原始符号: 驱动来源}，来源形如 '@自由变量' 或 '#fixed'。"""
    out = {}
    with io.open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("//") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


def load_values(path: str) -> dict:
    """读优化结果：支持 `变量=值` 文本与 CSV（表头含 变量名/var）。"""
    with io.open(path, encoding="utf-8-sig") as f:
        text = f.read()
    out = {}
    first = text.splitlines()[0] if text.splitlines() else ""
    if "," in first:                                  # CSV
        rdr = csv.DictReader(io.StringIO(text))
        for row in rdr:
            name = (row.get("变量名") or row.get("var") or row.get("变量") or "").strip()
            val = (row.get("值") or row.get("value") or "").strip()
            if name:
                out[name] = val
    else:                                             # 变量=值
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("//") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


def load_init(path: str) -> dict:
    """读原理图初值文件（可选）：`符号=值`，用于给固定符号（Dummy）填值。"""
    out = {}
    if path and os.path.exists(path):
        with io.open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("//") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip()
    return out


def expand(template: dict, values: dict, init: dict, netlist: str):
    """按模板展开，返回 (行列表, 报告)。三条断言在这里执行。"""
    # ---- 断言 1：模板必须覆盖原理图的每一个符号，且不重复 ----
    net = parse_netlist(netlist)
    symbols = list(net.all_variables)
    dup = sorted({s for s in symbols if symbols.count(s) > 1})
    assert not dup, "原理图符号表里有重复：%s" % dup
    tpl_keys = set(template)
    miss = sorted(set(symbols) - tpl_keys, key=_natkey)
    extra = sorted(tpl_keys - set(symbols), key=_natkey)
    assert not miss, "模板缺符号（回写会静默失效）：%s" % miss
    assert not extra, "模板里有原理图不存在的符号：%s" % extra

    # ---- 展开：同组符号写同一个值 ----
    lines, fixed_missing, unknown = [], [], []
    group_values = {}
    for sym in sorted(symbols, key=_natkey):
        src = template[sym]
        if src.startswith("@"):
            var = src[1:]
            if var not in values or values[var] == "":
                # 值缺失：留空并登记（下游可据此判断"初值文件没提供"）
                lines.append((sym, "", "@" + var))
                unknown.append(sym)
                group_values.setdefault(var, set()).add("")
                continue
            val = values[var]
            group_values.setdefault(var, set()).add(val)
            lines.append((sym, val, "@" + var))
        elif src == "#fixed":
            val = init.get(sym, "")
            lines.append((sym, val, "#fixed"))
            if val == "":
                fixed_missing.append(sym)
        else:
            lines.append((sym, "", src))
            unknown.append(sym)

    # ---- 断言 2：同一组符号必须拿到同一个值（绑定关系的核心保证） ----
    bad = {v: sorted(vals) for v, vals in group_values.items() if len(vals) > 1}
    assert not bad, "同一自由变量被写成了不同值：%s" % bad

    # ---- 断言 3：展开结果重新解析后，符号集合必须与原始网表完全一致 ----
    text = "\n".join("%s=%s" % (s, v) for s, v, _ in lines) + "\n"
    parsed = {ln.split("=")[0].strip() for ln in text.splitlines() if "=" in ln}
    assert parsed == set(symbols), (
        "展开结果的符号集合与原始网表不一致：缺 %s，多 %s"
        % (sorted(set(symbols) - parsed), sorted(parsed - set(symbols))))

    report = {
        "n_symbols": len(symbols),
        "n_free_variables": len({v for v in template.values() if v.startswith("@")}),
        "n_fixed": len([1 for v in template.values() if v == "#fixed"]),
        "missing_values": sorted(set(unknown), key=_natkey),
        "fixed_missing": sorted(set(fixed_missing), key=_natkey),
    }
    return lines, report


def main() -> int:
    ap = argparse.ArgumentParser(description="模块二：把自由变量展开成原理图回写参数文件")
    ap.add_argument("--template", default=DEFAULT_TEMPLATE, help="回写模板路径")
    ap.add_argument("--netlist", default=DEFAULT_NETLIST, help="原始网表（用于核对符号集合）")
    ap.add_argument("--values", help="优化结果（变量=值 或 CSV）；--check 时不需要")
    ap.add_argument("--init", default="", help="原理图初值文件（可选，给固定符号填值）")
    ap.add_argument("--out", default="params_writeback.txt", help="输出的回写参数文件")
    ap.add_argument("--check", action="store_true", help="只校验模板与符号集合，不展开")
    args = ap.parse_args()

    if not os.path.exists(args.template):
        print("[错误] 找不到模板：%s\n先跑 `python agent.py --no-llm` 生成它。" % args.template)
        return 1
    template = load_template(args.template)
    print("模板：%s（%d 行）" % (args.template, len(template)))

    if args.check:
        lines, rep = expand(template, {}, load_init(args.init), args.netlist)
        print("✅ 模板校验通过：符号 %d 个（自由变量 %d 个 + 固定符号 %d 个）"
              % (rep["n_symbols"], rep["n_free_variables"], rep["n_fixed"]))
        print("   （--check 只校验覆盖关系，不检查数值）")
        return 0

    if not args.values:
        print("[错误] 指定 --values（优化结果），或用 --check 只做校验。")
        return 1
    values = load_values(args.values)
    init = load_init(args.init)
    print("优化结果：%s（%d 个变量%s）"
          % (args.values, len(values), "；含初值文件" if init else ""))
    lines, rep = expand(template, values, init, args.netlist)

    with io.open(args.out, "w", encoding="utf-8") as f:
        f.write("// 由 expand_params.py 生成：%d 个原理图符号（自由变量 %d 个）\n"
                % (rep["n_symbols"], rep["n_free_variables"]))
        for s, v, src in lines:
            f.write("%s=%s   // %s\n" % (s, v, src))
    print("✅ 已写出回写文件：%s" % args.out)
    print("   符号数 %d = 自由变量 %d + 固定符号 %d（断言 1/2/3 全部通过）"
          % (rep["n_symbols"], rep["n_free_variables"], rep["n_fixed"]))
    if rep["missing_values"]:
        print("   ⚠️ %d 个符号没拿到值（多为合并成员缺初值）：%s"
              % (len(rep["missing_values"]), ", ".join(rep["missing_values"][:12])))
    if rep["fixed_missing"]:
        print("   ⚠️ %d 个 Dummy 固定符号缺初值（用 --init extractcdfVal_0.txt 提供）：%s"
              % (len(rep["fixed_missing"]), ", ".join(rep["fixed_missing"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
