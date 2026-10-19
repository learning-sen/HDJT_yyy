# 源代码（待打包上传九天平台）

> 对应赛题 6.2（2）：智能体流程 Python 源码（Spec 解析、拓扑模块识别与参数约减）
> + 九天平台源码（参数化电路图标注、基于约束的多目标尺寸优化）。

## 目录

| 目录 | 覆盖的赛题功能 | 入口 |
|---|---|---|
| module1_spec_agent/ | **Spec 解析**：自然语言 → 结构化 JSON | python agent.py |
| module2_topology_agent/ | **拓扑模块识别与参数约减**：网表 → 模块/匹配/约减 | python agent.py --no-llm |
| module3_size_optimization/ | **基于约束的多目标尺寸优化**（九天平台） | pythone optimization.py … |

## 各目录说明

### module1_spec_agent
- gent.py 智能体入口（ReAct 决策循环 + CoT 日志）
- lib/spec_agent.py、lib/spec_parser.py、lib/spec_schema.py  Spec 解析与 schema 校验
- lib/agent_runtime.py、lib/llm_client.py、lib/agent_config.py  运行时 / LLM 客户端 / 配置
- lib/netlist_parser.py、lib/topology*.py、lib/param_reduction.py  确定性工具（供模块二复用）
- system_prompt.txt 系统提示词；config.json 模型与接口配置（Key 只写环境变量名）

运行：
    python -m pip install -r requirements.txt
    export DASHSCOPE_API_KEY=...        # Windows: \="..."
    python agent.py

### module2_topology_agent
- gent.py 主流程（三段式：确定性解析 → 确定性识别 → 大模型写决策依据）
- 
etlist_parser.py Spectre 网表解析（续行/注释/派生参数）
- 	opo_analyzer.py 拓扑识别与参数约减（镜像置换 σ 传播 + 三条防伪守卫）
- expand_params.py 变量回写模板校验
- system_prompt.txt、config.json

运行：
    python agent.py --no-llm       # 纯确定性，不调模型、不花钱
    python agent.py                # 附带大模型生成的决策依据

### module3_size_optimization
- optimization.py 提交版（赛方原件 + 末尾补丁，覆盖策略层，不改原类）
- eda_2025_case_1_upstream.py 赛方原始模板（未改动，用于对照）
- make_submission.py 由模板生成提交版
- selftest_submission.py 打桩自测（8 项）

运行（九天服务器，先 source setup.bash）：
    pythone optimization.py --ae_lib 2026_EDA_case1 --ae_cell OPA --ae_view schematic \
        --mde_cell OPA_loopgain --mde_view spe_state1_Corner \
        --param_file case1_params_0.txt --best_param_file best_params.txt

## 依赖

- 本地：openai（见 equirements.txt）
- 九天平台：pyAether、
umpy、scipy（赛方环境自带）
