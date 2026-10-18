#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块四-② 反标脚本：把最优尺寸写回原理图，生成带最优参数的新视图 `.schematic_var_best`

用途（对应 `任务分析.docx` 模块四②）：
    "将最优尺寸回写至电路图的反标脚本"（赛题 6.2 第 4 项交付物）

用法
----
    # 推荐：拷到新视图再反标（不动原图）
    pythone writeback.py --ae_lib 2026_EDA_case1 --ae_cell OPA --ae_view schematic \
        --param_file best_schematic_params.txt --out_view schematic_var_best

    # 本机验证（不需要 PyAether）：用假平台走一遍反标 + 读回校验
    python writeback.py --mock --param_file best_schematic_params.txt

    # 确实只想改原图（危险，需显式声明）
    pythone writeback.py ... --in_place

安全约定
--------
- **默认不修改原 schematic**：先尝试把 cellview 拷成 `--out_view` 再写。
- 如果平台没有可用的"拷贝 cellview"接口，脚本**直接退出并提示**，不会偷偷改原图；
  确认要改原图时再加 `--in_place`（此时会先写一份 `params_before.txt` 备份）。
- 写完**逐参数读回校验**（`aeEmyInstGetParameter`），不一致会逐条列出并返回非 0。

产物
----
    params_var_best.txt      反标使用的参数快照（赛方三列 CSV 格式）
    params_before.txt        反标前该视图上的参数（--in_place 时尤其重要）
    writeback_verify.txt     逐参数读回校验结果
    writeback_report.json    机器可读记录（视图、参数数、失败/不一致数）
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m4_common import (EXPORT_SCHEMA, kind_of, param_to_float,
                       parse_param_line, read_param_file, split_inst_param,
                       write_param_file)

DEFAULTS = {
    "ae_lib": "2026_EDA_case1",
    "ae_cell": "OPA",
    "ae_view": "schematic",
    "out_view": "schematic_var_best",
}

# 需要反标的参数类型（与赛方 extract_params 一致）
PARAM_KINDS = ("segW", "segL", "l", "m", "fw", "segments")


# ---------------------------------------------------------------------------
# 参数读写（与 sim_engine.py 保持一致的多格式解析）
# ---------------------------------------------------------------------------
# 参数读写/单位换算统一由 m4_common 提供

# ---------------------------------------------------------------------------
# 平台操作
# ---------------------------------------------------------------------------
def find_inst(cv, inst_name):
    return ae.dbFindInst(cv=cv, name=inst_name)


def read_back(cv, params):
    """把视图上的实际参数读回来（用于校验）。"""
    actual = {}
    for name in params:
        inst_name, param_name = split_inst_param(name)
        inst = find_inst(cv, inst_name)
        if not inst:
            actual[name] = "<instance not found>"
            continue
        try:
            actual[name] = ae.aeEmyInstGetParameter(param_name, inst)
        except Exception as e:
            actual[name] = "<read error: %s>" % e
    return actual


def try_copy_view(cv, out_view):
    """尝试把 cv 拷成新 view。返回新 cv 或 None（接口不可用时）。"""
    lib, cell = cv.libName, cv.cellName
    candidates = [
        ("dbCopyCellView", (lib, cell, cv.viewName, out_view)),
        ("dbCopyCellView", (cv, lib, cell, out_view)),
        ("dbCopyCV", (cv, out_view)),
        ("dbCopyCV", (lib, cell, cv.viewName, out_view)),
        ("dbCopyDesign", (cv, out_view)),
    ]
    for fname, args in candidates:
        fn = getattr(ae, fname, None)
        if fn is None:
            continue
        try:
            ret = fn(*args)
            if ret:
                print("==== 视图拷贝成功：%s -> %s（用 %s）====" % (cv.viewName, out_view, fname))
                return ret if hasattr(ret, "instances") else ae.dbOpenCV(lib, cell, out_view)
        except Exception as e:
            print("  (尝试 %s 失败: %s)" % (fname, e))
    return None


def apply_and_verify(cv, params, verbose=True):
    """写入参数并逐条读回校验。返回 (failed, mismatched)。"""
    failed = []
    for name, raw in params.items():
        inst_name, param_name = split_inst_param(name)
        if param_name not in PARAM_KINDS:
            continue
        inst = find_inst(cv, inst_name)
        if not inst:
            failed.append((name, "instance not found"))
            continue
        try:
            ret = ae.cdfSetParam(inst, param_name, str(raw))
        except Exception as e:
            failed.append((name, "exception: %s" % e))
            continue
        if not ret:
            failed.append((name, "cdfSetParam returned false"))

    save_res = None
    try:
        save_res = ae.dbCheckAndSaveDesign(cv)
    except Exception as e:
        failed.append(("<save>", "dbCheckAndSaveDesign: %s" % e))
    if verbose:
        print("==== 写入 %d 个参数，失败 %d 个，保存结果 %s ====" % (len(params), len(failed), save_res))

    actual = read_back(cv, params)
    mismatched = []
    for name, want in params.items():
        if split_inst_param(name)[1] not in PARAM_KINDS:
            continue
        got = actual.get(name)
        try:
            if abs(param_to_float(got) - param_to_float(want)) > 1e-9 * max(1.0, abs(param_to_float(want))):
                mismatched.append((name, want, got))
        except Exception:
            mismatched.append((name, want, got))
    return failed, mismatched


# ---------------------------------------------------------------------------
# mock：不依赖 PyAether 的完整流程演练
# ---------------------------------------------------------------------------
class MockInst(object):
    def __init__(self, name):
        self.name = name


class MockCV(object):
    def __init__(self, lib, cell, view, insts):
        self.libName, self.cellName, self.viewName = lib, cell, view
        self.instances = [MockInst(n) for n in insts]
        self.store = {}

    def set(self, inst_name, param, value):
        self.store[(inst_name, param)] = str(value)

    def get(self, param, inst):
        return self.store.get((inst.name, param), "0")


def run_mock(a):
    """用假平台走通：读参数 -> 反标 -> 读回校验 -> 落盘。"""
    params = read_param_file(a.param_file)
    if not params:
        print("ERROR: 参数文件为空或不存在: %s" % a.param_file, file=sys.stderr)
        return 2
    insts = sorted({split_inst_param(n)[0] for n in params})

    src = MockCV(a.ae_lib, a.ae_cell, a.ae_view, insts)
    for n, v in params.items():
        inst, p = split_inst_param(n)
        src.set(inst, p, "0")            # 模拟"反标前"的初值

    target = MockCV(a.ae_lib, a.ae_cell, a.out_view, insts)
    failed, mismatched = [], []
    for n, v in params.items():
        inst, p = split_inst_param(n)
        if p not in PARAM_KINDS:
            continue
        if inst not in insts:
            failed.append((n, "instance not found"))
            continue
        target.set(inst, p, v)
        got = target.get(p, MockInst(inst))
        try:
            if abs(param_to_float(got) - param_to_float(v)) > 1e-9 * max(1.0, abs(param_to_float(v))):
                mismatched.append((n, v, got))
        except Exception:
            mismatched.append((n, v, got))

    out_dir = a.out_dir or "."
    os.makedirs(out_dir, exist_ok=True)
    write_param_file(os.path.join(out_dir, "params_var_best.txt"), params)
    write_param_file(os.path.join(out_dir, "params_before.txt"),
                     {n: "0" for n in params})
    with io.open(os.path.join(out_dir, "writeback_verify.txt"), "w", encoding="utf-8") as f:
        f.write("# 反标读回校验（mock）\n")
        f.write("参数总数: %d, 类型不符: %d, 失败: %d, 不一致: %d\n"
                % (len(params), len(failed), len(failed), len(mismatched)))
        for n, want, got in mismatched:
            f.write("MISMATCH %s: want %s got %s\n" % (n, want, got))
    report = {
        "mode": "mock",
        "src_view": a.ae_view, "out_view": a.out_view,
        "n_params": len(params), "n_failed": len(failed), "n_mismatched": len(mismatched),
        "failed": failed, "mismatched": mismatched,
        "note": "mock 模式：用内存假视图验证反标与校验逻辑，未触碰真实原理图",
    }
    with io.open(os.path.join(out_dir, "writeback_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("==== mock 反标完成：%d 参数，失败 %d，不一致 %d ====" %
          (len(params), len(failed), len(mismatched)))
    print("==== 产物在 %s ====" % os.path.abspath(out_dir))
    return 0 if not failed and not mismatched else 1


# ---------------------------------------------------------------------------
# 真机
# ---------------------------------------------------------------------------
def run_real(a):
    if ae is None:
        print("ERROR: 未导入 pyAether。请在服务器上运行，或用 --mock 验证逻辑。", file=sys.stderr)
        return 2
    params = read_param_file(a.param_file)
    if not params:
        print("ERROR: 参数文件为空或不存在: %s" % a.param_file, file=sys.stderr)
        return 2
    ae.emyInitAether("-adv")

    out_dir = a.out_dir or "."
    os.makedirs(out_dir, exist_ok=True)

    src_cv = ae.dbOpenCV(a.ae_lib, a.ae_cell, a.ae_view)
    if not src_cv:
        print("ERROR: dbOpenCV(%s,%s,%s) 失败" % (a.ae_lib, a.ae_cell, a.ae_view), file=sys.stderr)
        return 3
    write_param_file(os.path.join(out_dir, "params_before.txt"), read_back(src_cv, params))

    target_cv = None
    if not a.in_place:
        # 目标视图若已存在（例如在 Aether 里手工拷过），直接写入它，避免依赖拷贝接口
        try:
            existing = ae.dbOpenCV(a.ae_lib, a.ae_cell, a.out_view)
        except Exception:
            existing = None
        if existing:
            print("==== 目标视图已存在，直接写入：%s ====" % a.out_view)
            target_cv = existing
        else:
            target_cv = try_copy_view(src_cv, a.out_view)
        if target_cv is None:
            ae.dbCloseCV(src_cv)
            print("\nERROR: 没能创建新视图 `%s`（平台缺少可用的 cellview 拷贝接口）。" % a.out_view,
                  file=sys.stderr)
            print("       为保护原图，已中止。可选做法：", file=sys.stderr)
            print("       1) 在 Aether 里手动把 schematic 复制成视图 %s，再运行本脚本（会自动识别该视图）"
                  % (a.out_view, a.out_view), file=sys.stderr)
            print("       2) 确认要直接改原图，加 --in_place", file=sys.stderr)
            return 4

    cv = target_cv if target_cv is not None else src_cv
    failed, mismatched = apply_and_verify(cv, params)
    try:
        ae.dbCloseCV(cv)
    except Exception:
        pass
    if target_cv is not None:
        try:
            ae.dbCloseCV(src_cv)
        except Exception:
            pass

    write_param_file(os.path.join(out_dir, "params_var_best.txt"), params)
    with io.open(os.path.join(out_dir, "writeback_verify.txt"), "w", encoding="utf-8") as f:
        f.write("# 反标读回校验\n")
        f.write("视图: %s/%s/%s\n" % (a.ae_lib, a.ae_cell, a.out_view if target_cv else a.ae_view))
        f.write("参数总数: %d, 失败: %d, 不一致: %d\n\n" % (len(params), len(failed), len(mismatched)))
        for n, r in failed:
            f.write("FAILED  %s: %s\n" % (n, r))
        for n, want, got in mismatched:
            f.write("MISMATCH %s: want %s got %s\n" % (n, want, got))
        if not failed and not mismatched:
            f.write("RESULT: OK 所有参数写入并读回一致\n")
    report = {
        "mode": "real",
        "lib": a.ae_lib, "cell": a.ae_cell,
        "src_view": a.ae_view, "out_view": a.out_view,
        "in_place": bool(a.in_place),
        "n_params": len(params), "n_failed": len(failed), "n_mismatched": len(mismatched),
        "failed": failed, "mismatched": mismatched,
    }
    with io.open(os.path.join(out_dir, "writeback_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=str)

    print("\n==== 反标完成：%d 参数，失败 %d，不一致 %d ====" % (len(params), len(failed), len(mismatched)))
    print("==== 产物：%s/{params_var_best.txt, params_before.txt, writeback_verify.txt, writeback_report.json} ====" % out_dir)
    return 0 if not failed and not mismatched else 1


def build_parser():
    p = argparse.ArgumentParser(description="模块四-② 反标：把最优尺寸写回原理图")
    p.add_argument("--ae_lib", default=DEFAULTS["ae_lib"])
    p.add_argument("--ae_cell", default=DEFAULTS["ae_cell"])
    p.add_argument("--ae_view", default=DEFAULTS["ae_view"])
    p.add_argument("--out_view", default=DEFAULTS["out_view"],
                   help="反标后的新视图名（默认 schematic_var_best）")
    p.add_argument("--target_view", default=None,
                   help="直接用已有视图作为写入目标（跳过拷贝）")
    p.add_argument("--param_file", default="best_schematic_params.txt")
    p.add_argument("--out_dir", default=".")
    p.add_argument("--in_place", action="store_true",
                   help="直接修改 --ae_view 原图（危险；会先备份参数）")
    p.add_argument("--mock", action="store_true", help="本地验证逻辑（不需要 PyAether）")
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    if a.target_view:
        a.out_view = a.target_view
        a.in_place = True
    if a.mock:
        return run_mock(a)
    return run_real(a)


if __name__ == "__main__":
    raise SystemExit(main())
