# 模块四：PyAether 辅助自动化流程脚本

> 对应赛题 PDF §5 表格**第 4 项**「PyAether 辅助自动化流程脚本（九天服务器）」，
> 赛题原文列了 5 个子项。本目录逐项实现，全部为**纯标准库 + PyAether**，
> 无第三方依赖（除了平台自带的 pyAether）。

## 一、子项 → 文件映射

| # | 赛题原文 | 文件 | 本地可验证 | 服务器实测 |
|---|---|---|---|---|
| 1 | 电路图器件尺寸转为待优化变量的**参数化脚本** | `param_extract.py` | ✅ `--mock` | ⏳ |
| 2 | **读取电路器件连接关系**脚本 | `netlist_export.py` | ✅ `--mock` | ⏳ |
| 3 | 调用 MDE 完成 PVT 仿真、提取性能指标的**仿真引擎**脚本 | `sim_engine.py` | ✅ `--mock` | ⏳ |
| 4 | 将最优尺寸回写至电路图的**反标脚本** | `writeback.py` | ✅ `--mock` | ⏳ |
| 5 | **高集成自动优化接口**脚本（输入尺寸文件即可自动调用仿真输出性能结果） | `run_auto.sh` | 逻辑审阅 | ⏳ |

全部脚本都支持 `--mock`（不需要 PyAether，用假数据验证解析/聚合/落盘逻辑），
这样在没上服务器之前就能把链路跑通。

## 二、一条龙用法（服务器上，先 `source setup.bash`）

```bash
cd /home/eda_2026/EDA_2026_Empyrean_lab_start

# 1) 参数化：导出待优化变量（= 赛方 extractcdfVal_0.txt）
pythone ~/work/module4/param_extract.py --ae_lib 2026_EDA_case1 --ae_cell OPA \
    --ae_view schematic --out_dir ./m4_params

# 2) 连接关系：导出网表 + 连接表（可直接交给模块二做拓扑识别）
pythone ~/work/module4/netlist_export.py --ae_lib 2026_EDA_case1 --ae_cell OPA \
    --ae_view schematic --out_dir ./m4_net

# 3) 仿真引擎：给定尺寸 -> 全 PVT 仿真 -> 最坏情况指标
pythone ~/work/module4/sim_engine.py --ae_lib 2026_EDA_case1 --ae_cell OPA \
    --ae_view schematic --mde_cell OPA_loopgain --mde_view spe_state1_Corner \
    --param_file case1_params_0.txt --out_dir ./m4_sim

# 4) 反标：最优尺寸写回原理图，生成 schematic_var_best 视图
pythone ~/work/module4/writeback.py --ae_lib 2026_EDA_case1 --ae_cell OPA \
    --ae_view schematic --out_view schematic_var_best \
    --param_file ./m4_sim/best_schematic_params.txt --out_dir ./m4_wb

# 5) 高集成接口：一条命令 仿真（+反标）
./run_auto.sh case1_params_0.txt ./m4_auto          # 只仿真
./run_auto.sh --full case1_params_0.txt ./m4_full   # 仿真 + 反标
```

## 三、各脚本产物

| 脚本 | 产物 | 用途 |
|---|---|---|
| `param_extract.py` | `extractcdfVal_0.txt`、`params_meta.json`、`params_table.md` | 给模块三构造搜索空间（含边界/类型，不用再猜）；清单可直接进技术报告 |
| `netlist_export.py` | `export.netlist`、`connectivity.json`、`connectivity.md` | 给模块二做拓扑识别/匹配判定；连接表可进报告 |
| `sim_engine.py` | `metrics.json/.csv/.md`、`raw/` | 全 PVT 最坏情况指标 + 估算分 + 逐项判定；`metrics.md` 可直接贴报告 |
| `writeback.py` | `params_var_best.txt`、`params_before.txt`、`writeback_verify.txt`、`writeback_report.json` | 赛题 6.2 第 4 项（反标后电路图）+ 逐参数读回校验 |
| `run_auto.sh` | 汇总以上 | 赛题 6.2「高集成自动优化接口」 |

## 四、口径与安全约定

- **指标口径与赛方 `score.py` 完全一致**：PM/Gain/UGB 取所有 PVT 角的 **Min**，
  GM/I_OPA 取 **Max**；面积公式 MOS=`fw·L·m·1.5`、电容=`fw·L·m`、电阻=`segW·segL·segments·2`。
- **长度单位统一为 µm**（与赛方 `param_convert` 一致：`u`=µm、`n`=nm、无单位=米）。
- **反标默认不动原图**：先把 cellview 拷成 `--out_view`；平台若没有可用的拷贝接口，
  脚本**中止**并提示，只有显式加 `--in_place` 才会改原图（且会先导出 `params_before.txt`）。
- **写参数后逐条读回校验**，不一致会写进 `writeback_verify.txt` 并返回非 0。

## 五、本地自检

```bash
python module4/tests/selftest_module4.py
```

覆盖 41 项：三种参数格式解析、单位换算、`--mock` 全链路、最坏情况聚合与估算分、
反标读回校验、参数化导出格式、连接关系导出，以及**跨模块验证**（模块四导出的网表能被
模块二 `netlist_parse_netlist()` 正确解析出 6 个器件）。

## 六、【待核实】清单（上服务器逐条确认，填回代码注释）

| # | 事项 | 影响 | 查法 |
|---|---|---|---|
| 1 | 顶层端口读取接口（`cv.terminals` / `cellTerms` / `pins`） | 网表 `subckt` 行 | `netlist_export.py` 会依次尝试并打印命中的属性名 |
| 2 | 器件 master 名属性（`cellName`/`masterName`/`master.name`） | 器件类型判定 | 同上，脚本会打印 |
| 3 | `MdeSession.open` 在 `-adv` 模式下的权限行为 | 仿真引擎能否启动 | 直接跑 `sim_engine.py` |
| 4 | `result.name()` 与 `*summary*.csv` 实际命名 | 指标解析 | `sim_engine.py` 用 glob 兜底，若解析失败会打印候选文件 |
| 5 | cellview 拷贝接口名（`dbCopyCellView`/`dbCopyCV`/…） | 反标能否生成新视图 | `writeback.py` 会依次尝试并打印 |
| 6 | `segments` 参数是否所有电阻都有 | 面积计算 | 面积里若缺 `segments` 会按 1 计，报告里要注明 |
