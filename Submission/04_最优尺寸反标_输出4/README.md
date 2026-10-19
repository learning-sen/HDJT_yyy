# 输出 4：最优尺寸反标

| 文件 | 说明 |
|---|---|
| 2026_EDA_case1_best_params.txt | 平台验证过的最优尺寸（105 条，parameter, 名字, 值） |
| 变量清单_优化后_105行.csv | 同上，转成 名字=值（赛题示例格式） |

该文件已通过 un_score.sh 全流程反标 + 仿真验证，平台复核 **84.9584 / 100**。

## 待补

**OPA/schematic_var_best（含最优尺寸的电路图）** —— 需在服务器用 writeback.py 生成，
输入就是本目录的 2026_EDA_case1_best_params.txt。
见 ../08_模块四_待补/README-待补.md。
