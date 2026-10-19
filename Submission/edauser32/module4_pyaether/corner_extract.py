#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块四-⑧ 逐角提取器：把 MDE 的 `*_transpose.csv` 转成赛题 6.2 第 5 项要的"全 PVT 逐角明细表"

背景（2026-10-18 服务器实测）
---------------------------
`sim_engine.py` 调用 `result.saveResultsToDir()` 会得到 4 个 CSV：
    <结果名>_summary.csv    聚合包络：Output, Min, Max, Mean, Median, Std Dev
    <结果名>_detail.csv     每个角的工艺/温度/电压设置
    <结果名>_transpose.csv  **每角一行**：Corner + 工艺 + vdd + temp + 各项指标  ← 我们要的
    <结果名>_yield.csv      良率统计

实测 `transpose.csv` 的表头（注意前两列同名，且部分角是 `<AS IS>`）：
    "Corner","spe_demo.scs","spe_demo.scs","vdd","temp","Pass/Fail",
    "Loop_Gain","LP_Phase","Gain_db","UGB","Phase_Margin","Gain_Margin","I_OPA"

产物
----
    per_corner.csv   逐角明细（列：corner,process,temp,vdd,Gain_db,UGB,Phase_Margin,Gain_Margin,I_OPA）
                     —— 可直接喂给 `report_gen.py --corner_csv`
    per_corner.md    人读表格 + 全场景覆盖检查 + 与 summary 包络的交叉校验
    per_corner.json  机器可读

用法
----
    python corner_extract.py --raw_dir ~/m4_smoke/raw --out_dir ~/m4_final
    python corner_extract.py --raw_dir ~/m4_smoke/raw --result Results478   # 指定结果名
"""
import argparse
import csv
import glob
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m4_common import setup_stdio

setup_stdio()

# 指标名 -> 输出列名（transpose.csv 里的列名）
METRIC_COLS = {
    "Gain_db": "Gain_db",
    "UGB": "UGB",
    "Phase_Margin": "Phase_Margin",
    "Gain_Margin": "Gain_Margin",
    "I_OPA": "I_OPA",
}
OUT_COLS = ["corner", "process", "temp", "vdd", "Gain_db", "UGB",
            "Phase_Margin", "Gain_Margin", "I_OPA"]

# 与 score.py 一致的最坏情况方向
WORST = {"Gain_db": min, "UGB": min, "Phase_Margin": min,
         "Gain_Margin": max, "I_OPA": max}


def find_transpose(raw_dir, result=""):
    """找 transpose.csv；给 result 前缀则优先匹配。<结果名>_transpose.csv。"""
    if result:
        p = os.path.join(raw_dir, "%s_transpose.csv" % result)
        if os.path.exists(p):
            return p
    cands = glob.glob(os.path.join(raw_dir, "*_transpose.csv"))
    if not cands:
        return None
    return max(cands, key=os.path.getmtime)


def find_summary(raw_dir, result=""):
    if result:
        p = os.path.join(raw_dir, "%s_summary.csv" % result)
        if os.path.exists(p):
            return p
    cands = glob.glob(os.path.join(raw_dir, "*_summary.csv"))
    return max(cands, key=os.path.getmtime) if cands else None


def _num(s):
    s = (s or "").strip().strip('"')
    if s == "" or s.lower() in ("<as is>", "n/a", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_transpose(path):
    """解析 transpose.csv（表头前两列同名，按位置取；工艺取非 <AS IS> 的那个）。"""
    rows = []
    with io.open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        hdr = [h.strip().strip('"') for h in header]
        # 定位各列（按名字找，找不到按实测位置兜底）
        def idx(name, default):
            try:
                return hdr.index(name)
            except ValueError:
                return default
        i_corner = idx("Corner", 0)
        i_gain = idx("Gain_db", 8)
        i_ugb = idx("UGB", 9)
        i_pm = idx("Phase_Margin", 10)
        i_gm = idx("Gain_Margin", 11)
        i_i = idx("I_OPA", 12)
        i_vdd = idx("vdd", 3)
        i_temp = idx("temp", 4)
        # 前两列可能都叫 "spe_demo.scs"：取第 1、2 列
        i_p1, i_p2 = 1, 2

        for r in reader:
            if not r or not r[i_corner].strip():
                continue
            corner = r[i_corner].strip().strip('"')

            def cell(i):
                return r[i].strip().strip('"') if i < len(r) else ""

            # 工艺：两列里非 <AS IS> 的那个
            procs = [p for p in (cell(i_p1), cell(i_p2))
                     if p and p.upper() != "<AS IS>"]
            process = procs[-1] if procs else "—"
            rows.append({
                "corner": corner,
                "process": process,
                "vdd": _num(cell(i_vdd)),
                "temp": _num(cell(i_temp)),
                "Gain_db": _num(cell(i_gain)),
                "UGB": _num(cell(i_ugb)),
                "Phase_Margin": _num(cell(i_pm)),
                "Gain_Margin": _num(cell(i_gm)),
                "I_OPA": _num(cell(i_i)),
            })
    return rows


def parse_summary(path):
    """解析 summary.csv -> {Output: {'min':x,'max':x}}（用于交叉校验）。"""
    out = {}
    if not path or not os.path.exists(path):
        return out
    with io.open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
        for row in csv.DictReader(f):
            name = (row.get("Output") or "").strip().strip('"')
            if not name:
                continue
            out[name] = {"min": _num(row.get("Min")), "max": _num(row.get("Max"))}
    return out


def worst_case(rows):
    w = {}
    for k, fn in WORST.items():
        vals = [r[k] for r in rows if r.get(k) is not None]
        w[k] = fn(vals) if vals else None
    return w


def coverage(rows):
    """全场景覆盖检查（赛题 6.2 第 5 项）：TT/FF/SS、-40/125℃、±10% 电压。"""
    procs = {(r.get("process") or "").lower() for r in rows}
    temps = {r.get("temp") for r in rows if r.get("temp") is not None}
    vdds = {round(r.get("vdd"), 4) for r in rows if r.get("vdd") is not None}
    has_nominal = any("nominal" in (r.get("corner") or "").lower() for r in rows)
    checks = [
        ("工艺角 TT", ("tt" in procs) or has_nominal),
        ("工艺角 FF", "ff" in procs),
        ("工艺角 SS", "ss" in procs),
        ("低温 −40℃", any(t <= -40 for t in temps)),
        ("高温 125℃", any(t >= 125 for t in temps)),
        ("标称电压与 ±10%", len(vdds) >= 3 or len(vdds) == 2),
        ("常温 27℃（Nominal）", any(20 <= t <= 35 for t in temps)),
    ]
    return checks, {"process": sorted(procs), "temp": sorted(temps), "vdd": sorted(vdds)}


def write_outputs(rows, out_dir, src_transpose, summary_rows):
    os.makedirs(out_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, "per_corner.csv")
    with io.open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUT_COLS)
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in OUT_COLS})

    wc = worst_case(rows)
    checks, seen = coverage(rows)

    # 交叉校验：逐角最坏值 vs summary 包络
    cross = []
    for k, agg in summary_rows.items():
        if k not in wc:
            continue
        s = agg.get("min") if WORST.get(k) is min else agg.get("max")
        wv = wc.get(k)
        if s is None or wv is None:
            cross.append((k, wv, s, "无法比对"))
            continue
        rel = abs(wv - s) / max(abs(s), 1e-12)
        cross.append((k, wv, s, "一致 ✅" if rel < 1e-6 else "差异 %.2e ⚠️" % rel))

    L = ["# 全 PVT 逐角明细", "",
         "- 数据源：`%s`" % src_transpose,
         "- 角数：**%d**" % len(rows),
         "- 工艺角：%s" % ", ".join(seen["process"]),
         "- 温度：%s" % ", ".join("%g" % t for t in seen["temp"]),
         "- 电压：%s" % ", ".join("%g" % v for v in seen["vdd"]),
         "", "## 1. 全场景覆盖检查（赛题 6.2 第 5 项）", "",
         "| 要求 | 是否覆盖 |", "|---|---|"]
    for name, ok in checks:
        L.append("| %s | %s |" % (name, "✅" if ok else "❌ 需补跑"))
    L += ["", "## 2. 逐角明细", "",
          "| 角 | 工艺 | 温度(℃) | vdd(V) | Gain(dB) | UGB(Hz) | PM(°) | GM(dB) | I_OPA(A) |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |"
                 % (r["corner"], r["process"],
                    "%g" % r["temp"] if r["temp"] is not None else "",
                    "%g" % r["vdd"] if r["vdd"] is not None else "",
                    "%.6g" % r["Gain_db"] if r["Gain_db"] is not None else "",
                    "%.6g" % r["UGB"] if r["UGB"] is not None else "",
                    "%.6g" % r["Phase_Margin"] if r["Phase_Margin"] is not None else "",
                    "%.6g" % r["Gain_Margin"] if r["Gain_Margin"] is not None else "",
                    "%.6g" % r["I_OPA"] if r["I_OPA"] is not None else ""))
    L += ["", "## 3. 逐角最坏值 vs summary 包络（交叉校验）", "",
          "| 指标 | 逐角最坏值 | summary 包络 | 结论 |", "|---|---|---|---|"]
    for k, wv, s, verdict in cross:
        L.append("| %s | %s | %s | %s |"
                 % (k, "%.6g" % wv if wv is not None else "—",
                    "%.6g" % s if s is not None else "—", verdict))
    md_path = os.path.join(out_dir, "per_corner.md")
    with io.open(md_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L) + "\n")

    js_path = os.path.join(out_dir, "per_corner.json")
    with io.open(js_path, "w", encoding="utf-8") as f:
        json.dump({"source": src_transpose, "n_corners": len(rows),
                   "rows": rows, "worst_case": wc,
                   "coverage": {n: ok for n, ok in checks},
                   "seen": seen, "cross_check": cross},
                  f, ensure_ascii=False, indent=1)

    print("==== 逐角提取完成：%d 个角 -> %s ====" % (len(rows), csv_path))
    print("     工艺角: %s" % ", ".join(seen["process"]))
    print("     温度: %s ℃" % ", ".join("%g" % t for t in seen["temp"]))
    print("     电压: %s V" % ", ".join("%g" % v for v in seen["vdd"]))
    bad = [n for n, ok in checks if not ok]
    print("     覆盖检查: %s" % ("全部通过 ✅" if not bad else "缺 " + "、".join(bad)))
    for k, wv, s, verdict in cross:
        print("     交叉校验 %-14s 逐角=%s summary=%s %s"
              % (k, "%.6g" % wv if wv is not None else "—",
                 "%.6g" % s if s is not None else "—", verdict))
    return 0 if not bad else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="模块四-⑧ 逐角明细提取（MDE transpose.csv）")
    ap.add_argument("--raw_dir", required=True, help="sim_engine 的 raw/ 目录")
    ap.add_argument("--out_dir", default=".", help="输出目录")
    ap.add_argument("--result", default="", help="结果名前缀（如 Results478）；默认取最新")
    a = ap.parse_args(argv)

    tp = find_transpose(a.raw_dir, a.result)
    if not tp:
        print("ERROR: 在 %s 下找不到 *_transpose.csv" % a.raw_dir, file=sys.stderr)
        return 2
    rows = parse_transpose(tp)
    if not rows:
        print("ERROR: %s 解析出 0 个角（表头可能变了，请贴前 3 行给我）" % tp, file=sys.stderr)
        return 3
    sm = find_summary(a.raw_dir, a.result)
    return write_outputs(rows, a.out_dir, tp, parse_summary(sm))


if __name__ == "__main__":
    raise SystemExit(main())
