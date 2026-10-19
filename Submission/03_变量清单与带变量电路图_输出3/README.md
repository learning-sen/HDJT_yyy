# 输出 3：变量清单 + 带变量的 schematic

| 文件 | 说明 |
|---|---|
| 变量清单_约减后_47行.txt | 模块二约减后的 47 个自由变量（值为空，供 PyAether --param_file） |
| 变量清单_优化后_105行.csv | 最优解的 105 条尺寸，格式与赛题示例一致（PM0_l=5.195u） |
| params_writeback_template.txt | 105 条原理图符号 → 变量 的映射模板 |

## 待补

**OPA/schematic_var（带变量的电路图）** —— 需在服务器用模块四的 param_extract.py 生成。
见 ../08_模块四_待补/README-待补.md。
