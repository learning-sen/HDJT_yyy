# 提交物索引（Submission）

> 按赛题 6.2「输出内容」六项组织。**模块一~三已完成并可交付，模块四代码已就绪、待服务器验证。**
> 截止：2026-10-19 24:00

---

## 一、目录 → 赛题 6.2 对应

| 目录 | 对应赛题项 | 状态 |
|---|---|---|
| `01_Spec解析_输出1` | 6.2 输出 1：自然语言 → 结构化 Spec（JSON） | ✅ |
| `02_拓扑识别与参数约减_输出2` | 6.2 输出 2：模块识别依据、约减后变量数、约减后网表 | ✅ |
| `03_变量清单与带变量电路图_输出3` | 6.2 输出 3：变量清单 CSV + **带变量 schematic** | 🟡 CSV ✅ / schematic ⏳ 模块四 |
| `04_最优尺寸反标_输出4` | 6.2 输出 4：`schematic_var_best` | 🟡 反标输入 ✅ / 反标电路图 ⏳ 模块四 |
| `05_全PVT仿真验证_输出5` | 6.2 输出 5：全 PVT 仿真结果与达标情况 | ✅ |
| `06_代码与算法性能_输出6` | 6.2 输出 6：运行次数 / 时间 / 内存 | ✅ |
| `07_源代码与提交包` | 6.2 源代码：模块 1/2/3 源码 + `eda_2026_case_1.tar.gz` | ✅ |
| `08_模块四_待补` | 模块四 5 个脚本 + `schematic_var` / `schematic_var_best` | 🟡 代码已就绪，待服务器验证 |

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

## 三、还缺什么

| # | 缺项 | 阻塞 | 补法 |
|---|---|---|---|
| 1 | `OPA/schematic_var`（带变量电路图） | 需在服务器跑参数化脚本 | `bash module4/run_auto.sh --params ./m4_params` |
| 2 | `OPA/schematic_var_best`（反标电路图） | 同上 | `bash module4/run_auto.sh --full <sizes> ./m4_out` |
| 3 | 技术报告（Doc + PDF ≤80 页） | — | 待撰写 |
| 4 | 汇报 PPT（≤20 页） | — | 待制作 |
| 5 | 演示视频（≤5 min MP4） | — | 待录制 |

---

## 四、复现（模块一~三）

```bash
# 模块一 / 二（Windows + .venv）
py -3.12 -m venv .venv && & .\.venv\Scripts\Activate.ps1
python -m pip install -r Submission/07_源代码与提交包/requirements.txt
python module1/agent/agent.py          # Spec 解析
python module2/agent/agent.py --no-llm # 拓扑识别与约减

# 模块三（九天服务器）
source ~/EDA_2026_Empyrean_lab_start/setup.bash
cd ~/EDA_2026_Empyrean_lab_start/EDA_2026_Empyrean_score
./run_score.sh eda_2026_case_1.tar.gz
```

---

## 五、说明

- `server/` 目录是赛方原件（`score.py`、`run_score.sh`、`eda_2025_case_1.py`、`case1_params_0.txt`），**未放入 Submission**：
  其中 `setup.bash` 含内网 license 地址，按 AGENTS.md 2.3 不得入库。
- `module3/修正说明.md` 记录了 P0-1 ~ P0-20 共 20 条修正及其证据，报告"技术难点与解决"章节可直接引用。
- 所有 md5 见 `MANIFEST.md5`。
