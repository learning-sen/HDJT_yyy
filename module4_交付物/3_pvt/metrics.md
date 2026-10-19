# PVT 仿真结果

- 电路：`2026_EDA_case1 / OPA / schematic`
- MDE：`OPA_loopgain / spe_state1_Corner`
- 参数文件：`/home/edauser32/EDA_2026_Empyrean_lab_start/case1_params_0.txt`（105 个符号）
- 最坏情况聚合：PM/Gain/UGB 取 Min，GM/I_OPA 取 Max
- 估算分（不含时间分）：**58.27 / 80**
- 三条硬约束：全部满足 ✅
- [P0-8] 旧路径修复：扫描 122 个文件，改动 0 个

| 指标 | 最坏值 | 单位 | 门限 | 判定 |
|---|---|---|---|---|
| Phase_Margin | 73.1725 | deg | 50.0 | ✅ |
| Gain_db | 29.4006 | dB | 20.0 | ✅ |
| UGB | 7.64114e+06 | Hz | 越大越好 | — |
| Gain_Margin | -15.0247 | dB | -10.0 | ✅ |
| I_OPA | 0.00156799 | A | 0.003 | ✅ |
| Total_Area | 11299.2 | um² | ≤ 8000 满分 | ⚠️ |

## 结果文件与资源占用

- 峰值内存：512.4 MB

| 文件 | 大小(B) |
|---|---|
| `Results1080_detail.csv` | 1662 |
| `Results1080_transpose.csv` | 1207 |
| `Results1080_summary.csv` | 517 |
| `Results1080_yield.csv` | 53 |

## 波形文件（Bode 原始数据）

- 目录：`/home/edauser32/m4_final2/waves`
- 文件：`ac.ac`（AC 扫频）
- 角：C1_0, C1_1, C1_2, C1_3, C1_4, C1_5, C1_6, C1_7, Nominal
- 用 `iwave` 打开任一 `ac.ac` 即可看环路增益/相位曲线。
