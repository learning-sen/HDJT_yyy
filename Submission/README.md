# 提交物索引（Submission）

> 按赛题 6.2 组织。**模块一~三已完成并可交付；模块四暂不纳入本目录。**
> 截止：2026-10-19 24:00

---

## 一、目录 → 赛题 6.2 对应

| 目录 | 对应赛题项 | 状态 |
|---|---|---|
| `01_Spec解析_输出1` | 6.2 输出 1：自然语言 → 结构化 Spec（JSON） | ✅ |
| `02_拓扑识别与参数约减_输出2` | 6.2 输出 2：模块识别依据、约减后变量数、约减后网表 | ✅ |
| `03_变量清单与带变量电路图_输出3` | 6.2 输出 3：变量清单 CSV | ✅（schematic 待模块四） |
| `04_最优尺寸反标_输出4` | 6.2 输出 4：最优尺寸清单 | ✅（`_var_best` 待模块四） |
| `05_全PVT仿真验证_输出5` | 6.2 输出 5：全 PVT 仿真结果与达标情况 | ✅ |
| `06_代码与算法性能_输出6` | 6.2 输出 6：运行次数 / 时间 / 内存 | ✅ |
| `07_评分提交包` | 平台评分用 `eda_2026_case_1.tar.gz` | ✅ |
| `edauser32_源代码` | 6.2（2）源代码（待打包上传九天平台） | ✅ 打包即用 |

---

## 二、核心结论（写报告可直接用）

| 项 | 数值 |
|---|---|
| 平台自动分 | **84.9584 / 100**（初始解 78.27） |
| PM | 61.20°（≥50 ✅） |
| GM | −10.84 dB（≤−10 ✅） |
| DC Gain | **45.85 dB**（≥40 ✅） |
| UGB | 13.84 MHz |
| I_OPA | 0.839 mA（≤3 ✅） |
| Area | 8361 µm² |
| 运行时间 | 6951 s（< 7200 s，时间分满 20） |
| 原始变量 → 约减后 | 105 → 47（约减 55.2%） |
| 识别功能模块 / 对称配对 / Dummy | 13 / 22 / 4 |

---

## 三、待办

| # | 事项 | 说明 |
|---|---|---|
| 1 | **上传源代码包到九天平台** | `edauser32_源代码.tar.gz` 已打好，按 `ftp资料上传说明.docx` 上传 |
| 2 | ~~技术报告（Doc+PDF ≤80 页）~~ | ✅ 已完成：`00_技术报告/技术报告_20261019.docx` + `.pdf`（19 页） |
| 3 | PPT（≤20 页）、视频（≤5 min） | 尚未产出；PPT 内容可从技术报告压缩 |

---

## 四、复现（模块一~三）

```bash
# 模块一 / 二（Windows + .venv）
py -3.12 -m venv .venv && & .\.venv\Scripts\Activate.ps1
python -m pip install -r Submission/edauser32_源代码/requirements.txt
python Submission/edauser32_源代码/module1_spec_agent/agent.py
python Submission/edauser32_源代码/module2_topology_agent/agent.py --no-llm

# 模块三（九天服务器）
source ~/EDA_2026_Empyrean_lab_start/setup.bash
cd ~/EDA_2026_Empyrean_lab_start/EDA_2026_Empyrean_score
./run_score.sh eda_2026_case_1.tar.gz
```

---

## 五、说明

- 本目录**只放交付给评委的内容**。
