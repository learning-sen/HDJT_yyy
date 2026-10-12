# 归档：队友 learning-sen 的 module1 实现（2026-10-12）

本目录是**只读快照**，从 GitHub 远端仓库归档而来，用于把队友的实现与工作区本地实现**并列保存**，
互不覆盖。工作区当前在用的实现仍在顶层 `module1/`。

## 1. 来源与版本

| 项 | 值 |
|---|---|
| 远端仓库 | https://github.com/learning-sen/HDJT_yyy.git |
| 分支 / 提交 | `origin/main` @ `f496082`（`f496082aa35299e74a195a2678a8e5d82122ad6e`） |
| 归档时间 | 2026-10-12 20:30 左右（Asia/Shanghai） |
| 公共基线 | `dcd0ecb`（"文件夹更名"），本快照 = 基线 + 他这 5 个提交 |
| 归档方式 | `git archive origin/main` → 精确复制差异文件（保留目录结构） |
| 校验结果 | 14/14 个文件与远端 blob 哈希**完全一致**（`git hash-object` 对比通过） |

他的提交记录（基线 `dcd0ecb` 之后，全部作者 `learning-sen <1034669420@qq.com>`）：

| 提交 | 时间 | 说明 |
|---|---|---|
| `a0500ae` | 2026-10-11 20:54:02 | 虚拟环境教程 |
| `d78a0fd` | 2026-10-11 21:06:41 | 提高 gitignore 的必要性 |
| `0da0d19` | 2026-10-11 23:00:08 | 首次试验 |
| `5fd8d65` | 2026-10-11 23:04:27 | 2 次试验 |
| `f496082` | 2026-10-12 20:13:04 | module1 压缩包(10.12) |

## 2. 归档内容（14 个文件）

```
archive/learning-sen_module1_2026-10-12/
├── README.md                        ← 本文件
├── .gitignore                       ← 他新增（忽略 .venv/、__pycache__ 等）
├── requirements.txt                 ← 他新增：openai>=1.60.1,<2.0.0
└── module1/
    ├── spec_case1.json              ← 他的最终 Spec 解析结果
    ├── system_prompt.txt            ← 他的系统提示词
    ├── trace_20261011-230046.zip    ← 他打包的提交件（内含 agent.py/config.json/spec_case1.json/system_prompt/trace）
    ├── 教程-虚拟环境版.md            ← 他写的 861 行虚拟环境+运行教程
    └── agent/
        ├── agent.py                 ← 单文件实现（224 行），依赖 openai 库
        ├── config.json              ← 网关指向公有 dashscope
        └── output/
            ├── spec_case1.json
            ├── spec_20261011-225048.json
            ├── spec_20261011-230046.json
            └── trace_20261011-224638.jsonl / -225048.jsonl / -230046.jsonl
```

> 说明：远端 `module1/教程.md` 与基线 `dcd0ecb` **完全相同**（不是他改的），因此未纳入归档，
> 避免与工作区本地那份同名文档混淆。

## 3. 他这套是什么

**单文件 + 第三方库 + 虚拟环境** 路线，只覆盖**模块一（自然语言 Spec 解析）**：

| 维度 | 他的实现 | 工作区本地实现（`../module1`） |
|---|---|---|
| 代码结构 | 单文件 `agent/agent.py`（224 行） | `agent.py` 入口 + `lib/` 12 个模块 |
| 依赖 | **需要 `openai` 库 + 虚拟环境** | **纯标准库，零依赖** |
| 调用方式 | `OpenAI()` 客户端调 `/chat/completions` | 自己用 `urllib` 拼 JSON，含 function calling |
| 网关 | `https://dashscope.aliyuncs.com/compatible-mode/v1`（公有） | `https://ws-r96l7kx7y1u2cnpy.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`（赛事私有网关） |
| 流程形态 | 单次调用 + 校验/补全（`check_spec` / `autofill`） | ReAct 决策循环 + 工具注册表 + CoT 推理链 |
| 降级 | 无 Key 时报错退出 | 自动回退确定性工具链，产物一致并标注 `source: fallback` |
| 模块二（拓扑识别/参数约减） | ❌ 没有 | ✅ 已实现并跑通 |
| 产物格式 | 同一套四要素 JSON | 同一套四要素 JSON |

**兼容性结论**：两边 `spec_case1.json` 的字段结构完全一致（`design_type` / `constraints[name,op,value,unit,type,priority]` /
`objectives[name,direction,unit,priority]` / `pvt_condition` / `worst_case`），可直接互换比较；
差异只在**取值与优先级**（例：硬约束 `DC_Gain` 的 priority，他是 1、本地是 2；优化目标优先级排序也不同）。

## 4. 他的产物要点（供对照）

`spec_case1.json` 硬约束 4 条：`DC_Gain >= 40 dB`、`Phase_Margin >= 50 deg`、`Gain_Margin <= -10 dB`、`I_OPA <= 3 mA`；
优化目标 4 条：`DC_Gain`↑、`UGB`↑、`Power`↓、`Area`↓（优先级 1/1/2/2）。

## 5. 怎么运行他这套（需要时）

他的 `教程-虚拟环境版.md` 有完整步骤，要点：

```powershell
cd archive\learning-sen_module1_2026-10-12
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt          # openai>=1.60.1,<2.0.0
$env:DASHSCOPE_API_KEY = "sk-你的Key"     # 不要写进配置文件
cd module1\agent
python agent.py --check                  # 只检查环境，不调模型
python agent.py "D:\C_projects\HDJT_yyy\extracted\赛题数据本身\全差分运放设计需求.txt"
```

⚠️ **两个注意点**：

1. 工作区自带的 Python（`C:\Users\Lenovo\.dsh\dsh-runtimes\...\python.exe`）**没有装 `openai`**（已验证），
   直接跑他的 `agent.py` 会 `ModuleNotFoundError`；必须先按上面建虚拟环境并安装依赖。
2. 他的默认输入路径是 `agent.py` 上两级目录下的 `extracted/赛题数据本身/全差分运放设计需求.txt`
   （源码里写死为 `HERE.parent.parent / "extracted" / ...`）。原仓库里那就是工作区顶层，**但从本归档目录运行时该路径不存在**，
   所以必须像上面第二行那样**显式传入需求文件路径**，否则会报找不到文件。

## 6. 与工作区的边界

- 本目录是**快照**，不要在这里改代码；要改请回顶层 `module1/`。
- 本地成果已提交到分支 `work/module12-agent`（提交 `00c6326`）；`main` 分支未被改动。
- 远端 `main` 与本地是**两条并行路线**（他单文件、本地 `lib/` 架构），尚未合并。
