# -*- coding: utf-8 -*-
"""
从赛方模板生成提交版 optimization.py（模块三）。

设计：**不改赛方原类**，只在文件尾部插入一个补丁块，用 types.MethodType
覆盖 SimulatePlatform 的两个方法与入口流程。这样：
  - PyAether / MDE / 参数回写这些我们本地无法测试的部分，原样保留；
  - 我们只替换"优化策略"这一层，风险最小、可回退。

补丁内容（依据 run_score.sh 与 score.py 实测）：
  P0-2 时间预算夹紧：预算不超过 7200s（时间分满分区）- 300s 收尾余量。
  P0-3 参数上下界对齐 score.py：m/segments 1..100、fw 0.15..50、segW 0.42..10、
       segL 5..100、电容 l 4..30、其余 l 0.13..20，且按 score.py 的方式 clamp。
  P0-4 回写补全：电阻多写 segments、电容多写 fw/m，否则这些变量永远不被优化。
  P0-5 分组降级：模块二分组按本电路过滤，匹配不到就退化为全独立变量，
       不对 Hidden 电路硬套 case1 的分组。
  P1 默认约减：未传 --symmetry_devices/--dummy_devices 时，自动使用模块二识别出的
     对称/匹配/Dummy 分组（对 Hidden 电路会自动过滤为空 -> 退化为全独立，仍能跑）。
  P2 预算感知：先评估初始点测出单次耗时 T_eval，再按预算反推种群/代数；
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

# [P0-10] 初值局部化（v1 的归一化 sigma 保留作对照，实际使用 P0-13 的相对扰动）
LOCAL_SIGMA = float(os.environ.get('OPT_LOCAL_SIGMA', '0.08'))

# [P0-13] 种群规模固定，maxiter 交给硬截止控制，不再用不可靠的 t_eval 反推
POP_FIXED = int(os.environ.get('OPT_POP', '20'))
REL_SIGMA = float(os.environ.get('OPT_REL_SIGMA', '0.50'))   # 每个参数按自身值 ±50%
SPARSE_P = float(os.environ.get('OPT_SPARSE_P', '0.35'))     # 每个候选只动 35% 的参数

# [P0-11] 面积预剪枝：先只算面积（CV 读一遍，很便宜），面积超过初始解的 N 倍就
# 跳过整次 PVT 仿真。面积是 25 分的大头，离谱点不可能赢，省下的时间给有效点。
AREA_CAP_FACTOR = float(os.environ.get('OPT_AREA_CAP_FACTOR', '6.0'))

# 服务器上冒烟测试用：OPT_TIME_LIMIT=300 就只跑 5 分钟（判分时不设这个变量 -> 10800）
TIME_LIMIT_TOTAL = float(os.environ.get('OPT_TIME_LIMIT', str(TIME_LIMIT_TOTAL)))

# score.py 的真实基线（run_score.sh 传入）
SCORE_GAIN_MIN_DB = 20.0

# [P0-14] 增益项的基准，默认 20dB（= score.py 原样，保证自动分最优）。
# 若想把增益往 40dB 推（赛题 6.3(3) 的最终排名门槛），用 OPT_GAIN_TARGET=40 启动。
# 代价：会拿 Area 的分去换增益（Area 在 score.py 里值 25 分，增益超 20dB 后是 0 分）。
SCORE_GAIN_TARGET_DB = float(os.environ.get('OPT_GAIN_TARGET', '20.0'))

# =====================================================================
# [P0-15] 按赛题 6.3 的真实评分表重写目标函数（默认启用）
#   约束 30 分：PM>=50 (10) / GM<=-10dB (10) / I_OPA<=3mA (10)
#   目标 40 分：DC Gain>=40dB 才计分，40~60dB 线性 (10)
#               UGB 越大越好 (15)     Area 越小越好 (15)
#   时间 10 分：单次运行内无法横向比较，按满分；每违反一条约束扣 5
#   合计 80 分（对应 6.3 里模块三的部分）
# 说明：6.3 的 UGB/Gain/Area 真实得分是"与其他队伍比值"，赛场上无从得知，
#       这里用参考值做线性归一（可用环境变量调整，便于按往届水平校准）。
# =====================================================================
# [P0-16] 增益硬门槛：DC Gain < 40dB 的候选一律不选（用户明确要求）。
# 实跑证据：局部 ±15% 扰动只能把增益停在 25~31dB，永远够不到 40dB。
# 所以同时做两件事：
#   ① fitness 里给 <40dB 加 1e5 级惩罚，并按"离 40 还有多远"排序（够不到 40 时至少往 40 靠）
#   ② 扰动改成增益导向：只放大 l / fw（抬高 ro 与 gm），其余参数仍双向扰动
GAIN_GATE = os.environ.get('OPT_GAIN_GATE', '1') == '1'
GAIN_GATE_PENALTY = 1.0e5
UP_ONLY_SUFFIX = ('l', 'fw')   # [P0-18] 撤掉 m：实测 m 增大会抬高面积却换不到 UGB

# [P0-17] 电流窗口：目标 2.5~2.8mA（用预算换 UGB），worst-case 不超 2.8mA。
# 理由：score.py 取 PVT 最坏值判 I_OPA<=3mA，留 0.2mA 余量才稳；
#       而 UGB 15 分是大头，提电流是最直接的手段。
IOPA_SCORE_MAX_A = float(os.environ.get('OPT_IOPA_MAX', '0.003'))   # 6.3 硬约束
IOPA_SOFT_HI_A = float(os.environ.get('OPT_IOPA_HI', '0.0028'))     # 内部软上限
IOPA_TARGET_LO_A = float(os.environ.get('OPT_IOPA_LO', '0.0025'))   # 期望下限

PM_MIN_DEG = float(os.environ.get('OPT_PM_MIN', '50.0'))
GM_MAX_DB = float(os.environ.get('OPT_GM_MAX', '-10.0'))
IOPA_MAX_A = float(os.environ.get('OPT_IOPA_MAX', '0.003'))   # 3mA；电流想放宽就调大
GAIN_MIN_DB = float(os.environ.get('OPT_GAIN_MIN', '43.0'))   # 6.3(3)：<40dB 该项 0 分
GAIN_REF_DB = float(os.environ.get('OPT_GAIN_REF', '60.0'))
UGB_REF_HZ = float(os.environ.get('OPT_UGB_REF', '5.0e7'))    # 50MHz 视为满分
AREA_REF_UM2 = float(os.environ.get('OPT_AREA_REF', '8000.0'))


def _est_score_pdf(scores):
    """赛题 6.3 口径的 80 分制评分（模块三部分）。"""
    s = 0.0
    viol = 0.0
    n_bad = 0
    pm = scores.get('Phase_Margin')
    gm = scores.get('Gain_Margin')
    gain = scores.get('Gain_db')
    iopa = scores.get('I_OPA')
    ugb = scores.get('UGB')
    area = scores.get('Total_Area')

    # ---- 约束 30 分 ----
    if pm is None or pm == -float('inf'):
        viol += 6.0
        n_bad += 1
    elif pm >= PM_MIN_DEG:
        s += 10.0
    else:
        viol += 1.0 + (PM_MIN_DEG - pm) / 5.0
        n_bad += 1

    if gm is None or gm == float('inf'):
        viol += 6.0
        n_bad += 1
    elif gm <= GM_MAX_DB:
        s += 10.0
    else:
        viol += 1.0 + (gm - GM_MAX_DB) / 2.0
        n_bad += 1

    if iopa is None or iopa == float('inf'):
        viol += 6.0
        n_bad += 1
    elif iopa <= IOPA_SCORE_MAX_A:
        s += 10.0
        # [P0-18] 撤掉"+3 电流奖励"：实测 37 次评估里没有一个点进入 2.5~2.8mA，
        # 加了奖励后达标点反而从 3 个掉到 1 个、最高增益从 45.3 掉到 41.0。
        # 只保留 2.8mA 软上限做 PVT 安全余量。
        if iopa > IOPA_SOFT_HI_A:
            viol += (iopa - IOPA_SOFT_HI_A) / 2.0e-4
    else:
        viol += 1.0 + (iopa - IOPA_SCORE_MAX_A) / 0.001
        n_bad += 1

    # ---- 目标 40 分 ----
    # Gain：>=40dB 才计分（6.3(3)），40~GAIN_REF 线性到 10 分
    if gain is None or gain == -float('inf'):
        viol += 6.0
        n_bad += 1
    elif gain >= GAIN_MIN_DB:
        s += min(gain / GAIN_REF_DB, 1.0) * 10.0
    else:
        # 未到 40dB：该项记 0 分，但留 0~3 分的过渡梯度把它往上拉
        s += max(gain, 0.0) / GAIN_MIN_DB * 3.0

    # UGB：越大越好
    if ugb is not None and ugb > 1.0:
        s += min(ugb / UGB_REF_HZ, 1.0) * 15.0

    # Area：越小越好
    if area is not None and area > 1.0:
        s += min(AREA_REF_UM2 / area, 1.0) * 15.0

    # ---- 时间 10 分 ----
    s += max(0.0, 10.0 - 5.0 * n_bad)
    return s, viol
SCORE_UGB_BASE = 2.0e8
SCORE_AREA_BASE = 8000.0

# ---- P0-2：时间预算的真实口径 ----
# run_score.sh 的 TIME_LIMIT=10800s 只是"杀进程"上限；
# 而 score.py 的时间分满分区是 execution_time <= time_base = 7200s。
# 也就是说跑满 8640s 会让时间分从 20 掉到 7200/8640*20 ≈ 16.7，白丢 3.3 分。
# 所以优化预算必须夹到 7200 - 余量 以内。
TIME_FULL_SCORE = 7200.0
TIME_SAFETY = 300.0

# 模块二识别结果（针对本赛题电路；Hidden 电路名字不同会被自动过滤掉）
DEFAULT_DUMMY_DEVICES = "R5,R6,C4,C5"
DEFAULT_SYMMETRY_DEVICES = (
    "(NM15,NM14),(PM11,PM7),(PM10,PM9),(PM3,PM2),(NM4,NM5),(NM6,NM7),"
    "(NM8,NM9),(NM10,NM11),(NM12,NM13),(PM8,PM12),(R1,R2),(R0,R3),(C0,C11),(C2,C3)"
)


# =====================================================================
# [P0-3] 参数上下界：严格对齐 score.py 的 read_parameters()
# 上游模板对"所有连续参数"一律用 0.13..20，但 score.py 实际按参数名分别 clamp：
#   m / segments : 整数 1..100
#   l            : 电容(C*) 4..30，其余 0.13..20
#   fw           : 0.15..50
#   segW         : 0.42..10
#   segL         : 5..100
# 不一致的后果：优化器在 [0,1] 归一化空间里探索的点，反归一化后落在评分时会被
# clamp 掉的区间 -> "优化出来的解" ≠ "最终被评的解"，白花仿真次数。
# =====================================================================
_BOUNDS = {
    'm':        (1.0, 100.0, 'integer'),
    'segments': (1.0, 100.0, 'integer'),
    'fw':       (0.15, 50.0, 'continuous'),
    'segW':     (0.42, 10.0, 'continuous'),
    'segL':     (5.0, 100.0, 'continuous'),
    'l':        (0.13, 20.0, 'continuous'),
}
_CAP_L = (4.0, 30.0)


def _bounds_for(inst_name, param_name):
    """返回 (min, max, type)，口径同 score.py。"""
    if param_name == 'l' and inst_name[:1] in ('C', 'c'):
        return _CAP_L[0], _CAP_L[1], 'continuous'
    return _BOUNDS.get(param_name, (0.13, 20.0, 'continuous'))


def _patched_read_parameters(file_name, dummy_devices=None):
    """替代上游 read_parameters：同样的单位换算、同样的上下界、同样的 clamp 策略。

    上游用 0.13..20 一把尺子量所有连续参数，与 score.py 的 clamp 区间不一致；
    这里逐参数对齐，保证"优化空间 == 评分空间"。
    """
    parameters = {}
    dummy_devices = dummy_devices or []
    with open(file_name, 'r') as param_file:
        for line in param_file:
            fields = line.strip().replace('"', '').replace(' ', '').split(',')
            if len(fields) < 3 or fields[0] != 'parameter':
                continue
            name = fields[1]
            index = name.rfind('_')
            inst_name = name[:index]
            param_name = name[(index + 1):]
            lo, hi, ptype = _bounds_for(inst_name, param_name)
            try:
                if ptype == 'integer':
                    value = float(fields[2])
                else:
                    value = param_convert(fields[2])
            except Exception as e:
                print('WARN: 跳过无法解析的参数行 %r (%s)' % (line.strip(), e), flush=True)
                continue
            # score.py 的做法是 clamp（不报错），这里保持一致
            if value < lo:
                value = lo
            if value > hi:
                value = hi
            parameters[name] = Parameter(name, ptype, value, lo, hi,
                                         inst_name in dummy_devices)
    # 记住输入文件的变量清单（原样、原序），供 [P0-4] 回写时严格复用
    global INPUT_SCHEMA
    INPUT_SCHEMA = list(parameters.keys())
    print('==== [P0-3] Read %d parameters (bounds aligned with score.py): %s ===='
          % (len(parameters), file_name), flush=True)
    return parameters


# [P0-4 修订] 回写必须"照抄输入参数文件的 schema"，不能自己发明变量。
# 实测 case1_params_0.txt 的组成（105=29*3+6*1+6*2）：
#   MOS (29 个) : fw, l, m       -> 87
#   电容 (6 个) : l 只有 1 个     -> 6
#   电阻 (6 个) : segL, segW      -> 12
# 也就是说电容**没有** fw/m、电阻**没有** segments。
# （score.py::calc_area 里的 fw/m/segments 是它直接从电路 CV 读的，与参数文件无关。）
# 上游 extract_params 的硬编码 schema 恰好与之一致，所以这里改为：
#   - 默认：按输入文件里实际出现过的变量名逐个回写（严格同名同序）；
#   - OPT_EXTRA_PARAMS=1 时才追加 R_segments / C_fw / C_m 做实验。
INPUT_SCHEMA = []


def _patched_extract_params(lib, cell, view, param_file_name):
    """[P0-4] 按输入参数文件的 schema 回写最优解。

    为什么不再自己拼 if/elif：
      回写文件是交给 score.py::read_parameters 再 set 回电路的，
      多写一个输入文件里没有的参数，就等于偷偷改了赛方的参数化口径。
    """
    cv = ae.dbOpenCV(lib, cell, view)
    if cv is None:
        print('dbOpenCV failed !!!', flush=True)
        return
    extra = os.environ.get('OPT_EXTRA_PARAMS', '0') == '1'

    with open(param_file_name, 'w') as param_file:
        if INPUT_SCHEMA:
            # 主路径：严格复用输入文件的变量清单
            for name in INPUT_SCHEMA:
                idx = name.rfind('_')
                inst_name, param_name = name[:idx], name[idx + 1:]
                inst = ae.dbFindInst(cv=cv, name=inst_name)
                if not inst:
                    continue
                try:
                    val = ae.aeEmyInstGetParameter(param_name, inst)
                except Exception:
                    continue
                if val is None:
                    continue
                param_file.write('parameter, %s, %s\n' % (name, val))
            if extra:
                for inst in cv.instances:
                    n = str(inst.name)
                    more = ()
                    if n[:1] in ('R', 'r'):
                        more = ('segments',)
                    elif n[:1] in ('C', 'c'):
                        more = ('fw', 'm')
                    for k in more:
                        try:
                            val = ae.aeEmyInstGetParameter(k, inst)
                        except Exception:
                            continue
                        if val is not None:
                            param_file.write('parameter, %s_%s, %s\n' % (n, k, val))
        else:
            # 兜底：没读到输入文件时，退回上游的同款 schema
            for inst in cv.instances:
                n = str(inst.name)
                if n[:1] in ('R', 'r'):
                    keys = ('segW', 'segL')
                elif n[:1] in ('C', 'c'):
                    keys = ('l',)
                elif n.startswith('PM') or n.startswith('NM'):
                    keys = ('fw', 'l', 'm')
                else:
                    continue
                for k in keys:
                    try:
                        val = ae.aeEmyInstGetParameter(k, inst)
                    except Exception:
                        continue
                    if val is not None:
                        param_file.write('parameter, %s_%s, %s\n' % (n, k, val))
    ae.dbCloseCV(cv)
    print('==== [P0-4] wrote %d lines (schema=%s) -> %s ===='
          % (len(INPUT_SCHEMA) if INPUT_SCHEMA else -1,
             'from input file' if INPUT_SCHEMA else 'fallback', param_file_name), flush=True)


# 覆盖上游同名全局函数：_patched_objective / _patched_run_de 里用的是全局名，故会自动生效
_UPSTREAM_READ_PARAMETERS = read_parameters
_UPSTREAM_EXTRACT_PARAMS = extract_params
read_parameters = _patched_read_parameters
extract_params = _patched_extract_params


def _fix_sim_paths():
    """[P0-8] 修复 MDE 配置里指向旧机器的绝对路径 —— 这是"全员 0 分"的真正根因。

    实跑证据（server/2026_EDA_case1_optimization.log L46-50）：
        Creating simulation netlist fails.
        Simulation failed. Reason: "File does not exist:
        /home/eda_2025/EDA_2025_Empyrean_lab_start/hes_release/models/spectre/spe_demo.scs."

    而工作目录下 ./hes_release/models/spectre/spe_demo.scs 是**存在**的
    （run_score.sh 会 cp -rf circuits/* 到工作目录，circuits 里带 hes_release）。

    做法（不硬编码任何用户名/年份，纯按"存在性"判断）：
      扫描 MDE 的 setting / adeL2View.file / *.scs，
      把其中**不存在**的绝对路径里 `hes_release/` 之后的部分，
      重定向到 <当前工作目录>/hes_release/...（只有当那个位置确实存在时才改）。
    """
    root = os.getcwd()
    pat = re.compile(r'/[^\s"\'<>,;:]*hes_release/[^\s"\'<>,;:]*')
    targets = []
    for dirpath, dirnames, files in os.walk('.'):
        # 跳过体积大又无关的目录，保证启动时间
        dirnames[:] = [d for d in dirnames
                       if d not in ('hes_release', 'layout', '__pycache__')]
        for fn in files:
            if fn in ('setting', 'adeL2View.file') or fn.endswith('.scs'):
                targets.append(os.path.join(dirpath, fn))
        if len(targets) > 500:
            break

    def _repl(m):
        old = m.group(0)
        if os.path.exists(old):
            return old                      # 本来就能访问，不动
        tail = old.split('/hes_release/', 1)[1]
        cand = os.path.join(root, 'hes_release', tail)
        return cand if os.path.exists(cand) else old

    fixed = 0
    for p in targets:
        try:
            with open(p, 'r', errors='ignore') as f:
                txt = f.read()
        except Exception:
            continue
        new = pat.sub(_repl, txt)
        if new != txt:
            try:
                with open(p, 'w') as f:
                    f.write(new)
                fixed += 1
                print('[P0-8] 修复模型路径: %s' % p, flush=True)
            except Exception as e:
                print('[P0-8] 写入失败 %s: %s' % (p, e), flush=True)
    print('==== [P0-8] 模型路径修复完成：扫描 %d 个候选文件，改动 %d 个（cwd=%s）===='
          % (len(targets), fixed, root), flush=True)


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
        s += min(gain / SCORE_GAIN_TARGET_DB, 1.0) * 10.0
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

    # [P0-12] 硬截止：预算用完后的评估立即返回（不再跑仿真）。
    # 实跑证据：OPT_TIME_LIMIT=300 -> 预算 240s，实际跑了 1043.8s（超 4.3 倍）。
    # 原因是 scipy 的 callback 每代只调一次，maxiter=1 时等于没检查。
    # 正式跑若照样超时，会被 run_score.sh 在 10800s 强杀 -> 时间分掉到 13.3 且可能写不出 best。
    if getattr(self, '_deadline', None) is not None and time.time() > self._deadline:
        self.iter_count = getattr(self, 'iter_count', 0) + 1
        print('==== iter %d TIMEOUT-SKIP（预算已用完，跳过仿真）====' % self.iter_count,
              flush=True)
        return 1e9

    # [P0-11] 面积预剪枝：只算面积，明显离谱就不跑 PVT 仿真（省下大量评估次数）
    try:
        self.calc_area()
        a = getattr(self, 'total_area', None)
        if a and a > 0:
            if getattr(self, '_init_area', None) is None:
                self._init_area = a
            cap = AREA_CAP_FACTOR * self._init_area
            if a > cap:
                self.iter_count = getattr(self, 'iter_count', 0) + 1
                pen = 1e6 + (a / cap) * 10.0
                print('==== iter %d SKIP-SIM area %.1f > cap %.1f (pen %.1f) ===='
                      % (self.iter_count, a, cap, pen), flush=True)
                return pen
    except Exception as e:
        print('WARN: 面积预检失败（继续走仿真）: %s' % e, flush=True)

    scores = self.evaluate()

    # [P0-9] 仿真失败时上游 evaluate() 返回 ""，直接用会 KeyError 崩掉整轮
    #（参考实跑就是这样死的：log 末尾 'Phase_Margin' 后 Best parameters saved to: 空）
    if not isinstance(scores, dict) or 'Phase_Margin' not in scores:
        print('WARN: 本次仿真无效，按最差解处理（约束全违反）', flush=True)
        scores = {
            'Phase_Margin': -float('inf'), 'Gain_Margin': float('inf'),
            'Gain_db': -float('inf'), 'I_OPA': float('inf'),
            'UGB': 0.0, 'Total_Area': 1e9,
        }

    # [P0-15] 默认用赛题 6.3 口径；OPT_OBJECTIVE=score_py 可切回 score.py 口径
    if os.environ.get('OPT_OBJECTIVE', 'pdf') == 'score_py':
        score, viol = _est_score(scores)
    else:
        score, viol = _est_score_pdf(scores)
    fitness = -score + viol * 1e3

    # [P0-16] 增益硬门槛：Gain < 40dB 的候选排在所有达标解之后；
    # 若本次运行始终没有达标解，则按"离 40 还差多少"排序，best 会趋近 40。
    gain_now = scores.get('Gain_db')
    if GAIN_GATE and (gain_now is None or gain_now < GAIN_MIN_DB):
        short = GAIN_MIN_DB - (gain_now if isinstance(gain_now, (int, float)) and gain_now > -1e3 else 0.0)
        fitness += GAIN_GATE_PENALTY + short * 10.0

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

    # ---- P2：按实测耗时反推预算；并用 [P0-2] 夹到时间分满分区以内 ----
    budget = (time_limit or TIME_LIMIT_TOTAL) * BUDGET_RATIO
    cap = TIME_FULL_SCORE - TIME_SAFETY
    if budget > cap:
        print('==== [P0-2] 预算 %.0fs 超出时间分满分区，压缩到 %.0fs'
              '（满分线 %.0fs - 收尾余量 %.0fs）===='
              % (budget, cap, TIME_FULL_SCORE, TIME_SAFETY), flush=True)
        budget = cap
    remain = max(budget - (time.time() - t0), 1.0)

    # [P0-13] 不再用 t_eval 反推 pop/maxiter。
    # 实跑证据：第一次评估含 MDE 预热，t_eval 被测成 81.4s（后续实际约 20s），
    # 于是推出 pop=12/maxiter=1，DE 只跑 1 代，等于没优化。
    # 现在改为：固定种群 + 大 maxiter，由 [P0-12] 的硬截止负责按时收尾。
    pop_total = int(os.environ.get('OPT_POP', str(POP_FIXED)))
    if max_iter is None:
        max_iter = MAX_ITER_CAP
    print('\n==== BUDGET: t_eval(first,含预热)=%.1fs pop=%d maxiter=%d budget=%.0fs '
          'n_param=%d（靠硬截止收尾）===='
          % (t_eval, pop_total, max_iter, budget, n_param), flush=True)

    rng = np.random.default_rng(RANDOM_SEED)

    # [P0-13] 初值局部化 v2：**相对扰动 + 稀疏掩码**
    # 旧版问题：归一化空间 ±8% 对宽区间参数（segL 5~100、fw 0.15~50）等于实际值 ±40%，
    # 而且一次动全部 63 个参数 -> 仿真直接死（PM/UGB=-inf）。
    # 现在：每个候选只动 25% 的参数，且每个参数按"自身当前值的 ±15%"缩放。
    rel_sigma = float(os.environ.get('OPT_REL_SIGMA', str(REL_SIGMA)))
    sparse_p = float(os.environ.get('OPT_SPARSE_P', str(SPARSE_P)))
    names = list(reduced_params.keys())
    n_p = len(names)
    rows = [init_norm]
    for _ in range(max(1, pop_total - 1)):
        row = init_norm.copy()
        mask = rng.random(n_p) < sparse_p
        if not mask.any():
            mask[rng.integers(0, n_p)] = True
        for j in np.where(mask)[0]:
            p = reduced_params[names[j]]
            suffix = names[j].rsplit('_', 1)[-1]
            if suffix in UP_ONLY_SUFFIX:
                # [P0-16] 增益导向：只放大 l / fw（抬高 ro 与 gm）
                v = p.value * (1.0 + abs(rng.uniform(0.0, rel_sigma)))
            else:
                v = p.value * (1.0 + rng.uniform(-rel_sigma, rel_sigma))
            v = min(max(v, p.min), p.max)
            row[j] = p.normalize(v)
        rows.append(row)
    init = np.clip(np.array(rows, dtype=float), 0.0, 1.0)
    init[0] = init_norm
    print('==== [P0-13] 初值局部化：相对扰动 %.0f%% / 每次只动 %.0f%% 的参数 ===='
          % (rel_sigma * 100, sparse_p * 100), flush=True)

    deadline = t0 + budget
    self._deadline = deadline          # [P0-12] 供 objective 内做硬截止检查

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

    # [P0-8] 必须在 emyInitAether / MdeSession.open 之前把旧机绝对路径修好
    try:
        _fix_sim_paths()
    except Exception as e:
        print('WARN: [P0-8] 模型路径修复异常（继续跑）: %s' % e, flush=True)

    ae.emyInitAether('-adv')

    # ---- P1：默认使用模块二的约减分组（CLI 有传就以 CLI 为准）----
    # [P0-5] 分组按本电路实际存在的器件过滤；一个都没匹配上就退化为全独立变量，
    #        绝不对 Hidden 电路硬套 case1 的分组（宁可维度高，不可分组错）。
    raw_all = read_parameters(args.param_file, [])
    if os.environ.get('OPT_NO_REDUCTION', '0') == '1':
        print('==== [P0-5] OPT_NO_REDUCTION=1：关闭模块二分组，全部变量独立优化 ====',
              flush=True)
        dummy_arg, sym_arg = '', ''
    else:
        dummy_arg, sym_arg = _filter_groups(
            raw_all,
            args.dummy_devices or DEFAULT_DUMMY_DEVICES,
            args.symmetry_devices or DEFAULT_SYMMETRY_DEVICES)
    print('==== 约减配置（来自模块二，已按本电路过滤）====')
    print('  dummy_devices    : %s' % (dummy_arg or '(无)'))
    print('  symmetry_devices : %s' % (sym_arg or '(无)'))
    if not dummy_arg and not sym_arg:
        print('==== [P0-5] 本电路未匹配到模块二分组 -> 退化为全独立变量'
              '（安全，但搜索维度更高）====', flush=True)

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
