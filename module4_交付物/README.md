# 模块四交付物（本地副本）

> 生成日期：2026-10-19　｜　对应赛题 6.2 第 2/3/4/5/6 项
> 原始运行发生在九天服务器 `edauser32@eda202601`，本目录是**结果副本**。

## 目录说明

| 目录 | 内容 | 赛题 6.2 | 状态 |
|---|---|---|---|
| `3_pvt/pvt_report.md` | **全 PVT 仿真验证报告**（9 角明细 + 覆盖检查 + 达标判定 + 波形/电路图） | 第 5 项 | ✅ 94 行，覆盖 7/7 |
| `3_pvt/per_corner.csv/md/json` | 逐角明细（TT/FF/SS × 1.62/1.8/1.98V × −40/27/125℃） | 第 5 项 | ✅ 9 角 |
| `3_pvt/metrics.json` | 最坏情况指标 + 面积（PM 73.17 / GM −15.02 / Gain 29.40 / UGB 7.64M / I_OPA 1.568mA / Area 11299.2 µm²） | 第 5 项 | ✅ |
| `3_pvt/raw/*.csv` | MDE 原始 `transpose`/`summary` CSV | 第 5 项 | ✅ |
| `3_pvt/shots/03_bode_nominal.png` | Bode 图（AC 扫频，iwave 导出截图） | 第 5 项 | ✅ |
| `3_pvt/figures/01_schematic_parameterized.png` | 带变量的电路图（全电路 + CDF 参数面板） | 第 3 项 | ✅ |
| `3_pvt/figures/02_schematic_var_best.png` | 反标后电路图（尺寸已写回，标注为数值） | 第 4 项 | ✅ |
| `1_params/` | 105 变量 CSV + 元数据 + 变量表 | 第 3 项 | ⏳ 待从服务器剪贴板补 |
| `2_netlist/` | `export.netlist` + `connectivity.json/md` | 第 2 项 | ⏳ 待补 |
| `3_pvt/metrics.md`、`algorithm_stats.md` | 指标表、代码质量与算法性能 | 第 5/6 项 | ⏳ 待补 |
| `6_schematic_var_best/` | `.oa` 视图原件 | 第 4 项 | 说明：二进制原件在九天平台（`2026_EDA_case1/OPA/schematic_var_best`），报告中以截图证明 |
| `_terminal_snapshots/` | 服务器终端输出留档（**非交付物**） | — | 留档 |

## 数据来源与可信度

- **逐角数值**：来自服务器 MDE 产物 `Results1080_transpose.csv`，与本目录 `raw/Results1080_transpose.csv` 一致；
  逐角最坏值与 `summary.csv` 包络**交叉校验 5 项全部一致**。
- **本地重建方式**：因该账号无法用 FileZilla 下载二进制，`3_pvt` 下的 CSV/报告是用服务器实测数值在本地
  重跑 `corner_extract.py` + `report_gen.py` 生成的（生成逻辑与服务器同一份代码）。
- **图片**：三张 PNG 均为服务器 VNC 桌面实拍（Windows 截图），已统一压到宽 1600 px（377~629 KB）。

## 已知说明

- 报告第 2 节"优化前后对比"的初始解一栏为 `—`：这份是**初始解**的验证（尚未跑正式优化）；等 3 小时优化跑完后，
  用最优参数重跑 `sim_engine.py` + `report_gen.py --init_dir <初始解目录>` 即可填满对比列。
- 报告第 6 节"代码质量与算法性能"在正式优化完成后由 `stats.py --log optimization.log` 补上
  （评估次数/总耗时/峰值内存；当前已有单次仿真的 512.4 MB）。
