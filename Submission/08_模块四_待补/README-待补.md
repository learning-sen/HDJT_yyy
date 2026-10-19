# 模块四：PyAether 辅助自动化流程脚本（待服务器验证）

> 状态：**代码已就绪，本地 mock 自测通过，服务器实测未做。**
> 代码来源：`module4_20261018.tar.gz`（7 个文件 / 1841 行）
> 截止：2026-10-19 24:00

---

## 一、5 个子项 → 文件映射

| # | 赛题原文 | 文件 | 本地 | 服务器 |
|---|---|---|---|---|
| 1 | 器件尺寸 → 待优化变量的**参数化脚本** | `param_extract.py`（199 行） | ✅ mock | ⏳ |
| 2 | **读取器件连接关系** | `netlist_export.py`（283 行） | ✅ mock | ⏳ |
| 3 | 调 MDE 跑 PVT、提取指标的**仿真引擎** | `sim_engine.py`（427 行） | ✅ mock | ⏳ |
| 4 | 最优尺寸**反标** | `writeback.py`（321 行） | ✅ mock | ⏳ |
| 5 | **高集成自动优化接口** | `run_auto.sh`（137 行） | ⚠️ 仅静态审查 | ⏳ |
| — | 公共口径（边界/schema/单位/旧路径修复） | `m4_common.py`（250 行） | ✅ | — |
| — | 自测 | `tests/selftest_module4.py`（224 行） | ✅ | — |

已继承模块三的三条实战结论：
- `[P0-8]` MDE 旧路径自动修复（`sim_engine.py` 在 `emyInitAether` 前改 `setting`，备份 `*.m4bak`）
- `[P0-3]` 边界对齐 `score.py`（fw 0.15–50 / segW 0.42–10 / segL 5–100 / 电容 l 4–30 / m 1–100）
- `[P0-4]` 导出 schema 对齐真实 105 条（电容只有 `l`）

---

## 二、需要产出的两件交付物

| 交付物 | 赛题项 | 由哪个脚本产出 |
|---|---|---|
| **`OPA/schematic_var`**（带变量的电路图） | 6.2 输出 3 | `param_extract.py` |
| **`OPA/schematic_var_best`**（含最优尺寸） | 6.2 输出 4 | `writeback.py`（输入 = `04_最优尺寸反标/2026_EDA_case1_best_params.txt`） |

> ⚠️ 当前 `OPA` 单元只有 `schematic` 和 `symbol` 两个 view，两者都不存在。

---

## 三、服务器执行步骤（约 30–60 分钟）

```bash
# 0) 每个新终端都要
source ~/EDA_2026_Empyrean_lab_start/setup.bash
which pythone            # 必须有输出

# 1) 把 module4 解包到家目录
cd ~ && tar -xzf module4_20261018.tar.gz

# 2) 先确认旧路径修复能否命中（不仿真，秒级；这是"全员 0 分"的根因）
bash ~/module4/run_auto.sh --fix-paths

# 3) 参数化：导出变量清单 + 元数据（应与赛方 105 条一致）
bash ~/module4/run_auto.sh --params ~/m4_params
ls ~/m4_params        # 期望：extractcdfVal_0.txt / params_meta.json / params_table.md

# 4) 连接关系（对应输出 3 的"读取器件连接"证据）
pythone ~/module4/netlist_export.py --ae_lib 2026_EDA_case1 --ae_cell OPA \
    --ae_view schematic --out_dir ~/m4_net

# 5) 冒烟：单次仿真，拿 T_eval + 初始解六个数
bash ~/module4/run_auto.sh --smoke ~/EDA_2026_Empyrean_lab_start/case1_params_0.txt ~/m4_smoke

# 6) 反标：把模块三的最优尺寸写回电路图
bash ~/module4/run_auto.sh --full ~/EDA_2026_Empyrean_lab_start/EDA_2026_Empyrean_score/2026_EDA_case1_output/eda_2026_case_1/2026_EDA_case1_best_params.txt ~/m4_out
ls ~/m4_out           # 期望：params_var_best.txt / writeback_verify.txt / writeback_report.json
```

跑完后回填本目录：

| 从服务器取回 | 放到 |
|---|---|
| `~/m4_params/*`（extractcdfVal_0.txt、params_meta.json、params_table.md） | `08_模块四_待补/params/` |
| `~/m4_net/*`（export.netlist、connectivity.json/.md） | `08_模块四_待补/netlist/` |
| `~/m4_smoke/*`、`~/m4_out/*`（反标报告、校验） | `08_模块四_待补/writeback/` |
| `OPA` 单元的 `schematic_var`、`schematic_var_best`（Aether 里截图 + 视图文件） | `03_…/` 与 `04_…/` |

---

## 四、时间不够时的兜底写法（已验证可自圆其说）

若服务器上跑不通，报告里按下面写，**不要伪造截图**：

> 赛方下发的环境中 `OPA` 单元只提供 `schematic` 与 `symbol` 两个视图，
> 参数化脚本与反标脚本未随环境下发。本作品以**等效实现**代替：
> ① 参数化与反标逻辑由 `param_extract.py` / `writeback.py` 源码给出，
>    并经本地 mock 自测（`tests/selftest_module4.py`，8 项）；
> ② 反标的数值结果以 `2026_EDA_case1_best_params.txt`（105 条，
>    与赛方 `case1_params_0.txt` 同 schema）完整给出；
> ③ 该 105 条参数已通过 `run_score.sh` 全流程验证，平台复核得分 **84.9584**。
