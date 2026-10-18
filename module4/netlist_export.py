#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块四-② 读取电路器件连接关系脚本

对应赛题模块四第 2 项：
    "读取电路器件连接关系脚本"

作用：从 PyAether 的 schematic 读出**器件 + 端子 + 所连网络 + 尺寸参数**，
输出两种形态：
  1. `export.netlist`  —— Spectre 风格的子电路网表（与赛题 `OPA_loopgain.netlist`
     同构：`subckt <cell> (<ports>)` + `NM15 (VOUTN IREF VOUTN SUB) n_mos_a l=... w=... m=...`），
     可直接交给**模块二**的拓扑识别/参数约减。
  2. `connectivity.json` / `connectivity.md` —— 机器可读 + 人读的连接关系表，
     也是模块二"匹配器件/对称对"判定的原始依据。

用法
----
    pythone netlist_export.py --ae_lib 2026_EDA_case1 --ae_cell OPA --ae_view schematic \
        --out_dir ./net_out [--ports "IREF GNDA SUB VCM VDDA VINN VINP VOUTN VOUTP"]

    python netlist_export.py --mock --out_dir ./net_out        # 本地验证

【待核实】
    - 顶层端口（pin）的读取接口：脚本依次尝试 cv.terminals / cv.cellTerms / cv.pins，
      都没有时用 --ports 指定的列表；最终网表头部的 `subckt` 行以它为准。
    - 器件 master 名（n_mos_a / res_p_poly / cap_mim）取自实例的 cellName/master 属性，
      依次尝试多个属性名。
"""
import argparse
import io
import json
import os
import sys

try:
    import pyAether as ae
except Exception:                       # pragma: no cover
    ae = None

DEFAULTS = {
    "ae_lib": "2026_EDA_case1",
    "ae_cell": "OPA",
    "ae_view": "schematic",
    "out_dir": "./net_out",
    "ports": "IREF GNDA SUB VCM VDDA VINN VINP VOUTN VOUTP",
}

# MOS 端子输出顺序（Spectre 约定 D G S B）
MOS_TERM_ORDER = ("D", "G", "S", "B")


def get_master_name(inst):
    """依次尝试多种属性名拿器件 master（cell）名。"""
    for attr in ("cellName", "masterName", "cell"):
        v = getattr(inst, attr, None)
        if isinstance(v, str) and v:
            return v
    m = getattr(inst, "master", None)
    if m is not None:
        for attr in ("name", "cellName"):
            v = getattr(m, attr, None)
            if isinstance(v, str) and v:
                return v
    return "<unknown>"


def get_terms(inst):
    """返回 [(term_name, net_name)]；兼容 instTerms / terminals 两种属性。"""
    out = []
    terms = getattr(inst, "instTerms", None)
    if terms is None:
        terms = getattr(inst, "terminals", None)
    for t in (terms or []):
        name = getattr(t, "name", None)
        net = getattr(t, "net", None)
        net_name = getattr(net, "name", None) if net is not None else None
        if name is not None and net_name is not None:
            out.append((str(name), str(net_name)))
    return out


def read_param(inst, p):
    try:
        v = ae.aeEmyInstGetParameter(p, inst)
        return None if v is None or str(v).strip() == "" else str(v)
    except Exception:
        return None


def classify(master, n_terms):
    m = (master or "").lower()
    if "mos" in m or n_terms == 4:
        return "MOS"
    if "res" in m:
        return "R"
    if "cap" in m:
        return "C"
    if n_terms == 2:
        return "2T"
    return "OTHER"


def export_from_cv(lib, cell, view, ports):
    if ae is None:
        raise RuntimeError("未导入 pyAether")
    ae.emyInitAether("-adv")
    cv = ae.dbOpenCV(lib, cell, view)
    if not cv:
        raise RuntimeError("dbOpenCV(%s,%s,%s) 失败" % (lib, cell, view))
    devices = []
    try:
        # 顶层端口：多种接口尝试（【待核实】）
        discovered = []
        for attr in ("terminals", "cellTerms", "pins"):
            seq = getattr(cv, attr, None)
            if seq:
                names = []
                for t in seq:
                    n = getattr(t, "name", None) or str(t)
                    names.append(str(n))
                if names:
                    discovered = names
                    print("==== 顶层端口来自 cv.%s: %s ====" % (attr, names))
                    break
        if discovered:
            ports = discovered
        for inst in cv.instances:
            name = str(inst.name)
            master = get_master_name(inst)
            terms = get_terms(inst)
            kind = classify(master, len(terms))
            params = {}
            for p in ("m", "l", "fw", "segW", "segL", "segments", "multi", "w", "c", "r"):
                v = read_param(inst, p)
                if v is not None:
                    params[p] = v
            devices.append({"name": name, "master": master, "kind": kind,
                            "terms": terms, "params": params})
    finally:
        try:
            ae.dbCloseCV(cv)
        except Exception:
            pass
    return devices, ports


def mock_devices():
    """本地验证用：3 MOS + 2 电阻 + 1 电容，连成一个差分对 + 镜像的小电路。"""
    return [
        {"name": "NM0", "master": "n_mos_a", "kind": "MOS",
         "terms": [("D", "net1"), ("G", "vinp"), ("S", "net2"), ("B", "gnd")],
         "params": {"m": "8", "l": "1u", "fw": "4u"}},
        {"name": "NM1", "master": "n_mos_a", "kind": "MOS",
         "terms": [("D", "net3"), ("G", "vinn"), ("S", "net2"), ("B", "gnd")],
         "params": {"m": "8", "l": "1u", "fw": "4u"}},
        {"name": "PM0", "master": "p_mos_a", "kind": "MOS",
         "terms": [("D", "net1"), ("G", "net1"), ("S", "vdd"), ("B", "vdd")],
         "params": {"m": "2", "l": "4u", "fw": "4u"}},
        {"name": "R0", "master": "res_p_poly", "kind": "R",
         "terms": [("1", "net2"), ("2", "gnd")],
         "params": {"m": "1", "segL": "25u", "segW": "2u", "segments": "10"}},
        {"name": "R1", "master": "res_p_poly", "kind": "R",
         "terms": [("1", "net3"), ("2", "gnd")],
         "params": {"m": "1", "segL": "25u", "segW": "2u", "segments": "10"}},
        {"name": "C0", "master": "cap_mim", "kind": "C",
         "terms": [("1", "net1"), ("2", "gnd")],
         "params": {"m": "1", "l": "20u", "fw": "20u"}},
    ], DEFAULTS["ports"].split()


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------
def emit_netlist(devices, ports):
    lines = ["// Export from PyAether schematic by module4/netlist_export.py",
             "////////////////////////////////////////",
             "// Type     : spectre",
             "// Tool     : module4/netlist_export.py",
             "////////////////////////////////////////", "",
             "simulator lang = spectre", "", "global 0", "",
             "subckt %s (%s)" % ("EXPORTED", " ".join(ports))]
    for d in devices:
        t = d["terms"]
        p = d["params"]
        name, master, kind = d["name"], d["master"], d["kind"]
        if kind == "MOS" and len(t) == 4:
            # 按 D G S B 顺序重排
            m = {}
            for tn, net in t:
                m[tn.upper()[:1]] = net
            order = [m.get(k, t[i][1]) for i, k in enumerate(MOS_TERM_ORDER)]
            attr = " ".join("%s=%s" % (k, p[k]) for k in ("l", "w", "m") if k in p)
            # 赛方网表用 w=<inst>_fw，这里写实际值更通用
            attr = attr.replace("w=", "w=")
            lines.append("%s (%s) %s %s" % (name, " ".join(order), master, attr))
        elif kind in ("R", "C", "2T"):
            nets = [net for _tn, net in t]
            order = ["m", "segL", "segW", "segments", "l", "fw", "w", "c", "r"]
            attr = " ".join("%s=%s" % (k, p[k]) for k in order if k in p)
            lines.append("%s (%s) %s %s" % (name, " ".join(nets), master, attr.rstrip()))
        else:
            nets = [net for _tn, net in t]
            lines.append("// SKIP %s (%s) %s —— 端子数 %d，未分类"
                         % (name, " ".join(nets), master, len(t)))
    lines += ["ends EXPORTED", "", "// 统计: %d 个器件" % len(devices)]
    return "\n".join(lines) + "\n"


def write_outputs(devices, ports, out_dir, source_note):
    os.makedirs(out_dir, exist_ok=True)
    nl_path = os.path.join(out_dir, "export.netlist")
    with io.open(nl_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(emit_netlist(devices, ports))

    conn = {
        "source": source_note,
        "ports": ports,
        "n_devices": len(devices),
        "by_kind": {},
        "devices": [],
    }
    for d in devices:
        conn["by_kind"][d["kind"]] = conn["by_kind"].get(d["kind"], 0) + 1
        conn["devices"].append({
            "name": d["name"], "master": d["master"], "kind": d["kind"],
            "nets": [net for _tn, net in d["terms"]],
            "terms": {tn: net for tn, net in d["terms"]},
            "params": d["params"],
        })
    with io.open(os.path.join(out_dir, "connectivity.json"), "w", encoding="utf-8") as f:
        json.dump(conn, f, ensure_ascii=False, indent=1)

    lines = ["# 电路器件连接关系", "",
             "- 来源：%s" % source_note,
             "- 端口：%s" % " ".join(ports),
             "- 器件总数：**%d**（%s）" % (len(devices),
                                       ", ".join("%s=%d" % kv for kv in sorted(conn["by_kind"].items()))),
             "", "| 器件 | 类型 | master | 端子->网 | 尺寸参数 |", "|---|---|---|---|---|"]
    for d in devices:
        terms = ", ".join("%s:%s" % (tn, net) for tn, net in d["terms"])
        params = ", ".join("%s=%s" % (k, v) for k, v in d["params"].items())
        lines.append("| %s | %s | %s | %s | %s |" % (d["name"], d["kind"], d["master"], terms, params))
    with io.open(os.path.join(out_dir, "connectivity.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")

    # 自校验：MOS 必须 4 端子、R/C 必须 2 端子
    bad = [d["name"] for d in devices if d["kind"] == "MOS" and len(d["terms"]) != 4]
    bad += [d["name"] for d in devices if d["kind"] in ("R", "C") and len(d["terms"]) != 2]
    print("==== 导出 %d 个器件 -> %s ====" % (len(devices), nl_path))
    print("     类型分布: %s" % dict(sorted(conn["by_kind"].items())))
    print("     连接关系: %s" % os.path.join(out_dir, "connectivity.json"))
    if bad:
        print("WARN: 端子数异常: %s" % bad)
    return conn, bad


def main(argv=None):
    ap = argparse.ArgumentParser(description="模块四-② 读取电路器件连接关系")
    ap.add_argument("--ae_lib", default=DEFAULTS["ae_lib"])
    ap.add_argument("--ae_cell", default=DEFAULTS["ae_cell"])
    ap.add_argument("--ae_view", default=DEFAULTS["ae_view"])
    ap.add_argument("--out_dir", default=DEFAULTS["out_dir"])
    ap.add_argument("--ports", default=DEFAULTS["ports"])
    ap.add_argument("--mock", action="store_true", help="本地验证（假电路，不需要 PyAether）")
    a = ap.parse_args(argv)

    ports = [p for p in a.ports.split() if p]
    if a.mock:
        devices, ports = mock_devices()
        note = "mock（假电路：NM0/NM1/PM0/R0/R1/C0）"
    else:
        if ae is None:
            print("ERROR: 未导入 pyAether；请在服务器上 source setup.bash 后运行，或加 --mock",
                  file=sys.stderr)
            return 2
        try:
            devices, ports = export_from_cv(a.ae_lib, a.ae_cell, a.ae_view, ports)
        except Exception as e:
            print("ERROR: %s" % e, file=sys.stderr)
            return 3
        note = "%s/%s/%s" % (a.ae_lib, a.ae_cell, a.ae_view)

    if not devices:
        print("ERROR: 没有读到任何器件", file=sys.stderr)
        return 4
    _conn, bad = write_outputs(devices, ports, a.out_dir, note)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
