#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块四公共库：参数读写 / 单位换算 / 变量边界 / 导出 schema / MDE 旧路径修复

为什么单独抽出来：模块四有 5 个脚本，都要用同一套"什么是合法参数、单位怎么算、
真机路径怎么修"。口径分散在多份代码里一定会走样（2026-10-18 就吃过一次亏：
边界用了 0.13..20，而 score.py 实际按参数名 clamp 成 segL 5..100 / fw 0.15..50 …）。

**所有口径的唯一来源**
- `BOUNDS_*`：严格照抄 `score.py::read_parameters()` 的 clamp（队友 P0-3 实测）
- `EXPORT_SCHEMA`：照着真实 `case1_params_0.txt` 的 105 个变量反推（队友 P0-4 实测）
  105 = MOS 29×3(`m,l,fw`) + 电容 6×1(**只有 `l`**) + 电阻 6×2(`segL,segW`)
- `fix_sim_paths()`：修复 MDE corner 配置里指向旧机器的绝对路径（队友 P0-8 实测）

只依赖标准库；不 import pyAether（由调用方负责）。
"""
import io
import os
import re
import shutil

# ---------------------------------------------------------------------------
# 变量边界：严格对齐 score.py::read_parameters()（队友 P0-3 实测值）
# ---------------------------------------------------------------------------
BOUNDS_COMMON = {
    "fw": (0.15, 50.0),      # µm
    "segW": (0.42, 10.0),    # µm
    "segL": (5.0, 100.0),    # µm
}
BOUNDS_L_DEFAULT = (0.13, 20.0)     # 除电容外所有 l
BOUNDS_L_CAP = (4.0, 30.0)          # 电容的 l
BOUNDS_INT = (1, 100)               # m / segments（整数）

# 真实参数文件 schema（P0-4）：器件类型 -> 该类型在参数文件里出现的参数
EXPORT_SCHEMA = {
    "MOS": ("m", "l", "fw"),
    "C": ("l",),
    "R": ("segW", "segL"),
}

UNIT = {"m": "-", "segments": "-", "l": "µm", "fw": "µm", "segW": "µm", "segL": "µm"}

INTEGER_PARAMS = ("m", "segments", "multi")


def kind_of(inst_name):
    """按实例名判器件类型：R* -> R，C* -> C，NM*/PM* -> MOS，其它 None。"""
    n = str(inst_name)
    if n[:1] in ("R", "r"):
        return "R"
    if n[:1] in ("C", "c"):
        return "C"
    if n.startswith(("NM", "PM", "nm", "pm")):
        return "MOS"
    return None


def bounds_for(kind, param):
    """返回 (min, max, is_integer)。"""
    if param in INTEGER_PARAMS:
        return (BOUNDS_INT[0], BOUNDS_INT[1], True)
    if param == "l":
        lo, hi = BOUNDS_L_CAP if kind == "C" else BOUNDS_L_DEFAULT
        return (lo, hi, False)
    if param in BOUNDS_COMMON:
        lo, hi = BOUNDS_COMMON[param]
        return (lo, hi, False)
    return (0.13, 20.0, False)


# ---------------------------------------------------------------------------
# 参数文件读写（兼容赛方三种写法）
# ---------------------------------------------------------------------------
def split_inst_param(name):
    """'NM2_fw' -> ('NM2', 'fw')"""
    i = name.rfind("_")
    return (name[:i], name[i + 1:]) if i > 0 else (name, "")


def parse_param_line(line):
    """解析一行参数，返回 (name, raw_value) 或 None。

    支持：
        "parameter","NM2_fw","4u"      <- 赛方 case1_params_0.txt
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
    if len(fields) >= 3 and fields[0].lower() == "parameter":
        return (fields[1], fields[2])
    if len(fields) >= 2:
        return (fields[0], fields[1])
    return None


def read_param_file(path):
    """读参数文件 -> {name: raw_value}（保持文件顺序）。"""
    out = {}
    with io.open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            kv = parse_param_line(line)
            if kv:
                out[kv[0]] = kv[1]
    return out


def write_param_file(path, params):
    """按赛方格式写出（三列带引号 CSV），保证 score.py 能读。"""
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        for name in params:
            f.write('"parameter","%s","%s"\n' % (name, params[name]))
    return path


def param_to_float(raw):
    """长度值 -> **µm**（与赛方 param_convert 完全一致）。

    'u'/'um' = 微米；'n'/'nm' = 纳米；'p'/'f' 同理；**无单位按"米"**（4e-6 -> 4 µm）。
    面积公式因此直接得到 µm²。
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


def schema_check(params, verbose=True):
    """检查参数文件是否符合真实 schema（P0-4）。

    返回 (unknown, missing_count)：
        unknown      —— 文件里出现、但 schema 里不该有的参数（例如电容的 fw/m）
        missing_count—— 该文件里 MOS/R/C 各类器件缺了多少个 schema 参数
    只做提示，不阻断（Hidden 电路可能有差异）。
    """
    unknown = []
    for name in params:
        inst, p = split_inst_param(name)
        kind = kind_of(inst)
        if kind is None:
            continue
        if p not in EXPORT_SCHEMA[kind]:
            unknown.append("%s(属于 %s 的 %s)" % (name, kind, p))
    return unknown


# ---------------------------------------------------------------------------
# P0-8：修复 MDE 配置里指向旧机器的绝对路径
# ---------------------------------------------------------------------------
PATH_RE = re.compile(r"(/[^\s\"'<>;]+hes_release/[^\s\"'<>;:]+)")
SKIP_DIRS = {".git", "__pycache__", "hes_release", "results", "case_results"}


def _candidate_files(root, max_depth=6):
    """找出可能含旧绝对路径的文本文件：setting / adeL2View.file / *.scs。"""
    root = os.path.abspath(root)
    base_depth = root.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(root):
        depth = dirpath.rstrip(os.sep).count(os.sep) - base_depth
        if depth > max_depth:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            low = fn.lower()
            if low in ("setting", "adel2view.file") or low.endswith(".scs"):
                yield os.path.join(dirpath, fn)


def fix_sim_paths(root=None, verbose=True, backup=True, dry_run=False):
    """把不存在的 `/.../hes_release/...` 绝对路径重定向到 `<root>/hes_release/...`（仅当目标存在）。

    背景（队友 P0-8 实测）：MDE corner 配置里写死了旧机路径
    `/home/eda_2025/EDA_2025_Empyrean_lab_start/hes_release/models/spectre/spe_demo.scs`，
    而当前环境是 `/home/edauser32/EDA_2026_.../hes_release/...` —— 仿真直接 `File does not exist`，
    整轮 0 分。这里只改**确实不存在**、且**新位置确实存在**的路径，不硬编码用户名/年份。

    返回 {"scanned": n, "modified": m, "details": [(path, 旧->新 列表)]}
    """
    root = os.path.abspath(root or os.getcwd())
    scanned, modified, details = 0, 0, []
    for path in _candidate_files(root):
        try:
            with io.open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
                text = f.read()
        except OSError:
            continue
        scanned += 1
        changes = []

        def _repl(m):
            old = m.group(1)
            if os.path.exists(old):
                return old
            idx = old.find("hes_release/")
            if idx < 0:
                return old
            cand = os.path.join(root, old[idx:])
            if os.path.exists(cand):
                changes.append((old, cand))
                return cand
            return old

        new = PATH_RE.sub(_repl, text)
        if new != text:
            modified += 1
            details.append((path, changes))
            if not dry_run:
                try:
                    if backup:
                        shutil.copy2(path, path + ".m4bak")
                    with io.open(path, "w", encoding="utf-8", newline="") as f:
                        f.write(new)
                except OSError as e:
                    if verbose:
                        print("WARN: 写回 %s 失败: %s" % (path, e))
    if verbose:
        print("[P0-8] 模型路径修复完成：扫描 %d 个候选文件，改动 %d 个（root=%s）"
              % (scanned, modified, root))
        for path, changes in details:
            for old, new in changes:
                print("         %s\n           %s\n        -> %s" % (os.path.basename(path), old, new))
        if modified and not dry_run and backup:
            print("           （原文件已备份为 *.m4bak）")
    return {"scanned": scanned, "modified": modified, "details": details}
