#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块四-① 仿真引擎：输入尺寸参数文件 -> 调用 MDE 跑 PVT -> 输出最坏情况性能指标

用途（对应 `任务分析.docx` 模块四①）：
    "调用 MDE 完成 PVT 仿真、提取性能指标的仿真引擎脚本"

用法
----
    # 真机（服务器上，需先 source setup.bash）
    pythone sim_engine.py --ae_lib 2026_EDA_case1 --ae_cell OPA --ae_view schematic \
        --mde_cell OPA_loopgain --mde_view spe_state1_Corner \
        --param_file case1_params_0.txt --out_dir ./sim_results

    # 只写参数不仿真（验证参数格式/反标用）
    pythone sim_engine.py ... --dry_run

    # 本地验证（不需要 PyAether）：造一份假结果，把解析/聚合/输出链路跑通
    python sim_engine.py --mock --out_dir ./sim_results

产物（--out_dir 下）
-------------------
    metrics.json   最坏情况指标 + 面积 + 可行性与逐项判定
    metrics.csv    一行一指标（Excel 可开）
    metrics.md     Markdown 表格（可直接贴技术报告）
    raw/           原始 summary.csv、result.txt、params.txt

指标口径（与赛方 score.py / optimization.py 一致）
-----------------------------------------------
    Phase_Margin / Gain_db / UGB  取所有 PVT 角的 **Min**（最坏）
    Gain_Margin / I_OPA          取所有 PVT 角的 **Max**（最坏）
    面积按赛方公式：MOS=fw*L*m*1.5；电容=fw*L*m；电阻=segW*segL*segments*2

【待核实】项（已集中在 DEFAULTS 与函数注释里）
    1. `ae.MdeSession.open` 在 `-adv` 模式下的行为/权限
    2. `result.name()` 与 `*_summary.csv` 的实际命名（若不同，改 SUMMARY_GLOB）
    3. PVT 角数（MDE view 决定；本脚本只做聚合，不预设角数）
"""
import argparse
import csv
import glob
import io
import json
import os
import re
import shutil
import sys

# 本地/无平台环境下也能 import（便于 --mock 与单元测试）
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
WORST_DIR = {
    "Phase_Margin": True,
    "Gain_db": True,
    "UGB": True,
    "Gain_Margin": False,
    "I_OPA": False,
}

# 评分门限（score.py 实测）
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
# 参数文件读写（兼容赛方三种写法）
# ---------------------------------------------------------------------------
def parse_param_line(line):
    """解析一行参数，返回 (name, raw_value) 或 None。

    支持：
        "parameter","NM2_fw","4u"      <- 赛方 case1_params_0.txt / extractcdfVal
        parameter, NM2_fw, 4u          <- 赛方 extract_params() 的输出
        NM2_fw=4u                      <- 自定义/精简格式
    """
    s = line.strip()
    if not s or s.startswith(("#", "//")):
        return None
    if "=" in s and not s.startswith(('"', "parameter")):
        k, _, v = s.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        return (k, v) if k else None
    fields = [f.strip().strip('"').strip("'") for f in s.split(",")]
    # 去掉可能的首列标记 "parameter"
    if len(fields) >= 3 and fields[0].lower() == "parameter":
        return (fields[1], fields[2])
    if len(fields) >= 2:
        return (fields[0], fields[1])
    return None


def read_param_file(path):
    """读参数文件 -> OrderedDict{name: raw_value}（保持文件顺序）。"""
    out = {}
    with io.open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            kv = parse_param_line(line)
            if kv:
                out[kv[0]] = kv[1]
    return out


def write_param_file(path, params):
    """按赛方格式写出（带引号的三列 CSV），保证 score.py 能读。"""
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        for name in params:
            f.write('"parameter","%s","%s"\n' % (name, params[name]))
    return path


def split_inst_param(name):
    """'NM2_fw' -> ('NM2', 'fw')"""
    i = name.rfind("_")
    return (name[:i], name[i + 1:]) if i > 0 else (name, "")


# ---------------------------------------------------------------------------
# 指标解析与聚合
# ---------------------------------------------------------------------------
def parse_summary_csv(path):
    """解析 MDE 的 *_summary.csv（列：Output, Min, Max，可能还有 Typ）。"""
    rows = {}
    with io.open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
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
    """按 WORST_DIR 取最坏值；缺数据记为 None。"""
    metrics = {}
    for name, take_min in WORST_DIR.items():
        r = rows.get(name) or {}
        v = r.get("min") if take_min else r.get("max")
        metrics[name] = v
    return metrics


def judge(metrics, area_um2):
    """按 score.py 的门限给出逐项判定与估算分（不含时间分）。"""
    ok = {}
    for name, (mode, lim, _unit) in LIMITS.items():
        v = metrics.get(name)
        if v is None:
            ok[name] = None
        else:
            ok[name] = (v >= lim) if mode == "min" else (v <= lim)
    score = 0.0
    if ok.get("Phase_Margin"):  score += 10.0
    if ok.get("Gain_Margin"):   score += 10.0
    if ok.get("I_OPA"):         score += 10.0
    g = metrics.get("Gain_db")
    if g is not None and g >= GAIN_BASE:
        score += min(g / GAIN_BASE, 1.0) * 10.0
    u = metrics.get("UGB")
    if u is not None and u > 1.0:
        score += min(u / UGB_BASE, 1.0) * 15.0
    if area_um2 and area_um2 > 1.0:
        score += min(AREA_BASE / area_um2, 1.0) * 25.0
    feasible = all(v for v in ok.values()) and ok.get("Gain_db", False)
    return {"per_item": ok, "est_score_no_time": round(score, 2), "feasible": bool(feasible)}


# ---------------------------------------------------------------------------
# 面积（与赛方 score.py 完全一致的公式）
# ---------------------------------------------------------------------------
def param_to_float(raw):
    """长度值 -> **µm**（与赛方 param_convert 完全一致）。

    规则（赛方口径）：'u'/'um' = 微米；'n'/'nm' = 纳米；'p' = 皮米；'f' = 飞米；
    **无单位按"米"**（如 4e-6 -> 4 µm）。面积公式因此直接得到 µm²。
    """
    s = str(raw).strip().strip('"').strip("'")
    m = re.match(r"^\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*([a-zA-Z\u03bc]*)\s*$", s)
    if not m:
        raise ValueError("无法解析的数值: %r" % raw)
    num = float(m.group(1))
    unit = m.group(2).lower().replace("\u03bc", "u")
    if unit == "":
        return num * 1e6          # 无单位 = 米 -> µm
    if unit in ("u", "um"):
        return num
    if unit in ("n", "nm"):
        return num * 1e-3
    if unit in ("p", "pm"):
        return num * 1e-6
    if unit in ("f", "fm"):
        return num * 1e-9
    raise ValueError("不认识的长度单位: %r" % unit)


def dimensionless(raw):
    """无量纲值（m / segments / multi）-> float。"""
    return float(str(raw).strip().strip('"').strip("'"))


def calc_area_from_cv(cv):
    """遍历 schematic 实例算总面积（µm²）。需 PyAether；无平台时返回 None。"""
    if ae is None or cv is None:
        return None
    total = 0.0
    detail = []
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
    """没有 PyAether 时，用参数文件近似算面积（µm²，与 score.py 同公式）。"""
    LEN_PARAMS = ("l", "fw", "w", "segL", "segW")
    per_inst = {}
    for name, raw in params.items():
        inst, p = split_inst_param(name)
        per_inst.setdefault(inst, {})[p] = raw
    total = 0.0
    for inst, p in per_inst.items():
        def length(key, default=None):
            if key in p:
                return param_to_float(p[key])
            return default
        try:
            if inst[:1] in ("R", "r"):
                segw, segl = length("segW"), length("segL")
                segs = dimensionless(p.get("segments", 1.0))
                if segw is None or segl is None:
                    continue
                total += segw * segl * segs * 2.0
            elif inst[:1] in ("C", "c"):
                fw, l = length("fw"), length("l")
                m = dimensionless(p.get("m", 1.0))
                if fw is None or l is None:
                    continue
                total += fw * l * m
            elif inst.startswith(("PM", "NM")):
                fw, l = length("fw"), length("l")
                m = dimensionless(p.get("m", 1.0))
                if fw is None or l is None:
                    continue
                total += fw * l * m * 1.5
        except (KeyError, ValueError):
            continue
    return total


# ---------------------------------------------------------------------------
# 写参数（反标）到 schematic
# ---------------------------------------------------------------------------
def apply_params(cv, params, verbose=True):
    """把 {符号: 原始字符串} 写入 schematic。返回失败列表。"""
    if ae is None:
        raise RuntimeError("无 PyAether：apply_params 只能在服务器上执行")
    failed = []
    for name, raw in params.items():
        inst_name, param_name = split_inst_param(name)
        inst = ae.dbFindInst(cv=cv, name=inst_name)
        if not inst:
            failed.append((name, "instance not found"))
            continue
        ret = ae.cdfSetParam(inst, param_name, str(raw))
        if not ret:
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
# 仿真主流程
# ---------------------------------------------------------------------------
def run_simulation(a):
    """真机：写参数 -> 开 MDE -> 跑 PVT -> 落盘 -> 解析。返回 metrics dict。"""
    if ae is None:
        raise RuntimeError("未导入 pyAether：请在服务器上（source setup.bash 后）运行")
    os.makedirs(a.out_dir, exist_ok=True)
    raw_dir = os.path.join(a.out_dir, "raw")
    os.makedirs(raw_dir, exist_ok=True)

    ae.emyInitAether("-adv")

    params = read_param_file(a.param_file)
    print("==== 读取参数 %d 个：%s ====" % (len(params), a.param_file))

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

    # ---- MDE 仿真 ----
    mde = ae.MdeSession.open(a.ae_lib, a.mde_cell, a.mde_view)
    if not mde:
        raise RuntimeError("MdeSession.open 失败: %s" % getattr(ae.MdeSession, "s", ""))
    try:
        print("==== MDE 工程目录: %s ====" % mde.getSetting().getProjectDirectory())
        if not mde.createSimulationNetlist():
            raise RuntimeError("createSimulationNetlist 失败")
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

    # ---- 解析 summary.csv ----
    cands = [p for p in glob.glob(os.path.join(raw_dir, "**", "*summary*.csv"), recursive=True)]
    cands.sort(key=os.path.getmtime, reverse=True)
    if not cands:
        cands = [p for p in glob.glob(os.path.join(raw_dir, "**", "*.csv"), recursive=True)
                 if not p.endswith("result.txt")]
    if not cands:
        raise RuntimeError("找不到 MDE 的 summary CSV，请检查结果目录: %s" % raw_dir)
    rows = parse_summary_csv(cands[0])
    print("==== 解析 %s：%d 个 Output ====" % (cands[0], len(rows)))

    metrics = worst_case(rows)
    area_um2 = area[0] if isinstance(area, tuple) else area
    verdict = judge(metrics, area_um2)
    payload = {
        "param_file": os.path.abspath(a.param_file),
        "ae": {"lib": a.ae_lib, "cell": a.ae_cell, "view": a.ae_view},
        "mde": {"cell": a.mde_cell, "view": a.mde_view},
        "n_params": len(params),
        "apply_failed": failed,
        "metrics_worst_case": metrics,
        "area_um2": area_um2,
        "raw_rows": rows,
        "verdict": verdict,
        "result_name": result_name,
    }
    emit_outputs(a.out_dir, payload)
    return payload


def run_mock(a):
    """本地：伪造一份 MDE summary，走完整的解析/聚合/输出链路。"""
    os.makedirs(os.path.join(a.out_dir, "raw"), exist_ok=True)
    fake = os.path.join(a.out_dir, "raw", "Results_mock_summary.csv")
    with io.open(fake, "w", encoding="utf-8", newline="") as f:
        f.write("Output,Min,Max,Typ\n")
        f.write("Phase_Margin,52.4,61.2,57.1\n")      # 最坏取 Min
        f.write("Gain_db,44.8,49.1,47.0\n")           # 最坏取 Min
        f.write("UGB,1.85e8,2.31e8,2.05e8\n")         # 最坏取 Min
        f.write("Gain_Margin,-13.1,-11.2,-12.0\n")    # 最坏取 Max
        f.write("I_OPA,0.0012,0.0027,0.0019\n")       # 最坏取 Max
    params = {}
    if a.param_file and os.path.exists(a.param_file):
        params = read_param_file(a.param_file)
    area = calc_area_from_params(params) if params else 5200.0
    rows = parse_summary_csv(fake)
    metrics = worst_case(rows)
    verdict = judge(metrics, area)
    payload = {
        "param_file": a.param_file or "(mock)",
        "ae": {"lib": a.ae_lib, "cell": a.ae_cell, "view": a.ae_view},
        "mde": {"cell": a.mde_cell, "view": a.mde_view},
        "n_params": len(params),
        "apply_failed": [],
        "metrics_worst_case": metrics,
        "area_um2": area,
        "raw_rows": rows,
        "verdict": verdict,
        "result_name": "Results_mock",
        "mock": True,
    }
    emit_outputs(a.out_dir, payload)
    return payload


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------
def emit_outputs(out_dir, payload):
    os.makedirs(out_dir, exist_ok=True)
    with io.open(os.path.join(out_dir, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1, default=str)

    m = payload["metrics_worst_case"]
    with io.open(os.path.join(out_dir, "metrics.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", "worst_value", "unit", "limit", "pass"])
        units = {"Phase_Margin": "deg", "Gain_Margin": "dB", "I_OPA": "A",
                 "Gain_db": "dB", "UGB": "Hz"}
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
             "- 三条硬约束：%s" % ("全部满足 ✅" if payload["verdict"]["feasible"] else "**未满足** ❌"),
             "", "| 指标 | 最坏值 | 单位 | 门限 | 判定 |", "|---|---|---|---|---|"]
    units = {"Phase_Margin": "deg", "Gain_Margin": "dB", "I_OPA": "A",
             "Gain_db": "dB", "UGB": "Hz"}
    for k, v in m.items():
        lim = LIMITS.get(k)
        judge_v = payload["verdict"]["per_item"].get(k)
        mark = "✅" if judge_v else ("❌" if judge_v is not None else "—")
        lines.append("| %s | %s | %s | %s | %s |"
                     % (k, ("%.6g" % v) if isinstance(v, (int, float)) else v,
                        units.get(k, ""), lim[1] if lim else "越大越好", mark))
    lines.append("| Total_Area | %.1f | um² | ≤ %.0f 满分 | %s |"
                 % (payload["area_um2"] or 0, AREA_BASE,
                    "✅" if (payload["area_um2"] or 1e9) <= AREA_BASE else "⚠️"))
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
    p = argparse.ArgumentParser(description="模块四-① PVT 仿真引擎（调用 MDE，提取指标）")
    p.add_argument("--ae_lib", default=DEFAULTS["ae_lib"])
    p.add_argument("--ae_cell", default=DEFAULTS["ae_cell"])
    p.add_argument("--ae_view", default=DEFAULTS["ae_view"])
    p.add_argument("--mde_cell", default=DEFAULTS["mde_cell"])
    p.add_argument("--mde_view", default=DEFAULTS["mde_view"])
    p.add_argument("--param_file", default="case1_params_0.txt")
    p.add_argument("--out_dir", default=DEFAULTS["out_dir"])
    p.add_argument("--mock", action="store_true", help="本地验证模式（假数据，不需要 PyAether）")
    p.add_argument("--dry_run", action="store_true", help="只写参数、不跑仿真")
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    if a.mock:
        run_mock(a)
        return 0
    if ae is None:
        print("ERROR: 未导入 pyAether。请在服务器上 source setup.bash 后运行，"
              "或加 --mock 在本地验证链路。", file=sys.stderr)
        return 2
    if a.dry_run:
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
