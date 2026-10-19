#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块四-⑥ 报告生成器：把仿真/优化结果生成赛题 6.2 第 5 项要求的"全 PVT 仿真验证报告"

输入（都可选，有几个就能写几段）：
    --sim_dir     含 sim_engine.py 产物 metrics.json 的目录（最优解那次）
    --init_dir    含初始解 metrics.json 的目录（用于"优化前后对比"）
    --corner_csv  逐角明细表 CSV（列：corner,temp,vdd,Phase_Margin,Gain_Margin,Gain_db,UGB,I_OPA）
    --wave_dir    波形图目录（.png/.pdf/.jpg），报告里按文件名引用
    --opt_log     optimization.log（用于"代码质量与算法性能"摘要）
    --out         输出文件名（默认 pvt_report.md）

产物：Markdown 报告（可直接用 pandoc/Word 转成 Doc/PDF），含：
    1. 基本信息与测试环境
    2. 优化前后对比表
    3. 最坏情况指标 + 三条硬约束判定 + 评分估算
    4. 逐角明细表（若有）+ 全场景覆盖检查（TT/FF/SS × 温度 × 电压）
    5. 波形索引（若有）
    6. 代码质量与算法性能摘要（若有）
    7. 结论

用法
----
    python report_gen.py --sim_dir ~/m4_final --init_dir ~/m4_smoke \\
        --corner_csv ~/m4_final/per_corner.csv --wave_dir ~/m4_final/waves \\
        --opt_log ~/run_full.log --out ~/pvt_report.md
"""
import argparse
import glob
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m4_common import setup_stdio

setup_stdio()

# 评分门限与基线（与 score.py 一致）
LIMITS = {
    "Phase_Margin": ("min", 50.0, "deg", "PM"),
    "Gain_Margin": ("max", -10.0, "dB", "GM"),
    "I_OPA": ("max", 0.003, "A", "I_OPA"),
    "Gain_db": ("min", 20.0, "dB", "Gain"),
}
UGB_BASE = 2.0e8
AREA_BASE = 8000.0
GAIN_BASE = 20.0

CORNER_COLS = ["corner", "temp", "vdd", "Phase_Margin", "Gain_Margin", "Gain_db", "UGB", "I_OPA"]


def load_metrics(sim_dir):
    """读 sim_engine 产出的 metrics.json；目录不存在或文件缺失返回 None。"""
    if not sim_dir:
        return None
    path = os.path.join(sim_dir, "metrics.json")
    if not os.path.exists(path):
        return None
    try:
        return json.load(io.open(path, encoding="utf-8"))
    except Exception as e:
        print("WARN: 读 %s 失败: %s" % (path, e))
        return None


def m_of(payload):
    return (payload or {}).get("metrics_worst_case") or {}


def fmt(v, nd=4):
    if v is None:
        return "—"
    if isinstance(v, float):
        if abs(v) >= 1e6 or (v != 0 and abs(v) < 1e-3):
            return "%.4g" % v
        return ("%." + str(nd) + "f") % v
    return str(v)


def judge_line(metrics, area):
    """返回 [(名称, 值, 门限, 判定)] 与估算分。"""
    rows = []
    for key, (mode, lim, unit, label) in LIMITS.items():
        v = metrics.get(key)
        if v is None:
            ok = None
        elif mode == "min":
            ok = v >= lim
        else:
            ok = v <= lim
        rows.append((label, v, "%s %.3g %s" % ("≥" if mode == "min" else "≤", lim, unit), ok))
    score = 0.0
    if rows[0][3]:
        score += 10.0
    if rows[1][3]:
        score += 10.0
    if rows[2][3]:
        score += 10.0
    g = metrics.get("Gain_db")
    if g is not None and g >= GAIN_BASE:
        score += min(g / GAIN_BASE, 1.0) * 10.0
    u = metrics.get("UGB")
    if u is not None and u > 1.0:
        score += min(u / UGB_BASE, 1.0) * 15.0
    if area and area > 1.0:
        score += min(AREA_BASE / area, 1.0) * 25.0
    return rows, round(score, 3)


def read_corner_csv(path):
    """读逐角 CSV（表头必须含 corner；其余列按 CORNER_COLS 有则用）。"""
    if not path or not os.path.exists(path):
        return None
    rows = []
    with io.open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
        import csv as _csv
        reader = _csv.DictReader(f)
        for r in reader:
            rows.append({k.strip(): (v or "").strip() for k, v in r.items()})
    return rows or None


def coverage_check(corner_rows):
    """检查 TT/FF/SS、温度、电压是否覆盖到位（赛题 6.2 第 5 项）。"""
    text = " ".join(
        " ".join(str(v) for v in r.values()).lower() for r in corner_rows)
    has = {k: (k.lower() in text) for k in ("tt", "ff", "ss", "125", "-40", "40")}
    checks = [
        ("工艺角 TT", has["tt"]),
        ("工艺角 FF", has["ff"]),
        ("工艺角 SS", has["ss"]),
        ("高温 125℃", "125" in text),
        ("低温 −40℃", ("-40" in text) or ("40" in text)),
        ("电压 ±10%", ("1.1" in text) or ("0.9" in text) or ("±10" in text) or ("10%" in text)),
    ]
    return checks


def scan_waves(wave_dir):
    if not wave_dir or not os.path.isdir(wave_dir):
        return []
    out = []
    for ext in ("png", "jpg", "jpeg", "pdf", "svg"):
        out += glob.glob(os.path.join(wave_dir, "*." + ext))
    return sorted(out)


def summarize_opt_log(path):
    """从优化日志里刨：评估次数、总耗时、峰值内存（若有）。"""
    if not path or not os.path.exists(path):
        return None
    text = io.open(path, encoding="utf-8", errors="replace").read()
    info = {}
    iters = [int(m) for m in re.findall(r"\biter\s+(\d+)\b", text, re.I)]
    if iters:
        info["评估/迭代次数"] = max(iters)
    m = re.findall(r"TOTAL:\s*([\d.]+)\s*s", text)
    if m:
        info["总耗时"] = "%.1f s" % float(m[-1])
    m = re.findall(r"Execution duration:\s*([\d:]+)", text)
    if m:
        info["总耗时"] = m[-1] + " (HH:MM:SS)"
    m = re.findall(r"Maximum resident set size[^:]*:\s*(\d+)", text)
    if m:
        info["峰值内存"] = "%.1f MB" % (int(m[-1]) / 1024.0)
    m = re.findall(r"ru_maxrss[=:\s]+(\d+)", text)
    if m and "峰值内存" not in info:
        info["峰值内存"] = "%.1f MB" % (int(m[-1]) / 1024.0)
    m = re.findall(r"t_eval=([\d.]+)s", text)
    if m:
        info["单次评估耗时(T_eval)"] = "%s s" % m[-1]
    return info or None


def main(argv=None):
    ap = argparse.ArgumentParser(description="模块四-⑥ PVT 验证报告生成器")
    ap.add_argument("--sim_dir", default="", help="含 metrics.json 的目录（最优解）")
    ap.add_argument("--init_dir", default="", help="含 metrics.json 的目录（初始解，用于对比）")
    ap.add_argument("--corner_csv", default="", help="逐角明细 CSV")
    ap.add_argument("--wave_dir", default="", help="波形图目录（png/pdf）")
    ap.add_argument("--opt_log", default="", help="优化日志（算法性能摘要）")
    ap.add_argument("--title", default="全 PVT 仿真验证报告")
    ap.add_argument("--out", default="pvt_report.md")
    a = ap.parse_args(argv)

    best = load_metrics(a.sim_dir)
    init = load_metrics(a.init_dir)
    corners = read_corner_csv(a.corner_csv)
    waves = scan_waves(a.wave_dir)
    opt = summarize_opt_log(a.opt_log)

    if not best:
        print("WARN: 没读到最优解的 metrics.json（--sim_dir=%s），报告会缺主表" % a.sim_dir,
              file=sys.stderr)
    mb, mb_area = m_of(best), ((best or {}).get("area_um2"))
    mi, mi_area = m_of(init), ((init or {}).get("area_um2"))

    L = []
    L.append("# %s" % a.title)
    L.append("")
    L.append("> 由 `module4/report_gen.py` 自动生成；数据源为 `sim_engine.py` 的真实仿真结果。")
    L.append("> 指标口径：PM/Gain/UGB 取所有 PVT 角的 **Min**，GM/I_OPA 取 **Max**（与赛方 `score.py` 一致）。")
    L.append("")

    # 1. 基本信息
    L.append("## 1. 基本信息")
    L.append("")
    L.append("| 项 | 内容 |")
    L.append("|---|---|")
    ae = (best or {}).get("ae") or {}
    mde = (best or {}).get("mde") or {}
    L.append("| 电路 | `%s / %s / %s` |" % (ae.get("lib", "—"), ae.get("cell", "—"), ae.get("view", "—")))
    L.append("| MDE | `%s / %s` |" % (mde.get("cell", "—"), mde.get("view", "—")))
    L.append("| 参数文件 | `%s`（%s 个符号） |" % ((best or {}).get("param_file", "—"), (best or {}).get("n_params", "—")))
    L.append("| 结果名 | `%s` |" % ((best or {}).get("result_name", "—")))
    pf = (best or {}).get("path_fix") or {}
    if pf:
        L.append("| 旧路径修复 | 扫描 %s 个文件，改动 %s 个 |" % (pf.get("scanned", "—"), pf.get("modified", "—")))
    L.append("")

    # 2. 优化前后对比
    if mi or mb:
        L.append("## 2. 优化前后对比")
        L.append("")
        L.append("| 指标 | 初始解 | 最优解 | 变化 |")
        L.append("|---|---|---|---|")
        for key, label in (("Phase_Margin", "PM (deg)"), ("Gain_Margin", "GM (dB)"),
                           ("Gain_db", "DC Gain (dB)"), ("UGB", "UGB (Hz)"),
                           ("I_OPA", "I_OPA (A)")):
            a_, b_ = mi.get(key), mb.get(key)
            delta = "—"
            if a_ is not None and b_ is not None:
                try:
                    delta = "%+.3g" % (b_ - a_)
                except Exception:
                    delta = "—"
            L.append("| %s | %s | %s | %s |" % (label, fmt(a_), fmt(b_), delta))
        da = "—"
        if mi_area and mb_area:
            da = "%+.1f%%" % ((mb_area - mi_area) / mi_area * 100.0)
        L.append("| Total_Area (µm²) | %s | %s | %s |" % (fmt(mi_area, 1), fmt(mb_area, 1), da))
        L.append("")

    # 3. 最坏情况 + 判定 + 评分
    if mb:
        rows, score = judge_line(mb, mb_area)
        L.append("## 3. 最坏情况指标与达标判定")
        L.append("")
        L.append("| 指标 | 最坏值 | 门限 | 判定 |")
        L.append("|---|---|---|---|")
        for label, v, lim, ok in rows:
            mark = "✅" if ok else ("❌" if ok is not None else "—")
            L.append("| %s | %s | %s | %s |" % (label, fmt(v), lim, mark))
        L.append("| Total_Area | %s µm² | ≤ %.0f 满分 | %s |"
                 % (fmt(mb_area, 1), AREA_BASE, "✅" if (mb_area or 1e9) <= AREA_BASE else "⚠️"))
        L.append("")
        L.append("- 估算得分（不含时间分）：**%.2f / 80**" % score)
        L.append("- 三条硬约束：%s" % ("全部满足 ✅" if all(r[3] for r in rows[:3]) else "**存在不满足** ❌"))
        L.append("")

    # 4. 逐角明细
    L.append("## 4. 全 PVT 逐角明细")
    L.append("")
    if corners:
        cols = [c for c in CORNER_COLS if c in corners[0]]
        L.append("| " + " | ".join(cols) + " |")
        L.append("|" + "|".join("---" for _ in cols) + "|")
        for r in corners:
            L.append("| " + " | ".join(r.get(c, "") for c in cols) + " |")
        L.append("")
        L.append("### 4.1 全场景覆盖检查（赛题 6.2 第 5 项）")
        L.append("")
        L.append("| 要求 | 是否覆盖 |")
        L.append("|---|---|")
        for name, ok in coverage_check(corners):
            L.append("| %s | %s |" % (name, "✅" if ok else "❌ 需补跑"))
        L.append("")
    else:
        L.append("> ⚠️ 未提供逐角明细（`--corner_csv`）。赛题 6.2 第 5 项要求覆盖 "
                 "TT/FF/SS × 高温 125℃ / 低温 −40℃ × 标称电压 ±10% 的全场景结果。")
        L.append("> 现有 `metrics.json` 只含 Min/Max/Typ 包络，**需要补逐角数据**。")
        L.append("")

    # 5. 波形
    L.append("## 5. 仿真波形")
    L.append("")
    if waves:
        for w in waves:
            L.append("- `%s`" % os.path.basename(w))
            L.append("")
            L.append("  ![](%s)" % w)
            L.append("")
    else:
        L.append("> ⚠️ 未提供波形图（`--wave_dir`）。需要环路增益/相位 vs 频率的 Bode 图。")
        L.append("")

    # 6. 算法性能
    L.append("## 6. 代码质量与算法性能")
    L.append("")
    if opt:
        L.append("| 项 | 值 |")
        L.append("|---|---|")
        for k, v in opt.items():
            L.append("| %s | %s |" % (k, v))
        L.append("")
    else:
        L.append("> ⚠️ 未提供优化日志（`--opt_log`），无法汇总评估次数/耗时/内存。")
        L.append("")

    # 7. 结论
    L.append("## 7. 结论")
    L.append("")
    if mb:
        ok_all = all(r[3] for r in judge_line(mb, mb_area)[0][:3]) and mb.get("Gain_db", 0) >= GAIN_BASE
        L.append("最优尺寸在全部 PVT 角下%s满足硬约束；" % ("" if ok_all else "**未完全**"))
        L.append("最坏情况 DC Gain = %s dB、UGB = %s Hz、Area = %s µm²。"
                 % (fmt(mb.get("Gain_db")), fmt(mb.get("UGB")), fmt(mb_area, 1)))
        gaps = []
        if mb.get("UGB") and mb["UGB"] < UGB_BASE:
            gaps.append("UGB（距满分基线 %.3g Hz 还差 %.2f 倍）"
                        % (UGB_BASE, UGB_BASE / mb["UGB"]))
        if mb_area and mb_area > AREA_BASE:
            gaps.append("面积（距满分 %.0f µm² 还差 %.1f%%）"
                        % (AREA_BASE, (mb_area - AREA_BASE) / mb_area * 100.0))
        if gaps:
            L.append("")
            L.append("后续可继续提升：" + "；".join(gaps) + "。")
    L.append("")

    with io.open(a.out, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L) + "\n")
    print("==== 报告已生成: %s（%d 行）====" % (a.out, len(L)))
    print("     数据源: 最优解=%s / 初始解=%s / 逐角=%s / 波形=%d 张 / 日志=%s"
          % (bool(best), bool(init), bool(corners), len(waves), bool(opt)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
