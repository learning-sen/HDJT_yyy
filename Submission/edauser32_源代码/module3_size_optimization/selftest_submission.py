# -*- coding: utf-8 -*-
"""
提交版 optimization.py 的本地逻辑自检（不需要服务器 / 不需要 pyAether）。

做法：造 pyAether、scipy.optimize 的桩模块，导入提交文件，只测**纯逻辑**部分：
  T1 _est_score            —— 目标函数是否与 score.py 的真实评分一致
  T2 _filter_groups        —— 模块二的默认分组能否按本电路正确过滤
  T3 read_parameters + apply_symmetry_constraints —— 参数从 105 降到多少
  T4 _patched_run_de       —— 预算计算 / 初始点兜底写文件 / 时间到提前停 / 异常仍保文件
用法：python module3/tools/selftest_submission.py
"""
import importlib.util
import io
import os
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                       # module3/
REPO = os.path.dirname(ROOT)
SUB = os.path.join(ROOT, "submission", "optimization.py")
TEMPLATE = os.path.join(REPO, "module2", "params_writeback_template.txt")

_fail = []


def check(name, cond, detail=""):
    print("[%s] %s%s" % ("PASS" if cond else "FAIL", name, ("  " + detail) if detail else ""))
    if not cond:
        _fail.append(name)


def install_stubs(tmpdir):
    """造 pyAether / scipy 桩，让提交文件可以被导入。"""
    # pyAether 桩：只要求"有这些名字"，本测试不调用
    pkg = os.path.join(tmpdir, "pyAether.py")
    with io.open(pkg, "w", encoding="utf-8") as f:
        f.write(
            "def emyInitAether(*a, **k): pass\n"
            "def dbOpenCV(*a, **k): return None\n"
            "def dbFindInst(*a, **k): return None\n"
            "def dbFindTerm(*a, **k): return None\n"
            "def dbSetTermPropVal(*a, **k): pass\n"
            "def dbCreateTerm(*a, **k): pass\n"
            "def dbOpenCellViewByType(*a, **k): return None\n"
            "def dbSave(*a, **k): pass\n"
            "def dbClose(*a, **k): pass\n"
            "def aeRunTcl(*a, **k): pass\n"
        )
    # scipy.optimize 桩：differential_evolution 只做几次评估，用于验证补丁流程
    os.makedirs(os.path.join(tmpdir, "scipy", "optimize"), exist_ok=True)
    with io.open(os.path.join(tmpdir, "scipy", "__init__.py"), "w") as f:
        f.write("")
    with io.open(os.path.join(tmpdir, "scipy", "optimize", "__init__.py"), "w", encoding="utf-8") as f:
        f.write(
            "import numpy as np\n"
            "class _R(object): pass\n"
            "def differential_evolution(func, bounds, init=None, maxiter=1, tol=0, **kw):\n"
            "    x = np.array(init, dtype=float)\n"
            "    best_x, best_f = None, float('inf')\n"
            "    for it in range(max(1, min(maxiter, 3))):\n"
            "        for row in x:\n"
            "            fv = func(row)\n"
            "            if fv < best_f: best_f, best_x = fv, row.copy()\n"
            "        cb = kw.get('callback')\n"
            "        if cb is not None and cb(best_x, 0.0): break\n"
            "        x = np.clip(x + np.random.normal(0, 0.05, x.shape), 0, 1)\n"
            "    r = _R(); r.x = best_x; r.fun = best_f; r.success = True; r.nit = it + 1\n"
            "    return r\n"
        )
    sys.path.insert(0, tmpdir)


def make_fake_params(tmpdir):
    """从 module2 的 105 个符号生成赛方格式的 case1_params_0.txt，并返回行数。"""
    syms = []
    for line in io.open(TEMPLATE, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("//") or "=" not in line:
            continue
        syms.append(line.split("=")[0].strip())
    vals = {"fw": "4u", "l": "1u", "m": "2", "segL": "25u", "segW": "2u",
            "w": "10u", "multi": "1", "seg": "1", "nf": "1"}
    path = os.path.join(tmpdir, "case1_params_0.txt")
    with io.open(path, "w", encoding="utf-8") as f:
        for s in syms:
            f.write('"parameter","%s","%s"\n' % (s, vals.get(s.rsplit("_", 1)[-1], "1")))
    return path, len(syms)


def import_submission(tmpdir):
    spec = importlib.util.spec_from_file_location("sub_opt", SUB)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sub_opt"] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    tmp = tempfile.mkdtemp(prefix="subtest_")
    install_stubs(tmp)
    import numpy as np
    sub = import_submission(tmp)
    print("导入成功；上游行数 %d + 补丁\n" % 919)

    # ---------- T1 目标函数 ----------
    perfect = {"Phase_Margin": 60.0, "Gain_Margin": -12.0, "Gain_db": 40.0,
               "I_OPA": 0.002, "UGB": 3e8, "Total_Area": 5000.0}
    s, v = sub._est_score(perfect)
    check("T1a 全达标 -> 80 分（不含时间分）", abs(s - 80.0) < 1e-9 and v == 0.0, "score=%s viol=%s" % (s, v))

    boundary = {"Phase_Margin": 50.0, "Gain_Margin": -10.0, "Gain_db": 20.0,
                "I_OPA": 0.003, "UGB": 2e8, "Total_Area": 8000.0}
    s, v = sub._est_score(boundary)
    check("T1b 恰好压线 -> 80 分", abs(s - 80.0) < 1e-9 and v == 0.0, "score=%s viol=%s" % (s, v))

    bad = {"Phase_Margin": 40.0, "Gain_Margin": -5.0, "Gain_db": 18.0,
           "I_OPA": 0.004, "UGB": 1e8, "Total_Area": 20000.0}
    s, v = sub._est_score(bad)
    # 只剩 UGB 15*(0.5)+Area 25*(0.4)=7.5+10=17.5
    check("T1c 约束违反 -> 分数下降且 viol>0", v > 0 and s < 20, "score=%.2f viol=%.2f" % (s, v))

    # ---------- T2/T3 约减 ----------
    param_path, n_sym = make_fake_params(tmp)
    params_all = sub.read_parameters(param_path, [])
    check("T2a 读参数文件", len(params_all) > 0, "%d 个符号（模板 %d）" % (len(params_all), n_sym))

    dummy_arg, sym_arg = sub._filter_groups(
        params_all, sub.DEFAULT_DUMMY_DEVICES, sub.DEFAULT_SYMMETRY_DEVICES)
    check("T2b 默认分组被正确过滤", len(dummy_arg.split(",")) == 4 and sym_arg.count("(") >= 10,
          "dummy=%d 组, symmetry=%d 组" % (len(dummy_arg.split(",")) if dummy_arg else 0,
                                           sym_arg.count("(")))

    dummy_devices = [d for d in dummy_arg.split(",") if d]
    params = sub.read_parameters(param_path, dummy_devices)
    non_dummy = {n: p for n, p in params.items() if not p.is_dummy}
    dummy_params = {n: p for n, p in params.items() if p.is_dummy}
    sym = sub.parse_symmetry_constraints(sym_arg)
    reduced, mapping = sub.apply_symmetry_constraints(non_dummy, sym) if sym else (non_dummy, None)
    check("T3a 约减生效", 40 <= len(reduced) <= 70,
          "全部 %d -> dummy %d / 待优化 %d -> 约减后 %d"
          % (len(params), len(dummy_params), len(non_dummy), len(reduced)))
    check("T3b dummy 只占 6 个符号", len(dummy_params) == 6, "%d" % len(dummy_params))

    # ---------- T4 预算感知 DE（用假 platform）----------
    out_dir = os.path.join(tmp, "results")
    best_file = os.path.join(tmp, "2026_EDA_case1_best_params.txt")
    written = {"n": 0}

    def fake_extract(lib, cell, view, path):
        with io.open(path, "w", encoding="utf-8") as f:
            f.write('"parameter","NM2_fw","4u"\n')
        written["n"] += 1
    sub.extract_params = fake_extract

    class FakeParam(object):
        def __init__(self, v):
            self.value = v
            self.min = 0.0
            self.max = 1.0
        def normalize(self, v):
            return float(v)
        def format_value(self, v):
            return "%.4g" % v

    class FakePlatform(object):
        ae_lib, ae_cell, ae_view = "2026_EDA_case1", "OPA", "schematic"
        output_path = out_dir
        best_param_file = best_file
        iter_count = 0
        best_fitness = float("inf")
        def normalize_values(self, *a):
            return a
        def denormalize_values(self, rp, x):
            return x
        def set_params(self, *a):
            return None
        def evaluate(self):
            return {"Phase_Margin": 55.0 + np.random.rand(), "Gain_Margin": -11.0,
                    "Gain_db": 45.0, "I_OPA": 0.0015, "UGB": 1.5e8, "Total_Area": 6000.0}

    plat = FakePlatform()
    plat.optimization_objective = types.MethodType(sub._patched_objective, plat)
    plat.run_de_optimization = types.MethodType(sub._patched_run_de, plat)
    reduced_fake = {"NM2_fw": FakeParam(0.3), "NM2_l": FakeParam(0.5), "PM0_m": FakeParam(0.2)}
    plat.run_de_optimization(reduced_fake, max_iter=None, pop_size=None, time_limit=30.0)

    check("T4a 优化后 best_param_file 存在", os.path.exists(best_file), best_file)
    check("T4b 至少写过一次最优参数", written["n"] >= 1, "写入 %d 次" % written["n"])
    check("T4c 输出目录已自动创建", os.path.isdir(out_dir), out_dir)
    check("T4d 迭代计数正常", plat.iter_count >= 2, "iter=%d" % plat.iter_count)

    # ---------- T5 单次评估模式（--evaluate 分支）----------
    import argparse as _ap

    class FakePlatform2(object):
        def __init__(self, **kw):
            self.__dict__.update(kw)
            self.only_set_called = False
            self.eval_called = False
        def only_set_params(self, params):
            self.only_set_called = True
        def evaluate(self):
            self.eval_called = True
            return {"Phase_Margin": 61.0, "Gain_Margin": -12.0, "Gain_db": 47.0,
                    "I_OPA": 0.001, "UGB": 2.5e8, "Total_Area": 4000.0}

    ns = _ap.Namespace(ae_lib="2026_EDA_case1", ae_cell="OPA", ae_view="schematic",
                       mde_cell="OPA_loopgain", mde_view="spe_state1_Corner",
                       param_file=param_path, output_path=os.path.join(tmp, "r2"),
                       output_file="output.log",
                       best_param_file=os.path.join(tmp, "best2.txt"),
                       symmetry_devices="", dummy_devices="", max_iter=100,
                       pop_size=300, verbose=False, set_params=True, evaluate=True,
                       use_algorithm_de=False)
    sub.parse_arguments = lambda: ns
    sub.SimulatePlatform = FakePlatform2
    sub._patched_main()
    check("T5a 单次评估模式走通", os.path.exists(ns.best_param_file), ns.best_param_file)

    print()
    if _fail:
        print("❌ 失败 %d 项: %s" % (len(_fail), _fail))
        return 1
    print("✅ 全部通过（本地逻辑自检；PyAether/MDE 部分未验证，需服务器实测）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
