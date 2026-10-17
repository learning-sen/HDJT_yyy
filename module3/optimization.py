#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块三 · 提交入口：基于约束的多目标尺寸优化（单文件，仅标准库）

为什么做成单文件：赛题要求的提交结构是
    eda_2026_case_1.tar.gz / eda_2026_case_1 / optimization.py
单文件可以彻底避免"评分机上 import 路径不对/漏文件"这一类致命错误。

三种运行模式
------------
    python optimization.py --selfcheck                 # 只做环境与逻辑自检（不仿真、不调模型）
    python optimization.py --mock                      # 本地假仿真器跑通算法链路（无需服务器）
    python optimization.py --real  [赛方参数...]        # 真机：调用赛方仿真接口做优化

真机模式还要能处理两种调用约定（【待核实】以样例 optimization.py / run_score.sh 为准）：
    A) 评分脚本带全套参数调用我们  -> 我们从 argv 里取出 --param_file/--output_path 等
    B) 评分脚本不带参数调用我们    -> 我们用 CONFIG 里的默认值去调赛方提供的接口脚本

【待核实】清单（全部集中在文件顶部 CONFIG 一节，改这里即可，不用翻代码）
    1. 赛方仿真接口脚本的路径与文件名
    2. 一次调用是"全部 PVT 角"还是"一个角一次"
    3. 日志里 Gain/Phase/UGB/PM/GM/I_OPA 的字段名与单位
    4. PVT 角数是几个（本文件按 CORNERS 预算）
    5. --param_file 的格式与数值单位（SI / µm）
    6. 单次仿真耗时（决定预算；本文件自动测量并自适应）

评分口径（赛题 6.3）已内置：
    硬约束（全 PVT）：PM >= 50 deg, GM <= -10 dB, I_OPA <= 3 mA
    目标：DC Gain 越大越好（< 40dB 该项 0 分）、UGB 越大越好、Area 越小越好
    面积：MOS = fw*L*m*1.5；电容 = W*L；电阻 = W*L*2
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import subprocess
import sys
import time

# =====================================================================
# CONFIG —— 所有【待核实】项都放这里
# =====================================================================
CONFIG = {
    # ---- 赛方接口（待核实）----
    "provided_script": "optimization.py",       # 赛方提供的仿真接口脚本（样例包里的那个）
    "provided_extra_args": [],                  # 例：["--ae_lib", "input_comp_lib", ...]
    "sim_corner_mode": "all_in_one",            # "all_in_one" | "per_corner"
    "n_corners": 11,                            # 待核实：PVT 角总数
    "param_unit": "auto",                       # "si" | "um" | "auto"
    "sim_timeout_s": 1800,                      # 单次仿真超时

    # ---- 日志解析（待核实：按现场日志补/改正则）----
    "patterns": {
        "dc_gain_db": [r"DC\s*Gain\s*[:=]\s*([-\d.eE+]+)",
                       r"\bgain\s*[:=]\s*([-\d.eE+]+)\s*dB"],
        "ugb_hz":     [r"UGB\s*[:=]\s*([-\d.eE+]+)", r"UGF\s*[:=]\s*([-\d.eE+]+)"],
        "pm_deg":     [r"Phase\s*Margin\s*[:=]\s*([-\d.eE+]+)", r"\bPM\s*[:=]\s*([-\d.eE+]+)"],
        "gm_db":      [r"Gain\s*Margin\s*[:=]\s*([-\d.eE+]+)", r"\bGM\s*[:=]\s*([-\d.eE+]+)"],
        "i_opa_ma":   [r"I_?OPA\s*[:=]\s*([-\d.eE+]+)", r"current\s*[:=]\s*([-\d.eE+]+)"],
    },
    "corner_names": [],                          # 待核实：若日志分角，填角名列表

    # ---- 约束与目标（赛题原文）----
    "pm_min": 50.0,
    "gm_max": -10.0,                             # 注意符号：若日志给 |GM| 正值，这里改成 10 并把比较方向取反
    "i_max_ma": 3.0,
    "gain_floor_db": 40.0,

    # ---- 变量边界（赛题附件 2）----
    "bounds_um": {
        "w": (0.13, 20.0), "fw": (0.13, 20.0),
        "l": (0.13, 10.0), "segL": (0.13, 20.0), "segW": (0.13, 20.0),
        "m": (1, 20), "multi": (1, 20), "seg": (1, 20), "nf": (1, 20),
    },
    "integer_params": {"m", "multi", "seg", "nf"},

    # ---- 预算（3 小时硬上限）----
    "total_budget_s": 3 * 3600,
    "budget_use_ratio": 0.70,                    # 留 30% 给收尾/反标/PVT/意外
    "budget_use_ratio_mock": 0.95,

    # ---- 算法 ----
    "de_pop": 24,
    "de_F": 0.6,
    "de_CR": 0.9,
    "seed": 2026,
    "ckpt": "ckpt.json",
    "out_dir": ".",
}

# =====================================================================
# 通用小工具
# =====================================================================
VAR_RE = re.compile(r"^([A-Za-z_]\w*?)_(segL|segW|seg|fw|l|m|multi|nf|w)$")


def log(msg):
    print("[opt] " + msg, flush=True)


def param_name_of(symbol):
    """'NM2_fw' -> ('NM2', 'fw')；不认识返回 (symbol, None)。"""
    m = VAR_RE.match(symbol)
    return (m.group(1), m.group(2)) if m else (symbol, None)


def is_integer_param(suffix):
    return suffix in CONFIG["integer_params"]


def bounds_of(suffix):
    return CONFIG["bounds_um"].get(suffix)


# =====================================================================
# 参数文件读写（待核实：格式与单位）
# =====================================================================
def read_param_file(path):
    """读赛方 extractcdfVal_*.txt：返回 {符号: 原始字符串}（保留原样，便于回写）。"""
    out = {}
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(("#", "//")) or "=" not in line:
                continue
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


def parse_value(raw):
    """'1u' / '1e-6' / '0.13' -> float（无单位默认按 µm）；无法解析返回 None。"""
    raw = raw.strip().strip("'\"")
    m = re.fullmatch(r"([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)([a-zA-Z]*)", raw)
    if not m:
        return None
    val, suf = float(m.group(1)), m.group(2).lower()
    mult = {"": 1.0, "u": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15,
            "k": 1e3, "meg": 1e6, "m": 1e-3}.get(suf)
    return None if mult is None else val * mult


def detect_unit(symbols_raw):
    """猜数值单位：出现 u/n 后缀 -> SI；数值多在 0.1~100 -> µm。"""
    if any(re.search(r"\d[uUnNpP]$", v) for v in symbols_raw.values()):
        return "si"
    vals = [parse_value(v) for v in symbols_raw.values()]
    vals = [x for x in vals if x]
    if vals and max(vals) < 1e-3:
        return "si"
    return "um"


def to_um(value, unit):
    """物理值 -> µm。"""
    return value * 1e6 if unit == "si" else value


def from_um(value_um, unit):
    return value_um * 1e-6 if unit == "si" else value_um


def format_value(value, unit):
    """µm 值 -> 写回参数字符串（SI 时用科学计数法，µm 时直接给数）。"""
    if unit == "si":
        return "%.6e" % (value * 1e-6)
    return "%.6g" % value


# =====================================================================
# 变量空间
# =====================================================================
def build_space(raw_params, unit, optimize_all=True, groups=None):
    """从参数文件构造可优化变量表。

    返回 spec = {symbol: {"param": suffix, "lo":µm, "hi":µm, "integer":bool,
                          "init":µm, "unit":unit}}
    只认尺寸类后缀；其它（如 ad/as 派生量、常量）保持不动。
    """
    spec = {}
    for sym, raw in raw_params.items():
        _dev, suf = param_name_of(sym)
        b = bounds_of(suf) if suf else None
        v = parse_value(raw)
        if b is None or v is None:
            continue
        lo, hi = b
        val_um = to_um(v, unit)
        spec[sym] = {"param": suf, "lo": lo, "hi": hi,
                     "integer": is_integer_param(suf),
                     "init": min(max(val_um, lo), hi), "unit": unit}
    if groups:                                  # 可选：把分组内变量绑到基准
        spec = apply_groups(spec, groups)
    return spec


def apply_groups(spec, groups):
    """groups: [[symbol, symbol, ...], ...]。组内只保留第一个作为自由变量，
    其余标记 bound_to（评估时取值与基准相同）。"""
    by_sym = {}
    for grp in groups:
        grp = [s for s in grp if s in spec]
        if len(grp) < 2:
            continue
        base = grp[0]
        for s in grp[1:]:
            by_sym[s] = base
    out = {}
    for sym, s in spec.items():
        if sym in by_sym:
            continue
        out[sym] = s
    # 绑定关系单独存（不参与搜索）
    bound = {s: b for s, b in by_sym.items() if b in out}
    for v in out.values():
        v["bound"] = {}
    for s, b in bound.items():
        out[b].setdefault("bound", {})[s] = b
    return out


# =====================================================================
# 指标解析 / 聚合 / 约束 / 面积
# =====================================================================
def parse_metrics(text):
    """从日志文本抽指标。能处理两种常见形态：
       ① 全文一份（所有角已聚合成最坏值）
       ② 分角多段（每段一份）
    返回 list[dict]；空 list 表示没解析到。
    """
    blocks = re.split(r"(?im)^\s*(?:corner|角|case)\s*[:=#]", text)
    out = []
    for block in blocks:
        row = {}
        for key, pats in CONFIG["patterns"].items():
            for p in pats:
                m = re.search(p, block, re.I)
                if m:
                    try:
                        row[key] = float(m.group(1))
                    except ValueError:
                        pass
                    break
        if len(row) >= 3:
            out.append(row)
    return out


def aggregate(corners):
    if not corners:
        return None
    def pick(k, fn):
        vals = [c[k] for c in corners if k in c]
        return fn(vals) if vals else None
    return {
        "n_corners": len(corners),
        "pm_min": pick("pm_deg", min),
        "gm_worst": pick("gm_db", max),
        "i_max": pick("i_opa_ma", max),
        "gain_min": pick("dc_gain_db", min),
        "ugb_min": pick("ugb_hz", min),
    }


def constraints_ok(agg):
    bad = {}
    if agg is None:
        return False, {"no_data": 1.0}
    if agg["pm_min"] is None or agg["pm_min"] < CONFIG["pm_min"]:
        bad["PM"] = CONFIG["pm_min"] - (agg["pm_min"] if agg["pm_min"] is not None else -1e9)
    if agg["gm_worst"] is None or agg["gm_worst"] > CONFIG["gm_max"]:
        bad["GM"] = (agg["gm_worst"] if agg["gm_worst"] is not None else 1e9) - CONFIG["gm_max"]
    if agg["i_max"] is None or agg["i_max"] > CONFIG["i_max_ma"]:
        bad["I_OPA"] = (agg["i_max"] if agg["i_max"] is not None else 1e9) - CONFIG["i_max_ma"]
    return (not bad), bad


def area_um2(values_um):
    """按赛题公式算面积。values_um: {symbol: µm 值}（调用方保证整数参数已取整）。"""
    total, detail = 0.0, {}
    for sym, v in values_um.items():
        dev, suf = param_name_of(sym)
        if suf not in ("w", "fw", "l", "segL", "segW"):
            continue
        # 这里只做"逐器件归集"，具体公式在下方按器件名首字母判断
        detail.setdefault(dev, {})[suf] = v
    for dev, p in detail.items():
        w = p.get("w", p.get("fw"))
        l = p.get("l", p.get("segW", p.get("segL")))
        if w is None or l is None:
            continue
        if dev.startswith(("NM", "PM")):
            m = 1.0
            for sym, v in values_um.items():       # 找同器件的 m
                d2, s2 = param_name_of(sym)
                if d2 == dev and s2 == "m":
                    m = float(v)
            total += w * l * m * 1.5
        elif dev.startswith("C"):
            total += w * l
        elif dev.startswith("R"):
            total += w * l * 2            # 注意【待核实】：串联分段是否要乘段数
    return total


# =====================================================================
# 假仿真器（本地跑通算法链路用；趋势正确、物理不精确）
# =====================================================================
def mock_simulate(values_um):
    """values_um: {symbol: µm/整数}。返回与真实日志同结构的角列表（这里造 3 个角）。"""
    def g(*names, default=1.0):
        for n in names:
            if n in values_um:
                return float(values_um[n])
        return default
    w_in = g("PM9_fw", "PM10_fw", default=10.0)
    l_in = g("PM9_l", "PM10_l", default=1.0)
    m_mir = g("NM2_m", "NM8_m", default=8.0)
    w_out = g("PM7_fw", "PM11_fw", default=10.0)
    l_out = g("PM7_l", "PM11_l", default=1.0)
    c_l = g("C0_l", "C11_l", default=2.0)
    gm = 180.0 * math.sqrt(max(w_in, 1e-3) / max(l_in, 1e-3))
    gain = 20 * math.log10(max(gm, 1e-3)) + 14.0 * math.log10(max(w_out / max(l_out, 1e-3), 1e-3))
    ugb = 1.0e6 * gm / (1.0 + l_in) * (m_mir / 8.0) ** 0.3
    pm = 58.0 + 42.0 * (l_in / (l_in + 2.0)) - 0.6 * (m_mir - 8) - 8.0 / max(c_l, 0.5)
    i_ma = 0.38 * m_mir * (w_in / 10.0) ** 0.2
    rows = []
    for k, (dg, du, dp) in enumerate(((1.00, 1.00, 1.00),
                                      (0.94, 0.88, 0.86),
                                      (1.06, 1.12, 1.14))):
        rows.append({"corner": "mock%d" % (k + 1),
                     "dc_gain_db": gain * dg,
                     "ugb_hz": ugb * du,
                     "pm_deg": pm - (1 - dp) * 20,
                     "gm_db": -13.0 + k,
                     "i_opa_ma": i_ma * (1 + 0.08 * k)})
    return rows


# =====================================================================
# 真实仿真适配器（待核实）
# =====================================================================
class RealBackend:
    def __init__(self, args, workdir):
        self.args = args
        self.workdir = workdir
        self.script = os.path.join(workdir, CONFIG["provided_script"])
        self.t_eval = None

    def simulate(self, values_original):
        """values_original: {符号: 原始字符串值}（已按赛方单位格式化）。
        写 param 文件 -> 调赛方脚本 -> 解析 -> 返回角列表。"""
        pfile = "param_%d.txt" % int(time.time() * 1000 % 1e9)
        with open(os.path.join(self.workdir, pfile), "w", encoding="utf-8") as f:
            for k in sorted(values_original):
                f.write("%s=%s\n" % (k, values_original[k]))
        cmd = [sys.executable, self.script] + CONFIG["provided_extra_args"] + [
            "--param_file", pfile,
            "--output_path", "./results_opt",
            "--output_file", "output.log",
        ]
        t0 = time.time()
        try:
            r = subprocess.run(cmd, cwd=self.workdir, capture_output=True,
                               text=True, timeout=CONFIG["sim_timeout_s"])
            text = (r.stdout or "") + "\n" + (r.stderr or "")
        except subprocess.TimeoutExpired:
            return None
        self.t_eval = time.time() - t0
        log_path = os.path.join(self.workdir, "results_opt", "output.log")
        if os.path.exists(log_path):
            text += "\n" + open(log_path, encoding="utf-8", errors="replace").read()
        return parse_metrics(text)


# =====================================================================
# 代价函数（可行性优先）
# =====================================================================
def cost_of(agg, area):
    ok, bad = constraints_ok(agg)
    if not ok:
        return 1e6 + sum(bad.values())
    if agg["gain_min"] < CONFIG["gain_floor_db"]:
        return 1e5 + (CONFIG["gain_floor_db"] - agg["gain_min"])
    # 可行：三项目标归一化后加权（权重按"每 1% 换多少分"定，先用经验值，A/B 调）
    gain_score = (100.0 - agg["gain_min"]) / 10.0            # 每 10dB 约 1 分
    ugb_score = (1e7 / max(agg["ugb_min"], 1.0))             # UGB 越大越好
    area_score = area / 100.0                                # 面积越小越好
    return 0.5 * gain_score + 1.0 * ugb_score + 1.0 * area_score


# =====================================================================
# 差分进化
# =====================================================================
def optimize(spec, evaluate, budget_evals, time_limit_s, seed=None, log_every=1):
    rng = random.Random(seed if seed is not None else CONFIG["seed"])
    syms = list(spec)
    lo = [spec[s]["lo"] for s in syms]
    hi = [spec[s]["hi"] for s in syms]
    D = len(syms)
    cache, best = {}, {"cost": float("inf"), "values": None, "agg": None}
    t0 = time.time()
    n_eval = 0

    def to_values(x):
        """归一化向量 -> {自由变量: 物理值(µm/整数)}，并把绑定变量补成基准值。"""
        v = {}
        for i, s in enumerate(syms):
            p = lo[i] + x[i] * (hi[i] - lo[i])
            v[s] = int(round(p)) if spec[s]["integer"] else p
        out = dict(v)
        for s, meta in spec.items():
            for b in (meta.get("bound") or {}):
                out[b] = v[s]          # 绑定变量跟随基准
        return out

    def f(x):
        nonlocal n_eval, best
        v = to_values(x)
        key = json.dumps(v, sort_keys=True)
        if key in cache:
            return cache[key][0]
        if budget_evals and n_eval >= budget_evals:
            return float("inf")
        if time_limit_s and time.time() - t0 > time_limit_s:
            return float("inf")
        n_eval += 1
        agg = evaluate(v)
        if agg is None:
            c = 1e9
        else:
            c = cost_of(agg, area_um2(v))
        cache[key] = (c, agg)
        if c < best["cost"]:
            best = {"cost": c, "values": v, "agg": agg, "n_eval": n_eval}
            try:
                with open(CONFIG["ckpt"], "w", encoding="utf-8") as fp:
                    json.dump({"best": best, "n_eval": n_eval}, fp,
                              ensure_ascii=False, indent=1)
            except OSError:
                pass
        return c

    if D == 0:
        return best, {"n_eval": 0, "elapsed_s": 0.0, "gen": 0}

    pop = CONFIG["de_pop"]
    # 初始种群：0 号是初始解（赛题要求"在给定初始解条件下优化"）
    init = [(spec[s]["init"] - lo[i]) / (hi[i] - lo[i]) for i, s in enumerate(syms)]
    popu = [list(init)]
    for _ in range(pop - 1):
        popu.append([rng.random() for _ in range(D)])
    costs = [f(x) for x in popu]

    gen = 0
    while True:
        gen += 1
        improved = False
        for i in range(pop):
            idx = rng.sample(range(pop), 3)
            while i in idx:
                idx = rng.sample(range(pop), 3)
            a, b, c = idx
            trial = [popu[a][k] + CONFIG["de_F"] * (popu[b][k] - popu[c][k]) for k in range(D)]
            trial = [min(1.0, max(0.0, t)) for t in trial]
            jr = rng.randrange(D)
            trial = [trial[k] if (rng.random() < CONFIG["de_CR"] or k == jr) else popu[i][k]
                     for k in range(D)]
            ct = f(trial)
            if ct < costs[i]:
                popu[i], costs[i] = trial, ct
                improved = True
        if best["values"] is not None:
            popu[0], costs[0] = to_x(best["values"], syms, lo, hi), best["cost"]
        if log_every and gen % log_every == 0:
            log("gen %-3d best=%.4f  n_eval=%d  elapsed=%.0fs  best_agg=%s"
                % (gen, best["cost"], n_eval, time.time() - t0,
                   {k: (round(v, 2) if isinstance(v, float) else v)
                    for k, v in (best["agg"] or {}).items()}))
        if not improved or (budget_evals and n_eval >= budget_evals):
            break
        if time_limit_s and time.time() - t0 > time_limit_s:
            break
    return best, {"n_eval": n_eval, "elapsed_s": time.time() - t0, "gen": gen}


def to_x(values, syms, lo, hi):
    return [min(1.0, max(0.0, (values[s] - lo[i]) / (hi[i] - lo[i])))
            for i, s in enumerate(syms)]


# =====================================================================
# 输出
# =====================================================================
def write_outputs(best, spec, unit, raw_params, meta, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    values = best["values"] or {}
    # 1) 自由变量（µm）
    with open(os.path.join(out_dir, "best_free_values.txt"), "w", encoding="utf-8") as f:
        for s in sorted(values):
            f.write("%s=%s\n" % (s, format_value(values[s], unit)))
    # 2) 完整参数文件（原有符号 + 优化后的值；未优化的保持原样）
    full = {}
    for s, raw in raw_params.items():
        if s in values:
            full[s] = format_value(values[s], unit)
        else:
            full[s] = raw
    with open(os.path.join(out_dir, "best_schematic_params.txt"), "w", encoding="utf-8") as f:
        for s in sorted(full):
            f.write("%s=%s\n" % (s, full[s]))
    # 3) CSV（赛题要求的"变量=值"）
    with open(os.path.join(out_dir, "best_sizes.csv"), "w", encoding="utf-8") as f:
        f.write("var,value_um,type\n")
        for s in sorted(values):
            f.write("%s,%.6g,%s\n" % (s, values[s],
                                      "integer" if spec[s]["integer"] else "continuous"))
    # 4) 报告（JSON + Markdown）
    rep = {
        "n_variables": len(spec),
        "n_eval": meta["n_eval"],
        "elapsed_s": round(meta["elapsed_s"], 1),
        "generations": meta["gen"],
        "best_cost": best["cost"],
        "best_agg": best["agg"],
        "area_um2": area_um2(values) if values else None,
        "unit": unit,
        "config_snapshot": {k: CONFIG[k] for k in
                            ("pm_min", "gm_max", "i_max_ma", "gain_floor_db",
                             "total_budget_s", "budget_use_ratio")},
    }
    with open(os.path.join(out_dir, "opt_report.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    ok, bad = constraints_ok(best["agg"]) if best["agg"] else (False, {})
    lines = [
        "# 模块三优化结果", "",
        "- 变量数：%d" % len(spec),
        "- 评估次数：%d" % meta["n_eval"],
        "- 运行时间：%.1f s" % meta["elapsed_s"],
        "- 代数：%d" % meta["gen"],
        "- 最优代价：%.6g" % best["cost"],
        "- 面积：%.1f µm²" % (rep["area_um2"] or 0),
        "- 三条硬约束：%s" % ("全部满足 ✅" if ok else "**未满足** ❌ %s" % bad),
        "", "## 最坏情况指标", "",
        "| 指标 | 值 | 门限 | 判定 |", "|---|---|---|---|",
    ]
    if best["agg"]:
        a = best["agg"]
        def judge(v, op):
            return "✅" if v is not None and op else "❌"
        lines += [
            "| PM (deg) | %s | ≥ %.0f | %s |" % (a["pm_min"], CONFIG["pm_min"],
                                                judge(a["pm_min"], (a["pm_min"] or -1e9) >= CONFIG["pm_min"])),
            "| GM (dB) | %s | ≤ %.0f | %s |" % (a["gm_worst"], CONFIG["gm_max"],
                                                judge(a["gm_worst"], (a["gm_worst"] or 1e9) <= CONFIG["gm_max"])),
            "| I_OPA (mA) | %s | ≤ %.1f | %s |" % (a["i_max"], CONFIG["i_max_ma"],
                                                   judge(a["i_max"], (a["i_max"] or 1e9) <= CONFIG["i_max_ma"])),
            "| DC Gain (dB) | %s | ≥ %.0f（<%.0f 记 0 分） | %s |"
            % (a["gain_min"], CONFIG["gain_floor_db"], CONFIG["gain_floor_db"],
               judge(a["gain_min"], (a["gain_min"] or -1e9) >= CONFIG["gain_floor_db"])),
            "| UGB (Hz) | %s | 越大越好 | — |" % a["ugb_min"],
            "| 角数 | %s | — | — |" % a["n_corners"],
        ]
    lines += ["", "## 产物", "",
              "| 文件 | 内容 |", "|---|---|",
              "| `best_free_values.txt` | 优化后的自由变量（可直接做反标源） |",
              "| `best_schematic_params.txt` | 覆盖**原理图全部符号**的参数文件（喂 `--param_file`） |",
              "| `best_sizes.csv` | `变量,值,类型` 表格 |",
              "| `opt_report.json` | 机器可读结果（评估次数/时间/最坏指标/面积） |",
              "| `ckpt.json` | 断点（中断后可从最优解继续） |"]
    with open(os.path.join(out_dir, "opt_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return rep


# =====================================================================
# 三种模式
# =====================================================================
def run_selfcheck(args):
    ok = True
    def chk(name, cond, detail=""):
        nonlocal ok
        print("[%s] %s%s" % ("✅" if cond else "❌", name, ("  " + detail) if detail else ""))
        ok = ok and cond
    chk("Python 版本 >= 3.8", sys.version_info >= (3, 8), sys.version.split()[0])
    chk("标准库可用（json/math/re/subprocess）", True)
    chk("CONFIG 里三条硬约束已填",
        CONFIG["pm_min"] == 50.0 and CONFIG["gm_max"] == -10.0 and CONFIG["i_max_ma"] == 3.0)
    chk("预算合法", 0 < CONFIG["budget_use_ratio"] <= 1,
        "可用 %.0f s / 总 %.0f s" % (CONFIG["total_budget_s"] * CONFIG["budget_use_ratio"],
                                    CONFIG["total_budget_s"]))
    # 解析自检
    demo = ("corner: tt\nDC Gain = 72.5 dB\nUGB = 2.1e8\nPhase Margin = 63.2 deg\n"
            "Gain Margin = -12.4 dB\nI_OPA = 1.85 mA\n")
    rows = parse_metrics(demo)
    chk("日志解析自检（字段名匹配）", bool(rows) and abs(rows[0]["pm_deg"] - 63.2) < 1e-6,
        "解析到 %d 条" % len(rows))
    # 面积自检
    a = area_um2({"NM2_fw": 1.0, "NM2_l": 2.0, "NM2_m": 4, "C0_l": 2.0, "C0_w": 10.0})
    chk("面积公式自检", abs(a - (1.0 * 2.0 * 4 * 1.5 + 2.0 * 10.0)) < 1e-6, "%.1f µm²" % a)
    print("\n自检%s。真机运行前请先确认 CONFIG 顶部 6 项【待核实】。" % ("通过" if ok else "未通过"))
    return 0 if ok else 1


def run_mock(args):
    # 变量空间：优先用真实参数文件，没有就用一个 8 变量的小例子
    out_dir = args.out_dir or "./results_mock"
    CONFIG["ckpt"] = os.path.join(out_dir, "ckpt.json")
    if args.param_file and os.path.exists(args.param_file):
        raw = read_param_file(args.param_file)
        unit = CONFIG["param_unit"] if CONFIG["param_unit"] != "auto" else detect_unit(raw)
        spec = build_space(raw, unit)
        log("参数文件 %s：%d 个符号，其中 %d 个可优化（单位 %s）"
            % (args.param_file, len(raw), len(spec), unit))
    else:
        raw = {"PM9_fw": "10u", "PM9_l": "1u", "NM2_m": "8",
               "PM7_fw": "10u", "PM7_l": "1u", "C0_l": "2u", "NM2_l": "1u"}
        unit = "si"
        spec = build_space(raw, unit)
        log("未给参数文件：使用内置 8 变量示例")
    t_eval = 0.02
    budget = args.budget_evals or 80
    time_limit = t_eval * budget * 3
    def evaluate(values):
        return aggregate(mock_simulate(values))
    best, meta = optimize(spec, evaluate, budget, time_limit)
    rep = write_outputs(best, spec, unit, raw, meta, out_dir)
    log("mock 完成：评估 %d 次，耗时 %.1fs，最优代价 %.4g" %
        (meta["n_eval"], meta["elapsed_s"], best["cost"]))
    log("最坏指标：%s" % rep["best_agg"])
    return 0


def run_real(args):
    out_dir = args.out_dir or "./results_opt"
    CONFIG["ckpt"] = os.path.join(out_dir, "ckpt.json")
    if not os.path.exists(CONFIG["provided_script"]):
        log("找不到赛方接口脚本 %s —— 先用 --selfcheck / --mock，或用 --dry-run 探测。"
            % CONFIG["provided_script"])
        return 2
    raw = read_param_file(args.param_file) if args.param_file else {}
    if not raw:
        log("需要 --param_file（赛方给的 extractcdfVal_0.txt）")
        return 2
    unit = CONFIG["param_unit"] if CONFIG["param_unit"] != "auto" else detect_unit(raw)
    spec = build_space(raw, unit)
    log("可优化变量 %d 个（单位 %s，模式 %s）" % (len(spec), unit, CONFIG["sim_corner_mode"]))
    backend = RealBackend(args, os.getcwd())

    t_probe = time.time()
    probe = backend.simulate({s: format_value(spec[s]["init"], unit) for s in spec})
    dt = time.time() - t_probe
    if probe is None:
        log("首次仿真失败/超时（%.1fs）。用 --dry-run 看原始输出，核对 CONFIG['patterns']。" % dt)
        return 3
    log("首次仿真成功：%.1fs/次，解析到 %d 条角结果" % (dt, len(probe)))
    n_per_eval = dt if CONFIG["sim_corner_mode"] == "all_in_one" else dt * CONFIG["n_corners"]
    budget_s = CONFIG["total_budget_s"] * CONFIG["budget_use_ratio"]
    budget_evals = max(4, int(budget_s / max(n_per_eval, 1e-6)))
    log("预算：可用 %.0fs / 单次 %.1fs -> 上限 %d 次评估" % (budget_s, n_per_eval, budget_evals))

    def evaluate(values):
        # 关键：写回参数文件时必须覆盖**全部**原始符号（不只自由变量），
        # 否则被绑定/未优化符号会保持原理图初值，绑定关系在仿真里静默失效。
        payload = dict(raw)
        for s in spec:
            payload[s] = format_value(values[s], unit)
        return aggregate(backend.simulate(payload))

    best, meta = optimize(spec, evaluate, budget_evals,
                          time_limit_s=budget_s * 0.95, seed=args.seed)
    rep = write_outputs(best, spec, unit, raw, meta, out_dir)
    log("完成：评估 %d 次，%.0fs；最优代价 %.4g；约束%s"
        % (meta["n_eval"], meta["elapsed_s"], best["cost"],
           "满足" if constraints_ok(best["agg"])[0] else "未满足"))
    log("报告：%s" % os.path.join(out_dir, "opt_report.md"))
    return 0


def run_dry(args):
    """探测模式：只跑一次仿真，把原始输出打出来（用于核对日志字段名）。"""
    if not os.path.exists(CONFIG["provided_script"]):
        log("找不到 %s；把本文件放到样例包目录下再试。" % CONFIG["provided_script"])
        return 2
    raw = read_param_file(args.param_file) if args.param_file else {}
    if not raw:
        log("需要 --param_file")
        return 2
    unit = detect_unit(raw)
    vals = {s: raw[s] for s in raw}
    backend = RealBackend(args, os.getcwd())
    rows = backend.simulate(vals)
    log("单次仿真完成，耗时 %.1fs" % (backend.t_eval or -1))
    print("\n===== 解析结果 =====")
    print(json.dumps(rows, ensure_ascii=False, indent=1))
    print("\n===== 若解析为空或字段不对：请把赛方 output.log 的前 80 行发出来，")
    print("      据此改 CONFIG['patterns'] 与 CONFIG['sim_corner_mode']。 =====")
    return 0 if rows else 4


def main():
    ap = argparse.ArgumentParser(description="模块三：基于约束的多目标尺寸优化（单文件）")
    ap.add_argument("--selfcheck", action="store_true", help="环境/逻辑自检")
    ap.add_argument("--mock", action="store_true", help="用假仿真器跑通算法链路")
    ap.add_argument("--real", action="store_true", help="真机优化")
    ap.add_argument("--dry-run", action="store_true", help="只跑一次仿真并打印解析结果")
    ap.add_argument("--param-file", default=argparse.SUPPRESS,
                    help="赛方参数文件（extractcdfVal_0.txt）；兼容评分脚本传入")
    ap.add_argument("--out-dir", default=argparse.SUPPRESS)
    ap.add_argument("--budget-evals", type=int, default=0, help="覆盖评估次数上限（mock 用）")
    ap.add_argument("--seed", type=int, default=CONFIG["seed"])
    # 兼容赛方可能传入的参数（我们不一定用，但不能因此报错退出）
    for k in ("--ae_lib", "--ae_cell", "--ae_view", "--mde_cell", "--mde_view",
              "--output_path", "--output_file"):
        ap.add_argument(k, default=None)
    args, unknown = ap.parse_known_args()
    args.param_file = getattr(args, "param_file", "")
    args.out_dir = getattr(args, "out_dir", None)   # None -> 各模式用各自默认目录
    if unknown:
        log("忽略未知参数：%s" % " ".join(unknown))

    if args.selfcheck:
        return run_selfcheck(args)
    if args.mock:
        return run_mock(args)
    if args.dry_run:
        return run_dry(args)
    return run_real(args)


if __name__ == "__main__":
    raise SystemExit(main())
