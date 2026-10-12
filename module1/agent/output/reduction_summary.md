# 模块 2 报告：拓扑模块识别与参数约减

> 由 `python -m src.topology` 自动生成，可直接引用进技术报告。

## 1. 输入

| 项 | 值 |
|---|---|
| 网表 | `OPA_loopgain.netlist` |
| 子电路 | `OPA` |
| 对外端口 | IREF, GNDA, SUB, VCM, VDDA, VINN, VINP, VOUTN, VOUTP |
| 器件总数 | 59（MOS 29） |
| 自动分段折叠 | 2 条链 → 逻辑器件 43 个 |

## 2. 识别到的拓扑模块

| ID | 类型 | 器件 | 置信度 |
|---|---|---|---|
| CM1 | current_mirror | NM2, NM13, NM12, NM9, NM8, NM7, NM6, NM3 | 3 |
| CM2 | current_mirror | PM5, PM6 | 3 |
| CM3 | current_mirror | PM0, PM4, PM1 | 3 |
| CM4 | current_mirror | PM3, PM2 | 2 |
| IP1 | input_pair | PM10, PM9 | 3 |
| AL1 | active_load | NM7, NM6 | 2 |
| MP1 | matching_pair | NM12, NM13 | 2 |
| MP2 | matching_pair | NM12, NM6 | 2 |
| MP3 | matching_pair | NM12, NM7 | 2 |
| MP4 | matching_pair | NM8, NM9 | 2 |
| MP5 | matching_pair | PM10, PM9 | 2 |
| MP6 | matching_pair | PM2, PM3 | 2 |
| MP7 | matching_pair | R0, R3 | 2 |
| MP8 | matching_pair | C2, C3 | 2 |
| TIE1 | two_terminal_shorted | R6 | 2 |
| TIE2 | two_terminal_shorted | R5 | 2 |
| TIE3 | two_terminal_shorted | C5 | 2 |
| TIE4 | two_terminal_shorted | C4 | 2 |
| CMFB1 | cmfb | NM11, PM12, PM8, PM6, PM3, PM2, R3, C3… | 3 |
| BIAS1 | bias_branch | NM0, NM1, NM10, NM11, NM14, NM15, NM4, NM5… | 2 |
| SEG1 | segmented_device | R0, R0_2_res_gen, R0_3_res_gen, R0_4_res_gen, R0_5_res_gen, R0_6_res_gen, R0_7_res_gen, R0_8_res_gen… | 3 |
| SEG2 | segmented_device | R3, R3_2_res_gen, R3_3_res_gen, R3_4_res_gen, R3_5_res_gen, R3_6_res_gen, R3_7_res_gen, R3_8_res_gen… | 3 |

### 2.1 判定依据（为何识别为该模块）

- **CM1（current_mirror）**：同型(nmos)；栅极同接 net53；源极同接 GNDA；NM2 栅漏短接 -> 参考管
- **CM2（current_mirror）**：同型(pmos)；栅极同接 net5；源极同接 VDDA；PM5 栅漏短接 -> 参考管
- **CM3（current_mirror）**：同型(pmos)；栅极同接 net6；源极同接 VDDA；PM0 栅漏短接 -> 参考管
- **CM4（current_mirror）**：同型(pmos)；栅极同接 vcmfb；源极同接 VDDA；组内无二极管连接，取 PM3 为参考管
- **IP1（input_pair）**：同型(pmos)；源极同接 net37（尾节点）；栅极分别接输入端口 VINN / VINP；漏极分别接 net44 / net4
- **AL1（active_load）**：电流镜 CM1 的器件；漏极接在输入对管漏极节点 ['net4', 'net44'] 上；以有源器件替代电阻作负载，提高增益
- **MP1（matching_pair）**：同 model(n_mos_a)、同 multi(4)、同一支路（源极同接 GNDA、栅极同接 net53）；-> 版图匹配要求尺寸绑定，共享同一组变量（只保留一个基准变量）
- **MP2（matching_pair）**：同 model(n_mos_a)、同 multi(4)、同一支路（源极同接 GNDA、栅极同接 net53）；-> 版图匹配要求尺寸绑定，共享同一组变量（只保留一个基准变量）
- **MP3（matching_pair）**：同 model(n_mos_a)、同 multi(4)、同一支路（源极同接 GNDA、栅极同接 net53）；-> 版图匹配要求尺寸绑定，共享同一组变量（只保留一个基准变量）
- **MP4（matching_pair）**：同 model(n_mos_a)、同 multi(4)、同一支路（源极同接 GNDA、栅极同接 net53）；-> 版图匹配要求尺寸绑定，共享同一组变量（只保留一个基准变量）
- **MP5（matching_pair）**：同 model(p_mos_a)、同 multi(2)、源极同接 net37 的差分两臂，栅极分别接 VINN / VINP；-> 版图匹配要求尺寸绑定，共享同一组变量（只保留一个基准变量）
- **MP6（matching_pair）**：同 model(p_mos_a)、同 multi(40)、同一支路（源极同接 VDDA、栅极同接 vcmfb）；-> 版图匹配要求尺寸绑定，共享同一组变量（只保留一个基准变量）
- **MP7（matching_pair）**：同 model(res_p_poly)、同 multi(None)、同 model 且共享节点 ['outaverage']，另一端分别接 ['VOUTP'] / ['VOUTN']；-> 版图匹配要求尺寸绑定，共享同一组变量（只保留一个基准变量）
- **MP8（matching_pair）**：同 model(cap_mim)、同 multi(None)、同 model 且共享节点 ['outaverage']，另一端分别接 ['VOUTP'] / ['VOUTN']；-> 版图匹配要求尺寸绑定，共享同一组变量（只保留一个基准变量）
- **TIE1（two_terminal_shorted）**：两端器件 R6 的两个端子都接在 net12 上 -> 电气上短路；版图里常见于寄生/去耦电容或参考电阻，**保留其变量**，但需在报告中说明为何保留
- **TIE2（two_terminal_shorted）**：两端器件 R5 的两个端子都接在 net11 上 -> 电气上短路；版图里常见于寄生/去耦电容或参考电阻，**保留其变量**，但需在报告中说明为何保留
- **TIE3（two_terminal_shorted）**：两端器件 C5 的两个端子都接在 net12 上 -> 电气上短路；版图里常见于寄生/去耦电容或参考电阻，**保留其变量**，但需在报告中说明为何保留
- **TIE4（two_terminal_shorted）**：两端器件 C4 的两个端子都接在 net11 上 -> 电气上短路；版图里常见于寄生/去耦电容或参考电阻，**保留其变量**，但需在报告中说明为何保留
- **CMFB1（cmfb）**：检测到共模相关节点: ['VCM', 'outaverage', 'vcmfb']；电阻分压网络 R0/R0：从 VOUTP 与 VOUTP 取平均到 VOUTP；涉及器件 11 个：['NM11', 'PM12', 'PM8', 'PM6', 'PM3', 'PM2', 'R3', 'C3', 'C2', 'R0', 'R3']；作用：稳定全差分输出的共模电平
- **BIAS1（bias_branch）**：偏置节点 ['IREF', 'VCM', 'vcmfb'] 直接驱动 11 个器件（栅极或独立源），构成参考偏置支路
- **SEG1（segmented_device）**：器件 R0 被自动拆分为 9 段串联（后缀 _<n>_res_gen）；参数完全相同（同一物理器件的分段实现）；-> 应视为**一个**器件，只保留一组变量
- **SEG2（segmented_device）**：器件 R3 被自动拆分为 9 段串联（后缀 _<n>_res_gen）；参数完全相同（同一物理器件的分段实现）；-> 应视为**一个**器件，只保留一组变量

## 3. 参数约减

| 阶段 | 变量数 |
|---|---|
| 原始网表（器件级，未折叠分段） | 153 |
| 折叠自动分段后 | 117 |
| **约减后** | **88** |
| 约减比例 | **24.8%** |

### 3.1 变量统计

- 按参数：l=22, w=28, m=28, segL=5, segW=5
- 按器件类型：cap=15, mos=63, res=10
- 整数变量 28 个（m / seg，优化时需取整），连续变量 60 个
- 尺寸绑定组 11 组

### 3.2 约减决策链（为何删除/绑定某变量）

- **bind_matching_pair** → 绑定 8 组，删除 23 个冗余变量
  - 理由：匹配器件必须尺寸绑定：保留一个基准变量，另一器件由匹配规则导出
- **bind_current_mirror** → 处理 3 个电流镜，删除 6 个冗余 l 变量
  - 理由：电流镜镜像管沟道长度必须与参考管一致；镜像比用 w/m 比例表达
- **collapse_segmented** → 变量只保留 1 组（原 10 个器件各自一组）
  - 理由：自动分段器件 R0（9 段）是同一物理器件，全链共用一组变量
- **collapse_segmented** → 变量只保留 1 组（原 10 个器件各自一组）
  - 理由：自动分段器件 R3（9 段）是同一物理器件，全链共用一组变量
- **render_reduced_netlist** → 约减后网表含 34 个器件
  - 理由：只保留参与优化的器件（已折叠分段、已剔除 dummy），并写出其变量

### 3.3 冗余变量映射（删除的变量指向哪个基准变量）

| 被删除变量 | 映射到 | 理由 |
|---|---|---|
| `NM13_l` | `NM2_l` | 与 NM12 为匹配对（same_branch），尺寸必须绑定 |
| `NM13_fw` | `NM12_fw` | 与 NM12 为匹配对（same_branch），尺寸必须绑定 |
| `NM13_m` | `NM12_m` | 与 NM12 为匹配对（same_branch），尺寸必须绑定 |
| `NM6_l` | `NM2_l` | 与 NM12 为匹配对（same_branch），尺寸必须绑定 |
| `NM6_fw` | `NM12_fw` | 与 NM12 为匹配对（same_branch），尺寸必须绑定 |
| `NM6_m` | `NM12_m` | 与 NM12 为匹配对（same_branch），尺寸必须绑定 |
| `NM7_l` | `NM2_l` | 与 NM12 为匹配对（same_branch），尺寸必须绑定 |
| `NM7_fw` | `NM12_fw` | 与 NM12 为匹配对（same_branch），尺寸必须绑定 |
| `NM7_m` | `NM12_m` | 与 NM12 为匹配对（same_branch），尺寸必须绑定 |
| `NM9_l` | `NM2_l` | 与 NM8 为匹配对（same_branch），尺寸必须绑定 |
| `NM9_fw` | `NM8_fw` | 与 NM8 为匹配对（same_branch），尺寸必须绑定 |
| `NM9_m` | `NM8_m` | 与 NM8 为匹配对（same_branch），尺寸必须绑定 |
| `PM9_l` | `PM10_l` | 与 PM10 为匹配对（differential_arms），尺寸必须绑定 |
| `PM9_fw` | `PM10_fw` | 与 PM10 为匹配对（differential_arms），尺寸必须绑定 |
| `PM9_m` | `PM10_m` | 与 PM10 为匹配对（differential_arms），尺寸必须绑定 |
| `PM3_l` | `PM2_l` | 与 PM2 为匹配对（same_branch），尺寸必须绑定 |
| `PM3_fw` | `PM2_fw` | 与 PM2 为匹配对（same_branch），尺寸必须绑定 |
| `PM3_m` | `PM2_m` | 与 PM2 为匹配对（same_branch），尺寸必须绑定 |
| `R3_segL` | `R0_segL` | 与 R0 为匹配对（shared_node），尺寸必须绑定 |
| `R3_segW` | `R0_segW` | 与 R0 为匹配对（shared_node），尺寸必须绑定 |
| `C3_l` | `C2_l` | 与 C2 为匹配对（shared_node），尺寸必须绑定 |
| `C3_w` | `C2_w` | 与 C2 为匹配对（shared_node），尺寸必须绑定 |
| `C3_m` | `C2_m` | 与 C2 为匹配对（shared_node），尺寸必须绑定 |
| `NM12_l` | `NM2_l` | 电流镜 CM1 的镜像管，沟道长度须与参考管 NM2 一致 |
| `NM8_l` | `NM2_l` | 电流镜 CM1 的镜像管，沟道长度须与参考管 NM2 一致 |
| `NM3_l` | `NM2_l` | 电流镜 CM1 的镜像管，沟道长度须与参考管 NM2 一致 |
| `PM6_l` | `PM5_l` | 电流镜 CM2 的镜像管，沟道长度须与参考管 PM5 一致 |
| `PM4_l` | `PM0_l` | 电流镜 CM3 的镜像管，沟道长度须与参考管 PM0 一致 |
| `PM1_l` | `PM0_l` | 电流镜 CM3 的镜像管，沟道长度须与参考管 PM0 一致 |

## 4. 需要人工确认的点

- ⚠️ 候选差分对 PM11/PM7（源极同网 VDDA，栅极 net8/net0）未接输入端口，不判为 input_pair；若为次级的差分单元请在报告中说明
- ⚠️ 候选差分对 PM12/PM8（源极同网 net13，栅极 outaverage/VCM）未接输入端口，不判为 input_pair；若为次级的差分单元请在报告中说明
- ⚠️ R6 两端接同一网（net12）：按『真实器件』保留变量，请在报告说明其作用
- ⚠️ R5 两端接同一网（net11）：按『真实器件』保留变量，请在报告说明其作用
- ⚠️ C5 两端接同一网（net12）：按『真实器件』保留变量，请在报告说明其作用
- ⚠️ C4 两端接同一网（net11）：按『真实器件』保留变量，请在报告说明其作用
