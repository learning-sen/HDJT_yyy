#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块四-⑦ 算法性能统计：生成赛题 6.2 第 6 项要求的"代码质量与算法性能"表

赛题原文（6.2 第 6 项）："包括优化运行次数、运行时间、占用内存等"。

输入
----
    --log       一个或多个日志文件（optimization.log / run_full.log / *.txt）
    --metrics   可选：sim_engine 的 metrics.json（用于取 T_eval、参数个数）
    --out       输出 Markdown（默认 algorithm_stats.md）
    --json      同时输出 JSON（默认同名 .json）

用法
----
    python stats.py --log ~/run_full.log --metrics ~/m4_final/metrics.json

支持的日志形态（容错解析，找不到就写"未记录"而不是瞎编）
---------------------------------------------------------
    iter N ...                     -> 评估/迭代次数
    TOTAL: 123.4s                  -> 总耗时
    Execution duration: 00:12:34   -> 总耗时（HH:MM:SS）
    t_eval=1.234s                  -> 单次评估耗时
    Maximum resident set size: N   -> 峰值内存（/usr/bin/time -v 的输出）
    ru_maxrss=N                    -> 峰值内存（脚本自己记录）
    [P0-2] / [P0-4] / BUDGET: ...  -> 预算与预算压缩信息
"""
import argparse
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m4_common import setup_stdio

setup_stdio()

PAT_MEM_TIMEV = re.compile(r"Maximum resident set size[^:]*:\s*(\d+)")
PAT_MEM_RU = re.compile(r"ru_maxrss\s*[=:]\s*(\d+)")
PAT_ITER = re.compile(r"\biter\s+(\d+)\b", re.I)
PAT_TOTAL = re.compile(r"TOTAL:\s*([\d.]+)\s*s", re.I)
PAT_DUR = re.compile(r"Execution duration:\s*(\d+:\d+:\d+)")
PAT_TEVAL = re.compile(r"t_eval=([\d.]+)s", re.I)
PAT_NPARAM = re.compile(r"n_param=(\d+)")
PAT_BUDGET = re.compile(r"budget=([\d.]+)s")
PAT_NOREAD = re.compile(r"Best param file not exists", re.I)


def read_texts(paths):
    chunks = []
    for p in paths:
        if p and os.path.exists(p):
            chunks.append(io.open(p, encoding="utf-8", errors="replace").read())
    return "\n".join(chunks)


def collect(paths, metrics_path=""):
    text = read_texts([p for p in re.split(r"[,;]", paths or "") if p.strip()])
    st = {"来源日志": [p for p in re.split(r"[,;]", paths or "") if p.strip()]}

    iters = [int(x) for x in PAT_ITER.findall(text)]
    st["评估/迭代次数"] = max(iters) if iters else None

    total = None
    m = PAT_TOTAL.findall(text)
    if m:
        total = float(m[-1])
    else:
        m = PAT_DUR.findall(text)
        if m:
            h, mi, s = (int(x) for x in m[-1].split(":"))
            total = h * 3600 + mi * 60 + s
    st["总运行时间(s)"] = total

    m = PAT_TEVAL.findall(text)
    st["单次评估耗时(s)"] = float(m[-1]) if m else None

    mem = PAT_MEM_TIMEV.findall(text) or PAT_MEM_RU.findall(text)
    st["峰值内存(MB)"] = round(int(mem[-1]) / 1024.0, 1) if mem else None

    m = PAT_NPARAM.findall(text)
    st["参数个数"] = int(m[-1]) if m else None
    m = PAT_BUDGET.findall(text)
    st["时间预算(s)"] = float(m[-1]) if m else None
    if total and st["时间预算(s)"]:
        st["预算使用率(%)"] = round(total / st["时间预算(s)"] * 100.0, 1)
    st["是否出现'Best param file not exists'"] = bool(PAT_NOREAD.search(text))

    # 补充：从 metrics.json 取 T_eval / 参数数
    if metrics_path and os.path.exists(metrics_path):
        try:
            p = json.load(io.open(metrics_path, encoding="utf-8"))
            st.setdefault("参数个数", p.get("n_params"))
            if st.get("参数个数") is None:
                st["参数个数"] = p.get("n_params")
        except Exception:
            pass

    # 派生指标
    if st.get("总运行时间(s)") and st.get("评估/迭代次数"):
        st["平均每次评估耗时(s)"] = round(
            st["总运行时间(s)"] / max(st["评估/迭代次数"], 1), 3)
    return st


def to_md(st):
    L = ["# 代码质量与算法性能", "",
         "> 由 `module4/stats.py` 从真实运行日志自动汇总（缺失项如实写“未记录”，不做估算）。", "",
         "| 项 | 值 |", "|---|---|"]
    order = ["评估/迭代次数", "总运行时间(s)", "平均每次评估耗时(s)", "单次评估耗时(s)",
             "时间预算(s)", "预算使用率(%)", "峰值内存(MB)", "参数个数",
             "是否出现'Best param file not exists'"]
    for k in order:
        if k in st:
            v = st[k]
            L.append("| %s | %s |" % (k, "未记录" if v is None else v))
    L.append("")
    if st.get("来源日志"):
        L.append("日志来源：")
        for p in st["来源日志"]:
            L.append("- `%s`" % p)
        L.append("")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="模块四-⑦ 算法性能统计（6.2 第 6 项）")
    ap.add_argument("--log", default="", help="日志文件，多个用逗号分隔")
    ap.add_argument("--metrics", default="", help="metrics.json（可选）")
    ap.add_argument("--out", default="algorithm_stats.md")
    ap.add_argument("--json", dest="json_out", default="")
    a = ap.parse_args(argv)

    st = collect(a.log, a.metrics)
    with io.open(a.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(to_md(st))
    jout = a.json_out or (os.path.splitext(a.out)[0] + ".json")
    with io.open(jout, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)

    print("==== 性能统计已生成: %s / %s ====" % (a.out, jout))
    for k in ("评估/迭代次数", "总运行时间(s)", "单次评估耗时(s)", "峰值内存(MB)", "参数个数"):
        print("  %-16s %s" % (k, st.get(k, "未记录")))
    missing = [k for k in ("评估/迭代次数", "总运行时间(s)", "峰值内存(MB)") if st.get(k) is None]
    if missing:
        print("  ⚠️ 缺：%s —— 下次跑仿真时加 `/usr/bin/time -v` 前缀即可记录内存" % "、".join(missing))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
