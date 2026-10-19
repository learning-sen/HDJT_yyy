# 模块 2 报告：拓扑模块识别与参数约减

> 由 `python -m src.topology` 自动生成，可直接引用进技术报告。

## 1. 输入

| 项 | 值 |
|---|---|
| 网表 | `OPA_loopgain.netlist` |
| 子电路 | `OPA` |
| 对外端口 | IREF, GNDA, SUB, VCM, VDDA, VINN, VINP, VOUTN, VOUTP |
| 器件总数 | 59（MOS 29） |
| 自动分段折叠 | 2 条链 → 逻辑器件 41 个 |

## 2. 识别到的拓扑模块

| ID | 类型 | 器件 | 置信度 |
|---|---|---|---|
| CM1 | current_mirror | NM2, NM13, NM12, NM9, NM8, NM7, NM6, NM3 | 3 |
| CM2 | current_mirror | PM5, PM6 | 3 |
| CM3 | current_mirror | PM0, PM4, PM1 | 3 |
| CM4 | current_mirror | PM3, PM2 | 2 |
| IP1 | input_pair | PM12, PM8 | 2 |
| IP2 | input_pair | PM10, PM9 | 3 |
| AL1 | active_load | NM7, NM6 | 2 |
| MP1 | matching_pair | NM15, NM14 | 3 |
| MP2 | matching_pair | PM11, PM7 | 3 |
| MP3 | matching_pair | PM3, PM2 | 3 |
| MP4 | matching_pair | R6, R5 | 3 |
| MP5 | matching_pair | R1, R2 | 3 |
| MP6 | matching_pair | C5, C4 | 3 |
| MP7 | matching_pair | C11, C0 | 3 |
| MP8 | matching_pair | C3, C2 | 3 |
| MP9 | matching_pair | R0, R3 | 3 |
| MP10 | matching_pair | NM9, NM8 | 3 |
| MP11 | matching_pair | NM7, NM6 | 3 |
| MP12 | matching_pair | NM4, NM5 | 3 |
| MP13 | matching_pair | NM12, NM13 | 2 |
| DM1 | dummy | R6 | 3 |
| DM2 | dummy | R5 | 3 |
| DM3 | dummy | C5 | 3 |
| DM4 | dummy | C4 | 3 |
| CMFB1 | cmfb | NM11, PM12, PM8, PM6, PM3, PM2, C3, C2… | 3 |
| BIAS1 | bias_branch | NM0, NM1, NM10, NM11, NM14, NM15, NM4, NM5… | 2 |
| SEG1 | segmented_device | R0, R0_2_res_gen, R0_3_res_gen, R0_4_res_gen, R0_5_res_gen, R0_6_res_gen, R0_7_res_gen, R0_8_res_gen… | 3 |
| SEG2 | segmented_device | R3, R3_2_res_gen, R3_3_res_gen, R3_4_res_gen, R3_5_res_gen, R3_6_res_gen, R3_7_res_gen, R3_8_res_gen… | 3 |

### 2.1 判定依据（为何识别为该模块）

- **CM1（current_mirror）**：同型(nmos)；栅极同接 net53；源极同接 GNDA；NM2 栅漏短接 -> 参考管
- **CM2（current_mirror）**：同型(pmos)；栅极同接 net5；源极同接 VDDA；PM5 栅漏短接 -> 参考管
- **CM3（current_mirror）**：同型(pmos)；栅极同接 net6；源极同接 VDDA；PM0 栅漏短接 -> 参考管
- **CM4（current_mirror）**：同型(pmos)；栅极同接 vcmfb；源极同接 VDDA；组内无二极管连接，取 PM3 为参考管
- **IP1（input_pair）**：同型(pmos)同尺寸(同 model p_mos_a / 同 multi 6)；源极同接 net13（尾节点）；栅极分别接 outaverage / VCM（非输入端口，判为辅助差分对）；漏极分别接 net52 / net3；-> 差分两臂必须尺寸一致，做尺寸绑定
- **IP2（input_pair）**：同型(pmos)同尺寸(同 model p_mos_a / 同 multi 2)；源极同接 net37（尾节点）；栅极分别接 VINN / VINP（差分输入端口）；漏极分别接 net44 / net4；-> 差分两臂必须尺寸一致，做尺寸绑定
- **AL1（active_load）**：电流镜 CM1 的器件；漏极接在输入对管漏极节点 ['net4', 'net44'] 上；以有源器件替代电阻作负载，提高增益
- **MP1（matching_pair）**：同 model(n_mos_a)、同 multi(1)；对称两臂（栅极同接 IREF、源极同接 VOUTN，漏极分别接 VOUTN / VOUTP）；在差分端口对换下互为镜像（WL 颜色细化 + 全局自同构校验通过）；-> 版图匹配要求尺寸绑定，只保留一个基准变量
- **MP2（matching_pair）**：同 model(p_mos_a)、同 multi(4)；差分两臂（栅极分别接 net8 / net0，尾节点 VDDA）；在差分端口对换下互为镜像（WL 颜色细化 + 全局自同构校验通过）；-> 版图匹配要求尺寸绑定，只保留一个基准变量
- **MP3（matching_pair）**：同 model(p_mos_a)、同 multi(40)；对称两臂（栅极同接 vcmfb、源极同接 VDDA，漏极分别接 net8 / net0）；在差分端口对换下互为镜像（WL 颜色细化 + 全局自同构校验通过）；-> 版图匹配要求尺寸绑定，只保留一个基准变量
- **MP4（matching_pair）**：同 model(res_n_poly)、同 multi(1)；两端器件对称臂（端子 ['net12', 'net12'] / ['net11', 'net11']）；在差分端口对换下互为镜像（WL 颜色细化 + 全局自同构校验通过）；-> 版图匹配要求尺寸绑定，只保留一个基准变量
- **MP5（matching_pair）**：同 model(res_p_poly)、同 multi(1)；两端器件对称臂（端子 ['net0', 'net17'] / ['net8', 'net7']）；在差分端口对换下互为镜像（WL 颜色细化 + 全局自同构校验通过）；-> 版图匹配要求尺寸绑定，只保留一个基准变量
- **MP6（matching_pair）**：同 model(cap_mim)、同 multi(1)；两端器件对称臂（端子 ['net12', 'net12'] / ['net11', 'net11']）；在差分端口对换下互为镜像（WL 颜色细化 + 全局自同构校验通过）；-> 版图匹配要求尺寸绑定，只保留一个基准变量
- **MP7（matching_pair）**：同 model(cap_mim)、同 multi(2)；两端器件对称臂（端子 ['net17', 'VOUTP'] / ['net7', 'VOUTN']）；在差分端口对换下互为镜像（WL 颜色细化 + 全局自同构校验通过）；-> 版图匹配要求尺寸绑定，只保留一个基准变量
- **MP8（matching_pair）**：同 model(cap_mim)、同 multi(1)；两端器件对称臂（端子 ['VOUTN', 'outaverage'] / ['outaverage', 'VOUTP']）；在差分端口对换下互为镜像（WL 颜色细化 + 全局自同构校验通过）；-> 版图匹配要求尺寸绑定，只保留一个基准变量
- **MP9（matching_pair）**：同 model(res_p_poly)、同 multi(1)；两端器件对称臂（端子 ['VOUTP', 'outaverage'] / ['VOUTN', 'outaverage']）；在差分端口对换下互为镜像（WL 颜色细化 + 全局自同构校验通过）；-> 版图匹配要求尺寸绑定，只保留一个基准变量
- **MP10（matching_pair）**：同 model(n_mos_a)、同 multi(4)；对称两臂（栅极同接 net53、源极同接 GNDA，漏极分别接 VOUTN / VOUTP）；在差分端口对换下互为镜像（WL 颜色细化 + 全局自同构校验通过）；-> 版图匹配要求尺寸绑定，只保留一个基准变量
- **MP11（matching_pair）**：同 model(n_mos_a)、同 multi(4)；对称两臂（栅极同接 net53、源极同接 GNDA，漏极分别接 net44 / net4）；在差分端口对换下互为镜像（WL 颜色细化 + 全局自同构校验通过）；-> 版图匹配要求尺寸绑定，只保留一个基准变量
- **MP12（matching_pair）**：同 model(n_mos_a)、同 multi(4)；对称两臂（栅极同接 IREF、源极同接 net4，漏极分别接 net0 / net8）；在差分端口对换下互为镜像（WL 颜色细化 + 全局自同构校验通过）；-> 版图匹配要求尺寸绑定，只保留一个基准变量
- **MP13（matching_pair）**：同 model(n_mos_a)、同 multi(4)、同一镜像支路（源极同接 GNDA、栅极同接 net53，共 2 只）；由连接结构（图分析）判为匹配结构 -> 只绑 L（镜像比由 w/m 表达），只保留一个基准变量
- **DM1（dummy）**：两端器件 R6 的两个端子都接在同一网 net12：两端电压恒为 0 -> 电流恒为 0 -> 对任何仿真结果都没有影响；所在连通分量不接触任何对外端口或电源地网，与主电路无电气连接 -> 不参与电路功能，剔除其全部优化变量（器件保留在约减后网表中，尺寸按原值固定）
- **DM2（dummy）**：两端器件 R5 的两个端子都接在同一网 net11：两端电压恒为 0 -> 电流恒为 0 -> 对任何仿真结果都没有影响；所在连通分量不接触任何对外端口或电源地网，与主电路无电气连接 -> 不参与电路功能，剔除其全部优化变量（器件保留在约减后网表中，尺寸按原值固定）
- **DM3（dummy）**：两端器件 C5 的两个端子都接在同一网 net12：两端电压恒为 0 -> 电流恒为 0 -> 对任何仿真结果都没有影响；所在连通分量不接触任何对外端口或电源地网，与主电路无电气连接 -> 不参与电路功能，剔除其全部优化变量（器件保留在约减后网表中，尺寸按原值固定）
- **DM4（dummy）**：两端器件 C4 的两个端子都接在同一网 net11：两端电压恒为 0 -> 电流恒为 0 -> 对任何仿真结果都没有影响；所在连通分量不接触任何对外端口或电源地网，与主电路无电气连接 -> 不参与电路功能，剔除其全部优化变量（器件保留在约减后网表中，尺寸按原值固定）
- **CMFB1（cmfb）**：检测到共模相关节点: ['VCM', 'outaverage', 'vcmfb']；共模取样分压网络 R0 / R3：分别从输出 VOUTP 与 VOUTN 取样，在 outaverage 取平均；取样节点 outaverage 送入 PM12 的栅极；涉及器件 10 个：['NM11', 'PM12', 'PM8', 'PM6', 'PM3', 'PM2', 'C3', 'C2', 'R0', 'R3']；作用：稳定全差分输出的共模电平
- **BIAS1（bias_branch）**：偏置节点 ['IREF', 'VCM', 'vcmfb'] 直接驱动 11 个器件（栅极或独立源），构成参考偏置支路
- **SEG1（segmented_device）**：器件 R0 被自动拆分为 9 段串联（后缀 _<n>_res_gen）；参数完全相同（同一物理器件的分段实现）；-> 应视为**一个**器件，只保留一组变量
- **SEG2（segmented_device）**：器件 R3 被自动拆分为 9 段串联（后缀 _<n>_res_gen）；参数完全相同（同一物理器件的分段实现）；-> 应视为**一个**器件，只保留一组变量

## 3. 参数约减

| 阶段 | 变量数 |
|---|---|
| 原始网表（器件级，未折叠分段） | 141 |
| 折叠自动分段后 | 105 |
| **约减后** | **61** |
| 约减比例 | **41.9%** |

### 3.1 变量统计

- 按参数：l=15, w=21, m=21, segL=2, segW=2
- 按器件类型：cap=2, mos=55, res=4
- 整数变量 21 个（m / seg，优化时需取整），连续变量 40 个
- 尺寸绑定组 17 组

### 3.2 约减决策链（为何删除/绑定某变量）

- **remove_dummy** → 剔除 4 个器件的 6 个变量（器件保留在约减后网表中，尺寸按原值固定）
  - 理由：两端同网（电气惰性）/ 与主电路无电气连接（孤立）/ 全端子同网或悬空 —— 这些器件的尺寸不可能影响任何仿真结果，属纯冗余优化变量
- **bind_matching_group** → 绑定 13 组、删除 31 个冗余变量
  - 理由：匹配器件必须尺寸绑定：保留一个基准变量，其余由匹配规则导出。对换对称组绑全部尺寸；同支路镜像组只绑 L（镜像比由 w/m 表达）
- **bind_current_mirror** → 处理 4 个电流镜，删除 7 个冗余 l 变量
  - 理由：电流镜镜像管沟道长度必须与参考管一致；镜像比用 w/m 比例表达，所以只绑 L，不绑 w/m
- **collapse_segmented** → 变量只保留 1 组（原 10 个器件各自一组）
  - 理由：自动分段器件 R0 由 1 个基准器件 + 9 个自动生成段（共 10 段串联）组成，是同一物理器件，全链共用一组变量
- **collapse_segmented** → 变量只保留 1 组（原 10 个器件各自一组）
  - 理由：自动分段器件 R3 由 1 个基准器件 + 9 个自动生成段（共 10 段串联）组成，是同一物理器件，全链共用一组变量
- **render_reduced_netlist** → 约减后网表含 41 个器件（约减前逻辑器件 41 个，无丢失）
  - 理由：约减的是**变量**不是器件：全部器件保留（分段链折叠为基准器件），被绑定的参数写成基准变量名，字面常数/惰性器件按原值写出并加注释

### 3.3 冗余变量映射（删除的变量指向哪个基准变量）

| 被删除变量 | 映射到 | 理由 |
|---|---|---|
| `PM8_l` | `PM12_l` | IP1：与基准器件 PM12 尺寸绑定（auxiliary） |
| `PM8_fw` | `PM12_fw` | IP1：与基准器件 PM12 尺寸绑定（auxiliary） |
| `PM8_m` | `PM12_m` | IP1：与基准器件 PM12 尺寸绑定（auxiliary） |
| `PM9_l` | `PM10_l` | IP2：与基准器件 PM10 尺寸绑定（main） |
| `PM9_fw` | `PM10_fw` | IP2：与基准器件 PM10 尺寸绑定（main） |
| `PM9_m` | `PM10_m` | IP2：与基准器件 PM10 尺寸绑定（main） |
| `NM14_l` | `NM15_l` | MP1：与基准器件 NM15 尺寸绑定（same_branch） |
| `NM14_fw` | `NM15_fw` | MP1：与基准器件 NM15 尺寸绑定（same_branch） |
| `NM14_m` | `NM15_m` | MP1：与基准器件 NM15 尺寸绑定（same_branch） |
| `PM7_l` | `PM11_l` | MP2：与基准器件 PM11 尺寸绑定（differential_arms） |
| `PM7_fw` | `PM11_fw` | MP2：与基准器件 PM11 尺寸绑定（differential_arms） |
| `PM7_m` | `PM11_m` | MP2：与基准器件 PM11 尺寸绑定（differential_arms） |
| `PM2_l` | `PM3_l` | MP3：与基准器件 PM3 尺寸绑定（same_branch） |
| `PM2_fw` | `PM3_fw` | MP3：与基准器件 PM3 尺寸绑定（same_branch） |
| `PM2_m` | `PM3_m` | MP3：与基准器件 PM3 尺寸绑定（same_branch） |
| `R2_segL` | `R1_segL` | MP5：与基准器件 R1 尺寸绑定（symmetric_arms） |
| `R2_segW` | `R1_segW` | MP5：与基准器件 R1 尺寸绑定（symmetric_arms） |
| `C0_l` | `C11_l` | MP7：与基准器件 C11 尺寸绑定（symmetric_arms） |
| `C2_l` | `C3_l` | MP8：与基准器件 C3 尺寸绑定（symmetric_arms） |
| `R3_segL` | `R0_segL` | MP9：与基准器件 R0 尺寸绑定（symmetric_arms） |
| `R3_segW` | `R0_segW` | MP9：与基准器件 R0 尺寸绑定（symmetric_arms） |
| `NM8_l` | `NM2_l` | MP10：与基准器件 NM9 尺寸绑定（same_branch） |
| `NM8_fw` | `NM9_fw` | MP10：与基准器件 NM9 尺寸绑定（same_branch） |
| `NM8_m` | `NM9_m` | MP10：与基准器件 NM9 尺寸绑定（same_branch） |
| `NM6_l` | `NM2_l` | MP11：与基准器件 NM7 尺寸绑定（same_branch） |
| `NM6_fw` | `NM7_fw` | MP11：与基准器件 NM7 尺寸绑定（same_branch） |
| `NM6_m` | `NM7_m` | MP11：与基准器件 NM7 尺寸绑定（same_branch） |
| `NM5_l` | `NM4_l` | MP12：与基准器件 NM4 尺寸绑定（same_branch） |
| `NM5_fw` | `NM4_fw` | MP12：与基准器件 NM4 尺寸绑定（same_branch） |
| `NM5_m` | `NM4_m` | MP12：与基准器件 NM4 尺寸绑定（same_branch） |
| `NM13_l` | `NM2_l` | MP13：与基准器件 NM12 尺寸绑定（same_branch） |
| `NM12_l` | `NM2_l` | 电流镜 CM1 的镜像管，沟道长度须与参考管 NM2 一致 |
| `NM9_l` | `NM2_l` | 电流镜 CM1 的镜像管，沟道长度须与参考管 NM2 一致 |
| `NM7_l` | `NM2_l` | 电流镜 CM1 的镜像管，沟道长度须与参考管 NM2 一致 |
| `NM3_l` | `NM2_l` | 电流镜 CM1 的镜像管，沟道长度须与参考管 NM2 一致 |
| `PM6_l` | `PM5_l` | 电流镜 CM2 的镜像管，沟道长度须与参考管 PM5 一致 |
| `PM4_l` | `PM0_l` | 电流镜 CM3 的镜像管，沟道长度须与参考管 PM0 一致 |
| `PM1_l` | `PM0_l` | 电流镜 CM3 的镜像管，沟道长度须与参考管 PM0 一致 |
