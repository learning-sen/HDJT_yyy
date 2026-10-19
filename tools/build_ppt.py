# -*- coding: utf-8 -*-
"""生成汇报 PPT（≤20 页），对标赛题 6.4.1「汇报 PPT ≤20 页」。

用法：python tools/build_ppt.py
输出：Submission/00_技术报告/汇报PPT_20261019.pptx

设计约定：
- 16:9，深蓝标题条 + 白底正文，正文用微软雅黑（同时设 latin/eastAsia）。
- 所有数字取自技术报告终版与 Submission 产物，不另编。
- 每页带备注（讲稿），可直接用于录视频。
"""
import sys
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "Submission" / "00_技术报告" / "汇报PPT_20261019.pptx"

NAVY = RGBColor(0x1F, 0x38, 0x64)
ACCENT = RGBColor(0xC5, 0x5A, 0x11)
GRAY = RGBColor(0x59, 0x59, 0x59)
LIGHT = RGBColor(0xEE, 0xF2, 0xF8)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
FONT = "微软雅黑"

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]

_page = {"n": 0}


def _eastasia(run):
    """给 run 补 a:ea，保证中文不回退成宋体/Calibri。"""
    rPr = run.font._rPr
    ea = rPr.find(qn("a:ea"))
    if ea is None:
        ea = etree.SubElement(rPr, qn("a:ea"))
        latin = rPr.find(qn("a:latin"))
        if latin is not None:
            latin.addnext(ea)
    ea.set("typeface", FONT)


def style(run, size=16, bold=False, color=GRAY):
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    _eastasia(run)


def new_slide(title, kicker=None, notes=""):
    s = prs.slides.add_slide(BLANK)
    _page["n"] += 1

    bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, Inches(0.95))
    bar.fill.solid()
    bar.fill.fore_color.rgb = NAVY
    bar.line.fill.background()
    bar.shadow.inherit = False

    tb = s.shapes.add_textbox(Inches(0.55), Inches(0.16), Inches(11.6), Inches(0.66))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = title
    style(r, 26, True, WHITE)

    if kicker:
        kb = s.shapes.add_textbox(Inches(9.4), Inches(0.30), Inches(3.4), Inches(0.4))
        kp = kb.text_frame.paragraphs[0]
        kp.alignment = PP_ALIGN.RIGHT
        kr = kp.add_run()
        kr.text = kicker
        style(kr, 12, False, RGBColor(0xBD, 0xD7, 0xEE))

    # 页脚
    fb = s.shapes.add_textbox(Inches(0.55), Inches(7.02), Inches(8), Inches(0.32))
    fr = fb.text_frame.paragraphs[0].add_run()
    fr.text = "模拟电路 AI 智能化设计 · 赛题二"
    style(fr, 9, False, RGBColor(0x8C, 0x8C, 0x8C))

    nb = s.shapes.add_textbox(Inches(11.6), Inches(7.02), Inches(1.2), Inches(0.32))
    np_ = nb.text_frame.paragraphs[0]
    np_.alignment = PP_ALIGN.RIGHT
    nr = np_.add_run()
    nr.text = f"{_page['n']}"
    style(nr, 9, False, RGBColor(0x8C, 0x8C, 0x8C))

    if notes:
        s.notes_slide.notes_text_frame.text = notes
    return s


def bullets(slide, items, left=0.65, top=1.28, width=12.0, height=5.4, size=17, gap=10):
    tb = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = tb.text_frame
    tf.word_wrap = True
    first = True
    for item in items:
        level, text = (item if isinstance(item, tuple) else (0, item))
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.level = level
        p.space_after = Pt(gap)
        r = p.add_run()
        r.text = ("• " if level == 0 else "– ") + text
        style(r, size if level == 0 else size - 2, False, GRAY)


def table(slide, header, rows, left=0.65, top=1.35, width=12.0,
          col_widths=None, size=13, row_h=0.34, header_size=13):
    shape = slide.shapes.add_table(len(rows) + 1, len(header),
                                   Inches(left), Inches(top), Inches(width),
                                   Inches(row_h * (len(rows) + 1)))
    t = shape.table
    if col_widths:
        total = sum(col_widths)
        for i, w in enumerate(col_widths):
            t.columns[i].width = Inches(width * w / total)
    for j, h in enumerate(header):
        cell = t.cell(0, j)
        cell.text = ""
        cell.fill.solid()
        cell.fill.fore_color.rgb = NAVY
        p = cell.text_frame.paragraphs[0]
        r = p.add_run()
        r.text = str(h)
        style(r, header_size, True, WHITE)
    for i, row in enumerate(rows, start=1):
        for j, v in enumerate(row):
            cell = t.cell(i, j)
            cell.text = ""
            cell.fill.solid()
            cell.fill.fore_color.rgb = LIGHT if i % 2 else WHITE
            p = cell.text_frame.paragraphs[0]
            r = p.add_run()
            r.text = str(v)
            style(r, size, j == 0, NAVY if j == 0 else GRAY)
    return t


def note_box(slide, text, left=0.65, top=6.15, width=12.0):
    box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(top),
                                 Inches(width), Inches(0.62))
    box.fill.solid()
    box.fill.fore_color.rgb = RGBColor(0xFF, 0xF4, 0xE8)
    box.line.color.rgb = ACCENT
    box.shadow.inherit = False
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = text
    style(r, 13, True, ACCENT)


# ------------------------------------------------------------------ 1 封面
s = prs.slides.add_slide(BLANK)
_page["n"] += 1
bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
bg.fill.solid()
bg.fill.fore_color.rgb = NAVY
bg.line.fill.background()
bg.shadow.inherit = False

tb = s.shapes.add_textbox(Inches(0.9), Inches(1.5), Inches(11.5), Inches(0.6))
r = tb.text_frame.paragraphs[0].add_run()
r.text = "“中国电子杯”第三届高校 ICT 产教融合创新大赛 · 赛题二"
style(r, 16, False, RGBColor(0xBD, 0xD7, 0xEE))

tb = s.shapes.add_textbox(Inches(0.9), Inches(2.2), Inches(11.8), Inches(1.5))
r = tb.text_frame.paragraphs[0].add_run()
r.text = "模拟电路 AI 智能化设计"
style(r, 46, True, WHITE)

tb = s.shapes.add_textbox(Inches(0.9), Inches(3.5), Inches(11.8), Inches(1.0))
r = tb.text_frame.paragraphs[0].add_run()
r.text = "从自然语言 Spec 到全 PVT 验证的端到端智能设计系统"
style(r, 21, False, RGBColor(0xDD, 0xE6, 0xF2))

line = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.95), Inches(4.62), Inches(2.2), Inches(0.06))
line.fill.solid()
line.fill.fore_color.rgb = ACCENT
line.line.fill.background()

tb = s.shapes.add_textbox(Inches(0.9), Inches(4.95), Inches(11.8), Inches(1.2))
tf = tb.text_frame
tf.word_wrap = True
for i, txt in enumerate([
    "平台自动分 84.9584 / 100（初始解 78.27） ｜ 四项硬约束全 PVT 通过",
    "105 → 47 参数约减 ｜ 9 个工艺角验证 ｜ 单人运行 6951 秒",
]):
    p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
    rr = p.add_run()
    rr.text = txt
    style(rr, 16, False, WHITE)

tb = s.shapes.add_textbox(Inches(0.9), Inches(6.45), Inches(11.8), Inches(0.5))
r = tb.text_frame.paragraphs[0].add_run()
r.text = "2026-10-19"
style(r, 13, False, RGBColor(0x9D, 0xB4, 0xD0))
s.notes_slide.notes_text_frame.text = (
    "开场 15 秒：我们做的是把自然语言需求一路推到可交的电路尺寸。"
    "一句话给结果——平台自动分 84.96，四项硬约束在全部工艺角都满足。"
)

# ------------------------------------------------------------------ 2 赛题与目标
s = new_slide("赛题要求与我们的拆解", "01 背景")
table(s,
      ["模块", "输入", "输出", "运行位置"],
      [
          ("一　Spec 解析", "自然语言需求", "结构化 JSON Spec", "本地"),
          ("二　拓扑识别与约减", "电路网表", "变量清单 + 约减后网表", "本地"),
          ("三　多目标尺寸优化", "变量清单 + MDE", "最优尺寸 + 优化日志", "九天服务器"),
          ("四　PyAether 自动化", "电路图 + MDE", "参数化/仿真/反标/PVT 报告", "九天服务器"),
      ],
      top=1.30, col_widths=[3.0, 3.0, 4.2, 2.2], size=14, row_h=0.52)
bullets(s, [
    "评分构成：通用提交报告 20 分 + 客观性能 70 分 + PyAether 问卷 10 分",
    "客观性能里：Spec 解析与约减 20 分、约束满足 30 分、多目标优化 40 分、总运行时间 10 分",
    "我们读到的关键事实：评分器 score.py 才是唯一真相来源，赛题 PDF 只是意图说明",
], top=4.35, height=1.6, size=15)
s.notes_slide.notes_text_frame.text = (
    "四个模块按数据流串起来。这里强调一句：我们所有数字口径都以平台的 score.py 为准，"
    "因为 PDF 的评分表和平台实际给分并不完全一致，比如时间分上限。"
)

# ------------------------------------------------------------------ 3 总体架构
s = new_slide("总体架构：两层，靠纯文本文件交接", "02 架构")
table(s,
      ["层", "依赖", "职责", "产物"],
      [
          ("本地层", "Python + 大模型 API", "自然语言理解、网表静态分析、参数约减", "JSON / CSV / netlist"),
          ("服务器层", "PyAether + Aether + MDE + ALPS", "真实电路操作、SPICE 仿真、反标", "最优尺寸 / PVT 指标"),
      ],
      top=1.30, col_widths=[1.6, 3.6, 5.0, 3.0], size=14, row_h=0.55)
bullets(s, [
    "两层之间只传文本（JSON / CSV / netlist / txt），不传二进制、不共享内存——任一层都能单独复现",
    "本地层没有服务器也能跑完模块一、二；服务器层只负责「真的在跑电路」的那部分",
    "好处：调试时不必反复上服务器，且失败能定位到具体一层",
], top=3.55, height=2.4, size=16)
s.notes_slide.notes_text_frame.text = (
    "架构上刻意做了切割：本地能做的绝不放到服务器上做。"
    "服务器是按小时排队用的资源，把网表分析、Spec 解析放在本地，迭代速度差好几倍。"
)

# ------------------------------------------------------------------ 4 模块一
s = new_slide("模块一：会调工具的智能体，而不是「调一次模型」", "03 模块一")
table(s,
      ["#", "工具", "职责"],
      [
          ("1", "parse_requirement", "确定性解析需求文本，给基线指标（不让模型编数字）"),
          ("2", "normalize_metric_unit", "口语化指标名与单位归一化"),
          ("3", "validate_spec_schema", "校验硬约束/优化目标/单位/优先级四要素"),
          ("4", "check_grading_gates", "核对 PM≥50°、GM≤−10 dB、I_OPA≤3 mA、Gain≥40 dB"),
          ("5", "lookup_device_bounds", "给出器件取值范围，传给模块三"),
          ("6", "emit_structured_spec", "产出最终 Spec 并结束"),
      ],
      top=1.30, col_widths=[0.7, 4.0, 7.3], size=13, row_h=0.46)
bullets(s, [
    "模型只做「选择与判断」，数值一律由确定性代码给出——避免单位换算类幻觉",
    "模型不可用时退化为规则解析器，仍输出同结构 JSON，并在日志标为 rule_fallback",
], top=5.15, height=1.3, size=15)
s.notes_slide.notes_text_frame.text = (
    "为什么强调「智能体」：赛题原文就写了智能体。我们的实现是工具注册表加决策循环。"
    "关键取舍是数值不进模型，模型只选工具。"
)

# ------------------------------------------------------------------ 5 模块一 输出
s = new_slide("模块一：输出四要素齐全，直接对应那 10 分", "03 模块一")
table(s,
      ["字段", "内容", "满足评分"],
      [
          ("design_type", "fully_differential_opamp_with_cmfb", "✅"),
          ("constraints", "DC_Gain≥40dB；PM≥50°；GM≤−10dB；I_OPA≤3mA", "✅ 每项含 name/op/value/unit/type/priority"),
          ("objectives", "Power↓；DC_Gain↑；UGB↑；Area↓", "✅ 每项含 name/direction/unit/priority"),
          ("pvt / worst_case", "all_corners / true", "✅"),
      ],
      top=1.30, col_widths=[2.6, 5.6, 3.8], size=13, row_h=0.62)
note_box(s, "评分口径：缺一类信息扣 1 分；输入里没写 PM/GM/I_OPA 也要按评分底线补进 constraints")
s.notes_slide.notes_text_frame.text = (
    "这页是模块一的得分点。赛题给的例句里其实没写 PM、GM、电流的具体数值，"
    "但评分表里这三项各占 10 分，不满足直接 0 分，所以我们把补齐底线写成了硬规则。"
)

# ------------------------------------------------------------------ 6 模块二 方法
s = new_slide("模块二：先用图论把「结构」识别对", "04 模块二")
table(s,
      ["步骤", "方法", "为什么这么做"],
      [
          ("找对称", "Weisfeiler-Lehman 颜色细化求候选", "参数化后尺寸都是变量名，「比尺寸」永远不相等"),
          ("全局校验", "重建置换 σ，检查每个器件都有镜像", "同色只代表「可能」对称，必须逐器件验证"),
          ("找匹配", "差分对作种子，沿两臂对应找同类器件", "对称是图论性质，匹配是工艺性质，不能混"),
          ("补家族", "共源共栅偏置家族（同栅不同源）", "原判据「同栅同源」会把这族拆散"),
      ],
      top=1.30, col_widths=[2.0, 5.2, 4.8], size=13, row_h=0.58)
note_box(s, "核心认知：对称（可互换）≠ 匹配（版图要一致但电路不等价）", top=4.95)
bullets(s, [
    "初版把 CMFB 差分对当对称种子，导致 8 个器件找不到镜像对象，而冲突检测还报「无冲突」",
], top=5.75, height=0.8, size=14)
s.notes_slide.notes_text_frame.text = (
    "这页讲方法论。最容易犯的错是拿尺寸或型号判断对称，我们的做法是把电路当成图，"
    "用颜色细化找候选，再用全局校验兜底。"
)

# ------------------------------------------------------------------ 7 模块二 结果
s = new_slide("模块二：105 → 47，且证明没改坏电路", "04 模块二")
table(s,
      ["指标", "结果"],
      [
          ("识别覆盖率", "59 / 59 个器件，无遗漏"),
          ("功能模块", "13 个（4 电流镜 + 1 共源共栅家族 + 2 差分对 + 输出级 + CMFB + Dummy + 2 匹配）"),
          ("对称 / 匹配 / Dummy", "22 对 / 4 对 / 4 个"),
          ("变量约减", "105 → 47，约减 55.2%"),
          ("闭环校验", "59 → 59 器件，端子连接逐条一致"),
          ("符号账目", "105 = 47 自由变量（覆盖 99 符号）+ 6 Dummy"),
      ],
      top=1.30, col_widths=[3.4, 8.6], size=14, row_h=0.52)
note_box(s, "约减出错不会崩，只会让性能莫名上不去——所以用闭环校验把「静默失效」变成可发现")
s.notes_slide.notes_text_frame.text = (
    "三个数字要分清：105 是回写面，47 是搜索空间，53 是约减后网表符号数。"
    "闭环校验是这页最有说服力的地方——证明我们只是改了变量名，没动连接。"
)

# ------------------------------------------------------------------ 8 模块三 建模
s = new_slide("模块三：把 Spec 变成可算的优化问题", "05 模块三")
table(s,
      ["类别", "项", "表达式"],
      [
          ("硬约束", "相位裕度 / 增益裕度 / 工作电流", "PM≥50°；GM≤−10dB；I_OPA≤3mA（全 PVT）"),
          ("硬约束", "直流增益门槛", "DC Gain ≥ 40 dB（低于即该项 0 分）"),
          ("优化目标", "增益 / 带宽 / 面积", "Gain↑、UGB↑、Area↓"),
      ],
      top=1.28, col_widths=[2.0, 5.0, 5.0], size=13, row_h=0.55)
bullets(s, [
    "面积口径与评分器一致：MOS = fw·L·m·1.5，电容 = W·L，电阻 = segW·segL·segments·2",
    "变量边界按参数名逐一对齐 score.py 的 clamp，而不是「所有连续参数统一 0.13~20」",
    "边界没对齐的后果：优化器在非法区间搜到的点会被评分器夹住，等于白跑仿真",
], top=3.75, height=2.4, size=15)
s.notes_slide.notes_text_frame.text = (
    "建模这页的关键词是「对齐」。约束、目标、面积公式、变量边界，四样全部对齐评分器。"
)

# ------------------------------------------------------------------ 9 模块三 算法
s = new_slide("模块三：差分进化 + 三条保命设计", "05 模块三")
table(s,
      ["配置项", "取值", "理由"],
      [
          ("算法", "差分进化 DE，strategy=best1bin", "混合整数、目标函数含大量失败点，梯度法不适用"),
          ("种群 / 代数", "20 / 实际 10 代（预算优先）", "单次仿真约 34 秒，种群过大吃光预算"),
          ("初值", "围绕初始解 ±50% 扰动，每次只动 35% 参数", "全空间随机会把面积打到 1e5~1e6，AC 出不来"),
          ("预算", "6900 秒（7200 − 300）", "时间分在 7200 秒封顶"),
      ],
      top=1.28, col_widths=[2.4, 5.2, 4.4], size=13, row_h=0.52)
note_box(s, "P0-8：MDE 配置写死旧机绝对路径 → 仿真必失败 → 最优解写不出 → score.py 七项全 0", top=4.30)
bullets(s, [
    "这不是算法问题，而是环境问题：官方参考包就是这样 14 秒退出、拿到 0 分",
    "另有 P0-9：仿真失败按「最差解」处理，单点失败只赔一次评估，不赔整轮",
], top=5.25, height=1.4, size=14)
s.notes_slide.notes_text_frame.text = (
    "这页两个重点：一是算法配置为什么这么选，二是那个把所有人打成 0 分的环境问题。"
    "后者才是这次最有价值的发现。"
)

# ------------------------------------------------------------------ 10 成绩
s = new_slide("模块三：平台自动分 84.9584", "05 模块三")
table(s,
      ["分项", "得分", "说明"],
      [
          ("PM / GM / DC Gain / I_OPA", "10 / 10 / 10 / 10", "四项硬约束全 PVT 通过"),
          ("UGB", "1.0381", "排名类分项"),
          ("Area", "23.9204", "排名类分项"),
          ("Time", "20.0000", "6951 s < 7200 s，满分"),
          ("合计", "84.9584", "初始解 78.27，提升 6.69"),
      ],
      top=1.30, col_widths=[4.4, 3.0, 4.6], size=14, row_h=0.5)
table(s,
      ["Gain", "UGB", "PM", "GM", "I_OPA", "Area"],
      [("45.85 dB", "13.84 MHz", "61.20°", "−10.84 dB", "0.839 mA", "8361.08 µm²")],
      top=4.6, col_widths=[2, 2, 2, 2, 2, 2], size=15, row_h=0.62)
s.notes_slide.notes_text_frame.text = (
    "这是最终成绩。四项硬约束满分，时间分满分。六个物理量给我们念一遍。"
)

# ------------------------------------------------------------------ 11 模块四
s = new_slide("模块四：赛题 5 个子项，一一落位", "06 模块四")
table(s,
      ["#", "赛题子项", "实现", "产物"],
      [
          ("1", "器件尺寸转为待优化变量", "param_extract.py", "105 变量 + 元数据"),
          ("2", "读取器件连接关系", "netlist_export.py", "网表 + 连接表"),
          ("3", "调用 MDE 仿真并提取指标", "sim_engine.py", "六项指标 + 波形"),
          ("4", "最优尺寸回写电路图", "writeback.py", "schematic_var_best + 读回校验"),
          ("5", "高集成自动优化接口", "run_auto.sh", "输入尺寸 → 输出性能"),
      ],
      top=1.28, col_widths=[0.7, 5.4, 3.4, 4.5], size=13, row_h=0.5)
bullets(s, [
    "五个脚本共用 m4_common.py 一套口径（边界/单位/schema/旧路径修复），避免各写一份而走样",
    "反标默认不动原图：目标视图不存在先尝试拷贝，无拷贝接口就中止，只有 --in_place 才改原图",
    "所有脚本支持 --mock，评审在没有 license 的机器上也能复核",
], top=4.50, height=2.2, size=15)
s.notes_slide.notes_text_frame.text = (
    "模块四是工具链。设计原则是保守：宁可功能少一点，也不能把原始电路图改坏——只有一次提交机会。"
)

# ------------------------------------------------------------------ 12 PVT
s = new_slide("全 PVT 验证：9 个工艺角全部达标", "07 验证")
table(s,
      ["指标", "最坏值", "门限", "判定"],
      [
          ("DC Gain", "45.85 dB（Min）", "≥ 40 dB", "✅"),
          ("Phase Margin", "61.20°（Min）", "≥ 50°", "✅"),
          ("Gain Margin", "−10.84 dB（Max）", "≤ −10 dB", "✅"),
          ("I_OPA", "0.839 mA（Max）", "≤ 3 mA", "✅"),
          ("UGB / Area", "13.84 MHz / 8361 µm²", "排名项", "—"),
      ],
      top=1.28, col_widths=[3.0, 4.4, 3.2, 1.6], size=14, row_h=0.5)
bullets(s, [
    "覆盖：TT/FF/SS × 1.62/1.8/1.98 V × −40/27/125 ℃，共 9 角",
    "口径与 score.py 一致：PM/Gain/UGB 取 Min，GM/I_OPA 取 Max",
    "裕度最小的是 GM（0.84 dB），是最需要关注的指标",
], top=4.55, height=1.9, size=15)
s.notes_slide.notes_text_frame.text = (
    "全 PVT 这一页要强调口径：最坏值才是结论，不是典型值。GM 裕度最小，只有 0.84 dB。"
)

# ------------------------------------------------------------------ 13 电路图
s = new_slide("电路图：参数化视图与反标视图", "08 结果")
figs = [
    ("module4_交付物/3_pvt/figures/01_schematic_parameterized.png", "参数化视图（尺寸为变量）"),
    ("module4_交付物/3_pvt/figures/02_schematic_var_best.png", "反标视图（尺寸已写回数值）"),
]
x = 0.7
for rel, cap in figs:
    p = ROOT / rel
    if p.exists():
        s.shapes.add_picture(str(p), Inches(x), Inches(1.45), width=Inches(5.9))
        tb = s.shapes.add_textbox(Inches(x), Inches(5.85), Inches(5.9), Inches(0.4))
        r = tb.text_frame.paragraphs[0].add_run()
        r.text = cap
        style(r, 12, False, GRAY)
    x += 6.05
tb = s.shapes.add_textbox(Inches(0.7), Inches(6.4), Inches(12.0), Inches(0.4))
r = tb.text_frame.paragraphs[0].add_run()
r.text = "截图来自流程演示运行；最终尺寸见 2026_EDA_case1_best_params.txt（105 行）"
style(r, 11, False, RGBColor(0x8C, 0x8C, 0x8C))
s.notes_slide.notes_text_frame.text = (
    "左边是参数化后的图，尺寸都是变量名；右边是反标后的图，写的是具体数值。"
    "这一步让评委能直接打开图看到最终尺寸。"
)

# ------------------------------------------------------------------ 14 性能
s = new_slide("算法性能与代码质量", "09 工程")
table(s,
      ["指标", "数值"],
      [
          ("总运行时间", "6941.5 s（外壳计时 6951 s）"),
          ("目标函数评估次数", "204 次，单次约 34 s"),
          ("达到增益门槛的点", "39 个（Gain ≥ 41 dB）"),
          ("仿真失败点", "95 个（46.6%，激进扰动的代价）"),
          ("内存峰值", "556 MB"),
          ("本地自检", "模块三 8 项断言；模块四 60 项检查"),
      ],
      top=1.30, col_widths=[4.6, 7.4], size=14, row_h=0.5)
bullets(s, [
    "46.6% 的失败率听起来高，但它换来的是搜索空间的真实覆盖；失败点按「最差解」处理，不中断优化",
    "所有自检都能在没有 license 的机器上跑，便于评审复现",
], top=5.1, height=1.4, size=15)
s.notes_slide.notes_text_frame.text = (
    "性能这页给三个数：6951 秒、204 次评估、556 MB。失败率高是预期内的，代价换覆盖。"
)

# ------------------------------------------------------------------ 15 创新点
s = new_slide("为什么这套方案能拿分", "10 总结")
bullets(s, [
    "工具优先的智能体：数值交给确定性代码，判断交给模型，并用 source 字段区分 llm 与规则兜底",
    "把评分器当规格书：以 score.py 为唯一真相来源，反推预算、边界、回写 schema",
    "对称与匹配分离：图论性质与工艺性质分开建模，避免错误合并导致的性能悬崖",
    "面向隐藏电路的可降级设计：分组可过滤、可关闭，最坏是「变慢」而不是「跑废」",
    "闭环校验 + 三条回写断言：把「静默失效」变成「跑不起来」",
], top=1.35, height=4.4, size=18, gap=14)
note_box(s, "一句话：真正拉开差距的不是算法，而是「把不体面的事做对」——边界、写出、不崩")
s.notes_slide.notes_text_frame.text = (
    "这页讲我们和其他队伍可能的差别。核心是工程严谨性，不是算法花哨。"
)

# ------------------------------------------------------------------ 16 结论
s = new_slide("结论与后续工作", "11 结论")
table(s,
      ["项", "结果"],
      [
          ("平台自动分", "84.9584 / 100（初始解 78.27）"),
          ("全 PVT", "9 角全部满足四项硬约束"),
          ("参数约减", "105 → 47（55.2%），闭环校验通过"),
          ("端到端", "自然语言 → Spec → 识别 → 优化 → PVT → 反标，全程可复现"),
      ],
      top=1.28, col_widths=[3.0, 9.0], size=14, row_h=0.5)
bullets(s, [
    "后续一：统一模块二 47 维与模块三 63 维的分组口径",
    "后续二：以最优尺寸重采波形与反标截图",
    "后续三：补「尺寸 → 变量」的写入能力，并做隐藏电路端到端回归",
], top=4.15, height=2.0, size=15)
s.notes_slide.notes_text_frame.text = (
    "收尾：一句话总结成果，再给三条后续——都是我们清楚知道还没做完的部分。"
)

prs.save(str(OUT))
print(f"[OK] 已生成 {OUT}，共 {_page['n']} 页")
