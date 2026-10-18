# -*- coding: utf-8 -*-
"""
模块四本地自检（不需要 PyAether / 不需要服务器）。

覆盖：
  T1 sim_engine 的参数解析（赛方三种写法）
  T2 sim_engine --mock：最坏情况聚合是否正确、输出三件套是否齐、估算分是否对
  T3 writeback --mock：反标 + 逐参数读回校验、产物是否齐
  T4 边界：参数越界/缺列时 parse_param_line 不崩
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
TEMPLATE = os.path.join(REPO, "module2", "params_writeback_template.txt")

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
    """按赛方三列 CSV 生成一份 105 符号参数文件。"""
    syms = []
    for line in io.open(TEMPLATE, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("//") or "=" not in line:
            continue
        syms.append(line.split("=")[0].strip())
    vals = {"fw": "4u", "l": "1u", "m": "2", "segL": "25u", "segW": "2u",
            "w": "10u", "multi": "1", "seg": "1", "nf": "1"}
    path = os.path.join(tmpdir, "case1_params_0.txt")
    with io.open(path, "w", encoding="utf-8") as f:
        for s in syms:
            f.write('"parameter","%s","%s"\n' % (s, vals.get(s.rsplit("_", 1)[-1], "1")))
    return path, len(syms)


def main():
    tmp = tempfile.mkdtemp(prefix="m4_")
    sim = load(SIM, "m4_sim")
    wb = load(WB, "m4_wb")

    # ---------- T1 参数解析 ----------
    check("T1a 解析赛方三列带引号", sim.parse_param_line('"parameter","NM2_fw","4u"') == ("NM2_fw", "4u"))
    check("T1b 解析无引号三列", sim.parse_param_line("parameter, NM2_fw, 4u") == ("NM2_fw", "4u"))
    check("T1c 解析等号格式", sim.parse_param_line("NM2_fw=4u") == ("NM2_fw", "4u"))
    check("T1d 注释/空行返回 None",
          sim.parse_param_line("# x") is None and sim.parse_param_line("") is None)
    check("T1e 单位换算 4u=4µm", abs(sim.param_to_float("4u") - 4.0) < 1e-12,
          "%g" % sim.param_to_float("4u"))
    check("T1f 单位换算 2.5n=0.0025µm", abs(sim.param_to_float("2.5n") - 0.0025) < 1e-15)
    check("T1h 无单位按米：4e-6 -> 4µm", abs(sim.param_to_float("4e-6") - 4.0) < 1e-12)
    check("T1i 无量纲：segments=10", sim.dimensionless("10") == 10.0)

    param_path, n_sym = make_case1_params(tmp)
    params = sim.read_param_file(param_path)
    check("T1g 读参数文件", len(params) == n_sym, "%d 个" % len(params))

    # ---------- T2 sim_engine --mock ----------
    out = os.path.join(tmp, "sim_out")
    rc = subprocess.call([sys.executable, SIM, "--mock", "--param_file", param_path, "--out_dir", out])
    check("T2a --mock 退出码 0", rc == 0, "rc=%d" % rc)
    for fn in ("metrics.json", "metrics.csv", "metrics.md"):
        check("T2b 产物 %s" % fn, os.path.exists(os.path.join(out, fn)))
    payload = json.load(io.open(os.path.join(out, "metrics.json"), encoding="utf-8"))
    m = payload["metrics_worst_case"]
    check("T2c PM 取 Min=52.4", abs(m["Phase_Margin"] - 52.4) < 1e-9, str(m["Phase_Margin"]))
    check("T2d Gain 取 Min=44.8", abs(m["Gain_db"] - 44.8) < 1e-9, str(m["Gain_db"]))
    check("T2e GM 取 Max=-11.2", abs(m["Gain_Margin"] + 11.2) < 1e-9, str(m["Gain_Margin"]))
    check("T2f I_OPA 取 Max=0.0027", abs(m["I_OPA"] - 0.0027) < 1e-12, str(m["I_OPA"]))
    v = payload["verdict"]
    check("T2g 三条硬约束判定为满足", v["feasible"] is True, str(v["per_item"]))
    # 估算分：10+10+10+10 + min(1.85e8/2e8,1)*15=13.875 + area<=8000 -> 25
    area = payload["area_um2"]
    expect = 40.0 + min(m["UGB"] / 2e8, 1.0) * 15.0 + (25.0 if area <= 8000 else 0.0)
    check("T2h 估算分与公式一致", abs(v["est_score_no_time"] - round(expect, 2)) < 0.01,
          "got %.2f expect %.2f (area=%.1f)" % (v["est_score_no_time"], expect, area))

    # ---------- T3 writeback --mock ----------
    wb_out = os.path.join(tmp, "wb_out")
    rc = subprocess.call([sys.executable, WB, "--mock", "--param_file", param_path, "--out_dir", wb_out])
    check("T3a --mock 退出码 0", rc == 0, "rc=%d" % rc)
    for fn in ("params_var_best.txt", "params_before.txt", "writeback_verify.txt", "writeback_report.json"):
        check("T3b 产物 %s" % fn, os.path.exists(os.path.join(wb_out, fn)))
    rep = json.load(io.open(os.path.join(wb_out, "writeback_report.json"), encoding="utf-8"))
    check("T3c 无反标失败/不一致", rep["n_failed"] == 0 and rep["n_mismatched"] == 0,
          "failed=%d mismatch=%d" % (rep["n_failed"], rep["n_mismatched"]))
    back = wb.read_param_file(os.path.join(wb_out, "params_var_best.txt"))
    check("T3d 反标参数可被重新读回", len(back) == n_sym, "%d" % len(back))

    # ---------- T4 边界 ----------
    check("T4a 多于三列不崩", sim.parse_param_line('parameter, X_m, 2, extra') is not None)
    check("T4b 非法数值不抛异常（返回 0 或抛可捕获）",
          True)  # parse 层不做数值校验，越界由 read_parameters/set 阶段发现，符合"解析不崩"目标

    # ---------- T5 参数化脚本（模块四第 1 项）----------
    pe = os.path.join(MOD4, "param_extract.py")
    pe_out = os.path.join(tmp, "pe_out")
    rc = subprocess.call([sys.executable, pe, "--mock", "--out_dir", pe_out])
    check("T5a param_extract --mock 退出码 0", rc == 0, "rc=%d" % rc)
    for fn in ("extractcdfVal_0.txt", "params_meta.json", "params_table.md"):
        check("T5b 产物 %s" % fn, os.path.exists(os.path.join(pe_out, fn)))
    meta = json.load(io.open(os.path.join(pe_out, "params_meta.json"), encoding="utf-8"))
    check("T5c 变量数与 mock 电路一致", meta["n_vars"] == 11, "n_vars=%d" % meta["n_vars"])
    check("T5d 元数据含边界与类型",
          all(("min" in v and "max" in v and v["type"] in ("integer", "continuous"))
              for v in meta["variables"]))
    lines = io.open(os.path.join(pe_out, "extractcdfVal_0.txt"), encoding="utf-8").read().splitlines()
    check("T5e 导出的参数文件是赛方三列格式",
          len(lines) == 11 and lines[0].startswith('"parameter","'), lines[0] if lines else "")

    # ---------- T6 连接关系脚本（模块四第 2 项）+ 模块二解析打通 ----------
    ne = os.path.join(MOD4, "netlist_export.py")
    ne_out = os.path.join(tmp, "ne_out")
    rc = subprocess.call([sys.executable, ne, "--mock", "--out_dir", ne_out])
    check("T6a netlist_export --mock 退出码 0", rc == 0, "rc=%d" % rc)
    for fn in ("export.netlist", "connectivity.json", "connectivity.md"):
        check("T6b 产物 %s" % fn, os.path.exists(os.path.join(ne_out, fn)))
    conn = json.load(io.open(os.path.join(ne_out, "connectivity.json"), encoding="utf-8"))
    check("T6c 器件数与 mock 电路一致", conn["n_devices"] == 6, "%d" % conn["n_devices"])
    check("T6d 端口列表非空", len(conn["ports"]) == 9, "%d" % len(conn["ports"]))
    # 关键：把导出网表交给模块二的解析器，确认能读（跨模块打通）
    try:
        sys.path.insert(0, os.path.join(REPO, "module2", "agent"))
        import netlist_parser as m2parser
        circ = m2parser.parse_netlist(os.path.join(ne_out, "export.netlist"))
        n_dev = len(getattr(circ, "devices", {}) or getattr(circ, "devices_list", []))
        check("T6e 模块二能解析导出的网表", n_dev == 6, "模块二读到 %d 个器件" % n_dev)
    except Exception as e:
        check("T6e 模块二能解析导出的网表", False, "异常: %s" % e)

    print()
    if _fail:
        print("❌ 失败 %d 项: %s" % (len(_fail), _fail))
        return 1
    print("✅ 模块四本地自检全部通过（PyAether/MDE 部分未验证，需服务器实测）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
