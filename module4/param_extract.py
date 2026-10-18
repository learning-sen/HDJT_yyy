#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块四-① 参数化脚本：把电路图里的器件尺寸导出成"待优化变量"

对应赛题模块四第 1 项：
    "电路图器件尺寸转为待优化变量的参数化脚本"

它做三件事
----------
1. 遍历 schematic 的实例，把可变尺寸参数（MOS: m/l/fw；电阻: segW/segL/segments；
   电容: m/l/fw）导出成**赛方格式**的参数文件（`"parameter","NAME","VALUE"`），
   与 `case1_params_0.txt` / `extractcdfVal_0.txt` 完全一致，可直接喂给
   模块三的优化器或 `sim_engine.py`。
2. 同时导出**增强元数据** `params_meta.json`：每个变量的器件/参数/当前值/单位/
   取值上下界/类型（连续 or 整数），供模块三构造搜索空间，不必再猜边界。
3. 打印统计（器件数、变量数、按参数类型分布），并与模块二的 105 个符号口径对照。

用法
----
    pythone param_extract.py --ae_lib 2026_EDA_case1 --ae_cell OPA --ae_view schematic \
        --out_dir ./param_out [--out_name extractcdfVal_0.txt]

    python param_extract.py --mock --out_dir ./param_out     # 本地验证

产物
----
    param_out/extractcdfVal_0.txt   赛方格式的待优化变量表
    param_out/params_meta.json      增强元数据（含边界/类型/器件归类）
    param_out/params_table.md       人读表格
"""
import argparse
import io
import json
import os
import sys

try:
    import pyAether as ae
except Exception:                       # pragma: no cover
    ae = None

DEFAULTS = {
    "ae_lib": "2026_EDA_case1",
    "ae_cell": "OPA",
    "ae_view": "schematic",
    "out_dir": "./param_out",
    "out_name": "extractcdfVal_0.txt",
}

# 每类器件导出的参数与边界（边界来自赛题附件 2：W 0.13~20µm、L 0.13~10µm、m 1~20）
KIND_SPEC = {
    "R": {"params": ("segW", "segL", "segments"),
          "bounds": {"segW": (0.13, 20.0), "segL": (0.13, 20.0), "segments": (1, 20)},
          "integer": ("segments",)},
    "C": {"params": ("m", "l", "fw"),
          "bounds": {"m": (1, 20), "l": (0.13, 20.0), "fw": (0.13, 20.0)},
          "integer": ("m",)},
    "MOS": {"params": ("m", "l", "fw"),
            "bounds": {"m": (1, 20), "l": (0.13, 10.0), "fw": (0.13, 20.0)},
            "integer": ("m",)},
}

UNIT = {"segW": "µm", "segL": "µm", "segments": "-", "m": "-", "l": "µm", "fw": "µm"}


def kind_of(inst_name):
    """按实例名前缀判类型：R* 电阻 / C* 电容 / NM|PM 晶体管 / 其它跳过。"""
    n = str(inst_name)
    if n[:1] in ("R", "r"):
        return "R"
    if n[:1] in ("C", "c"):
        return "C"
    if n.startswith(("NM", "PM", "nm", "pm")):
        return "MOS"
    return None


def param_to_float(raw):
    """'4u' / '1e-6' / '2' -> float（SI 数值）。"""
    s = str(raw).strip().strip('"').strip("'")
    mult = 1.0
    for suf, m in (("meg", 1e6), ("k", 1e3), ("u", 1e-6), ("n", 1e-9),
                   ("p", 1e-12), ("f", 1e-15), ("m", 1e-3)):
        if s.lower().endswith(suf):
            mult = m
            s = s[: -len(suf)]
            break
    return float(s) * mult


def format_like_schematic(raw):
    """把原始值原样返回（赛方格式里保留 '4u' 这种写法最稳妥）。"""
    return str(raw).strip().strip('"').strip("'")


# ---------------------------------------------------------------------------
# 真机导出
# ---------------------------------------------------------------------------
def export_from_cv(lib, cell, view):
    """返回 [(symbol, raw_value, kind, param)]。"""
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
            for p in KIND_SPEC[kind]["params"]:
                try:
                    raw = ae.aeEmyInstGetParameter(p, inst)
                except Exception as e:
                    print("WARN: 读取 %s.%s 失败: %s" % (inst.name, p, e))
                    continue
                if raw is None or str(raw).strip() == "":
                    continue
                rows.append(("%s_%s" % (inst.name, p), format_like_schematic(raw), kind, p))
    finally:
        try:
            ae.dbCloseCV(cv)
        except Exception:
            pass
    return rows


def mock_rows():
    """本地验证用的小电路：2 MOS + 1 R + 1 C。"""
    return [
        ("NM0_m", "8", "MOS", "m"), ("NM0_l", "1u", "MOS", "l"), ("NM0_fw", "4u", "MOS", "fw"),
        ("PM0_m", "2", "MOS", "m"), ("PM0_l", "4u", "MOS", "l"), ("PM0_fw", "4u", "MOS", "fw"),
        ("R0_segW", "2u", "R", "segW"), ("R0_segL", "25u", "R", "segL"),
        ("C0_m", "1", "C", "m"), ("C0_l", "20u", "C", "l"), ("C0_fw", "20u", "C", "fw"),
    ]


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------
def write_outputs(rows, out_dir, out_name, source_note):
    os.makedirs(out_dir, exist_ok=True)
    # 1) 赛方格式（与 case1_params_0.txt / extractcdfVal_0.txt 一致）
    param_path = os.path.join(out_dir, out_name)
    with io.open(param_path, "w", encoding="utf-8", newline="\n") as f:
        for sym, raw, _kind, _p in rows:
            f.write('"parameter","%s","%s"\n' % (sym, raw))

    # 2) 增强元数据
    meta = []
    for sym, raw, kind, p in rows:
        inst = sym[: -(len(p) + 1)]
        lo, hi = KIND_SPEC[kind]["bounds"][p]
        try:
            val = param_to_float(raw)
            val_um = val * 1e6 if p in ("segW", "segL", "l", "fw") else val
        except Exception:
            val_um = None
        meta.append({
            "symbol": sym, "inst": inst, "param": p, "kind": kind,
            "raw": raw, "value_um": val_um,
            "unit": UNIT.get(p, ""),
            "min": lo, "max": hi,
            "type": "integer" if p in KIND_SPEC[kind]["integer"] else "continuous",
        })
    with io.open(os.path.join(out_dir, "params_meta.json"), "w", encoding="utf-8") as f:
        json.dump({"source": source_note, "n_vars": len(meta), "variables": meta},
                  f, ensure_ascii=False, indent=1)

    # 3) 人读表格
    by_kind = {}
    by_param = {}
    for m in meta:
        by_kind[m["kind"]] = by_kind.get(m["kind"], 0) + 1
        by_param[m["param"]] = by_param.get(m["param"], 0) + 1
    lines = [
        "# 待优化变量（参数化脚本导出）", "",
        "- 来源：%s" % source_note,
        "- 变量总数：**%d**" % len(meta),
        "- 按器件类型：%s" % ", ".join("%s=%d" % (k, v) for k, v in sorted(by_kind.items())),
        "- 按参数类型：%s" % ", ".join("%s=%d" % (k, v) for k, v in sorted(by_param.items())),
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
    print("     元数据: %s" % os.path.join(out_dir, "params_meta.json"))
    print("     表格  : %s" % os.path.join(out_dir, "params_table.md"))
    return meta


def main(argv=None):
    ap = argparse.ArgumentParser(description="模块四-① 参数化：导出待优化变量")
    ap.add_argument("--ae_lib", default=DEFAULTS["ae_lib"])
    ap.add_argument("--ae_cell", default=DEFAULTS["ae_cell"])
    ap.add_argument("--ae_view", default=DEFAULTS["ae_view"])
    ap.add_argument("--out_dir", default=DEFAULTS["out_dir"])
    ap.add_argument("--out_name", default=DEFAULTS["out_name"])
    ap.add_argument("--mock", action="store_true", help="本地验证（假数据，不需要 PyAether）")
    a = ap.parse_args(argv)

    if a.mock:
        rows = mock_rows()
        note = "mock（假电路：NM0/PM0/R0/C0）"
    else:
        if ae is None:
            print("ERROR: 未导入 pyAether；请在服务器上 source setup.bash 后运行，或加 --mock",
                  file=sys.stderr)
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

    meta = write_outputs(rows, a.out_dir, a.out_name, note)

    # 与模块二的 105 个符号口径对照（只做提示，不做断言：Hidden 电路规模不同）
    n_mos = sum(1 for m in meta if m["kind"] == "MOS")
    if n_mos:
        print("     提示: 本次导出 %d 个 MOS 变量；Public 电路模块二口径为 105 个符号（含 R/C）"
              % n_mos)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
