# 网表可读化：`OPA_loopgain.netlist`

> 由 `tools/netlist_readable.py` 自动生成。原网表里每个 MOS 后面跟着 10 行
> `+ad=... / +as=... / +nrd=...` 版图寄生参数续行，本视图把它们折叠成计数，
> 只保留真正有信息量的字段：**器件 / 端子 / 尺寸参数 / 所属功能模块**。

## 1. 一眼看懂

| 项 | 值 |
|---|---|
| 子电路 | `OPA` |
| 对外端口 | `IREF`, `GNDA`, `SUB`, `VCM`, `VDDA`, `VINN`, `VINP`, `VOUTN`, `VOUTP` |
| 原始器件数 | 59（MOS 29） |
| 折叠分段后逻辑器件 | 41（2 条分段链被折叠） |
| 优化变量（真变量） | 105 个；另有 12 个字面常数尺寸不计入 |
| 电气惰性/Dummy 器件 | `C4`, `C5`, `R5`, `R6` |
| testbench 器件 | 12 个（在 subckt 之外，见文末） |

**信号通路**：差分输入对 `PM10`/`PM9`（pmos，尾节点 `net37`），漏极分别接有源负载 `NM7`, `NM6`。
输出节点经共模取样网络回到共模反馈（见 `CMFB1`）。

**偏置通路**：4 组电流镜 —— CM1（参考管 `NM2`，镜像管 `NM13`, `NM12`, `NM9`, `NM8`, `NM7`, `NM6`, `NM3`）；CM2（参考管 `PM5`，镜像管 `PM6`）；CM3（参考管 `PM0`，镜像管 `PM4`, `PM1`）；CM4（参考管 `PM3`，镜像管 `PM2`）。

## 2. 器件总表（一行一个器件）

说明：`l/w/m` 列里标 **（变量）** 的是待优化变量，标 **（固定）** 的是字面常数；
`续行` 列是该器件被折叠掉的 `+...` 版图参数行数；`模块` 列见第 3 节。
**电阻/电容是两端器件**，表中「漏」列=端点1、「源」列=端点2（两端无极性）。

| 器件 | 类型 | 极性 | 模型 | 漏 | 栅 | 源 | 衬底 | multi | l | w/fw | m | segL | segW | 变量/固定 | 续行 | 模块 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `NM0` | mos | nmos | n_mos_a | IREF | IREF | net53 | SUB | 1 | NM0_l（变量） | NM0_fw（变量） | NM0_m（变量） |  |  | 3/0 | 9 | BIAS1 |
| `NM1` | mos | nmos | n_mos_a | net6 | IREF | net32 | SUB | 1 | NM1_l（变量） | NM1_fw（变量） | NM1_m（变量） |  |  | 3/0 | 9 | BIAS1 |
| `NM2` | mos | nmos | n_mos_a | net53 | net53 | GNDA | SUB | 1 | NM2_l（变量） | NM2_fw（变量） | NM2_m（变量） |  |  | 3/0 | 9 | CM1 |
| `NM3` | mos | nmos | n_mos_a | net32 | net53 | GNDA | SUB | 1 | NM3_l（变量） | NM3_fw（变量） | NM3_m（变量） |  |  | 3/0 | 9 | CM1 |
| `NM4` | mos | nmos | n_mos_a | net0 | IREF | net4 | SUB | 4 | NM4_l（变量） | NM4_fw（变量） | NM4_m（变量） |  |  | 3/0 | 9 | MP12,BIAS1 |
| `NM5` | mos | nmos | n_mos_a | net8 | IREF | net44 | SUB | 4 | NM5_l（变量） | NM5_fw（变量） | NM5_m（变量） |  |  | 3/0 | 9 | MP12,BIAS1 |
| `NM6` | mos | nmos | n_mos_a | net4 | net53 | GNDA | SUB | 4 | NM6_l（变量） | NM6_fw（变量） | NM6_m（变量） |  |  | 3/0 | 9 | CM1,AL1,MP11 |
| `NM7` | mos | nmos | n_mos_a | net44 | net53 | GNDA | SUB | 4 | NM7_l（变量） | NM7_fw（变量） | NM7_m（变量） |  |  | 3/0 | 9 | CM1,AL1,MP11 |
| `NM8` | mos | nmos | n_mos_a | VOUTP | net53 | GNDA | GNDA | 4 | NM8_l（变量） | NM8_fw（变量） | NM8_m（变量） |  |  | 3/0 | 9 | CM1,MP10 |
| `NM9` | mos | nmos | n_mos_a | VOUTN | net53 | GNDA | GNDA | 4 | NM9_l（变量） | NM9_fw（变量） | NM9_m（变量） |  |  | 3/0 | 9 | CM1,MP10 |
| `NM10` | mos | nmos | n_mos_a | net5 | IREF | net3 | SUB | 1 | NM10_l（变量） | NM10_fw（变量） | NM10_m（变量） |  |  | 3/0 | 9 | BIAS1 |
| `NM11` | mos | nmos | n_mos_a | vcmfb | IREF | net52 | SUB | 1 | NM11_l（变量） | NM11_fw（变量） | NM11_m（变量） |  |  | 3/0 | 9 | CMFB1,BIAS1 |
| `NM12` | mos | nmos | n_mos_a | net3 | net53 | GNDA | SUB | 4 | NM12_l（变量） | NM12_fw（变量） | NM12_m（变量） |  |  | 3/0 | 9 | CM1,MP13 |
| `NM13` | mos | nmos | n_mos_a | net52 | net53 | GNDA | SUB | 4 | NM13_l（变量） | NM13_fw（变量） | NM13_m（变量） |  |  | 3/0 | 9 | CM1,MP13 |
| `NM14` | mos | nmos | n_mos_a | VOUTP | IREF | VOUTP | SUB | 1 | NM14_l（变量） | NM14_fw（变量） | NM14_m（变量） |  |  | 3/0 | 9 | MP1,BIAS1 |
| `NM15` | mos | nmos | n_mos_a | VOUTN | IREF | VOUTN | SUB | 1 | NM15_l（变量） | NM15_fw（变量） | NM15_m（变量） |  |  | 3/0 | 9 | MP1,BIAS1 |
| `PM0` | mos | pmos | p_mos_a | net6 | net6 | VDDA | VDDA | 1 | PM0_l（变量） | PM0_fw（变量） | PM0_m（变量） |  |  | 3/0 | 9 | CM3 |
| `PM1` | mos | pmos | p_mos_a | net37 | net6 | VDDA | VDDA | 8 | PM1_l（变量） | PM1_fw（变量） | PM1_m（变量） |  |  | 3/0 | 9 | CM3 |
| `PM2` | mos | pmos | p_mos_a | net0 | vcmfb | VDDA | VDDA | 40 | PM2_l（变量） | PM2_fw（变量） | PM2_m（变量） |  |  | 3/0 | 9 | CM4,MP3,CMFB1,BIAS1 |
| `PM3` | mos | pmos | p_mos_a | net8 | vcmfb | VDDA | VDDA | 40 | PM3_l（变量） | PM3_fw（变量） | PM3_m（变量） |  |  | 3/0 | 9 | CM4,MP3,CMFB1,BIAS1 |
| `PM4` | mos | pmos | p_mos_a | net13 | net6 | VDDA | VDDA | 4 | PM4_l（变量） | PM4_fw（变量） | PM4_m（变量） |  |  | 3/0 | 9 | CM3 |
| `PM5` | mos | pmos | p_mos_a | net5 | net5 | VDDA | VDDA | 1 | PM5_l（变量） | PM5_fw（变量） | PM5_m（变量） |  |  | 3/0 | 9 | CM2 |
| `PM6` | mos | pmos | p_mos_a | vcmfb | net5 | VDDA | VDDA | 1 | PM6_l（变量） | PM6_fw（变量） | PM6_m（变量） |  |  | 3/0 | 9 | CM2,CMFB1 |
| `PM7` | mos | pmos | p_mos_a | VOUTP | net0 | VDDA | VDDA | 4 | PM7_l（变量） | PM7_fw（变量） | PM7_m（变量） |  |  | 3/0 | 9 | MP2 |
| `PM8` | mos | pmos | p_mos_a | net3 | VCM | net13 | VDDA | 6 | PM8_l（变量） | PM8_fw（变量） | PM8_m（变量） |  |  | 3/0 | 9 | IP1,CMFB1,BIAS1 |
| `PM9` | mos | pmos | p_mos_a | net4 | VINP | net37 | VDDA | 2 | PM9_l（变量） | PM9_fw（变量） | PM9_m（变量） |  |  | 3/0 | 9 | IP2 |
| `PM10` | mos | pmos | p_mos_a | net44 | VINN | net37 | VDDA | 2 | PM10_l（变量） | PM10_fw（变量） | PM10_m（变量） |  |  | 3/0 | 9 | IP2 |
| `PM11` | mos | pmos | p_mos_a | VOUTN | net8 | VDDA | VDDA | 4 | PM11_l（变量） | PM11_fw（变量） | PM11_m（变量） |  |  | 3/0 | 9 | MP2 |
| `PM12` | mos | pmos | p_mos_a | net52 | outaverage | net13 | VDDA | 6 | PM12_l（变量） | PM12_fw（变量） | PM12_m（变量） |  |  | 3/0 | 9 | IP1,CMFB1 |
| `C0` | cap | - | cap_mim | net7 |  | VOUTN |  | 2 | C0_l（变量） | 30u（固定） | 2（固定） |  |  | 1/2 |  | MP7 |
| `C2` | cap | - | cap_mim | outaverage |  | VOUTP |  | 1 | C2_l（变量） | 20u（固定） | 1（固定） |  |  | 1/2 |  | MP8,CMFB1 |
| `C3` | cap | - | cap_mim | VOUTN |  | outaverage |  | 1 | C3_l（变量） | 20u（固定） | 1（固定） |  |  | 1/2 |  | MP8,CMFB1 |
| `C4` | cap | - | cap_mim | net11 |  | net11 |  | 1 | C4_l（变量） | 10u（固定） | 1（固定） |  |  | 1/2 |  | MP6,DM4 |
| `C5` | cap | - | cap_mim | net12 |  | net12 |  | 1 | C5_l（变量） | 10u（固定） | 1（固定） |  |  | 1/2 |  | MP6,DM3 |
| `C11` | cap | - | cap_mim | net17 |  | VOUTP |  | 2 | C11_l（变量） | 30u（固定） | 2（固定） |  |  | 1/2 |  | MP7 |
| `R0` | res | - | res_p_poly | VOUTP |  | outaverage |  | 1 |  |  |  | R0_segL（变量） | R0_segW（变量） | 2/0 |  | MP9,CMFB1,SEG1 |
| `R1` | res | - | res_p_poly | net0 |  | net17 |  | 1 |  |  |  | R1_segL（变量） | R1_segW（变量） | 2/0 |  | MP5 |
| `R2` | res | - | res_p_poly | net8 |  | net7 |  | 1 |  |  |  | R2_segL（变量） | R2_segW（变量） | 2/0 |  | MP5 |
| `R3` | res | - | res_p_poly | VOUTN |  | outaverage |  | 1 |  |  |  | R3_segL（变量） | R3_segW（变量） | 2/0 |  | MP9,CMFB1,SEG2 |
| `R5` | res | - | res_n_poly | net11 |  | net11 |  | 1 |  |  |  | R5_segL（变量） | R5_segW（变量） | 2/0 |  | MP4,DM2 |
| `R6` | res | - | res_n_poly | net12 |  | net12 |  | 1 |  |  |  | R6_segL（变量） | R6_segW（变量） | 2/0 |  | MP4,DM1 |

## 3. 按功能模块看

| 模块 | 类型 | 器件 |
|---|---|---|
| `AL1` | active_load | `NM7`, `NM6` |
| `BIAS1` | bias_branch | `NM0`, `NM1`, `NM10`, `NM11`, `NM14`, `NM15`, `NM4`, `NM5`, `PM2`, `PM3`, `PM8` |
| `CMFB1` | cmfb | `NM11`, `PM12`, `PM8`, `PM6`, `PM3`, `PM2`, `C3`, `C2`, `R0`, `R3` |
| `CM1` | current_mirror | `NM2`, `NM13`, `NM12`, `NM9`, `NM8`, `NM7`, `NM6`, `NM3` |
| `CM2` | current_mirror | `PM5`, `PM6` |
| `CM3` | current_mirror | `PM0`, `PM4`, `PM1` |
| `CM4` | current_mirror | `PM3`, `PM2` |
| `DM1` | dummy | `R6` |
| `DM2` | dummy | `R5` |
| `DM3` | dummy | `C5` |
| `DM4` | dummy | `C4` |
| `IP1` | input_pair | `PM12`, `PM8` |
| `IP2` | input_pair | `PM10`, `PM9` |
| `MP1` | matching_pair | `NM15`, `NM14` |
| `MP2` | matching_pair | `PM11`, `PM7` |
| `MP3` | matching_pair | `PM3`, `PM2` |
| `MP4` | matching_pair | `R6`, `R5` |
| `MP5` | matching_pair | `R1`, `R2` |
| `MP6` | matching_pair | `C5`, `C4` |
| `MP7` | matching_pair | `C11`, `C0` |
| `MP8` | matching_pair | `C3`, `C2` |
| `MP9` | matching_pair | `R0`, `R3` |
| `MP10` | matching_pair | `NM9`, `NM8` |
| `MP11` | matching_pair | `NM7`, `NM6` |
| `MP12` | matching_pair | `NM4`, `NM5` |
| `MP13` | matching_pair | `NM12`, `NM13` |
| `SEG1` | segmented_device | `R0`, `R0_2_res_gen`, `R0_3_res_gen`, `R0_4_res_gen`, `R0_5_res_gen`, `R0_6_res_gen`, `R0_7_res_gen`, `R0_8_res_gen`, `R0_9_res_gen`, `R0_10_res_gen` |
| `SEG2` | segmented_device | `R3`, `R3_2_res_gen`, `R3_3_res_gen`, `R3_4_res_gen`, `R3_5_res_gen`, `R3_6_res_gen`, `R3_7_res_gen`, `R3_8_res_gen`, `R3_9_res_gen`, `R3_10_res_gen` |

> 每个模块的**判定依据**（为何这样识别）保存在 `topology_analysis.json` 的 `modules[].evidence`。

## 4. 被折叠的自动分段器件

Cadence/Aether 会把一个长电阻拆成多段串联，网表里表现为 `R0` + `R0_2_res_gen` …。
它们是**同一个物理器件**，本视图已折叠成一行，只保留一组变量。

| 基准器件 | 链上段数 | 链上器件（含基准） |
|---|---|---|
| `R0` | 10 | `R0`, `R0_2_res_gen`, `R0_3_res_gen`, `R0_4_res_gen`, `R0_5_res_gen`, `R0_6_res_gen`, `R0_7_res_gen`, `R0_8_res_gen`, `R0_9_res_gen`, `R0_10_res_gen` |
| `R3` | 10 | `R3`, `R3_2_res_gen`, `R3_3_res_gen`, `R3_4_res_gen`, `R3_5_res_gen`, `R3_6_res_gen`, `R3_7_res_gen`, `R3_8_res_gen`, `R3_9_res_gen`, `R3_10_res_gen` |

## 5. 网表连接清单（网 → 器件.端子）

| 网名 | 连接的器件端子 |
|---|---|
| `GNDA` | NM2.s, NM3.s, NM6.s, NM7.s, NM8.b, NM8.s, NM9.b, NM9.s, NM12.s, NM13.s |
| `IREF` | NM0.d, NM0.g, NM1.g, NM4.g, NM5.g, NM10.g, NM11.g, NM14.g, NM15.g |
| `net0` | NM4.d, PM2.d, PM7.g, R1.d |
| `net3` | NM10.s, NM12.d, PM8.d |
| `net4` | NM4.s, NM6.d, PM9.d |
| `net5` | NM10.d, PM5.d, PM5.g, PM6.g |
| `net6` | NM1.d, PM0.d, PM0.g, PM1.g, PM4.g |
| `net7` | C0.d, R2.s |
| `net8` | NM5.d, PM3.d, PM11.g, R2.d |
| `net11` | C4.d, C4.s, R5.d, R5.s |
| `net12` | C5.d, C5.s, R6.d, R6.s |
| `net13` | PM4.d, PM8.s, PM12.s |
| `net17` | C11.d, R1.s |
| `net32` | NM1.s, NM3.d |
| `net37` | PM1.d, PM9.s, PM10.s |
| `net44` | NM5.s, NM7.d, PM10.d |
| `net52` | NM11.s, NM13.d, PM12.d |
| `net53` | NM0.s, NM2.d, NM2.g, NM3.g, NM6.g, NM7.g, NM8.g, NM9.g, NM12.g, NM13.g |
| `outaverage` | C2.d, C3.s, PM12.g, R0.s, R3.s |
| `SUB` | NM0.b, NM1.b, NM2.b, NM3.b, NM4.b, NM5.b, NM6.b, NM7.b, NM10.b, NM11.b, NM12.b, NM13.b, NM14.b, NM15.b |
| `VCM` | PM8.g |
| `vcmfb` | NM11.d, PM2.g, PM3.g, PM6.d |
| `VDDA` | PM0.b, PM0.s, PM1.b, PM1.s, PM2.b, PM2.s, PM3.b, PM3.s, PM4.b, PM4.s, PM5.b, PM5.s, PM6.b, PM6.s, PM7.b, PM7.s, PM8.b, PM9.b, PM10.b, PM11.b, PM11.s, PM12.b |
| `VINN` | PM10.g |
| `VINP` | PM9.g |
| `VOUTN` | C0.s, C3.d, NM9.d, NM15.d, NM15.s, PM11.d, R3.d |
| `VOUTP` | C2.s, C11.s, NM8.d, NM14.d, NM14.s, PM7.d, R0.d |

## 6. subckt 之外的 testbench 器件

| 器件 | 类型 | 端子 | 参数 |
|---|---|---|---|
| `VV0` | vsrc | GND 0 | dc=0 type=dc |
| `VV_P` | vsrc | VDD 0 | dc=vdd type=dc |
| `VV3` | vsrc | net1 0 | dc=vdd/2 type=dc |
| `VV1` | vsrc | SUB 0 | dc=0 type=dc |
| `E0` | vcvs | net1 vin_n net0 0 | gain=0.5 |
| `E2` | vcvs | vin_p net1 net0 0 | gain=0.5 |
| `I0` | isrc | IREF GND SUB net1 net2 vin_n vin_p vout_n vout_p |  |
| `RR0` | res | net2 VDD | r=10m |
| `II12` | isrc | VDD IREF | dc=I_BIAS type=dc |
| `CC2` | cap | 0 vout_p | c=100f |
| `CC0` | cap | 0 vout_n | c=100f |
| `V5` | vsrc | net0 0 | mag=1 phase=0 type=sine sinedc=0 ampl=0 |
