#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块四-③ 仿真引擎：输入尺寸参数文件 -> 调用 MDE 跑 PVT -> 输出最坏情况性能指标

对应赛题模块四第 3 项：「调用 MDE 完成 PVT 仿真、提取性能指标的仿真引擎脚本」

相对初版的改进（依据 2026-10-18 服务器实测，见 module3/修正说明.md）
--------------------------------------------------------------------------
1. **[P0-8] 自动修复 MDE 旧路径**：MDE corner 配置里写死了旧机绝对路径
   （`/home/eda_2025/...`），当前环境是另一套目录 → 仿真必报
   `File does not exist` → 指标全空 → 最终 0 分。本脚本在 `emyInitAether` **之前**
   自动扫描 setting/adeL2View.file/*.scs，把不存在的旧路径重定向到
   `<当前目录>/hes_release/...`（仅当新位置确实存在，原文件备份为 *.m4bak）。
2. **[P0-3] 变量边界与 `score.py` 一致**：`fw` 0.15..50、`segW` 0.42..10、
   `segL` 5..100、电容 `l` 4..30、其它 `l` 0.13..20、`m` 整数 1..100。
   （统一放在 m4_common.py，模块四各脚本共用一份）
3. **[P0-4] schema 校验**：真实 `case1_params_0.txt` 是 105 个变量 =
   MOS 29×3(`m,l,fw`) + 电容 6×1(`l`) + 电阻 6×2(`segL,segW`)。
   文件里若出现不该有的参数（如电容的 `fw/m`）会给出提示。

用法
----
    pythone sim_engine.py --ae_lib 2026_EDA_case1 --ae_cell OPA --ae_view schematic \
        --mde_cell OPA_loopgain --mde_view spe_state1_Corner \
        --param_file case1_params_0.txt --out_dir ./sim_results

    # 只修复路径、不仿真（先确认 P0-8 是否命中）
    pythone sim_engine.py ... --fix_paths_only

    # 本地验证（不需要 PyAether）
    python sim_engine.py --mock --out_dir ./sim_results

产物：metrics.json / metrics.csv / metrics.md / raw/
指标口径与 score.py 一致：PM/Gain/UGB 取所有角的 Min，GM/I_OPA 取 Max；
面积 MOS=fw·L·m·1.5、电容=fw·L·m、电阻=segW·segL·segments·2（单位 µm²）。
"""
import argparse
import csv
import glob
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m4_common import (EXPORT_SCHEMA, bounds_for, dimensionless, fix_sim_paths,
                       kind_of, param_to_float, parse_param_line, read_param_file,
                       schema_check, split_inst_param, write_param_file)

try:
    import pyAether as ae
except Exception:                       # pragma: no cover
    ae = None


DEFAULTS = {
    "ae_lib": "2026_EDA_case1",
    "ae_cell": "OPA",
    "ae_view": "schematic",
    "mde_cell": "OPA_loopgain",
    "mde_view": "spe_state1_Corner",
    "out_dir": "./sim_results",
}

# 指标 -> 取值方向（True=取 Min，False=取 Max）
WORST_DIR = {"Phase_Margin": True, "Gain_db": True, "UGB": True,
             "Gain_Margin": False, "I_OPA": False}

# 评分门限（score.py 实测；与 run_score.sh 的 base 参数一致）
LIMITS = {
    "Phase_Margin": ("min", 50.0, "deg"),
    "Gain_Margin": ("max", -10.0, "dB"),
    "I_OPA": ("max", 0.003, "A"),
    "Gain_db": ("min", 20.0, "dB"),
}
AREA_BASE = 8000.0
UGB_BASE = 2.0e8
GAIN_BASE = 20.0


# ---------------------------------------------------------------------------
# 指标解析 / 聚合 / 判定
# ---------------------------------------------------------------------------
def parse_summary_csv(path):
    """解析 MDE 的 *_summary.csv（列：Output, Min, Max，可能还有 Typ）。"""
    rows = {}
    with io.open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
        for row in csv.DictReader(f):
            out = (row.get("Output") or "").strip()
            if not out:
                continue

            def num(key):
                v = (row.get(key) or "").strip()
                if v == "":
                    return None
                try:
                    return float(v)
                except ValueError:
                    return None
            rows[out] = {"min": num("Min"), "max": num("Max"), "typ": num("Typ")}
    return rows


def worst_case(rows):
    metrics = {}
    for name, take_min in WORST_DIR.items():
        r = rows.get(name) or {}
        metrics[name] = r.get("min") if take_min else r.get("max")
    return metrics


def judge(metrics, area_um2):
    """按 score.py 门限逐项判定 + 估算分（不含时间分）。"""
    ok = {}
    for name, (mode, lim, _u) in LIMITS.items():
        v = metrics.get(name)
        ok[name] = None if v is None else ((v >= lim) if mode == "min" else (v <= lim))
    score = 0.0
    if ok.get("Phase_Margin"):
        score += 10.0
    if ok.get("Gain_Margin"):
        score += 10.0
    if ok.get("I_OPA"):
        score += 10.0
    g = metrics.get("Gain_db")
    if g is not None and g >= GAIN_BASE:
        score += min(g / GAIN_BASE, 1.0) * 10.0
    u = metrics.get("UGB")
    if u is not None and u > 1.0:
        score += min(u / UGB_BASE, 1.0) * 15.0
    if area_um2 and area_um2 > 1.0:
        score += min(AREA_BASE / area_um2, 1.0) * 25.0
    feasible = all(v for v in ok.values()) and bool(ok.get("Gain_db"))
    return {"per_item": ok, "est_score_no_time": round(score, 2), "feasible": bool(feasible)}


# ---------------------------------------------------------------------------
# 面积（与 score.py::calc_area 完全一致；真机从电路 CV 读，mock 用近似）
# ---------------------------------------------------------------------------
def calc_area_from_cv(cv):
    """遍历 schematic 实例算总面积（µm²）。需 PyAether。"""
    if ae is None or cv is None:
        return None
    total, detail = 0.0, []
    for inst in cv.instances:
        name = str(inst.name)
        try:
            if name[:1] in ("R", "r"):
                segw = param_to_float(ae.aeEmyInstGetParameter("segW", inst))
                segl = param_to_float(ae.aeEmyInstGetParameter("segL", inst))
                segs = float(ae.aeEmyInstGetParameter("segments", inst))
                a = segw * segl * segs * 2.0
            elif name[:1] in ("C", "c"):
                fw = param_to_float(ae.aeEmyInstGetParameter("fw", inst))
                l = param_to_float(ae.aeEmyInstGetParameter("l", inst))
                m = float(ae.aeEmyInstGetParameter("m", inst))
                a = fw * l * m
            elif name.startswith(("PM", "NM")):
                fw = param_to_float(ae.aeEmyInstGetParameter("fw", inst))
                l = param_to_float(ae.aeEmyInstGetParameter("l", inst))
                m = float(ae.aeEmyInstGetParameter("m", inst))
                a = fw * l * m * 1.5
            else:
                continue
        except Exception as e:
            print("WARN: 面积计算跳过 %s: %s" % (name, e))
            continue
        total += a
        detail.append({"inst": name, "area_um2": a})
    return total, detail


def calc_area_from_params(params):
    """没有 PyAether 时的近似：只能算 MOS 与电阻（电容在参数文件里只有 l，缺 fw/m）。"""
    per_inst = {}
    for name, raw in params.items():
        inst, p = split_inst_param(name)
        per_inst.setdefault(inst, {})[p] = raw
    total = 0.0
    for inst, p in per_inst.items():
        kind = kind_of(inst)
        try:
            if kind == "R":
                total += param_to_float(p["segW"]) * param_to_float(p["segL"]) * 10.0 * 2.0
            elif kind == "MOS":
                total += param_to_float(p["fw"]) * param_to_float(p["l"]) * dimensionless(p["m"]) * 1.5
        except (KeyError, ValueError):
            continue
    return total


# ---------------------------------------------------------------------------
# 写参数（反标）
# ---------------------------------------------------------------------------
def apply_params(cv, params, verbose=True):
    if ae is None:
        raise RuntimeError("无 PyAether：apply_params 只能在服务器上执行")
    failed = []
    for name, raw in params.items():
        inst_name, param_name = split_inst_param(name)
        inst = ae.dbFindInst(cv=cv, name=inst_name)
        if not inst:
            failed.append((name, "instance not found"))
            continue
        if not ae.cdfSetParam(inst, param_name, str(raw)):
            failed.append((name, "cdfSetParam returned false"))
    if verbose:
        print("==== 写入参数 %d 个，失败 %d 个 ====" % (len(params), len(failed)))
    return failed


def save_design(cv):
    if ae is None:
        return None
    res = ae.dbCheckAndSaveDesign(cv)
    print("==== dbCheckAndSaveDesign -> %s ====" % res)
    return res


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def run_simulation(a):
    if ae is None:
        raise RuntimeError("未导入 pyAether：请在服务器上（source setup.bash 后）运行")
    out_dir = a.out_dir
    os.makedirs(out_dir, exist_ok=True)
    raw_dir = os.path.join(out_dir, "raw")
    os.makedirs(raw_dir, exist_ok=True)

    # [P0-8] 必须在 emyInitAether 之前修路径
    path_fix = None
    if not a.no_fix_paths:
        path_fix = fix_sim_paths(os.getcwd(), backup=True)

    ae.emyInitAether("-adv")

    params = read_param_file(a.param_file)
    print("==== 读取参数 %d 个：%s ====" % (len(params), a.param_file))
    unknown = schema_check(params)
    if unknown:
        print("WARN: [P0-4] 参数文件里有 %d 个不在真实 schema 内的参数（只提示，不阻断）:"
              % len(unknown))
        for u in unknown[:10]:
            print("        " + u)

    cv = ae.dbOpenCV(a.ae_lib, a.ae_cell, a.ae_view)
    if not cv:
        raise RuntimeError("dbOpenCV(%s, %s, %s) 失败" % (a.ae_lib, a.ae_cell, a.ae_view))
    failed = apply_params(cv, params)
    save_design(cv)
    area = None
    try:
        area = calc_area_from_cv(cv)
    except Exception as e:
        print("WARN: 面积计算失败: %s" % e)
    ae.dbCloseCV(cv)

    mde = ae.MdeSession.open(a.ae_lib, a.mde_cell, a.mde_view)
    if not mde:
        raise RuntimeError("MdeSession.open 失败: %s" % getattr(ae.MdeSession, "s", ""))
    try:
        print("==== MDE 工程目录: %s ====" % mde.getSetting().getProjectDirectory())
        if not mde.createSimulationNetlist():
            raise RuntimeError("createSimulationNetlist 失败（多半是 [P0-8] 旧路径没修掉）")
        result = mde.netlistAndRun()
        if not result or not result.isValid():
            raise RuntimeError("仿真失败: %s" % (mde.lastError() or "invalid result"))
        result.saveResultsToDir(raw_dir)
        result_name = result.name()
        print("==== 仿真完成，结果名: %s ====" % result_name)
    finally:
        try:
            mde.close()
        except Exception:
            pass

    cands = sorted(glob.glob(os.path.join(raw_dir, "**", "*summary*.csv"), recursive=True),
                   key=os.path.getmtime, reverse=True)
    if not cands:
        cands = [p for p in glob.glob(os.path.join(raw_dir, "**", "*.csv"), recursive=True)
                 if not p.endswith("result.txt")]
    if not cands:
        raise RuntimeError("找不到 MDE 的 summary CSV，请检查结果目录: %s" % raw_dir)
    rows = parse_summary_csv(cands[0])
    print("==== 解析 %s：%d 个 Output ====" % (cands[0], len(rows)))

    metrics = worst_case(rows)
    area_um2 = area[0] if isinstance(area, tuple) else area
    payload = {
        "param_file": os.path.abspath(a.param_file),
        "ae": {"lib": a.ae_lib, "cell": a.ae_cell, "view": a.ae_view},
        "mde": {"cell": a.mde_cell, "view": a.mde_view},
        "n_params": len(params),
        "schema_unknown": unknown,
        "path_fix": path_fix,
        "apply_failed": failed,
        "metrics_worst_case": metrics,
        "area_um2": area_um2,
        "raw_rows": rows,
        "verdict": judge(metrics, area_um2),
        "result_name": result_name,
    }
    emit_outputs(out_dir, payload)
    return payload


def run_mock(a):
    """本地：伪造 MDE summary，走完整解析/聚合/输出链路。"""
    raw_dir = os.path.join(a.out_dir, "raw")
    os.makedirs(raw_dir, exist_ok=True)
    fake = os.path.join(raw_dir, "Results_mock_summary.csv")
    with io.open(fake, "w", encoding="utf-8", newline="") as f:
        f.write("Output,Min,Max,Typ\n")
        f.write("Phase_Margin,52.4,61.2,57.1\n")
        f.write("Gain_db,44.8,49.1,47.0\n")
        f.write("UGB,1.85e8,2.31e8,2.05e8\n")
        f.write("Gain_Margin,-13.1,-11.2,-12.0\n")
        f.write("I_OPA,0.0012,0.0027,0.0019\n")
    params = read_param_file(a.param_file) if (a.param_file and os.path.exists(a.param_file)) else {}
    area = a.mock_area
    if params:
        approx = calc_area_from_params(params)
        if approx > 0:
            area = approx
    rows = parse_summary_csv(fake)
    metrics = worst_case(rows)
    payload = {
        "param_file": a.param_file or "(mock)",
        "ae": {"lib": a.ae_lib, "cell": a.ae_cell, "view": a.ae_view},
        "mde": {"cell": a.mde_cell, "view": a.mde_view},
        "n_params": len(params),
        "schema_unknown": [],
        "path_fix": None,
        "apply_failed": [],
        "metrics_worst_case": metrics,
        "area_um2": area,
        "raw_rows": rows,
        "verdict": judge(metrics, area),
        "result_name": "Results_mock",
        "mock": True,
    }
    emit_outputs(a.out_dir, payload)
    return payload


def run_fix_paths_only(a):
    res = fix_sim_paths(os.getcwd(), backup=True)
    return 0 if res["modified"] > 0 else 1


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------
def emit_outputs(out_dir, payload):
    os.makedirs(out_dir, exist_ok=True)
    with io.open(os.path.join(out_dir, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1, default=str)

    m = payload["metrics_worst_case"]
    units = {"Phase_Margin": "deg", "Gain_Margin": "dB", "I_OPA": "A",
             "Gain_db": "dB", "UGB": "Hz"}
    with io.open(os.path.join(out_dir, "metrics.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", "worst_value", "unit", "limit", "pass"])
        for k, v in m.items():
            lim = LIMITS.get(k)
            w.writerow([k, v, units.get(k, ""), lim[1] if lim else "",
                        payload["verdict"]["per_item"].get(k)])
        w.writerow(["Total_Area", payload["area_um2"], "um^2", AREA_BASE, None])

    lines = ["# PVT 仿真结果", "",
             "- 电路：`%s / %s / %s`" % (payload["ae"]["lib"], payload["ae"]["cell"], payload["ae"]["view"]),
             "- MDE：`%s / %s`" % (payload["mde"]["cell"], payload["mde"]["view"]),
             "- 参数文件：`%s`（%d 个符号）" % (payload["param_file"], payload["n_params"]),
             "- 最坏情况聚合：PM/Gain/UGB 取 Min，GM/I_OPA 取 Max",
             "- 估算分（不含时间分）：**%.2f / 80**" % payload["verdict"]["est_score_no_time"],
             "- 三条硬约束：%s" % ("全部满足 ✅" if payload["verdict"]["feasible"] else "**未满足** ❌")]
    pf = payload.get("path_fix")
    if pf:
        lines.append("- [P0-8] 旧路径修复：扫描 %d 个文件，改动 %d 个" % (pf["scanned"], pf["modified"]))
    lines += ["", "| 指标 | 最坏值 | 单位 | 门限 | 判定 |", "|---|---|---|---|---|"]
    for k, v in m.items():
        lim = LIMITS.get(k)
        jv = payload["verdict"]["per_item"].get(k)
        mark = "✅" if jv else ("❌" if jv is not None else "—")
        lines.append("| %s | %s | %s | %s | %s |"
                     % (k, ("%.6g" % v) if isinstance(v, (int, float)) else v,
                        units.get(k, ""), lim[1] if lim else "越大越好", mark))
    lines.append("| Total_Area | %.1f | um² | ≤ %.0f 满分 | %s |"
                 % (payload["area_um2"] or 0, AREA_BASE,
                    "✅" if (payload["area_um2"] or 1e9) <= AREA_BASE else "⚠️"))
    if payload.get("schema_unknown"):
        lines += ["", "## ⚠️ schema 提示（[P0-4]）", ""] + ["- " + u for u in payload["schema_unknown"][:15]]
    if payload.get("apply_failed"):
        lines += ["", "## 写参数失败项", ""] + ["- `%s`: %s" % (n, r) for n, r in payload["apply_failed"]]
    if payload.get("mock"):
        lines += ["", "> ⚠️ 本次为 `--mock` 模式（假数据），仅验证解析/聚合/输出链路。"]
    with io.open(os.path.join(out_dir, "metrics.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")

    print("\n==== 最坏情况指标 ====")
    for k, v in m.items():
        print("  %-14s %s" % (k, v))
    print("  %-14s %s um^2" % ("Total_Area", payload["area_um2"]))
    print("  估算分(不含时间分): %.2f / 80  可行: %s"
          % (payload["verdict"]["est_score_no_time"], payload["verdict"]["feasible"]))
    print("==== 已写出 %s/{metrics.json, metrics.csv, metrics.md} ====" % out_dir)


def build_parser():
    p = argparse.ArgumentParser(description="模块四-③ PVT 仿真引擎（调用 MDE，提取指标）")
    p.add_argument("--ae_lib", default=DEFAULTS["ae_lib"])
    p.add_argument("--ae_cell", default=DEFAULTS["ae_cell"])
    p.add_argument("--ae_view", default=DEFAULTS["ae_view"])
    p.add_argument("--mde_cell", default=DEFAULTS["mde_cell"])
    p.add_argument("--mde_view", default=DEFAULTS["mde_view"])
    p.add_argument("--param_file", default="case1_params_0.txt")
    p.add_argument("--out_dir", default=DEFAULTS["out_dir"])
    p.add_argument("--mock", action="store_true", help="本地验证模式（假数据，不需要 PyAether）")
    p.add_argument("--mock_area", type=float, default=5200.0, help="--mock 时使用的面积（µm²）")
    p.add_argument("--no_fix_paths", action="store_true", help="跳过 [P0-8] 旧路径修复")
    p.add_argument("--fix_paths_only", action="store_true", help="只修复旧路径，不仿真")
    p.add_argument("--dry_run", action="store_true", help="只写参数、不跑仿真")
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    if a.fix_paths_only:
        return run_fix_paths_only(a)
    if a.mock:
        run_mock(a)
        return 0
    if ae is None:
        print("ERROR: 未导入 pyAether。请在服务器上 source setup.bash 后运行，"
              "或加 --mock 在本地验证链路。", file=sys.stderr)
        return 2
    if a.dry_run:
        if not a.no_fix_paths:
            fix_sim_paths(os.getcwd(), backup=True)
        ae.emyInitAether("-adv")
        params = read_param_file(a.param_file)
        cv = ae.dbOpenCV(a.ae_lib, a.ae_cell, a.ae_view)
        if not cv:
            print("ERROR: dbOpenCV 失败", file=sys.stderr)
            return 3
        failed = apply_params(cv, params)
        save_design(cv)
        ae.dbCloseCV(cv)
        print("==== dry-run 完成：%d 个参数，失败 %d 个 ====" % (len(params), len(failed)))
        return 0 if not failed else 4
    try:
        run_simulation(a)
        return 0
    except Exception as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
