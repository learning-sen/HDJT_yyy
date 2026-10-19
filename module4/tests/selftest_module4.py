# -*- coding: utf-8 -*-
"""
模块四本地自检（不需要 PyAether / 不需要服务器）。

覆盖（对应 2026-10-18 服务器实测后的改进）：
  T1  参数解析与单位换算（m4_common，赛方三种写法）
  T2  sim_engine --mock：最坏情况聚合、估算分、三件套产物
  T3  writeback --mock：反标 + 逐参数读回校验
  T4  边界：解析不崩
  T5  param_extract --mock：**真实 schema**（MOS 3 / C 1 / R 2）
  T6  netlist_export --mock + 跨模块验证（模块二能解析导出的网表）
  T7  [P0-8] fix_sim_paths：旧路径重定向 + 备份；目标不存在时不改
  T8  [P0-3] 边界与 score.py 的 clamp 一致
  T9  [P0-4] schema_check 能识别电容的 fw/m 这类不该出现的参数
用法：python module4/tests/selftest_module4.py
"""
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
MOD4 = os.path.dirname(HERE)                      # module4/
REPO = os.path.dirname(MOD4)
SIM = os.path.join(MOD4, "sim_engine.py")
WB = os.path.join(MOD4, "writeback.py")
PE = os.path.join(MOD4, "param_extract.py")
NE = os.path.join(MOD4, "netlist_export.py")
TEMPLATE = os.path.join(REPO, "module2", "params_writeback_template.txt")

sys.path.insert(0, MOD4)

_fail = []


def check(name, cond, detail=""):
    print("[%s] %s%s" % ("PASS" if cond else "FAIL", name, ("  " + detail) if detail else ""))
    if not cond:
        _fail.append(name)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def make_case1_params(tmpdir):
    """自治地生成一份符合真实 schema 的 105 个变量参数文件（**不依赖 module2**）。

    真实口径：MOS 29×3(m,l,fw) + 电阻 6×2(segL,segW) + 电容 6×1(l) = 105。
    这样自检在服务器上（只有 module4/）也能完整跑。
    """
    mos = ["NM%d" % i for i in range(16)] + ["PM%d" % i for i in range(13)]   # 29
    res = ["R0", "R1", "R2", "R3", "R5", "R6"]                                # 6
    cap = ["C0", "C2", "C3", "C4", "C5", "C11"]                               # 6
    rows = []
    for d in mos:
        rows += [(d + "_m", "2"), (d + "_l", "1u"), (d + "_fw", "4u")]
    for d in res:
        rows += [(d + "_segL", "25u"), (d + "_segW", "2u")]
    for d in cap:
        rows += [(d + "_l", "20u")]
    path = os.path.join(tmpdir, "case1_params_0.txt")
    with io.open(path, "w", encoding="utf-8") as f:
        for name, val in rows:
            f.write('"parameter","%s","%s"\n' % (name, val))
    return path, len(rows)


def main():
    tmp = tempfile.mkdtemp(prefix="m4_")
    common = load(os.path.join(MOD4, "m4_common.py"), "m4_common")
    sim = load(SIM, "m4_sim")

    # ---------- T1 解析与单位 ----------
    check("T1a 三列带引号", common.parse_param_line('"parameter","NM2_fw","4u"') == ("NM2_fw", "4u"))
    check("T1b 无引号三列", common.parse_param_line("parameter, NM2_fw, 4u") == ("NM2_fw", "4u"))
    check("T1c 等号格式", common.parse_param_line("NM2_fw=4u") == ("NM2_fw", "4u"))
    check("T1d 注释/空行", common.parse_param_line("# x") is None and common.parse_param_line("") is None)
    check("T1e 4u=4µm", abs(common.param_to_float("4u") - 4.0) < 1e-12)
    check("T1f 2.5n=0.0025µm", abs(common.param_to_float("2.5n") - 0.0025) < 1e-15)
    check("T1g 无单位按米", abs(common.param_to_float("4e-6") - 4.0) < 1e-12)
    check("T1h 无量纲 segments", common.dimensionless("10") == 10.0)

    param_path, n_sym = make_case1_params(tmp)
    check("T1i 读参数文件", len(common.read_param_file(param_path)) == n_sym, "%d 个" % n_sym)

    # ---------- T8 边界（P0-3）----------
    check("T8a segL 5..100", common.bounds_for("R", "segL") == (5.0, 100.0, False),
          str(common.bounds_for("R", "segL")))
    check("T8b segW 0.42..10", common.bounds_for("R", "segW") == (0.42, 10.0, False))
    check("T8c fw 0.15..50", common.bounds_for("MOS", "fw") == (0.15, 50.0, False))
    check("T8d 电容 l 4..30", common.bounds_for("C", "l") == (4.0, 30.0, False))
    check("T8e 其它 l 0.13..20", common.bounds_for("MOS", "l") == (0.13, 20.0, False))
    check("T8f m 整数 1..100", common.bounds_for("MOS", "m") == (1, 100, True))

    # ---------- T9 schema（P0-4）----------
    unknown = common.schema_check({"C0_fw": "20u", "C0_l": "20u", "NM0_fw": "4u", "R0_segL": "25u"})
    check("T9a 识别电容不该有的 fw", len(unknown) == 1 and "C0_fw" in unknown[0], str(unknown))
    check("T9b 合法参数不误报",
          common.schema_check({"C0_l": "20u", "NM0_fw": "4u", "NM0_m": "2", "R0_segL": "25u"}) == [])

    # ---------- T2 sim_engine --mock ----------
    out = os.path.join(tmp, "sim_out")
    rc = subprocess.call([sys.executable, SIM, "--mock", "--param_file", param_path,
                          "--out_dir", out, "--mock_area", "5000"])
    check("T2a --mock 退出码 0", rc == 0, "rc=%d" % rc)
    for fn in ("metrics.json", "metrics.csv", "metrics.md"):
        check("T2b 产物 %s" % fn, os.path.exists(os.path.join(out, fn)))
    payload = json.load(io.open(os.path.join(out, "metrics.json"), encoding="utf-8"))
    m = payload["metrics_worst_case"]
    check("T2c PM Min=52.4", abs(m["Phase_Margin"] - 52.4) < 1e-9)
    check("T2d Gain Min=44.8", abs(m["Gain_db"] - 44.8) < 1e-9)
    check("T2e GM Max=-11.2", abs(m["Gain_Margin"] + 11.2) < 1e-9)
    check("T2f I_OPA Max=0.0027", abs(m["I_OPA"] - 0.0027) < 1e-12)
    check("T2g 三约束可行", payload["verdict"]["feasible"] is True)
    expect = 40.0 + min(m["UGB"] / 2e8, 1.0) * 15.0 + (25.0 if payload["area_um2"] <= 8000 else 0.0)
    check("T2h 估算分正确", abs(payload["verdict"]["est_score_no_time"] - round(expect, 2)) < 0.01,
          "got %s expect %.2f" % (payload["verdict"]["est_score_no_time"], expect))

    # ---------- T3 writeback --mock ----------
    wb_out = os.path.join(tmp, "wb_out")
    rc = subprocess.call([sys.executable, WB, "--mock", "--param_file", param_path, "--out_dir", wb_out])
    check("T3a --mock 退出码 0", rc == 0, "rc=%d" % rc)
    for fn in ("params_var_best.txt", "params_before.txt", "writeback_verify.txt", "writeback_report.json"):
        check("T3b 产物 %s" % fn, os.path.exists(os.path.join(wb_out, fn)))
    rep = json.load(io.open(os.path.join(wb_out, "writeback_report.json"), encoding="utf-8"))
    check("T3c 无反标失败/不一致", rep["n_failed"] == 0 and rep["n_mismatched"] == 0,
          "failed=%d mismatch=%d" % (rep["n_failed"], rep["n_mismatched"]))
    check("T3d 参数可重新读回",
          len(common.read_param_file(os.path.join(wb_out, "params_var_best.txt"))) == n_sym)

    # ---------- T4 边界 ----------
    check("T4a 多于三列不崩", common.parse_param_line("parameter, X_m, 2, extra") is not None)

    # ---------- T5 param_extract --mock（真实 schema）----------
    pe_out = os.path.join(tmp, "pe_out")
    rc = subprocess.call([sys.executable, PE, "--mock", "--out_dir", pe_out])
    check("T5a --mock 退出码 0", rc == 0, "rc=%d" % rc)
    for fn in ("extractcdfVal_0.txt", "params_meta.json", "params_table.md"):
        check("T5b 产物 %s" % fn, os.path.exists(os.path.join(pe_out, fn)))
    meta = json.load(io.open(os.path.join(pe_out, "params_meta.json"), encoding="utf-8"))
    check("T5c 变量数=9（2 MOS×3 + 1 R×2 + 1 C×1）", meta["n_vars"] == 9, "%d" % meta["n_vars"])
    kinds = {}
    for v in meta["variables"]:
        kinds.setdefault(v["kind"], []).append(v["param"])
    check("T5d schema：MOS=3 参数", sorted(kinds.get("MOS", [])) == ["fw", "l", "m", "fw", "l", "m"][:6] or
          len(kinds.get("MOS", [])) == 6, str(kinds.get("MOS")))
    check("T5e schema：电容只有 l", kinds.get("C") == ["l"], str(kinds.get("C")))
    check("T5f schema：电阻只有 segW/segL", sorted(kinds.get("R", [])) == ["segL", "segW"], str(kinds.get("R")))
    check("T5g 边界写进元数据",
          all("min" in v and "max" in v for v in meta["variables"]))
    lines = io.open(os.path.join(pe_out, "extractcdfVal_0.txt"), encoding="utf-8").read().splitlines()
    check("T5h 导出为赛方三列格式", len(lines) == 9 and lines[0].startswith('"parameter","'))

    # ---------- T6 netlist_export --mock + 跨模块 ----------
    ne_out = os.path.join(tmp, "ne_out")
    rc = subprocess.call([sys.executable, NE, "--mock", "--out_dir", ne_out])
    check("T6a --mock 退出码 0", rc == 0, "rc=%d" % rc)
    for fn in ("export.netlist", "connectivity.json", "connectivity.md"):
        check("T6b 产物 %s" % fn, os.path.exists(os.path.join(ne_out, fn)))
    conn = json.load(io.open(os.path.join(ne_out, "connectivity.json"), encoding="utf-8"))
    check("T6c 器件数=6（2 个 PIN 占位已剔除）", conn["n_devices"] == 6, "%d" % conn["n_devices"])
    check("T6f 端口占位被单列统计", conn.get("n_port_placeholders") == 2,
          "%s" % conn.get("n_port_placeholders"))
    m2parser_path = os.path.join(REPO, "module2", "agent", "netlist_parser.py")
    if not os.path.exists(m2parser_path):
        print("[SKIP] T6d 跨模块验证：本机没有 module2/agent/netlist_parser.py"
              "（服务器上只有 module4 时属预期；本地已跑过）")
    else:
        try:
            sys.path.insert(0, os.path.join(REPO, "module2", "agent"))
            import netlist_parser as m2parser
            circ = m2parser.parse_netlist(os.path.join(ne_out, "export.netlist"))
            n_dev = len(getattr(circ, "devices", {}) or getattr(circ, "devices_list", []))
            check("T6d 模块二能解析导出网表", n_dev == 6, "读到 %d 个器件" % n_dev)
        except Exception as e:
            check("T6d 模块二能解析导出网表", False, "异常: %s" % e)

    # ---------- T7 fix_sim_paths（P0-8）----------
    root = os.path.join(tmp, "fakecase")
    setting_dir = os.path.join(root, "2026_EDA_case1", "OPA_loopgain", "spe_state1_Corner")
    os.makedirs(setting_dir, exist_ok=True)
    rel = os.path.join("hes_release", "models", "spectre", "spe_demo.scs")
    os.makedirs(os.path.join(root, "hes_release", "models", "spectre"), exist_ok=True)
    io.open(os.path.join(root, rel), "w").write("// fake model\n")
    old_path = "/home/eda_2025/EDA_2025_Empyrean_lab_start/" + rel.replace(os.sep, "/")
    dead_path = "/home/nobody/whatever/hes_release/models/spectre/missing.scs"
    with io.open(os.path.join(setting_dir, "setting"), "w", encoding="utf-8") as f:
        f.write("model = %s\nother = %s\n" % (old_path, dead_path))
    res = common.fix_sim_paths(root, backup=True, verbose=False)
    txt = io.open(os.path.join(setting_dir, "setting"), encoding="utf-8").read()
    check("T7a 命中的旧路径被重定向", res["modified"] == 1 and old_path not in txt, "modified=%d" % res["modified"])
    check("T7b 重定向到当前目录 hes_release", os.path.join(root, rel).replace(os.sep, "/") in txt.replace(os.sep, "/"))
    check("T7c 目标不存在的路径保持原样", dead_path in txt)
    check("T7d 原文件已备份", os.path.exists(os.path.join(setting_dir, "setting.m4bak")))

    # ---------- T10 惰性加载：--mock 绝不能 import pyAether（否则白占 license）----------
    import argparse as _ap
    ns = _ap.Namespace(ae_lib="2026_EDA_case1", ae_cell="OPA", ae_view="schematic",
                       mde_cell="OPA_loopgain", mde_view="spe_state1_Corner",
                       param_file=param_path, out_dir=os.path.join(tmp, "lazy_out"),
                       mock_area=5000.0, mock=True, no_fix_paths=True,
                       fix_paths_only=False, dry_run=False)
    sim.run_mock(ns)
    check("T10a --mock 不加载 pyAether（不占 license）", sim.ae is None, "ae=%r" % (sim.ae,))
    for name in ("sim_engine", "param_extract", "netlist_export", "writeback"):
        src = io.open(os.path.join(MOD4, name + ".py"), encoding="utf-8").read()
        top_import = any(l.startswith("import pyAether") for l in src.splitlines())
        check("T10b 无顶层 import pyAether: %s" % name, not top_import)

    # ---------- T11 emyString 兼容（服务器实测坑：float(emyString) 会 TypeError）----------
    class FakeEmyString(object):
        """模拟 SWIG 包装的 emyString：不能直接 float()，只能 str()。"""

        def __init__(self, s):
            self._s = s

        def __float__(self):
            raise TypeError("float() argument must be a string or a number, not 'FakeEmyString'")

        def __str__(self):
            return self._s

    try:
        ok_num = common.to_num(FakeEmyString("10")) == 10.0
    except Exception as e:
        ok_num = False
        print("       to_num 异常: %s" % e)
    check("T11a to_num 能吃 emyString（先 str 再 float）", ok_num)
    try:
        ok_len = abs(common.param_to_float(FakeEmyString("4u")) - 4.0) < 1e-12
    except Exception as e:
        ok_len = False
        print("       param_to_float 异常: %s" % e)
    check("T11b param_to_float 能吃 emyString", ok_len)
    src_sim = io.open(os.path.join(MOD4, "sim_engine.py"), encoding="utf-8").read()
    check("T11c sim_engine 面积计算已全部走 str()",
          "def _get(param):" in src_sim and "to_num(_get(" in src_sim)

    # ---------- T12 report_gen（6.2 第 5 项）/ T13 stats（6.2 第 6 项）----------
    rg = os.path.join(MOD4, "report_gen.py")
    stats_py = os.path.join(MOD4, "stats.py")
    rep_out = os.path.join(tmp, "pvt_report.md")
    rc = subprocess.call([sys.executable, rg, "--sim_dir", out, "--out", rep_out])
    check("T12a report_gen 退出码 0", rc == 0, "rc=%d" % rc)
    rep_text = io.open(rep_out, encoding="utf-8").read() if os.path.exists(rep_out) else ""
    check("T12b 报告含三个关键小节",
          all(k in rep_text for k in ("最坏情况指标", "全 PVT 逐角明细", "代码质量与算法性能")),
          "%d 字符" % len(rep_text))
    log_path = os.path.join(tmp, "fake_opt.log")
    io.open(log_path, "w", encoding="utf-8").write(
        "iter 1 fitness -50\niter 25 fitness -78\nTOTAL: 1234.5s\n  t_eval=12.3s\n  n_param=63 budget=6900s\n")
    stats_out = os.path.join(tmp, "stats.md")
    rc = subprocess.call([sys.executable, stats_py, "--log", log_path, "--out", stats_out])
    check("T13a stats 退出码 0", rc == 0, "rc=%d" % rc)
    stj = json.load(io.open(os.path.join(tmp, "stats.json"), encoding="utf-8"))
    check("T13b 解析出评估次数/总耗时",
          stj.get("评估/迭代次数") == 25 and abs((stj.get("总运行时间(s)") or 0) - 1234.5) < 0.1,
          str({k: stj.get(k) for k in ("评估/迭代次数", "总运行时间(s)")}))
    check("T13c 峰值内存缺失时写 None 而不是编数", stj.get("峰值内存(MB)") is None)

    # ---------- T14 corner_extract（6.2 第 5 项逐角表，格式照服务器实测）----------
    ce = os.path.join(MOD4, "corner_extract.py")
    raw_dir = os.path.join(tmp, "raw2")
    os.makedirs(raw_dir, exist_ok=True)
    import csv as _csv
    header = ['Corner', 'spe_demo.scs', 'spe_demo.scs', 'vdd', 'temp', 'Pass/Fail',
              'Loop_Gain', 'LP_Phase', 'Gain_db', 'UGB', 'Phase_Margin', 'Gain_Margin', 'I_OPA']
    rows_def = [
        ("Nominal", "tt", "<AS IS>", 1.8, 27, 42.9, 1.25e7, 74.8, -15.8, 0.00154),
        ("C1_0", "<AS IS>", "ff", 1.62, -40, 41.7, 1.60e7, 73.2, -15.5, 0.00152),
        ("C1_1", "<AS IS>", "ff", 1.62, 125, 33.0, 1.01e7, 74.5, -16.2, 0.00151),
        ("C1_4", "<AS IS>", "ss", 1.62, -40, 40.1, 1.42e7, 72.8, -15.2, 0.00149),
        ("C1_5", "<AS IS>", "ss", 1.62, 125, 29.4, 7.64e6, 75.1, -16.4, 0.00146),
    ]
    with io.open(os.path.join(raw_dir, "Results478_transpose.csv"), "w",
                 encoding="utf-8", newline="") as f:
        w = _csv.writer(f, quoting=_csv.QUOTE_ALL)
        w.writerow(header)
        for r in rows_def:
            w.writerow([r[0], r[1], r[2], r[3], r[4], "", "", ""] + list(r[5:]))
    ce_out = os.path.join(tmp, "ce_out")
    rc = subprocess.call([sys.executable, ce, "--raw_dir", raw_dir, "--out_dir", ce_out])
    check("T14a corner_extract 退出码 0", rc == 0, "rc=%d" % rc)
    pc_rows = list(_csv.DictReader(io.open(os.path.join(ce_out, "per_corner.csv"), encoding="utf-8")))
    check("T14b 逐角表行数正确", len(pc_rows) == 5, "%d" % len(pc_rows))
    check("T14c 工艺角解析正确（tt/ff/ss）",
          {r["process"] for r in pc_rows} == {"tt", "ff", "ss"},
          str({r["process"] for r in pc_rows}))
    ce_md = io.open(os.path.join(ce_out, "per_corner.md"), encoding="utf-8").read()
    check("T14d 输出含全场景覆盖检查", "全场景覆盖检查" in ce_md)
    check("T14e 输出含与 summary 的交叉校验", "交叉校验" in ce_md)

    # ---------- T15 漏 import 的回归检查（真机踩过：archive_waves 用了 shutil 却没 import）----------
    for name in ("sim_engine", "writeback", "report_gen", "stats", "corner_extract",
                 "param_extract", "netlist_export"):
        src = io.open(os.path.join(MOD4, name + ".py"), encoding="utf-8").read()
        if "shutil." in src:
            check("T15 %s 用到 shutil 且已 import" % name, "import shutil" in src)

    print()
    if _fail:
        print("❌ 失败 %d 项: %s" % (len(_fail), _fail))
        return 1
    print("✅ 模块四本地自检全部通过（PyAether/MDE 部分未验证，需服务器实测）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
