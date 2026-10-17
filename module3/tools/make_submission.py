# -*- coding: utf-8 -*-
"""
从赛方模板生成提交版 optimization.py（模块三）。

设计：**不改赛方原类**，只在文件尾部插入一个补丁块，用 types.MethodType
覆盖 SimulatePlatform 的两个方法与入口流程。这样：
  - PyAether / MDE / 参数回写这些我们本地无法测试的部分，原样保留；
  - 我们只替换"优化策略"这一层，风险最小、可回退。

补丁内容（依据 run_score.sh 与 score.py 实测）：
  P1 默认约减：未传 --symmetry_devices/--dummy_devices 时，自动使用模块二识别出的
     对称/匹配/Dummy 分组（对 Hidden 电路会自动过滤为空 -> 退化为全独立，仍能跑）。
  P2 预算感知：先评估初始点测出单次耗时 T_eval，再按 3h×80% 反推种群/代数；
     到点用 scipy 的 callback 提前停止。
  P3 目标函数对齐真实评分：score.py 的公式（Gain≥20dB 满分10、UGB/2e8×15、
     Area 8000/area×25、PM/GM/I_OPA 各 10 + 违反再罚），而不是模板里按
     "首个可行值归一化"的 100/150/150 权重。
  P4 兜底：优化开始前先写一次 best_param_file；任何异常/超时都保证该文件存在
     （否则 score.py 读不到 -> 0 分）。
"""
import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
UPSTREAM = os.path.join(ROOT, "submission", "eda_2025_case_1_upstream.py")
OUT = os.path.join(ROOT, "submission", "optimization.py")

PATCH = r'''# =====================================================================
# [PATCH-MODULE3] 模块三改进：默认约减 + 预算感知 + 目标函数对齐真实评分
# 生成脚本：module3/tools/make_submission.py（依据 run_score.sh / score.py 实测）
# =====================================================================
import types
import time

TIME_LIMIT_TOTAL = 10800.0      # run_score.sh 默认 3 小时
BUDGET_RATIO = float(os.environ.get('OPT_BUDGET_RATIO', '0.80'))   # 留 20% 收尾/落盘/异常
MIN_POP = 12
MAX_POP = 36
MAX_ITER_CAP = 200
RANDOM_SEED = int(os.environ.get('OPT_SEED', '2026'))

# 服务器上冒烟测试用：OPT_TIME_LIMIT=300 就只跑 5 分钟（判分时不设这个变量 -> 10800）
TIME_LIMIT_TOTAL = float(os.environ.get('OPT_TIME_LIMIT', str(TIME_LIMIT_TOTAL)))

# score.py 的真实基线（run_score.sh 传入）
SCORE_GAIN_MIN_DB = 20.0
SCORE_UGB_BASE = 2.0e8
SCORE_AREA_BASE = 8000.0

# 模块二识别结果（针对本赛题电路；Hidden 电路名字不同会被自动过滤掉）
DEFAULT_DUMMY_DEVICES = "R5,R6,C4,C5"
DEFAULT_SYMMETRY_DEVICES = (
    "(NM15,NM14),(PM11,PM7),(PM10,PM9),(PM3,PM2),(NM4,NM5),(NM6,NM7),"
    "(NM8,NM9),(NM10,NM11),(NM12,NM13),(PM8,PM12),(R1,R2),(R0,R3),(C0,C11),(C2,C3)"
)


def _inst_names_of(parameters):
    """从参数名（形如 NM2_fw）反推实例名集合。"""
    return {n.rsplit('_', 1)[0] for n in parameters}


def _filter_groups(parameters, dummy_str, sym_str):
    """把默认分组过滤成"该电路里真实存在"的器件，避免 Hidden 电路报错。"""
    names = _inst_names_of(parameters)
    dummies = [d.strip() for d in dummy_str.split(',') if d.strip() and d.strip() in names]
    groups = []
    for g in re.findall(r'\(([^)]*)\)', sym_str):
        insts = [x.strip() for x in g.split(',') if x.strip()]
        insts = [x for x in insts if x in names]
        if len(insts) >= 2:
            groups.append(insts)
    return ','.join(dummies), ','.join('(%s)' % ','.join(g) for g in groups)


def _est_score(scores):
    """按 score.py 的真实公式估算得分（满分 100，不含时间分/时间罚分）。

    返回 (score, viol)：viol 是"归一化后的约束违反量"，用来在不可行时提供梯度。
    """
    s = 0.0
    viol = 0.0
    pm = scores.get('Phase_Margin')
    gm = scores.get('Gain_Margin')
    gain = scores.get('Gain_db')
    iopa = scores.get('I_OPA')
    ugb = scores.get('UGB')
    area = scores.get('Total_Area')

    if pm is None or pm == -float('inf'):
        viol += 6.0
    elif pm >= 50.0:
        s += 10.0
    else:
        viol += 1.0 + (50.0 - pm) / 5.0

    if gm is None or gm == float('inf'):
        viol += 6.0
    elif gm <= -10.0:
        s += 10.0
    else:
        viol += 1.0 + (10.0 + gm) / 2.0

    # 注意边界：score.py 是 `if gain_db < 20.0` 才算违反 -> gain == 20 可行且满分
    if gain is not None and gain >= SCORE_GAIN_MIN_DB:
        s += min(gain / SCORE_GAIN_MIN_DB, 1.0) * 10.0
    else:
        viol += 6.0

    if iopa is not None and iopa <= 0.003:
        s += 10.0
    else:
        viol += 6.0

    if ugb is not None and ugb > 1.0:
        s += min(ugb / SCORE_UGB_BASE, 1.0) * 15.0
    if area is not None and area > 1.0:
        s += min(SCORE_AREA_BASE / area, 1.0) * 25.0
    return s, viol


def _patched_objective(self, normalized_values, reduced_params):
    """可行性优先：不可行时 fitness 由 viol 主导；可行后等价于最大化真实评分。"""
    real_values = self.denormalize_values(reduced_params, normalized_values)
    self.set_params(reduced_params, real_values)
    scores = self.evaluate()

    score, viol = _est_score(scores)
    fitness = -score + viol * 1e3

    self.iter_count = getattr(self, 'iter_count', 0) + 1
    print('==== iter %d fitness %.6f (score %.2f, viol %.2f) PM=%s GM=%s Gain=%s UGB=%s I=%s Area=%s'
          % (self.iter_count, fitness, score, viol,
             scores.get('Phase_Margin'), scores.get('Gain_Margin'), scores.get('Gain_db'),
             scores.get('UGB'), scores.get('I_OPA'), scores.get('Total_Area')), flush=True)

    if fitness < getattr(self, 'best_fitness', float('inf')):
        self.best_fitness = fitness
        self.best_iter = self.iter_count
        try:
            os.makedirs(self.output_path, exist_ok=True)
            # 关键：把**当前最优**参数导出到 run_score.sh 指定的 best_param_file
            extract_params(self.ae_lib, self.ae_cell, self.ae_view, self.best_param_file)
            with open(os.path.join(self.output_path, 'best_result.txt'), 'w') as bf:
                bf.write('iter        : %d\n' % self.best_iter)
                bf.write('fitness     : %s\nscore       : %s\nviol        : %s\n'
                         % (fitness, score, viol))
                for k in ('UGB', 'Phase_Margin', 'Gain_db', 'Gain_Margin', 'I_OPA', 'Total_Area'):
                    bf.write('%-12s: %s\n' % (k, scores.get(k)))
            print('==== new best: iter %d fitness %.6f' % (self.best_iter, fitness), flush=True)
        except Exception as e:
            print('WARN: 保存最优解失败: %s' % e, flush=True)
    return fitness


def _patched_run_de(self, reduced_params, max_iter=None, pop_size=None, time_limit=None):
    """预算感知的差分进化：先测 T_eval，再分配种群/代数；超时前提前停。"""
    t0 = time.time()
    n_param = len(reduced_params)
    bounds = [(0.0, 1.0)] * n_param
    init_norm = np.array([p.normalize(p.value) for _, p in reduced_params.items()], dtype=float)

    self.iter_count = getattr(self, 'iter_count', 0)
    self.best_fitness = getattr(self, 'best_fitness', float('inf'))

    # ---- P4-a：先评估初始点（测耗时），同时保证 best_param_file 一定有内容 ----
    try:
        self.optimization_objective(init_norm, reduced_params)
    except Exception as e:
        print('WARN: 初始点评估失败: %s' % e, flush=True)
    t_eval = max(time.time() - t0, 0.05)
    if not os.path.exists(self.best_param_file):
        try:
            extract_params(self.ae_lib, self.ae_cell, self.ae_view, self.best_param_file)
            print('WARN: 已按初始参数兜底写出 %s' % self.best_param_file, flush=True)
        except Exception as e:
            print('ERROR: 兜底写 best_param_file 失败: %s' % e, flush=True)

    # ---- P2：按实测耗时反推预算 ----
    budget = (time_limit or TIME_LIMIT_TOTAL) * BUDGET_RATIO
    remain = max(budget - (time.time() - t0), 1.0)
    max_evals = max(20, int(remain / t_eval))
    pop_total = int(min(MAX_POP, max(MIN_POP, min(4 * n_param, max_evals // 8))))
    if max_iter is None:
        max_iter = int(min(MAX_ITER_CAP, max(1, max_evals // max(pop_total, 1) - 1)))
    print('\n==== BUDGET: t_eval=%.3fs max_evals~%d pop=%d maxiter=%d budget=%.0fs n_param=%d ===='
          % (t_eval, max_evals, pop_total, max_iter, budget, n_param), flush=True)

    rng = np.random.default_rng(RANDOM_SEED)
    init = np.vstack([init_norm, rng.uniform(0.0, 1.0, size=(max(1, pop_total - 1), n_param))])
    init[0] = init_norm

    deadline = t0 + budget

    def _cb(xk, convergence=None):
        if time.time() > deadline:
            print('==== 时间预算到达，提前结束 ====', flush=True)
            return True
        return False

    try:
        result = differential_evolution(
            func=lambda x: self.optimization_objective(x, reduced_params),
            bounds=bounds,
            init=init,
            maxiter=max_iter,
            tol=0.0,
            mutation=(0.5, 1.0),
            recombination=0.7,
            strategy='best1bin',
            polish=False,
            workers=1,
            callback=_cb,
        )
        print('\n==== DE done: success=%s fun=%.6f nit=%s ===='
              % (result.success, result.fun, getattr(result, 'nit', '?')), flush=True)
        try:
            real_values = self.denormalize_values(reduced_params, result.x)
            os.makedirs(self.output_path, exist_ok=True)
            with open(os.path.join(self.output_path, 'optimized_params.txt'), 'w') as f:
                for i, (name, _p) in enumerate(reduced_params.items()):
                    f.write('%s: %s\n' % (name, _p.format_value(real_values[i])))
        except Exception as e:
            print('WARN: 写 optimized_params.txt 失败: %s' % e, flush=True)
    except Exception as e:
        print('\n==== DE 异常退出（保留当前最优）: %s ====' % e, flush=True)

    # ---- P4-b：收尾再写一次，确保文件存在且为最优 ----
    try:
        if getattr(self, 'best_fitness', float('inf')) < float('inf'):
            extract_params(self.ae_lib, self.ae_cell, self.ae_view, self.best_param_file)
    except Exception as e:
        print('WARN: 收尾写 best_param_file 失败: %s' % e, flush=True)
    print('==== TOTAL: %.1fs, iters=%d, best_param_file=%s(存在=%s) ===='
          % (time.time() - t0, getattr(self, 'iter_count', 0), self.best_param_file,
             os.path.exists(self.best_param_file)), flush=True)


def _patched_main():
    args = parse_arguments()
    if getattr(args, 'verbose', False):
        print('[VERBOSE] args = %s' % vars(args))

    ae.emyInitAether('-adv')

    # ---- P1：默认使用模块二的约减分组（CLI 有传就以 CLI 为准）----
    raw_all = read_parameters(args.param_file, [])
    dummy_arg, sym_arg = _filter_groups(
        raw_all,
        args.dummy_devices or DEFAULT_DUMMY_DEVICES,
        args.symmetry_devices or DEFAULT_SYMMETRY_DEVICES)
    print('==== 约减配置（来自模块二，已按本电路过滤）====')
    print('  dummy_devices    : %s' % (dummy_arg or '(无)'))
    print('  symmetry_devices : %s' % (sym_arg or '(无)'))

    dummy_devices = [d for d in dummy_arg.split(',') if d]
    parameters = read_parameters(args.param_file, dummy_devices)
    non_dummy_params = {n: p for n, p in parameters.items() if not p.is_dummy}
    dummy_params = {n: p for n, p in parameters.items() if p.is_dummy}
    print('==== dummy params: %d | 待优化参数: %d ====' % (len(dummy_params), len(non_dummy_params)))

    symmetry_constraints = parse_symmetry_constraints(sym_arg)
    if symmetry_constraints:
        reduced_parameters, param_mapping = apply_symmetry_constraints(non_dummy_params, symmetry_constraints)
    else:
        reduced_parameters, param_mapping = non_dummy_params, None

    platform = SimulatePlatform(
        ae_lib=args.ae_lib, ae_cell=args.ae_cell, ae_view=args.ae_view,
        mde_cell=args.mde_cell, mde_view=args.mde_view,
        output_path=args.output_path, output_file=args.output_file,
        best_param_file=args.best_param_file,
        symmetry_constraints=symmetry_constraints, dummy_params=dummy_params)

    platform.param_mapping = param_mapping
    if param_mapping:
        platform.reverse_mapping = {}
        for orig, red in param_mapping.items():
            platform.reverse_mapping.setdefault(red, []).append(orig)

    # 用补丁版方法覆盖（不动原类）
    platform.optimization_objective = types.MethodType(_patched_objective, platform)
    platform.run_de_optimization = types.MethodType(_patched_run_de, platform)

    # ---- 冒烟测试：--set_params/--evaluate 只跑一次仿真并打印指标（不优化）----
    if getattr(args, 'set_params', False) or getattr(args, 'evaluate', False):
        print('\n==== SINGLE-EVAL MODE（只评估一次，不优化）====', flush=True)
        try:
            os.makedirs(args.output_path, exist_ok=True)
        except Exception:
            pass
        try:
            platform.only_set_params(parameters)
            scores = platform.evaluate()
            print('==== scores: %s ====' % scores, flush=True)
            try:
                extract_params(args.ae_lib, args.ae_cell, args.ae_view, args.best_param_file)
                print('==== 已写出 %s ====' % args.best_param_file, flush=True)
            except Exception as e:
                print('WARN: 写 best_param_file 失败: %s' % e, flush=True)
        except Exception as e:
            print('ERROR: 单次评估失败: %s' % e, flush=True)
        return

    platform.run_de_optimization(reduced_parameters, max_iter=None, pop_size=None)


'''

TAIL = r'''if __name__ == "__main__":
    try:
        _patched_main()
    except Exception as exc:
        import traceback
        traceback.print_exc()
        print('FATAL: 优化流程异常，尝试按初始参数兜底写出 best_param_file', flush=True)
        try:
            _a = parse_arguments()
            ae.emyInitAether('-adv')
            read_parameters(_a.param_file, [])
            extract_params(_a.ae_lib, _a.ae_cell, _a.ae_view, _a.best_param_file)
            print('FALLBACK OK: %s' % _a.best_param_file, flush=True)
        except Exception as e2:
            print('FALLBACK FAILED: %s' % e2, flush=True)
'''


def main():
    src = io.open(UPSTREAM, encoding="utf-8").read()
    marker = 'if __name__ == "__main__":'
    if src.count(marker) != 1:
        raise SystemExit("上游文件里 __main__ 标记数量异常: %d" % src.count(marker))
    idx = src.index(marker)
    out = src[:idx] + PATCH + TAIL
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    print("已生成: %s" % OUT)
    print("行数: %d（上游 %d 行 + 补丁 %d 行）"
          % (out.count("\n") + 1, src.count("\n") + 1, PATCH.count("\n") + TAIL.count("\n")))
    # 语法自检
    compile(out, OUT, "exec")
    print("语法自检: 通过")


if __name__ == "__main__":
    main()
