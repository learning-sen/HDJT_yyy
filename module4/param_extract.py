#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块四-① 参数化脚本：把电路图里的器件尺寸导出成"待优化变量"

对应赛题模块四第 1 项：「电路图器件尺寸转为待优化变量的参数化脚本」

做三件事
--------
1. 遍历 schematic，把**真实 schema** 的尺寸参数导出成赛方格式
   （`"parameter","NAME","VALUE"`），可直接喂给模块三优化器或 `sim_engine.py`。
2. 导出增强元数据 `params_meta.json`：器件/参数/当前值/单位/**上下界**/类型，
   供模块三构造搜索空间（不用再猜边界）。
3. 打印统计，并与赛方真实口径对照（Public 电路 = **105** 个变量）。

真实 schema（2026-10-18 用真实 `case1_params_0.txt` 反推，见 module3/修正说明.md P0-4）
--------------------------------------------------------------------------------
    105 = MOS 29×3 (`m,l,fw`) + 电容 6×1 (**只有 `l`**) + 电阻 6×2 (`segL,segW`)
    —— 电容的 `fw/m`、电阻的 `segments` 都在参数文件之外（score.py 直接从电路 CV 读）。

边界（P0-3，严格对齐 score.py::read_parameters 的 clamp）
--------------------------------------------------------
    fw 0.15..50 | segW 0.42..10 | segL 5..100 | 电容 l 4..30 | 其它 l 0.13..20 | m/segments 整数 1..100

用法
----
    pythone param_extract.py --ae_lib 2026_EDA_case1 --ae_cell OPA --ae_view schematic \
        --out_dir ./param_out [--out_name extractcdfVal_0.txt] [--expect 105]

    python param_extract.py --mock --out_dir ./param_out      # 本地验证

产物：extractcdfVal_0.txt / params_meta.json / params_table.md
"""
import argparse
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m4_common import (EXPORT_SCHEMA, UNIT, bounds_for, kind_of, param_to_float)

ae = None            # 惰性加载：只有真机模式才 import pyAether
                     # （import pyAether 会加载 OpenAccess 并检出一个 license，
                     #   --mock / 纯解析路径绝不能碰，否则在共享服务器上白占名额）


def _load_ae():
    """真机模式才加载 pyAether；返回模块对象。"""
    global ae
    if ae is None:
        from m4_common import load_aether
        ae = load_aether()
    return ae
DEFAULTS = {
    "ae_lib": "2026_EDA_case1",
    "ae_cell": "OPA",
    "ae_view": "schematic",
    "out_dir": "./param_out",
    "out_name": "extractcdfVal_0.txt",
    "expect": 105,        # Public 电路的真实变量数；Hidden 不同，仅作提示
}


# ---------------------------------------------------------------------------
# 导出
# ---------------------------------------------------------------------------
def export_from_cv(lib, cell, view):
    """返回 [(symbol, raw_value, kind, param)]，schema 见 EXPORT_SCHEMA。"""
    _load_ae()
    if ae is None:
        raise RuntimeError("未导入 pyAether")
    ae.emyInitAether("-adv")
    cv = ae.dbOpenCV(lib, cell, view)
    if not cv:
        raise RuntimeError("dbOpenCV(%s,%s,%s) 失败" % (lib, cell, view))
    rows = []
    try:
        for inst in cv.instances:
            kind = kind_of(inst.name)
            if kind is None:
                continue
            for p in EXPORT_SCHEMA[kind]:
                try:
                    raw = ae.aeEmyInstGetParameter(p, inst)
                except Exception as e:
                    print("WARN: 读取 %s.%s 失败: %s" % (inst.name, p, e))
                    continue
                if raw is None or str(raw).strip() == "":
                    continue
                rows.append(("%s_%s" % (inst.name, p), str(raw).strip().strip('"'), kind, p))
    finally:
        try:
            ae.dbCloseCV(cv)
        except Exception:
            pass
    return rows


def mock_rows():
    """本地验证用的小电路：2 MOS + 1 R + 1 C（按真实 schema：3+3+2+1 = 9 个变量）。"""
    return [
        ("NM0_m", "8", "MOS", "m"), ("NM0_l", "1u", "MOS", "l"), ("NM0_fw", "4u", "MOS", "fw"),
        ("PM0_m", "2", "MOS", "m"), ("PM0_l", "4u", "MOS", "l"), ("PM0_fw", "4u", "MOS", "fw"),
        ("R0_segW", "2u", "R", "segW"), ("R0_segL", "25u", "R", "segL"),
        ("C0_l", "20u", "C", "l"),
    ]


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------
def write_outputs(rows, out_dir, out_name, source_note):
    os.makedirs(out_dir, exist_ok=True)
    param_path = os.path.join(out_dir, out_name)
    with io.open(param_path, "w", encoding="utf-8", newline="\n") as f:
        for sym, raw, _k, _p in rows:
            f.write('"parameter","%s","%s"\n' % (sym, raw))

    meta = []
    for sym, raw, kind, p in rows:
        inst = sym[: -(len(p) + 1)]
        lo, hi, is_int = bounds_for(kind, p)
        val_um = None
        if p not in ("m", "segments", "multi"):
            try:
                val_um = param_to_float(raw)
            except ValueError:
                pass
        else:
            try:
                val_um = float(raw)
            except ValueError:
                pass
        meta.append({"symbol": sym, "inst": inst, "param": p, "kind": kind,
                     "raw": raw, "value_um": val_um, "unit": UNIT.get(p, ""),
                     "min": lo, "max": hi, "type": "integer" if is_int else "continuous"})

    with io.open(os.path.join(out_dir, "params_meta.json"), "w", encoding="utf-8") as f:
        json.dump({"source": source_note, "n_vars": len(meta), "schema": EXPORT_SCHEMA,
                   "variables": meta}, f, ensure_ascii=False, indent=1)

    by_kind, by_param = {}, {}
    for m in meta:
        by_kind[m["kind"]] = by_kind.get(m["kind"], 0) + 1
        by_param[m["param"]] = by_param.get(m["param"], 0) + 1
    # 越界检查（很重要：优化空间必须落在评分器的 clamp 内）
    out_of_range = []
    for m in meta:
        if m["value_um"] is None:
            continue
        if not (m["min"] - 1e-12 <= m["value_um"] <= m["max"] + 1e-12):
            out_of_range.append((m["symbol"], m["value_um"], m["min"], m["max"]))

    lines = [
        "# 待优化变量（参数化脚本导出）", "",
        "- 来源：%s" % source_note,
        "- 变量总数：**%d**" % len(meta),
        "- 按器件类型：%s" % ", ".join("%s=%d" % kv for kv in sorted(by_kind.items())),
        "- 按参数类型：%s" % ", ".join("%s=%d" % kv for kv in sorted(by_param.items())),
        "- schema：MOS=%s / C=%s / R=%s" % (EXPORT_SCHEMA["MOS"], EXPORT_SCHEMA["C"], EXPORT_SCHEMA["R"]),
        "- 越界变量：%d" % len(out_of_range),
        "", "| 变量 | 器件 | 参数 | 当前值 | 单位 | 下界 | 上界 | 类型 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for m in meta:
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s |"
                     % (m["symbol"], m["inst"], m["param"], m["raw"], m["unit"],
                        m["min"], m["max"], m["type"]))
    with io.open(os.path.join(out_dir, "params_table.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")

    print("==== 导出 %d 个待优化变量 -> %s ====" % (len(meta), param_path))
    print("     器件类型分布: %s" % dict(sorted(by_kind.items())))
    print("     参数类型分布: %s" % dict(sorted(by_param.items())))
    if out_of_range:
        print("     ⚠️ 有 %d 个变量超出评分器 clamp（会被 score.py 夹住）:" % len(out_of_range))
        for s, v, lo, hi in out_of_range[:8]:
            print("        %s = %s 不在 [%s, %s]" % (s, v, lo, hi))
    print("     元数据: %s" % os.path.join(out_dir, "params_meta.json"))
    print("     表格  : %s" % os.path.join(out_dir, "params_table.md"))
    return meta, out_of_range


def main(argv=None):
    ap = argparse.ArgumentParser(description="模块四-① 参数化：导出待优化变量")
    ap.add_argument("--ae_lib", default=DEFAULTS["ae_lib"])
    ap.add_argument("--ae_cell", default=DEFAULTS["ae_cell"])
    ap.add_argument("--ae_view", default=DEFAULTS["ae_view"])
    ap.add_argument("--out_dir", default=DEFAULTS["out_dir"])
    ap.add_argument("--out_name", default=DEFAULTS["out_name"])
    ap.add_argument("--expect", type=int, default=DEFAULTS["expect"],
                    help="期望变量数（Public=105；Hidden 不同，只作提示）")
    ap.add_argument("--mock", action="store_true", help="本地验证（假数据，不需要 PyAether）")
    a = ap.parse_args(argv)

    if a.mock:
        rows = mock_rows()
        note = "mock（假电路：NM0/PM0/R0/C0，按真实 schema）"
    else:
        try:
            _load_ae()
        except Exception as e:
            print("ERROR: 未导入 pyAether（%s）；请在服务器上 source setup.bash 后运行，"
                  "或加 --mock" % e, file=sys.stderr)
            return 2
        try:
            rows = export_from_cv(a.ae_lib, a.ae_cell, a.ae_view)
        except Exception as e:
            print("ERROR: %s" % e, file=sys.stderr)
            return 3
        note = "%s/%s/%s" % (a.ae_lib, a.ae_cell, a.ae_view)

    if not rows:
        print("ERROR: 没有导出任何变量（检查器件名前缀是否为 R/C/NM/PM）", file=sys.stderr)
        return 4

    meta, out_of_range = write_outputs(rows, a.out_dir, a.out_name, note)

    if not a.mock and a.expect and len(meta) != a.expect:
        print("     ⚠️ 变量数 %d 与期望 %d 不同：Public 电路应为 %d；"
              "Hidden 电路规模不同属正常。" % (len(meta), a.expect, a.expect))
    return 0 if not out_of_range else 1


if __name__ == "__main__":
    raise SystemExit(main())
