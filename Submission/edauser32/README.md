# 源代码

> 对应赛题 6.2（2）：
> **智能体流程 Python 源码**（Spec 解析、拓扑模块识别与参数约减）
> + **九天平台源码**（参数化电路图标注、基于约束的多目标尺寸优化）。

## 快速验证（无需 API Key）

```bash
python -m pip install -r requirements.txt

# ① 拓扑识别与参数约减（纯确定性，离线可跑）
cd module2_topology_agent
python agent.py --no-llm                  # 用自带 sample/OPA_loopgain.netlist
# 期望：识别覆盖 59/59 个器件；参数约减 105 -> 47（55.2%）

# ② 智能体自检（离线）
cd ../module1_spec_agent
python agent.py self-test
# 期望：约束 4 条 / 目标 1 条 / 推理链 8 步

# ③ 需要大模型时（可选）
export DASHSCOPE_API_KEY=sk-xxx           # Windows: $env:DASHSCOPE_API_KEY="sk-xxx"
python agent.py spec --input sample/需求_全差分运放.txt --out spec_case1.json
```

> 包内 `module1_spec_agent/sample/` 与 `module2_topology_agent/sample/` 为赛题 Public 样例输入，
> 因此**解包即可运行**，不依赖仓库其它目录。
> `module3` / `module4` 需九天服务器环境（`source setup.bash` 后使用 `pythone`）。

## 目录

| 目录 | 覆盖的赛题功能 | 入口 |
|---|---|---|
| `module1_spec_agent/` | **Spec 解析**：自然语言 → 结构化 JSON | `python agent.py` |
| `module2_topology_agent/` | **拓扑模块识别与参数约减**：网表 → 模块/匹配/约减 | `python agent.py --no-llm` |
| `module3_size_optimization/` | **基于约束的多目标尺寸优化**（九天平台） | `pythone optimization.py …` |
| `module4_pyaether/` | **PyAether 辅助自动化流程脚本**（参数化 / 连接关系 / 仿真引擎 / 反标 / 高集成接口） | `bash run_auto.sh` |

## 各目录说明

### module1_spec_agent
- `agent.py` 智能体入口（ReAct 决策循环 + CoT 日志）
- `lib/spec_agent.py`、`lib/spec_parser.py`、`lib/spec_schema.py` Spec 解析与 schema 校验
- `lib/agent_runtime.py`、`lib/llm_client.py`、`lib/agent_config.py` 运行时 / LLM 客户端 / 配置
- `lib/netlist_parser.py`、`lib/topology*.py`、`lib/param_reduction.py` 确定性工具（供模块二复用）
- `system_prompt.txt` 系统提示词；`config.json` 模型与接口配置（Key 只写环境变量名）

运行：
```bash
python -m pip install -r requirements.txt
export DASHSCOPE_API_KEY=...        # Windows: $env:DASHSCOPE_API_KEY="..."
python agent.py
```

### module2_topology_agent
- `agent.py` 主流程（三段式：确定性解析 → 确定性识别 → 大模型写决策依据）
- `netlist_parser.py` Spectre 网表解析（续行 / 双种注释 / 派生参数）
- `topo_analyzer.py` 拓扑识别与参数约减（镜像置换 σ 传播 + 三条防伪守卫）
- `expand_params.py` 变量回写模板校验
- `system_prompt.txt`、`config.json`

运行：
```bash
python agent.py --no-llm       # 纯确定性，不调模型、不花钱
python agent.py                # 附带大模型生成的决策依据
```

### module3_size_optimization
- `optimization.py` 提交版（赛方原件 + 末尾补丁，覆盖策略层，不改原类）
- `eda_2025_case_1_upstream.py` 赛方原始模板（未改动，用于对照）
- `make_submission.py` 由模板生成提交版
- `selftest_submission.py` 打桩自测（8 项）

运行（九天服务器，先 `source setup.bash`）：
```bash
pythone optimization.py --ae_lib 2026_EDA_case1 --ae_cell OPA --ae_view schematic \
    --mde_cell OPA_loopgain --mde_view spe_state1_Corner \
    --param_file case1_params_0.txt --best_param_file best_params.txt
```

### module4_pyaether
对应赛题 5 个子项：

| 子项 | 文件 |
|---|---|
| ① 器件尺寸 → 待优化变量的参数化脚本 | `param_extract.py` |
| ② 读取电路器件连接关系 | `netlist_export.py` |
| ③ 调用 MDE 完成 PVT 仿真、提取指标 | `sim_engine.py` |
| ④ 最优尺寸回写电路图（反标） | `writeback.py` |
| ⑤ 高集成自动优化接口 | `run_auto.sh` |
| 公共口径（边界 / schema / 单位 / 旧路径修复） | `m4_common.py` |
| PVT 汇总 / 波形抽取 / 评分统计 / 报告生成 | `corner_extract.py`、`report_gen.py`、`stats.py` |
| 自测 | `tests/selftest_module4.py` |

运行（九天服务器）：
```bash
source ~/EDA_2026_Empyrean_lab_start/setup.bash
which pythone

bash run_auto.sh --fix-paths                    # 修 MDE 旧机路径（秒级）
bash run_auto.sh --params ./m4_params           # 参数化 → schematic_var
bash run_auto.sh --smoke <params.txt> ./m4_smoke
bash run_auto.sh --full  <best_params.txt> ./m4_out   # 全 PVT + 反标 → schematic_var_best
```

