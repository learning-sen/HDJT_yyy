#!/bin/bash
# 在九天服务器上组装最终提交物：把 m4_deliverables 并入 Submission_Edauser32
# 用法：  bash assemble_on_server.sh
set -uo pipefail

ROOT="$HOME/Submission_Edauser32"
M4="$ROOT/m4_deliverables"
cd "$ROOT" || { echo "找不到 $ROOT"; exit 1; }

need=(
  "01_Spec解析_输出1" "02_拓扑识别与参数约减_输出2" "03_变量清单与带变量电路图_输出3"
  "04_最优尺寸反标_输出4" "05_全PVT仿真验证_输出5" "06_代码与算法性能_输出6"
)
for d in "${need[@]}"; do
  [ -d "$d" ] || { echo "缺少目录：$d（请先解包上传包）"; exit 1; }
done

echo "==== 1) 输出2：补连接关系 ===="
mkdir -p "02_拓扑识别与参数约减_输出2/连接关系"
cp -f "$M4/2_netlist/connectivity.md" "$M4/2_netlist/connectivity.json" \
      "$M4/2_netlist/export.netlist" "02_拓扑识别与参数约减_输出2/连接关系/" 2>/dev/null \
  && echo "  ok"

echo "==== 2) 输出3：变量清单 + 带变量电路图 ===="
cp -f "$M4/1_params/extractcdfVal_0.txt" "03_变量清单与带变量电路图_输出3/" 2>/dev/null
cp -f "$M4/1_params/params_table.md"     "03_变量清单与带变量电路图_输出3/变量表_105条.md" 2>/dev/null
cp -f "$M4/1_params/params_meta.json"    "03_变量清单与带变量电路图_输出3/" 2>/dev/null
cp -f "$M4/5_shots/01_schematic_parameterized.png" "03_变量清单与带变量电路图_输出3/带变量电路图_schematic_var.png" 2>/dev/null
echo "  ok"

echo "==== 3) 输出4：反标电路图 ===="
mkdir -p "04_最优尺寸反标_输出4/schematic_var_best"
cp -f "$M4/5_shots/02_schematic_var_best.png" "04_最优尺寸反标_输出4/反标后电路图_schematic_var_best.png" 2>/dev/null
cp -rf "$M4/6_schematic_var_best/schematic_var_best/." "04_最优尺寸反标_输出4/schematic_var_best/" 2>/dev/null
rm -f "04_最优尺寸反标_输出4/schematic_var_best/"*.cdslck* 2>/dev/null
echo "  ok"

echo "==== 4) 输出5：全 PVT + 波形 ===="
mkdir -p "05_全PVT仿真验证_输出5/逐角明细" "05_全PVT仿真验证_输出5/波形AC"
cp -f "$M4/3_pvt/per_corner.csv" "$M4/3_pvt/per_corner.md" "$M4/3_pvt/per_corner.json" \
      "05_全PVT仿真验证_输出5/逐角明细/" 2>/dev/null
cp -f "$M4/3_pvt/metrics.json" "$M4/3_pvt/metrics.csv" "$M4/3_pvt/metrics.md" \
      "05_全PVT仿真验证_输出5/逐角明细/" 2>/dev/null
cp -f "$M4/3_pvt/pvt_report.md" "05_全PVT仿真验证_输出5/PVT验证报告.md" 2>/dev/null
cp -f "$M4/5_shots/03_bode_nominal.png" "05_全PVT仿真验证_输出5/波形AC/03_bode_nominal.png" 2>/dev/null
[ -d "$M4/4_waves/waves" ] && cp -rf "$M4/4_waves/waves" "05_全PVT仿真验证_输出5/波形AC/"
echo "  ok"

echo "==== 5) 输出6：算法性能 + 运行日志 ===="
cp -f "$M4/3_pvt/algorithm_stats.json" "$M4/3_pvt/algorithm_stats.md" "06_代码与算法性能_输出6/" 2>/dev/null
cp -f "$M4/7_logs/m4_final2.log" "06_代码与算法性能_输出6/模块四运行日志.log" 2>/dev/null
echo "  ok"

echo "==== 6) 清理不需要给评委的内容 ===="
rm -f "$M4/code/交付物清单.md" 2>/dev/null
rm -f "$M4/2_netlist/_export.netlist.raw" 2>/dev/null
rm -f "$M4/3_pvt/per_corner_snapshot.txt" 2>/dev/null
rm -f "04_最优尺寸反标_输出4/schematic_var_best/"*.cdslck* 2>/dev/null
rm -f "$ROOT/module4_deliverables_20261019.tar.gz" 2>/dev/null
echo "  已删除：m4_deliverables/code/交付物清单.md、_export.netlist.raw、per_corner_snapshot.txt、*.cdslck、module4_deliverables_20261019.tar.gz"

echo "==== 7) 删除已并入的 m4_deliverables ===="
rm -rf "$M4"

echo "==== 8) 重生成 MANIFEST.md5 ===="
{ find . -type f ! -name 'MANIFEST.md5' -print0 | sort -z | xargs -0 md5sum; } > MANIFEST.md5
echo "  $(wc -l < MANIFEST.md5) 个文件"

echo
echo "==== 组装完成，最终结构 ===="
find . -maxdepth 2 | sort | sed 's|^\./||'
