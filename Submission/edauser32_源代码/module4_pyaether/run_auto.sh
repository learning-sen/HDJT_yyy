#!/bin/bash
# =====================================================================
# 模块四-③ 高集成自动优化接口
#   对应赛题模块四第 5 项："高集成自动优化接口脚本，输入尺寸文件即可自动调用仿真输出性能结果"
#
# 用法
# ----
#   ./run_auto.sh --smoke <sizes.txt> [out_dir]   冒烟：修路径 + 单次仿真，打印四个关键数（推荐先做）
#   ./run_auto.sh <sizes.txt> [out_dir]           输入尺寸 -> 自动仿真 -> 输出性能
#   ./run_auto.sh --full <sizes.txt> [out_dir]    一条龙：仿真 + 反标
#   ./run_auto.sh --opt [out_dir]                 自动优化闭环（调 optimization.py，3h 预算）
#   ./run_auto.sh --params [out_dir]              参数化：导出待优化变量 + 元数据
#   ./run_auto.sh --fix-paths                     只修 MDE 旧路径（P0-8），不仿真
#   ./run_auto.sh --mock <sizes.txt> [out_dir]    本地验证链路（假数据，不需要 PyAether）
#
# 环境变量（正常都有默认值）
#   AE_LIB / AE_CELL / AE_VIEW / MDE_CELL / MDE_VIEW / OUT_VIEW / PYTHON
#   OPT_TIME_LIMIT  传给 optimization.py 的时间预算（秒）
#   M4_NO_FIX=1     跳过 P0-8 路径修复
# =====================================================================
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

AE_LIB="${AE_LIB:-2026_EDA_case1}"
AE_CELL="${AE_CELL:-OPA}"
AE_VIEW="${AE_VIEW:-schematic}"
MDE_CELL="${MDE_CELL:-OPA_loopgain}"
MDE_VIEW="${MDE_VIEW:-spe_state1_Corner}"
OUT_VIEW="${OUT_VIEW:-schematic_var_best}"
PYTHON="${PYTHON:-pythone}"

info() { echo "[run_auto] $*"; }
warn() { echo "[run_auto][WARN] $*" >&2; }
die()  { echo "[run_auto][ERROR] $*" >&2; exit 1; }

usage() { sed -n '2,24p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 1; }

MODE="sim"
MOCK=0
ARGS=()
for arg in "$@"; do
    case "$arg" in
        --opt)       MODE="opt" ;;
        --full)      MODE="full" ;;
        --smoke)     MODE="smoke" ;;
        --params)    MODE="params" ;;
        --fix-paths) MODE="fix-paths" ;;
        --mock)      MOCK=1 ;;
        -h|--help)   usage ;;
        *)           ARGS+=("$arg") ;;
    esac
done

SIZES="${ARGS[0]:-}"
OUT_DIR="${ARGS[1]:-./auto_out}"

# ---- 解释器与环境自检（`pythone` 不是系统命令，是 setup.bash 提供的）----
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    for cand in python3 python; do
        command -v "$cand" >/dev/null 2>&1 && { PYTHON="$cand"; break; }
    done
    command -v "$PYTHON" >/dev/null 2>&1 || die "找不到 Python（试过 pythone/python3/python）"
    warn "没找到 pythone，退而使用 $PYTHON —— 真机仿真请在 source setup.bash 后再跑"
fi
if [ "$MOCK" != "1" ] && [ -z "${LM_LICENSE_FILE:-}" ]; then
    warn "LM_LICENSE_FILE 为空：多半没有 source setup.bash（会拿不到 license）"
fi

mkdir -p "$OUT_DIR" || die "无法创建输出目录 $OUT_DIR"
COMMON=(--ae_lib "$AE_LIB" --ae_cell "$AE_CELL" --ae_view "$AE_VIEW"
        --mde_cell "$MDE_CELL" --mde_view "$MDE_VIEW")
MOCK_ARG=(); [ "$MOCK" = "1" ] && MOCK_ARG=(--mock)
NOFIX_ARG=(); [ "${M4_NO_FIX:-0}" = "1" ] && NOFIX_ARG=(--no_fix_paths)

case "$MODE" in
fix-paths)
    info "只修复 MDE 旧路径（P0-8）"
    "$PYTHON" "$SCRIPT_DIR/sim_engine.py" "${COMMON[@]}" "${MOCK_ARG[@]+"${MOCK_ARG[@]}"}" --fix_paths_only
    rc=$?
    [ $rc -eq 0 ] && info "有文件被修复（原文件已备份为 *.m4bak）" || warn "没有文件需要修复（退出码 $rc）"
    exit 0
    ;;
params)
    info "参数化：导出待优化变量 -> $OUT_DIR/params"
    "$PYTHON" "$SCRIPT_DIR/param_extract.py" "${COMMON[@]}" "${MOCK_ARG[@]+"${MOCK_ARG[@]}"}" \
        --out_dir "$OUT_DIR/params" || die "参数化失败"
    exit 0
    ;;
sim|smoke|full)
    [ -n "$SIZES" ] || die "缺少尺寸参数文件；用法见 --help"
    [ -f "$SIZES" ] || die "尺寸参数文件不存在: $SIZES"
    info "模式=$MODE  参数=$SIZES  输出=$OUT_DIR"
    info "第 1 步：修复 MDE 旧路径 + 调 MDE 跑 PVT + 提取指标"
    T0=$(date +%s)
    "$PYTHON" "$SCRIPT_DIR/sim_engine.py" "${COMMON[@]}" "${MOCK_ARG[@]+"${MOCK_ARG[@]}"}" "${NOFIX_ARG[@]+"${NOFIX_ARG[@]}"}" \
        --param_file "$SIZES" --out_dir "$OUT_DIR" || die "仿真引擎失败"
    T1=$(date +%s)
    [ -f "$OUT_DIR/metrics.md" ] || die "没有生成 metrics.md"
    info "单次仿真耗时: $((T1 - T0)) s  ← 这个数就是 T_eval，用它算优化预算"
    if [ "$MODE" = "smoke" ]; then
        echo "--------------------------------------------------------------------"
        info "冒烟四查（逐条确认后再正式跑）："
        info "  1) 日志里应出现 '[P0-8] 模型路径修复完成：扫描 N 个候选文件，改动 M 个'（M>=1 才有救）"
        info "  2) metrics.md 里五个指标都不是 None（PM/GM/Gain/UGB/I_OPA）"
        info "  3) 上面的 T_eval 记下来；预算 ≈ 6900 / T_eval 次评估"
        info "  4) 若 M=0 且仿真仍失败 → 按 module3/操作指南-冒烟与提交.md §4 手工改 setting"
        echo "--------------------------------------------------------------------"
        exit 0
    fi
    if [ "$MODE" = "full" ]; then
        info "第 2 步：把尺寸反标到原理图（目标视图 $OUT_VIEW）"
        "$PYTHON" "$SCRIPT_DIR/writeback.py" --ae_lib "$AE_LIB" --ae_cell "$AE_CELL" \
            --ae_view "$AE_VIEW" --out_view "$OUT_VIEW" "${MOCK_ARG[@]+"${MOCK_ARG[@]}"}" \
            --param_file "$SIZES" --out_dir "$OUT_DIR" \
            || warn "反标未完全成功，详见 $OUT_DIR/writeback_verify.txt"
    fi
    ;;
opt)
    info "模式=opt  输出=$OUT_DIR"
    [ "$MOCK" = "1" ] && die "--opt 需要真实 PyAether，不能与 --mock 同用"
    OPT_PY="$SCRIPT_DIR/../submission/optimization.py"
    [ -f "$OPT_PY" ] || OPT_PY="$SCRIPT_DIR/optimization.py"
    [ -f "$OPT_PY" ] || die "找不到 optimization.py（应在 module3/submission/ 下）"
    info "调用优化器：$OPT_PY"
    "$PYTHON" "$OPT_PY" "${COMMON[@]}" \
        --param_file "${SIZES:-case1_params_0.txt}" \
        --best_param_file "$OUT_DIR/${AE_LIB}_best_params.txt" \
        --output_path "$OUT_DIR/results" || die "优化失败"
    info "第 2 步：用最优参数跑一次完整 PVT 验证"
    "$PYTHON" "$SCRIPT_DIR/sim_engine.py" "${COMMON[@]}" "${NOFIX_ARG[@]+"${NOFIX_ARG[@]}"}" \
        --param_file "$OUT_DIR/${AE_LIB}_best_params.txt" --out_dir "$OUT_DIR/verify" \
        || die "验证仿真失败"
    ;;
*)
    usage
    ;;
esac

echo "--------------------------------------------------------------------"
info "完成。主要产物："
[ -f "$OUT_DIR/metrics.md" ] && info "  性能指标表  : $OUT_DIR/metrics.md"
[ -f "$OUT_DIR/writeback_verify.txt" ] && info "  反标校验    : $OUT_DIR/writeback_verify.txt"
[ -f "$OUT_DIR/params/params_meta.json" ] && info "  参数元数据  : $OUT_DIR/params/params_meta.json"
[ -f "$OUT_DIR/verify/metrics.md" ] && info "  优化后验证  : $OUT_DIR/verify/metrics.md"
info "  机器可读结果: $OUT_DIR/metrics.json"
exit 0
