#!/bin/bash
# =====================================================================
# 模块四-③ 高集成自动优化接口
#   对应 `任务分析.docx` 模块四③：
#   "高集成自动优化接口脚本（输入尺寸 → 自动仿真 → 输出性能）"
#
# 用法
# ----
#   ./run_auto.sh <sizes.txt> [out_dir]          输入尺寸 -> 自动仿真 -> 输出性能
#   ./run_auto.sh --opt [out_dir]                自动优化闭环（调 optimization.py，3h 预算）
#   ./run_auto.sh --full <sizes.txt> [out_dir]   一条龙：仿真 + 反标 + 汇总报告
#   ./run_auto.sh --mock <sizes.txt> [out_dir]   本地验证链路（假数据，不需要 PyAether）
#
# 环境变量（都有默认值，正常情况下不用改）
#   AE_LIB / AE_CELL / AE_VIEW / MDE_CELL / MDE_VIEW / PYTHON
#   OPT_TIME_LIMIT  传给 optimization.py 的时间预算（秒，默认由脚本内 10800*0.8 决定）
# =====================================================================
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

AE_LIB="${AE_LIB:-2026_EDA_case1}"
AE_CELL="${AE_CELL:-OPA}"
AE_VIEW="${AE_VIEW:-schematic}"
MDE_CELL="${MDE_CELL:-OPA_loopgain}"
MDE_VIEW="${MDE_VIEW:-spe_state1_Corner}"
PYTHON="${PYTHON:-pythone}"          # 注意：服务器上的解释器叫 pythone
OUT_VIEW="${OUT_VIEW:-schematic_var_best}"

info() { echo "[run_auto] $*"; }
die()  { echo "[run_auto][ERROR] $*" >&2; exit 1; }

usage() {
    sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 1
}

MODE="sim"
ARGS=()
for arg in "$@"; do
    case "$arg" in
        --opt)  MODE="opt" ;;
        --full) MODE="full" ;;
        --mock) MOCK="1" ;;
        -h|--help) usage ;;
        *) ARGS+=("$arg") ;;
    esac
done
MOCK="${MOCK:-0}"

SIZES="${ARGS[0]:-}"
OUT_DIR="${ARGS[1]:-./auto_out}"

command -v "$PYTHON" >/dev/null 2>&1 || {
    if command -v python3 >/dev/null 2>&1; then PYTHON=python3;
    elif command -v python >/dev/null 2>&1; then PYTHON=python;
    else die "找不到 Python（试过 pythone/python3/python）"; fi
}

mkdir -p "$OUT_DIR" || die "无法创建输出目录 $OUT_DIR"

COMMON=(--ae_lib "$AE_LIB" --ae_cell "$AE_CELL" --ae_view "$AE_VIEW"
        --mde_cell "$MDE_CELL" --mde_view "$MDE_VIEW")
MOCK_ARG=()
[ "$MOCK" = "1" ] && MOCK_ARG=(--mock)

case "$MODE" in
sim|full)
    [ -n "$SIZES" ] || die "缺少尺寸参数文件；用法见 --help"
    [ -f "$SIZES" ] || die "尺寸参数文件不存在: $SIZES"
    info "模式=$MODE  参数=$SIZES  输出=$OUT_DIR"
    info "第 1 步：调用 MDE 跑 PVT 并提取指标"
    "$PYTHON" "$SCRIPT_DIR/sim_engine.py" "${COMMON[@]}" "${MOCK_ARG[@]}" \
        --param_file "$SIZES" --out_dir "$OUT_DIR" || die "仿真引擎失败"
    [ -f "$OUT_DIR/metrics.md" ] || die "没有生成 metrics.md"
    info "指标已写入 $OUT_DIR/metrics.{json,csv,md}"
    if [ "$MODE" = "full" ]; then
        info "第 2 步：把最优尺寸反标到原理图（新视图 $OUT_VIEW）"
        "$PYTHON" "$SCRIPT_DIR/writeback.py" --ae_lib "$AE_LIB" --ae_cell "$AE_CELL" \
            --ae_view "$AE_VIEW" --out_view "$OUT_VIEW" "${MOCK_ARG[@]}" \
            --param_file "$SIZES" --out_dir "$OUT_DIR" \
            || info "警告：反标未完全成功，详见 $OUT_DIR/writeback_verify.txt"
    fi
    ;;
opt)
    info "模式=opt  输出=$OUT_DIR"
    if [ "$MOCK" = "1" ]; then die "--opt 需要真实 PyAether，不能与 --mock 同用"; fi
    OPT_PY="$SCRIPT_DIR/../submission/optimization.py"
    [ -f "$OPT_PY" ] || OPT_PY="$SCRIPT_DIR/../optimization.py"
    [ -f "$OPT_PY" ] || die "找不到 optimization.py（应在 module3/submission/ 下）"
    info "调用优化器：$OPT_PY"
    "$PYTHON" "$OPT_PY" "${COMMON[@]}" \
        --param_file "${SIZES:-case1_params_0.txt}" \
        --best_param_file "$OUT_DIR/${AE_LIB}_best_params.txt" \
        --output_path "$OUT_DIR/results" \
        || die "优化失败"
    info "最优参数：$OUT_DIR/${AE_LIB}_best_params.txt"
    info "第 2 步：用最优参数跑一次完整 PVT 验证"
    "$PYTHON" "$SCRIPT_DIR/sim_engine.py" "${COMMON[@]}" \
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
[ -f "$OUT_DIR/verify/metrics.md" ] && info "  优化后验证  : $OUT_DIR/verify/metrics.md"
info "  机器可读结果: $OUT_DIR/metrics.json"
exit 0
