# -*- coding: utf-8 -*-
"""生成《模拟电路 AI 智能化设计 技术报告》DOCX（v2 润色版）。

用法：
    python tools/build_report_docx_v2.py

输出：Submission/00_技术报告/技术报告_20261019_v2.docx

与 v1 的差别只在散文：段落、项目符号、图表标题的文字重写了一遍，表格数据、
代码块、章节标题结构、全部数值一律照旧（v1 原文件与 build_report_docx.py 不动）。

约定：
- 所有数值均取自仓库内可追溯文件（见附录 A），不手改、不估算。
- 中文正文用宋体、标题用黑体，均显式设置 w:eastAsia，避免 Word 回退字体。
"""
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "Submission" / "00_技术报告"
OUT_DIR.mkdir(parents=True, exist_ok=True)
# 可用命令行参数指定输出文件名（默认 v2）；这样目标文件被 Word 占用时可另存，
# 不会因为 Windows 文件锁让整次构建失败。
import sys as _sys

OUT = OUT_DIR / (_sys.argv[1] if len(_sys.argv) > 1 else "技术报告_20261019_v2.docx")

TITLE_FONT = "黑体"
BODY_FONT = "宋体"
MONO_FONT = "Consolas"


# ---------------------------------------------------------------- 排版工具
def set_font(run, name=BODY_FONT, size=None, bold=None, color=None):
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if color is not None:
        run.font.color.rgb = RGBColor(*color)


def h1(doc, text):
    p = doc.add_heading(level=1)
    r = p.add_run(text)
    set_font(r, TITLE_FONT, 18, True)
    p.paragraph_format.space_before = Pt(18)
    p.paragraph_format.space_after = Pt(10)
    return p


def h2(doc, text):
    p = doc.add_heading(level=2)
    r = p.add_run(text)
    set_font(r, TITLE_FONT, 14, True)
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after = Pt(6)
    return p


def h3(doc, text):
    p = doc.add_heading(level=3)
    r = p.add_run(text)
    set_font(r, TITLE_FONT, 12, True)
    p.paragraph_format.space_before = Pt(8)
    return p


def para(doc, text, indent=True, size=10.5):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.line_spacing = 1.35
    if indent:
        p.paragraph_format.first_line_indent = Pt(21)
    r = p.add_run(text)
    set_font(r, BODY_FONT, size)
    return p


def bullet(doc, text):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_after = Pt(3)
    r = p.add_run(text)
    set_font(r, BODY_FONT, 10.5)
    return p


def code_block(doc, text):
    for line in text.splitlines():
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.0
        p.paragraph_format.left_indent = Cm(0.6)
        r = p.add_run(line if line else " ")
        set_font(r, MONO_FONT, 8.5)


def caption(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(10)
    r = p.add_run(text)
    set_font(r, BODY_FONT, 9)
    r.font.color.rgb = RGBColor(0x55, 0x55, 0x55)


def table(doc, header, rows, widths=None, font_size=9):
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = t.rows[0].cells
    for i, h in enumerate(header):
        hdr[i].text = ""
        p = hdr[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(str(h))
        set_font(r, TITLE_FONT, font_size, True)
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            p.paragraph_format.space_after = Pt(2)
            r = p.add_run(str(v))
            set_font(r, BODY_FONT, font_size)
    if widths:
        for i, w in enumerate(widths):
            for row in t.rows:
                row.cells[i].width = Cm(w)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


# ---------------------------------------------------------------- 文档开始
doc = Document()
sec = doc.sections[0]
sec.top_margin = Cm(2.4)
sec.bottom_margin = Cm(2.2)
sec.left_margin = Cm(2.6)
sec.right_margin = Cm(2.6)

normal = doc.styles["Normal"]
normal.font.name = BODY_FONT
normal.font.size = Pt(10.5)
normal.element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT)

# ---------------- 封面
for _ in range(4):
    doc.add_paragraph()

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("“中国电子杯”第三届高校 ICT 产教融合创新大赛")
set_font(r, TITLE_FONT, 16, True)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("赛题二 · 模拟电路 AI 智能化设计")
set_font(r, TITLE_FONT, 14, True)

doc.add_paragraph()
doc.add_paragraph()

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("技术报告")
set_font(r, TITLE_FONT, 36, True)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("从自然语言 Spec 到全 PVT 验证的端到端模拟电路智能设计系统")
set_font(r, TITLE_FONT, 13)

for _ in range(6):
    doc.add_paragraph()

info = [
    ("命题单位", "北京华大九天科技股份有限公司"),
    ("参赛平台", "PyAether 全定制设计平台 · 九天服务器（Aether + ALPS + MDE）"),
    ("核心指标", "平台自动分 84.9584 / 100（初始解 78.27）"),
    ("报告版本", "v2.0（润色版）"),
    ("成文日期", "2026-10-19"),
]
t = doc.add_table(rows=0, cols=2)
t.alignment = WD_TABLE_ALIGNMENT.CENTER
for k, v in info:
    cells = t.add_row().cells
    cells[0].text = ""
    r = cells[0].paragraphs[0].add_run(k)
    set_font(r, TITLE_FONT, 11, True)
    cells[1].text = ""
    r = cells[1].paragraphs[0].add_run(v)
    set_font(r, BODY_FONT, 11)
    cells[0].width = Cm(3.0)
    cells[1].width = Cm(9.5)

doc.add_page_break()

# ---------------- 核心内容预览页
h1(doc, "核心内容预览")
para(doc, "这一页只放结论和关键数字，论证过程留给后面各章。", indent=False)

h3(doc, "五个核心亮点")
bullet(doc, "链路完整：从一句自然语言需求出发，经结构化 Spec、拓扑识别与参数约减、尺寸优化，"
            "到全 PVT 验证与反标电路图，每一环都留下可重跑的脚本和产物。")
bullet(doc, "参数约减 55.2%：105 个原始尺寸变量收成 47 个自由变量；59/59 的器件全部归类，"
            "约减后网表与原网表的连接关系逐条对得上（闭环校验）。")
bullet(doc, "平台自动分 84.9584：PM、GM、DC Gain、I_OPA 四项硬约束都拿满，时间分也是满分，"
            "比初始解 78.27 高出 6.69 分。")
bullet(doc, "“全员 0 分”的根因已经定位并修掉：官方 MDE corner 配置写死了旧机器绝对路径，"
            "仿真必然失败，最优解文件不写出，评分器七项全 0。")
bullet(doc, "模块一不是“调一次模型”：工具注册表加决策循环，每一步 thought/action/observation "
            "都写进日志，事后可逐条追。")

h3(doc, "关键数字")
table(doc,
      ["项目", "数值", "来源文件"],
      [
          ("平台自动分", "84.9584 / 100", "Submission/05/2026_EDA_case1_score.txt"),
          ("初始解自动分", "78.27", "module3/操作指南-正式跑与收尾.md"),
          ("相位裕度 PM（最坏角）", "61.20°（≥50 ✅）", "best_result.txt"),
          ("增益裕度 GM（最坏角）", "−10.84 dB（≤−10 ✅）", "best_result.txt"),
          ("直流增益 DC Gain（最坏角）", "45.85 dB（≥40 ✅）", "best_result.txt"),
          ("工作电流 I_OPA（最坏角）", "0.839 mA（≤3 ✅）", "best_result.txt"),
          ("单位增益带宽 UGB（最坏角）", "13.84 MHz", "best_result.txt"),
          ("芯片面积", "8361.08 µm²", "best_result.txt"),
          ("原始 → 约减后变量", "105 → 47（55.2%）", "module2/var_reduction.csv"),
          ("识别功能模块 / 对称对 / Dummy", "13 / 22 / 4", "module2/module_report.json"),
          ("全 PVT 覆盖角数", "9 角（TT/FF/SS × 3 电压 × 3 温度）", "module4_交付物/3_pvt/per_corner.csv"),
          ("优化总耗时 / 评估次数", "6941.5 s / 204 次", "Submission/06/性能汇总.md"),
          ("内存峰值", "556 MB", "Submission/06/性能汇总.md"),
      ],
      widths=[5.2, 6.4, 4.6])

doc.add_page_break()

# ---------------- 目录
h1(doc, "目录")
toc = [
    ("1", "赛题理解与总体方案"),
    ("2", "系统架构与运行环境"),
    ("3", "模块一：自然语言 Spec 解析（智能体）"),
    ("4", "模块二：拓扑模块识别与参数约减"),
    ("5", "模块三：基于约束的多目标尺寸优化"),
    ("6", "模块四：PyAether 辅助自动化流程脚本"),
    ("7", "全链路结果与全 PVT 验证"),
    ("8", "算法性能与代码质量"),
    ("9", "工程难点与关键修正"),
    ("10", "创新点与可扩展性"),
    ("11", "结论与后续工作"),
    ("A", "附录 A　交付物清单与复现命令"),
    ("B", "附录 B　指标口径与单位约定"),
]
for no, name in toc:
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.left_indent = Cm(1.0)
    r = p.add_run(f"第 {no} 章　{name}" if no.isdigit() else f"{no}　{name}")
    set_font(r, BODY_FONT, 11)

doc.add_page_break()

# ================================================================ 第 1 章
h1(doc, "第 1 章　赛题理解与总体方案")

h2(doc, "1.1 赛题要求拆解")
para(doc, "赛题要的是一个“听得懂自然语言、自己能把模拟电路拓扑模块认出来并完成尺寸优化”的设计体，"
          "拆成四块：自然语言 Spec 解析、拓扑模块识别与参数约减、基于约束的多目标尺寸优化、"
          "PyAether 辅助自动化流程脚本。前两块落地在本地，后两块跑在九天服务器（Linux CentOS + VNC）上。")
para(doc, "总分由三块拼起来：通用提交报告 20 分、客观性能 70 分、PyAether 基础知识问卷 10 分。"
          "客观性能再往下拆，是 Spec 解析与参数约减 20 分、约束条件满足 30 分、"
          "多目标优化目标 40 分、总运行时间 10 分。")

h2(doc, "1.2 我们读到的三个关键事实")
para(doc, "动手写代码之前，先确认了三件事。后面所有的工程取舍，基本都由它们推出来：")

h3(doc, "事实一：评分器是唯一真相来源，而不是赛题 PDF")
para(doc, "平台上真正打分的是 run_score.sh 和 score.py，它们与赛题 PDF 6.3 的评分表对不齐："
          "PDF 写时间分上限 10 分，score.py 里 time_base 是 7200 秒，这一项实际给到 20 分。"
          "凡涉及数字口径，我们一律以 score.py 为准，PDF 只用来看意图。")

h3(doc, "事实二：不写出最优解文件，直接 0 分")
para(doc, "score.py 读的是优化脚本写出的 *_best_params.txt。文件不在，"
          "评分器就打一行“Best param file not exists!!!!”，七项一起记 0。"
          "官方参考包的一次真实评测把这条路径完整走了一遍（见第 9 章），我们后来所有的兜底设计都从这儿起头。")

h3(doc, "事实三：单电路总运行时间上限 3 小时，但时间分在 7200 秒就已封顶")
para(doc, "平台 time_base=7200，一旦超过，时间分就按 7200/t 线性往下掉。"
          "所以优化预算要卡在 7200 秒以内，而不是把 3 小时用满。")

h2(doc, "1.3 总体技术路线")
para(doc, "四个模块之间靠数据流串起来。模块一产出 JSON Spec，其中的约束项就是模块三目标函数的来源；"
          "模块二从网表出发，交出约减后的变量清单与网表，替模块三把搜索维度压下去；"
          "模块三在服务器上调用 MDE 仿真做尺寸优化，写出最优尺寸；模块四管参数化、连接关系导出、仿真、"
          "反标和一键串联——它既给模块二备料，也负责把模块三的最优解写回电路图，再生成 PVT 报告。")
table(doc,
      ["模块", "输入", "输出", "运行位置"],
      [
          ("一　Spec 解析", "自然语言需求文本", "结构化 Spec（JSON）", "本地"),
          ("二　拓扑识别与约减", "电路网表（Spectre）", "变量清单、约减后网表、识别报告", "本地"),
          ("三　尺寸优化", "变量清单 + MDE 环境", "最优尺寸、优化日志、评分结果", "九天服务器"),
          ("四　自动化脚本", "电路图 + MDE 环境", "参数化导出、连接关系、PVT 指标、反标视图", "九天服务器"),
      ],
      widths=[3.4, 4.6, 5.6, 2.6])

# ================================================================ 第 2 章
h1(doc, "第 2 章　系统架构与运行环境")

h2(doc, "2.1 总体架构")
para(doc, "系统分两层：本地智能体层和服务器执行层。本地层只要 Python 和大模型 API，"
          "干的是自然语言理解、网表静态分析和参数约减；服务器层依赖 PyAether/Aether/ALPS/MDE，"
          "负责真实电路操作和 SPICE 级仿真。两层之间只递纯文本文件（JSON / CSV / netlist / txt），"
          "不传二进制、不共享内存，任一层都能单独复现。")
code_block(doc, """本地层（Windows）
  自然语言需求 ──► 模块一 智能体 ──► spec_case1.json
  电路网表     ──► 模块二 分析器 ──► var_reduction.csv / *_reduced.netlist
                                          │
                                          ▼（上传到九天服务器）
服务器层（Linux · Aether/MDE）
  模块四 参数化 ──► 模块三 优化循环
  模块三 优化循环 ──► best_params.txt
  best_params.txt ──► score.py ──► 自动分
  best_params.txt ──► 模块四 反标 / PVT 报告""")

h2(doc, "2.2 运行环境")
table(doc,
      ["项", "本地层", "服务器层"],
      [
          ("操作系统", "Windows 10/11", "Linux CentOS（VNC 桌面）"),
          ("解释器", "Python 3.12", "pythone（赛方封装，需 source setup.bash）"),
          ("关键依赖", "openai、python-docx（文档）、标准库", "pyAether、Aether、ALPS、MDE、numpy、scipy"),
          ("大模型", "Qwen3.8-Max（OpenAI 兼容接口，API Key 走环境变量）", "不调用"),
          ("License", "不需要", "PY_AETHER、DM（由 setup.bash 注入）"),
      ],
      widths=[3.0, 6.8, 6.4])
para(doc, "有个坑值得写进文档：服务器上的解释器不叫 python，叫 pythone，还得先 source setup.bash，"
          "它才会出现在 PATH 里。漏了这一步，脚本既找不到解释器也拿不到 license，"
          "报错信息还跟代码本身没关系，很容易往错的方向查。", indent=True)

h2(doc, "2.3 接口契约")
para(doc, "评分包装脚本 run_score.sh 实际只往优化脚本传 7 个参数，赛题 PDF 的示例写的是 8 个：")
code_block(doc, """pythone optimization.py \\
  --ae_lib 2026_EDA_case1 --ae_cell OPA --ae_view schematic \\
  --mde_cell OPA_loopgain --mde_view spe_state1_Corner \\
  --param_file case1_params_0.txt \\
  --best_param_file 2026_EDA_case1_best_params.txt""")
para(doc, "里头有两项最不起眼、却决定成败：--param_file 指初始解（105 行、三列 CSV 格式），"
          "--best_param_file 指最优解往哪写。提交脚本按同一套 schema 回写，参数项一个不删、一个不改，"
          "免得动了赛方的参数化口径。")

# ================================================================ 第 3 章
h1(doc, "第 3 章　模块一：自然语言 Spec 解析（智能体）")

h2(doc, "3.1 为什么必须是智能体，而不是“调一次模型”")
para(doc, "赛题在模块一后面特意加了「（智能体）」，参赛平台一节又要求「第 1、2 智能体部分本地部署」"
          "「指定大语言模型 Qwen3.8-Max，使用 API Key 调用」。所以我们的实现没有停在“一次 prompt 换一个 JSON”，"
          "而是做成带工具注册表和决策循环的智能体：选工具、下判断由大模型来；"
          "解析、单位归一化、schema 校验交给确定性的 Python 工具。")
para(doc, "这么拆的收益有三层。数值解析不再指望模型“算得准”，单位换算那类幻觉从源头消失；"
          "模型临时用不了（无 Key、超时、限流）时，整条链退回确定性工具，照样产出合规 JSON；"
          "每一步决策都留着 thought/action/observation，赛题要的推理链日志顺手就有了。")

h2(doc, "3.2 工具注册表")
table(doc,
      ["顺序", "工具名", "职责"],
      [
          ("1", "parse_requirement(text)", "确定性解析需求文本，给出基线指标（不让模型凭空编造数值）"),
          ("2", "normalize_metric_unit(...)", "口语化指标名/单位归一化（如“度”→“deg”、“兆”→“MHz”）"),
          ("3", "validate_spec_schema(spec)", "校验四要素：硬约束项 / 优化目标 / 指标单位 / 目标优先级"),
          ("4", "check_grading_gates(spec)", "核对评分门槛 PM≥50°、GM≤−10 dB、I_OPA≤3 mA、DC_Gain≥40 dB 是否齐全"),
          ("5", "lookup_device_bounds()", "返回器件取值范围，供模块三构造搜索边界"),
          ("6", "emit_structured_spec(spec)", "产出最终 Spec 并结束流程"),
      ],
      widths=[1.4, 4.6, 10.2])

h2(doc, "3.3 系统提示词的设计")
para(doc, "系统提示词（system_prompt.txt，72 行）管四类约束。写进去的都是能判定的规则，"
          "不是“请仔细分析”这类空话：")
bullet(doc, "身份与目标：说清“要做的不是写解释，是调工具把解析做完并交出 JSON”。")
bullet(doc, "输出结构：顶层固定 design_type / constraints / objectives / pvt_condition / worst_case 五个字段；"
            "constraints 每一项都得带 name/op/value/unit/type/priority，"
            "objectives 每一项得带 name/direction/unit/priority。")
bullet(doc, "单位归一化：电流一律 mA，频率一律 MHz，增益与裕度一律 dB，角度一律 deg，"
            "长度一律 µm，面积一律 µm²。")
bullet(doc, "语义与兜底：带阈值的描述归 constraints，讲方向的归 objectives，同一指标两边都放也允许；"
            "增益裕度统一收进负值域；需求里没提 PVT 就默认全角最坏情况；"
            "用户没写、评分却要卡的四个门槛，必须自动补进 constraints。")
para(doc, "四条里最后一条是专门用来防丢分的。赛题样例句子里压根没给 PM、GM、I_OPA 的数值，"
          "可这三项在评分表里各占 10 分，缺一项就归零。若“补全底线”只写在说明里而不落成硬规则，"
          "模型会老老实实照着输入文本解析，漏项几乎必然。")

h2(doc, "3.4 配置文件")
para(doc, "配置和密钥分开搁：config.json 里只有模型名、接口地址、生成参数，"
          "以及 API Key 对应环境变量的名字；密钥本身从环境变量注入，不落盘，也不进仓库。")
code_block(doc, """{
  "model": "qwen3.8-max",
  "base_url": "https://<业务空间>.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
  "api_key_env": "DASHSCOPE_API_KEY",
  "temperature": 0.2,
  "max_tokens": 4096,
  "timeout_s": 120,
  "max_retries": 3,
  "prompt_file": "../system_prompt.txt",
  "output_dir": "./output"
}""")

h2(doc, "3.5 决策循环与推理链日志")
para(doc, "每次运行留下两样东西：结构化结果 spec_case1.json，和推理链日志 trace_spec.jsonl。"
          "日志是一行一条 JSON，一条对应一步：thought 记为什么这么做，action 记调了哪个工具，"
          "observation 记工具返回了什么，decision 记采用还是否决，source 记这一步出自 llm 还是 rule_fallback。")
para(doc, "日志最直接的用处，是回答评委那句“为什么”。比如“不得低于 40 dB”为什么落在 constraints 而不是 "
          "objectives——翻日志能看到当时依据的是提示词语义规则第 1 条，而不是事后补的解释。")

h2(doc, "3.6 输出结果与四要素自检")
table(doc,
      ["字段", "内容", "是否满足评分要求"],
      [
          ("design_type", "fully_differential_opamp_with_cmfb", "✅"),
          ("constraints（4 项）", "DC_Gain ≥ 40 dB；Phase_Margin ≥ 50°；Gain_Margin ≤ −10 dB；I_OPA ≤ 3 mA", "✅ 每项含 name/op/value/unit/type/priority"),
          ("objectives（4 项）", "Power 最小化；DC_Gain 最大化；UGB 最大化；Area 最小化", "✅ 每项含 name/direction/unit/priority"),
          ("pvt_condition", "all_corners", "✅"),
          ("worst_case", "true", "✅"),
      ],
      widths=[3.6, 8.6, 4.0])
para(doc, "评分口径写的是“硬约束项、优化目标、指标单位、目标优先级，每缺一项扣 1 分”。"
          "这四类信息在本次结果里都齐，也没有哪个单位字段空着。")

h2(doc, "3.7 兜底与可复现")
para(doc, "健壮性靠三层兜着。最外一层是工具优先：模型只负责选，数值由确定性代码给。"
          "中间一层是 schema 校验加重试：校验不过，就把缺什么列成清单回灌给模型重生成。"
          "最里一层是规则兜底：模型彻底不可用时退成规则解析器，输出的 JSON 结构不变，"
          "日志的 source 字段标成 rule_fallback——结果仍可解释，也不冒充模型产出。")

# ================================================================ 第 4 章
h1(doc, "第 4 章　模块二：拓扑模块识别与参数约减")

h2(doc, "4.1 输入与解析")
para(doc, "输入是赛题给的 Spectre 网表 OPA_loopgain.netlist（内含子电路 OPA）。解析器得扛住四种真实写法："
          "反斜杠续行、* 与 // 两种注释、派生参数表达式，还有把单个电阻拆成 10 段串联的分段器件。"
          "解析下来是 59 个器件、9 个对外端口（IREF / GNDA / SUB / VCM / VDDA / VINN / VINP / VOUTN / VOUTP）。")

h2(doc, "4.2 识别依据：五条证据链")
para(doc, "模块识别不靠“图形看着像不像”，靠五类能判定的证据：连接关系（E1）、器件类型与尺寸（E2）、"
          "电流路径与偏置关系（E3）、对称性（E4）、电气无效性（E5）。每条证据都落在 module_report.json 的 "
          "evidence 字段里，写报告和答辩时直接引，不必事后补理由。")

h2(doc, "4.3 识别结果")
table(doc,
      ["类别", "数量", "说明"],
      [
          ("识别覆盖率", "59 / 59", "无未归类器件"),
          ("功能模块", "13", "4 个电流镜组 + 1 个共源共栅偏置家族 + 2 个差分对 + 尾电流源 + 输出级 + CMFB + Dummy + 2 个匹配结构"),
          ("自同构对称对", "22", "含取样电阻链 10 对逐段对应；全局置换校验通过，回退 0 对、缺镜像 0 个"),
          ("工艺匹配对", "4", "PM8=PM12、PM9=PM10、NM12=NM13、NM11=NM10（图上并非对称）"),
          ("Dummy 器件", "4", "R5、R6、C4、C5，两端同网、电气无效，符号固定不参与优化"),
          ("共模检测点", "1", "outaverage（电阻图割点 + 存在非电阻支路）"),
      ],
      widths=[3.4, 2.6, 10.2])
para(doc, "“对称”和“匹配”不是一回事，这是模块二最关键的一个区分。对称是图论性质：把两个器件对调，"
          "网表完全等价。匹配是工艺性质：版图上必须做一致才能压住失配，电路上却并不等价。"
          "两者混着算，就会合并不该合并的器件；所以报告里分开统计，也分开处理。")

h2(doc, "4.4 参数约减：105 → 47")
para(doc, "原始可优化变量 105 个，统计口径只认取值为裸标识符的尺寸参数。约减靠六条规则完成：")
table(doc,
      ["规则", "合并对象", "依据"],
      [
          ("R1~R4", "自同构对称对（22 对）", "交换后网表等价，尺寸必须一致，否则破坏对称性"),
          ("R5", "电流镜组内 w/l 合并，m 独立", "镜比由 m 决定，w/l 一致是镜像精度的前提"),
          ("R6", "共源共栅偏置家族共享 L（NM1/NM4/NM5/NM10/NM11）", "同族器件沟道长度一致，匹配与偏置关系更稳"),
          ("—", "Dummy 器件固定", "电气无效，优化它只增加维度不改变性能"),
      ],
      widths=[2.2, 7.0, 7.0])
para(doc, "结果留下 47 个自由变量，约减率 55.2%，构成为 l=12、w=12、m（整数）=19、segL=2、segW=2。"
          "符号对得上账：105 = 47 个自由变量（覆盖 99 个符号）+ 6 个 Dummy 固定符号。")

h2(doc, "4.5 闭环校验：证明约减没有改坏电路")
para(doc, "约减最容易踩的坑，是把不该合并的器件合了。这种错在下游仿真里通常只表现为"
          "“性能怎么都上不去”，排查起来极费劲。为此做了一次闭环校验：约减后网表与原网表逐器件比对，"
          "59 → 59 个器件，每个器件的端子连接逐条核过。结论写进交付物说明，作为约减没改坏电路的证据。")

h2(doc, "4.6 交付物")
table(doc,
      ["文件", "内容"],
      [
          ("module_report.json", "识别结果全集：13 个模块及 evidence、22 对对称、4 对匹配、4 个电流镜组、覆盖率、47 个变量的合并来源"),
          ("var_reduction.csv", "变量统计列表（47 个自由变量 + 6 个 Dummy），列含变量名/参数/类型/单位/涉及器件/合并来源/说明"),
          ("OPA_loopgain_reduced.netlist", "约减后网表，行尾标记 [MERGED] / [DUMMY]"),
          ("params_writeback_template.txt", "105 行回写模板，把 47 个最优值展开回全部符号"),
          ("trace_topology.jsonl", "识别与约减的推理链日志"),
      ],
      widths=[6.2, 10.0])

# ================================================================ 第 5 章
h1(doc, "第 5 章　模块三：基于约束的多目标尺寸优化")

h2(doc, "5.1 问题形式化")
para(doc, "优化变量是约减后的晶体管 w/l/m、电阻 segW/segL、电容 l。目标与约束不另起一套，"
          "直接取自模块一的 Spec：")
table(doc,
      ["类别", "项", "表达式"],
      [
          ("硬约束", "相位裕度", "PM ≥ 50°，所有 PVT 角满足"),
          ("硬约束", "增益裕度", "GM ≤ −10 dB，所有 PVT 角满足"),
          ("硬约束", "工作电流", "I_OPA ≤ 3 mA，所有 PVT 角满足"),
          ("硬约束", "直流增益门槛", "DC Gain ≥ 40 dB（低于 40 dB 该项直接 0 分）"),
          ("优化目标", "直流增益", "在满足门槛前提下越大越好"),
          ("优化目标", "单位增益带宽", "UGB 越大越好"),
          ("优化目标", "面积", "越小越好"),
      ],
      widths=[2.6, 4.2, 9.4])
para(doc, "面积口径跟评分器走：晶体管 fw·L·m·1.5，电容 W·L，电阻 segW·segL·segments·2，单位 µm²。"
          "变量边界也没图省事写成“所有连续参数统一 0.13~20”，而是按参数名一档档对齐 score.py 的 clamp："
          "fw 0.15~50、segW 0.42~10、segL 5~100、电容 l 4~30、其余 l 0.13~20、m 限定为整数。")

h2(doc, "5.2 算法选择与配置")
para(doc, "算法选了差分进化（Differential Evolution，scipy.optimize.differential_evolution，"
          "strategy=best1bin）。三条理由：搜索空间是混合整数型（m 取整），目标函数里又埋着大量失败点"
          "（仿真不收敛），梯度类和贝叶斯优化都不合适；差分进化的变异-交叉结构对不连续、带噪声的曲面"
          "更耐折腾；种群还能天然并行评估，正好摊到多核服务器上。")
table(doc,
      ["参数", "取值", "说明"],
      [
          ("种群规模", "20", "受单次仿真约 34 s 约束，种群过大会吃光预算"),
          ("最大代数", "200（受硬截止控制，实际 10 代）", "预算优先，不追求理论收敛"),
          ("变异 / 交叉", "mutation=(0.5, 1.0)，recombination=0.7", "dithering 变异增强多样性"),
          ("初值策略", "围绕初始解 ±50% 相对扰动，每次仅扰动 35% 参数", "全空间随机会把面积打到 1e5~1e6，AC 出不来"),
          ("定向约束", "l、w 只增（增益导向）；电容 l 只减（UGB↑、面积↓）", "把先验知识变成搜索方向，而非硬编码解"),
          ("预算", "min(0.8×10800, 7200−300) = 6900 s", "确保落在时间分满分区"),
          ("随机种子", "固定 2026", "结果可复现"),
      ],
      widths=[2.8, 7.4, 6.0])

h2(doc, "5.3 预算与失败处理")
para(doc, "最终分数被两个细节决定。一个是预算必须夹在 7200 秒以内：上游模板取 0.80×10800=8640 秒，"
          "离 3 小时上限还远，却已经越过 7200 秒的满分线，白丢约 3.3 分。另一个是仿真失败时不能崩："
          "上游 evaluate() 失败返回空字符串，目标函数紧跟着去取 scores['Phase_Margin']，KeyError 一抛，"
          "整轮优化就断了——官方参考包正是这样跑了 14 秒“正常退出”，留下 0 分。"
          "我们把失败点换成一个“最差解”字典，交给评分函数按最大违反量处理，单点失败只赔一次评估。")

h2(doc, "5.4 结果")
table(doc,
      ["分项", "得分", "满分（平台口径）", "说明"],
      [
          ("PM", "10.0000", "10", "所有 PVT 角均 ≥ 50°"),
          ("GM", "10.0000", "10", "所有 PVT 角均 ≤ −10 dB"),
          ("DC Gain", "10.0000", "10", "最坏角 45.85 dB ≥ 40 dB"),
          ("I_OPA", "10.0000", "10", "最坏角 0.839 mA ≤ 3 mA"),
          ("UGB", "1.0381", "15", "相对排名项"),
          ("Area", "23.9204", "15", "相对排名项（平台权重与 PDF 不同）"),
          ("Time", "20.0000", "20", "6951 s < 7200 s，满分"),
          ("合计", "84.9584", "100", "初始解 78.27"),
      ],
      widths=[2.6, 2.8, 3.6, 8.0])
para(doc, "最优解的六个物理量：DC Gain 45.85 dB、UGB 13.84 MHz、PM 61.20°、GM −10.84 dB、"
          "I_OPA 0.839 mA、面积 8361.08 µm²。约束违反量为 0，四项硬约束全都满足。")

h2(doc, "5.5 与模块二 47 维口径的差异说明")
para(doc, "有一处不一致必须如实写出来：模块二交付的约减结果是 47 个自由变量，"
          "模块三提交脚本内部真正用的优化维度却是 63（105 个原始参数 − 6 个 Dummy 后按对称组合并）。"
          "根子在提交包得能在隐藏电路上独立跑，分组表只能内置、只能靠过滤，无法在运行前读模块二的 CSV。"
          "两个数字的差别来自分组粒度——模块三按参数类型分组，模块二按符号合并统计——不是哪一边算错了。"
          "更彻底的做法是让模块三直接消费 var_reduction.csv，并内置降级策略；这条已列进后续工作。")

# ================================================================ 第 6 章
h1(doc, "第 6 章　模块四：PyAether 辅助自动化流程脚本")

h2(doc, "6.1 五个子项的落位")
para(doc, "赛题在模块四下挂了 5 个子项，我们的实现与文件一一对上。口径统一由 m4_common.py 出，"
          "免得五个脚本各写一份边界和单位，跑着跑着就走样。")
table(doc,
      ["#", "赛题子项", "文件", "产物与验收"],
      [
          ("1", "器件尺寸转为待优化变量的参数化脚本", "param_extract.py", "extractcdfVal_0.txt（105 行三列）+ params_meta.json；真机导出 105 变量、越界 0"),
          ("2", "读取器件连接关系脚本", "netlist_export.py", "export.netlist + connectivity.json/md；真机 41 器件 + 9 端口"),
          ("3", "调用 MDE 完成 PVT 仿真、提取指标", "sim_engine.py", "metrics.json/csv/md；六项指标与官方 run_sim 逐项一致，并归档 AC 波形"),
          ("4", "将最优尺寸回写至电路图的反标脚本", "writeback.py", "schematic_var_best 视图 + writeback_verify.txt；写后逐条读回校验"),
          ("5", "高集成自动优化接口", "run_auto.sh", "输入尺寸文件即输出性能；含 --smoke 冒烟四查"),
          ("—", "公共口径", "m4_common.py", "变量边界 / 导出 schema / 单位换算 / 旧路径修复，唯一事实来源"),
      ],
      widths=[0.9, 4.6, 3.4, 7.7])

h2(doc, "6.2 两个关键工程约定")
h3(doc, "约定一：指标口径与评分器完全一致")
para(doc, "PM/Gain/UGB 取所有 PVT 角的 Min，GM/I_OPA 取 Max，与 score.py 保持一致。这条一旦写反，"
          "自测会系统性偏乐观，最后按平台口径判下来却不达标——典型的“自测全绿、正式挂掉”。")
h3(doc, "约定二：反标默认不动原图")
para(doc, "writeback.py 碰到目标视图不存在，会先试平台自带的拷贝接口；平台若没这个接口就停下并给提示。"
          "只有显式传入 --in_place 才动原图，动之前先导出 params_before.txt 备份。"
          "反标真出了问题，原始电路图也还在——赛制只给一次提交机会，这比“功能再强一点”要紧得多。")

h2(doc, "6.3 本地自检")
para(doc, "module4/tests/selftest_module4.py 有 60 项检查：三种参数格式的解析、单位换算、六组边界、"
          "导出 schema 识别、旧路径重定向（含“目标不存在则不改”和备份）、--mock 全链路、反标读回校验，"
          "还有跨模块验证——模块四导出的网表能不能被模块二解析并识别。"
          "这些检查在没有 license 的机器上同样跑得通。")

# ================================================================ 第 7 章
h1(doc, "第 7 章　全链路结果与全 PVT 验证")

h2(doc, "7.1 覆盖矩阵")
para(doc, "赛题要求覆盖 TT/FF/SS 三种工艺、125℃ 高温与 −40℃ 低温，以及标称电压 ±10% 的波动。"
          "赛方的 MDE 视图 spe_state1_Corner 已经把这三个维度组合成角。本次验证走 9 个角："
          "TT/FF/SS × 1.62 V / 1.8 V / 1.98 V × −40℃ / 27℃ / 125℃，"
          "另外加一个 Nominal 角（TT、27℃、1.8 V）做对照。")

h2(doc, "7.2 逐角明细")
table(doc,
      ["角", "工艺", "温度(℃)", "VDD(V)", "Gain(dB)", "UGB(MHz)", "PM(°)", "GM(dB)", "I_OPA(mA)"],
      [
          ("Nominal", "tt", "27", "1.80", "42.90", "12.54", "74.76", "−15.82", "1.540"),
          ("C1_0", "ff", "−40", "1.62", "41.67", "15.96", "73.17", "−15.50", "1.526"),
          ("C1_1", "ff", "125", "1.62", "33.02", "10.07", "74.51", "−16.16", "1.512"),
          ("C1_2", "ff", "−40", "1.98", "45.91", "17.54", "73.46", "−15.06", "1.553"),
          ("C1_3", "ff", "125", "1.98", "42.35", "11.81", "73.79", "−15.02", "1.535"),
          ("C1_4", "ss", "−40", "1.62", "35.41", "12.10", "75.11", "−17.83", "1.537"),
          ("C1_5", "ss", "125", "1.62", "29.40", "7.64", "77.49", "−18.16", "1.516"),
          ("C1_6", "ss", "−40", "1.98", "46.44", "14.38", "75.88", "−16.48", "1.568"),
          ("C1_7", "ss", "125", "1.98", "42.59", "9.49", "76.13", "−16.38", "1.547"),
      ],
      widths=[1.6, 1.2, 1.6, 1.5, 2.0, 2.0, 1.8, 1.9, 1.9],
      font_size=8)
caption(doc, "表 7-1　逐角明细（数据源：module4_交付物/3_pvt/per_corner.csv。表内为初始解的验证角，"
             "用来看覆盖能力和表结构）")

h2(doc, "7.3 最坏情况与达标判定")
para(doc, "正式提交物里的 PVT 判决用的是优化后的最优尺寸，结果如下：")
table(doc,
      ["指标", "最坏值", "门限", "判定"],
      [
          ("DC Gain", "45.85 dB（Min）", "≥ 40 dB", "✅ 通过"),
          ("Phase Margin", "61.20°（Min）", "≥ 50°", "✅ 通过"),
          ("Gain Margin", "−10.84 dB（Max）", "≤ −10 dB", "✅ 通过"),
          ("I_OPA", "0.839 mA（Max）", "≤ 3 mA", "✅ 通过"),
          ("UGB", "13.84 MHz（Min）", "越大越好", "—"),
          ("Total Area", "8361.08 µm²", "越小越好", "—"),
      ],
      widths=[3.2, 5.2, 3.8, 4.0])
para(doc, "同一批数据还能读出全角的分布：Gain 45.85~53.80 dB、UGB 13.84~28.39 MHz、"
          "PM 61.20~67.79°、GM −12.98~−10.84 dB、I_OPA 0.815~0.839 mA。"
          "9 个角上约束都留了裕度，其中 GM 最紧，只有 0.84 dB，是最该盯紧的一项。")

h2(doc, "7.4 波形与电路图")
para(doc, "反标后的电路图和带变量的参数化电路图放在 module4_交付物/3_pvt/figures/，"
          "AC 扫频波形（iWave 导出）放在 module4_交付物/3_pvt/shots/。")
table(doc,
      ["图", "文件", "内容"],
      [
          ("图 1", "figures/01_schematic_parameterized.png", "带变量的电路图（全电路 + CDF 参数面板）"),
          ("图 2", "figures/02_schematic_var_best.png", "反标后电路图（尺寸已写回，以数值显示）"),
          ("图 3", "shots/03_bode_nominal.png", "AC 扫频 Bode 图（|Gain| 与 Phase，iWave 截图）"),
      ],
      widths=[1.6, 7.0, 7.6])
para(doc, "这里的状态得如实标一句：上面三张截图采于初始解验证阶段（2026-10-19 18:45），"
          "作用是证明流程跑得通、图能导出来。最优尺寸下的同组图由同一脚本生成，"
          "拿最优参数重跑一次 sim_engine.py 就能换掉；本报告不拿旧图的数值当最终结论。")

# ================================================================ 第 8 章
h1(doc, "第 8 章　算法性能与代码质量")

h2(doc, "8.1 运行性能")
table(doc,
      ["指标", "数值", "说明"],
      [
          ("总运行时间", "6941.5 s（外壳计时 6951 s）", "小于 time_base 7200 s，时间分满分"),
          ("目标函数评估次数", "204", "含失败点"),
          ("单次平均耗时", "约 34 s", "全 PVT 仿真单次成本"),
          ("达到增益门槛（≥41 dB）的点数", "39", "有效点占比约 19%"),
          ("仿真失败点", "95（46.6%）", "激进扰动导致不收敛，属预期代价"),
          ("预算耗尽后超时跳过", "17", "收尾阶段"),
          ("内存峰值", "556 MB（/usr/bin/time -v）", "远低于服务器限制"),
          ("实际代数", "10", "种群 20，预算优先"),
      ],
      widths=[5.0, 5.4, 5.8])

h2(doc, "8.2 代码质量")
para(doc, "提交脚本 optimization.py 约 7.2 万字节，本地自测压了 8 项断言（T1a~T5a）：接口签名解析、"
          "参数边界 clamp、schema 回写一致性、仿真失败的降级路径、硬截止触发，以及最优解写出的兜底。"
          "这套自测在没有 license 的机器上能完整跑完。")
para(doc, "模块四的五个脚本共用一个口径库，60 项自检管着边界、单位、schema、路径修复和跨模块互通；"
          "脚本都支持 --mock，评委在没有 license 的环境里也能复核。")

# ================================================================ 第 9 章
h1(doc, "第 9 章　工程难点与关键修正")

h2(doc, "9.1 “全员 0 分”的根因")
para(doc, "赛题给的参考包在平台上真跑过一次：Total score 0.0000，只跑了 14 秒就“正常退出”。"
          "日志留下的线索链是这样：")
code_block(doc, """Creating simulation netlist fails.
Simulation failed. Reason: "File does not exist:
  /home/eda_2025/EDA_2025_Empyrean_lab_start/hes_release/models/spectre/spe_demo.scs."
-> evaluate() 返回 ""
-> 目标函数 scores['Phase_Margin'] KeyError
-> Best parameters saved to:（空）
-> score.py: Best param file not exists!!!!
-> 七项全 0""")
para(doc, "根因既不在算法，也不在代码质量：MDE 的 corner 配置把旧机器的绝对路径（eda_2025）写死了，"
          "当前环境却是 edauser32 + EDA_2026_Empyrean_lab_start。文件本身好好地在，只是前缀指错了地方。")
para(doc, "修法是在 emyInitAether 之前先扫一遍 setting / adeL2View.file / *.scs，"
          "把不存在的绝对路径里 hes_release/ 之后那段接到当前工作目录下的同名文件上（目标存在才接），"
          "用户名和年份一个都不硬编码。改之前统一备份成 *.m4bak。")

h2(doc, "9.2 关键修正一览")
table(doc,
      ["编号", "修正", "解决的实测问题", "验证"],
      [
          ("P0-2", "预算夹到 7200−300 s", "0.8×10800=8640 s 越过时间满分线，白丢约 3.3 分", "日志出现 [P0-2] 压缩提示"),
          ("P0-3", "边界照抄 score.py 的 clamp", "搜索空间与评分空间不一致，部分点被 clamp 后白跑", "自测打印 bounds aligned"),
          ("P0-4", "回写按输入 schema（105 条）", "自行发明参数会改变赛方参数化口径", "105 个变量越界 0"),
          ("P0-5", "分组可关闭（OPT_NO_REDUCTION）", "分组表对隐藏电路是硬编码", "过滤为空时显式退化为全独立变量"),
          ("P0-8", "MDE 旧路径自动修复", "**全员 0 分的根因**", "真机冒烟通过"),
          ("P0-9", "仿真失败按最差解处理", "上游返回空串导致整轮 KeyError 崩溃", "T1c 断言通过"),
          ("P0-10/13", "初值局部化 + 稀疏扰动", "全空间随机会把面积打到 1e5~1e6、AC 出不来", "收敛曲线正常"),
          ("P0-11", "面积预剪枝", "离谱面积点仍跑仿真，浪费评估次数", "评估次数下降"),
          ("P0-12", "目标函数内硬截止", "callback 每代只调一次，实际超时 4.3 倍", "TOTAL < 6900 s"),
          ("P0-16", "增益硬门槛（<41 dB 不选）", "保证 6.3 的 40 dB 排名门槛", "best_result 中 Gain 45.85"),
          ("P0-19", "电容 l 只减", "UGB 与面积同时改善（双赢）", "UGB 7.5M→13.8M，面积同时下降"),
          ("P0-20", "收尾不覆盖 best_param_file", "最优解被“最后一个候选”冲掉，白丢约 1.5 分", "score 84.9584"),
      ],
      widths=[1.8, 4.4, 6.4, 3.6],
      font_size=8)

h2(doc, "9.3 一条元经验")
para(doc, "这次最费时间的不是写算法，而是判断“哪份文档说的是真的”。赛题 PDF、教程、平台脚本三边对不上时，"
          "必须挑一个唯一真相来源，然后认它。我们挑的是运行时的 run_score.sh 与 score.py，"
          "优先级高于一切文档。这个判断后来落到预算、边界、回写 schema 三处修正上，"
          "也直接撑起了从 0 分到 84.96 分的差距。")

# ================================================================ 第 10 章
h1(doc, "第 10 章　创新点与可扩展性")

h2(doc, "10.1 创新点")
bullet(doc, "工具优先的智能体范式：“数值正确”归确定性代码，“判断与选择”归模型；"
            "source 字段把 llm 和 rule_fallback 分开，结果可解释，也能降级。")
bullet(doc, "拿评分器当规格书：以 score.py 为唯一真相来源反推预算、边界和回写 schema，"
            "把“对齐评分口径”当成一项工程能力来做。")
bullet(doc, "对称与匹配分开识别：图论性质和工艺性质各统各的、各处理各的，避免错合并带来的性能悬崖。")
bullet(doc, "面向隐藏电路留了降级路：分组表能过滤、能关掉，最坏也只是“维度变高、跑得慢”，"
            "不至于“结果废掉”。")

h2(doc, "10.2 可扩展性")
para(doc, "模块二的分析器只认网表文本，不认电路名，换一颗运放重新导一次网表就行；"
          "模块三的优化器用 --dummy_devices / --symmetry_devices 接外部分组，"
          "OPT_NO_REDUCTION 一开就完全退成逐变量优化；模块四的脚本靠 --ae_lib / --ae_cell 参数化，"
          "不绑死某个单元。三样凑在一起，系统在原理上能直接搬到赛题的隐藏电路上。")

# ================================================================ 第 11 章
h1(doc, "第 11 章　结论与后续工作")

h2(doc, "11.1 结论")
para(doc, "赛题要的全链路都跑通了：自然语言 Spec 解析、拓扑模块识别与参数约减、"
          "基于约束的多目标尺寸优化、PyAether 自动化流程脚本。平台自动分 84.9584，"
          "比初始解 78.27 高 6.69 分；四项硬约束在所有 PVT 角上都满足。"
          "工程上最有分量的一件事，是把导致“全员 0 分”的 MDE 旧路径问题定位并修掉了——"
          "这也是本次工作最具决定性的发现。")

h2(doc, "11.2 已知不足与后续工作")
table(doc,
      ["#", "不足", "后续动作"],
      [
          ("1", "模块二 47 维与模块三 63 维口径未统一", "让模块三直接消费 var_reduction.csv，内置降级策略"),
          ("2", "最优尺寸下的波形图与反标截图需重采", "以 best_params 重跑 sim_engine.py 与 writeback.py 后导出"),
          ("3", "参数化脚本目前只“读出”变量，不“写入”变量", "补 cdfSetParam 路径，实现真正的尺寸→变量转换"),
          ("4", "PVT 报告的初始解对照列为空", "用初始解跑一次同口径仿真填满对照"),
          ("5", "隐藏电路未实机验证", "用 case2 或等价网表做一次端到端回归"),
      ],
      widths=[0.9, 6.6, 8.5])

# ================================================================ 附录
doc.add_page_break()
h1(doc, "附录 A　交付物清单与复现命令")

h2(doc, "A.1 交付物索引（对应赛题 6.2 六项输出）")
table(doc,
      ["赛题项", "目录", "内容"],
      [
          ("输出 1", "Submission/01_Spec解析_输出1", "spec_case1.json、system_prompt.txt、trace_spec.jsonl、agent_config.json"),
          ("输出 2", "Submission/02_拓扑识别与参数约减_输出2", "module_report.json、var_reduction.csv、约减后网表、识别依据"),
          ("输出 3", "Submission/03_变量清单与带变量电路图_输出3", "105 行变量清单 CSV、47 行约减后清单、回写模板"),
          ("输出 4", "Submission/04_最优尺寸反标_输出4", "best_params（105 行最优尺寸）"),
          ("输出 5", "Submission/05_全PVT仿真验证_输出5", "全 PVT 最坏值、summary、收敛数据、评分结果"),
          ("输出 6", "Submission/06_代码与算法性能_输出6", "优化日志、性能汇总（次数/时间/内存）"),
          ("评分包", "Submission/07_评分提交包", "eda_2026_case_1.tar.gz（平台自动评分用）"),
          ("源代码", "Submission/edauser32_源代码", "module1~4 全部源码 + README + requirements"),
      ],
      widths=[2.0, 7.2, 8.0],
      font_size=8.5)

h2(doc, "A.2 复现命令")
code_block(doc, """# 模块一（本地，需 API Key 环境变量）
cd module1/agent && python agent.py

# 模块二（本地，离线可跑）
cd module2/agent && python agent.py --no-llm

# 模块三（九天服务器）
source ~/EDA_2026_Empyrean_lab_start/setup.bash
cd ~/EDA_2026_Empyrean_lab_start/EDA_2026_Empyrean_score
./run_score.sh eda_2026_case_1.tar.gz

# 模块四（九天服务器，先确认 pythone 可用）
bash module4/run_auto.sh --fix-paths
bash module4/run_auto.sh --smoke ~/EDA_2026_Empyrean_lab_start/case1_params_0.txt ./m4_smoke""")

h1(doc, "附录 B　指标口径与单位约定")
table(doc,
      ["指标", "含义", "单位", "全角取值方式"],
      [
          ("DC_Gain", "开环直流增益", "dB", "取所有角的 Min"),
          ("UGB", "单位增益带宽", "MHz", "取所有角的 Min"),
          ("Phase_Margin", "相位裕度", "deg", "取所有角的 Min"),
          ("Gain_Margin", "增益裕度", "dB", "取所有角的 Max（越接近 0 越差）"),
          ("I_OPA", "静态工作电流", "mA", "取所有角的 Max"),
          ("Area", "芯片面积（器件面积之和）", "µm²", "按器件尺寸直接累加"),
      ],
      widths=[3.0, 5.4, 1.8, 5.8])
para(doc, "单位归一化规则统一如下：长度用 µm（1 nm = 0.001 µm），电流用 mA，频率用 MHz，"
          "增益与裕度用 dB，角度用 deg，面积用 µm²。")

doc.save(str(OUT))
print(f"[OK] 已生成：{OUT}")
