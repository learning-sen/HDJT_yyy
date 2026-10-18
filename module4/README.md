# 模块四：PyAether 辅助自动化流程脚本

> 对应赛题 PDF §5 表格**第 4 项**「PyAether 辅助自动化流程脚本（九天服务器）」，赛题原文列了 5 个子项。
> 本目录逐项实现，纯标准库 + `pyAether`，无第三方依赖。

## 一、子项 → 文件映射

| # | 赛题原文 | 文件 | 本地验证 | 服务器实测 |
|---|---|---|---|---|
| 1 | 电路图器件尺寸转为待优化变量的**参数化脚本** | `param_extract.py` | ✅ `--mock` | ⏳ |
| 2 | **读取电路器件连接关系**脚本 | `netlist_export.py` | ✅ `--mock` | ⏳ |
| 3 | 调用 MDE 完成 PVT 仿真、提取性能指标的**仿真引擎**脚本 | `sim_engine.py` | ✅ `--mock` | ⏳ |
| 4 | 将最优尺寸回写至电路图的**反标脚本** | `writeback.py` | ✅ `--mock` | ⏳ |
| 5 | **高集成自动优化接口**脚本 | `run_auto.sh` | ⚠️ 仅静态审查（本机无 bash） | ⏳ |

公共口径（变量边界 / 导出 schema / 单位换算 / 旧路径修复）统一放在 `m4_common.py`，
**唯一事实来源**，避免 5 个脚本各写一份口径而走样。

## 二、2026-10-18 改进（依据队友服务器实测，见 `module3/修正说明.md`）

| 改进 | 依据 | 影响 |
|---|---|---|
| **`[P0-8]` MDE 旧路径自动修复** | 服务器实测：corner 配置写死 `/home/eda_2025/...`，仿真必报 `File does not exist` → 全员 0 分 | `sim_engine.py` 在 `emyInitAether` 之前扫描 `setting`/`adeL2View.file`/`*.scs`，把不存在的旧路径重定向到 `<cwd>/hes_release/...`（仅当新位置存在，原文件备份 `*.m4bak`）。可用 `--fix_paths_only` 先单独确认 |
| **`[P0-3]` 边界对齐 `score.py` 的 clamp** | `score.py::read_parameters` 按参数名分别 clamp，不是统一 0.13..20 | `m4_common.bounds_for()`：`fw` 0.15..50、`segW` 0.42..10、`segL` 5..100、电容 `l` 4..30、其它 `l` 0.13..20、`m` 整数 1..100 |
| **`[P0-4]` 导出 schema 对齐真实 105** | 实测 `case1_params_0.txt`：105 = MOS 29×3 + 电容 6×1(**只有 `l`**) + 电阻 6×2 | `param_extract.py` 按 `EXPORT_SCHEMA` 导出；`sim_engine.py` 遇到不该出现的参数（如电容 `fw/m`）会提示 |
| **反标兼容"目标视图已存在"** | OPA 目前只有 `schematic` 与 `symbol` 两个 view | `writeback.py`：若 `--out_view` 已存在就直接写入；否则尝试平台拷贝接口，失败则中止并提示（不偷改原图） |
| **pyAether 惰性加载** | 服务器实测：`import pyAether` 会加载 OpenAccess 并检出 `PY_AETHER` license | 四个脚本改为按需加载；`--mock`/自检/纯解析路径**不占 license**（共享服务器上很重要） |
| **`run_auto.sh` 环境自检 + 新模式** | 实测：`pythone` 不是系统命令，不 `source setup.bash` 会既找不到解释器也拿不到 license | 新增 `--smoke`（冒烟四查）、`--params`、`--fix-paths`；启动时检查 `pythone` 与 `LM_LICENSE_FILE` 并给出提示 |

## 三、一条龙用法（服务器上，**每个新终端先 `source setup.bash`**）

```bash
source ~/EDA_2026_Empyrean_lab_start/setup.bash
which pythone            # 必须有输出，否则别往下走

# 0) 先确认 [P0-8] 是否命中（不仿真，秒级）
bash module4/run_auto.sh --fix-paths

# 1) 参数化：导出待优化变量 + 元数据（应与赛方 105 口径一致）
bash module4/run_auto.sh --params ./m4_params

# 2) 连接关系：导出网表 + 连接表（可交给模块二）
pythone module4/netlist_export.py --ae_lib 2026_EDA_case1 --ae_cell OPA \
    --ae_view schematic --out_dir ./m4_net

# 3) 冒烟：单次仿真，一次拿到 T_eval / 初始解六个数 / best 文件可写性
bash module4/run_auto.sh --smoke ~/EDA_2026_Empyrean_lab_start/case1_params_0.txt ./m4_smoke

# 4) 正式：给定尺寸 -> 全 PVT 指标（+ 反标）
bash module4/run_auto.sh --full <sizes.txt> ./m4_out
```

## 四、各脚本产物

| 脚本 | 产物 | 用途 |
|---|---|---|
| `param_extract.py` | `extractcdfVal_0.txt`、`params_meta.json`、`params_table.md` | 给模块三构造搜索空间（含边界/类型）；清单可直接进报告 |
| `netlist_export.py` | `export.netlist`、`connectivity.json`、`connectivity.md` | 给模块二做拓扑识别/匹配判定 |
| `sim_engine.py` | `metrics.json/.csv/.md`、`raw/` | 全 PVT 最坏情况指标 + 估算分 + 逐项判定 |
| `writeback.py` | `params_var_best.txt`、`params_before.txt`、`writeback_verify.txt`、`writeback_report.json` | 赛题 6.2 第 4 项（反标电路图）+ 逐参数读回校验 |
| `run_auto.sh` | 汇总以上 | 赛题 6.2「高集成自动优化接口」 |

## 五、口径与安全约定

- **指标口径与 `score.py` 完全一致**：PM/Gain/UGB 取所有 PVT 角的 **Min**，GM/I_OPA 取 **Max**；
  面积 `MOS=fw·L·m·1.5`、`电容=fw·L·m`、`电阻=segW·segL·segments·2`，单位 **µm²**。
- **长度单位统一为 µm**（同赛方 `param_convert`：`u`=µm、`n`=nm、无单位=米）。
- **反标默认不动原图**：目标视图不存在时先尝试拷贝；平台无拷贝接口则**中止**，只有 `--in_place` 才改原图（且先导出 `params_before.txt`）。
- **写参数后逐条读回校验**，不一致写进 `writeback_verify.txt` 并返回非 0。
- **路径修复会备份**：改动任何 `setting`/`*.scs` 前先存 `*.m4bak`。

## 六、本地自检

```bash
python module4/tests/selftest_module4.py
```

共 **60 项**（服务器上只有 `module4/` 时，T6d 跨模块验证会 `[SKIP]`，其余全过）：三种参数格式解析、单位换算、`[P0-3]` 六组边界、`[P0-4]` schema 识别、
`[P0-8]` 旧路径重定向（含"目标不存在则不改"+备份）、`--mock` 全链路、反标读回校验、
参数化导出 schema、连接关系导出，以及**跨模块验证**（模块四导出的网表能被模块二
`parse_netlist()` 正确解析出 6 个器件）。

> 自检**不消耗 license**：pyAether 是惰性加载，`--mock` 与自检全程不会 `import pyAether`（有 T10 断言）。
> ⚠️ `run_auto.sh` **未在本地执行**（本机没有 bash/WSL）。上服务器先跑 `bash -n run_auto.sh`
> 做语法检查，再用 `--smoke`（假数据/真机均可）验证分支逻辑。

## 七、【待核实】清单（上服务器逐条确认）

| # | 事项 | 影响 | 查法 |
|---|---|---|---|
| 1 | 顶层端口读取接口（`cv.terminals` / `cellTerms` / `pins`） | 网表 `subckt` 行 | 脚本依次尝试并打印命中的属性名 |
| 2 | 器件 master 名属性（`cellName`/`masterName`/`master.name`） | 器件类型判定 | 同上，脚本会打印 |
| 3 | `MdeSession.open` 在 `-adv` 模式下的权限行为 | 仿真引擎能否启动 | 直接跑 `--smoke` |
| 4 | `result.name()` 与 `*summary*.csv` 实际命名 | 指标解析 | 脚本用 glob 兜底，失败会打印候选文件 |
| 5 | cellview 拷贝接口名（`dbCopyCellView`/`dbCopyCV`/…） | 反标能否**新建**视图 | 脚本依次尝试；也可先在 Aether 里手工拷出 `schematic_var_best`（脚本会自动识别） |
| 6 | 单次 `evaluate()` 的真实耗时 `T_eval` | 优化预算 | `--smoke` 会打印耗时 |

已确认（来自队友实测，不再列为待核实）：
- 参数文件是**三列带引号 CSV**，长度单位带 `u/n` 后缀；
- 真实 schema = MOS 3 / 电容 1 / 电阻 2（共 105）；
- `pythone` 由 `setup.bash` 提供；不 source 会拿不到 license；
- OPA 当前只有 `schematic` / `symbol` 两个视图。

## 八、真机验证记录（2026-10-18，服务器 edauser32@eda202601）

### 8.1 五个脚本的真机结果

| # | 脚本 | 真机命令 | 结果 |
|---|---|---|---|
| 1 | `param_extract.py` | `--ae_lib 2026_EDA_case1 --ae_cell OPA --ae_view schematic` | ✅ **105 个变量**；MOS=87 / R=12 / C=6；参数分布 `fw29 m29 l35 segL6 segW6`；越界 0 |
| 2 | `netlist_export.py` | 同上，`--out_dir ~/m4_net` | ✅ 顶层端口来自 **`cv.terminals`**（9 个）；真实器件 **41**（29 MOS + 6 R + 6 C）；**9 个 `PIN0~PIN8` 端口占位**（master `ipin/iopin`，0 端子）已剔除 |
| 3 | `sim_engine.py` | 同上 + `--param_file case1_params_0.txt` | ✅ 六项指标与官方 `run_sim_case1.sh` **完全一致**（UGB 7.64114e6 / PM 73.1725 / Gain 29.4006 / GM −15.0247 / I_OPA 1.568mA / Area 11299.2） |
| 4 | `writeback.py` | `--out_view schematic_var_best` | ✅ 视图创建成功；**`dbCopyCellView(设计对象, lib, cell, view)`** 是正确签名；参数落盘独立验证：写入 `0.55u` → 重开读回 `550n` → 恢复 `2u` |
| 5 | `run_auto.sh` | `--smoke <params> ~/m4_smoke` | ✅ 冒烟四查全部输出；`T_eval = 18 s`；六项指标与官方一致（面积 bug 见 8.2 已修） |

### 8.2 真机踩到并已修掉的坑

| 坑 | 现象 | 修法 |
|---|---|---|
| `dbCheckAndSaveDesign` 返回 False | 在 `dbCopyCellView` **返回的句柄**上写参数，保存失败 | 拷贝后**关闭句柄 → 重新 `dbOpenCV` 打开新视图** → 再写 → 保存（重开后 check&save 变 True） |
| `dbCopyCellView` 参数类型 | `argument 1 of type 'emyDesign const *'` | 候选签名把 `(设计对象, lib, cell, view)` 放第一位 |
| 端口占位混入器件统计 | `PIN0~PIN8`（ipin/iopin，0 端子）被算成 OTHER | 归类为 `PORT`，从器件列表剔除并单列 `n_port_placeholders` |
| 中文日志变 `\uXXXX` | 服务器 locale 为 C | `m4_common.setup_stdio()` 强制 UTF-8 |
| `import pyAether` 占 license | 自检也检出 `PY_AETHER` | 惰性加载（`--mock`/自检全程不 import） |
| **`aeEmyInstGetParameter` 返回 `emyString`** | `float(emyString)` → `TypeError: float() argument must be a string or a number, not 'emyString'`，面积被跳过 → `Total_Area = 0` | 一律先 `str()` 再转数字（`m4_common.to_num()`），有 T11 回归测试 |
| **老 bash（<4.4）下 `set -u` 展开空数组** | `run_auto.sh: MOCK_ARG[@]: unbound variable` | 用 `"${ARR[@]+"${ARR[@]}"}"` 可移植写法 |

### 8.3 顺带确立的基线（供模块三/报告引用）

- 初始解（`case1_params_0.txt`）跑官方评分器：**Total score 78.273 / 100**
  （PM/GM/Gain/I_OPA 各 10 满分；UGB 0.573/15；Area 17.70/25；时间 20/20）
- 剩余空间：**UGB +14.43、Area +7.30**（PM/GM/Gain/I_OPA 已满，别弄坏）
- 单次全 PVT 仿真 `T_eval ≈ 18.4 s`（含进程启动 + pyAether 初始化）
