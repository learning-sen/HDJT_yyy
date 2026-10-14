# -*- coding: utf-8 -*-
"""
模块二：电路网表拓扑模块识别与参数约减智能体

运行方式（必须先激活 .venv，见教程第 4 步）：
    python agent.py                       # 用默认的赛题网表
    python agent.py "D:\\path\\x.netlist"  # 指定网表
    python agent.py --check                # 只检查环境，不调模型
    python agent.py --no-llm               # 只跑确定性流程，不调模型（零成本、可离线）

三段式设计：
  第 1 段  netlist_parser  确定性解析   —— 事实来源，不允许出错
  第 2 段  topo_analyzer   确定性识别   —— 结构判定，必须可复现
  第 3 段  大模型         决策依据生成 —— 只写"为什么"，不许改结论
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
from pathlib import Path

from netlist_parser import parse_netlist
from topo_analyzer import analyze, emit_reduced_netlist

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent            # 项目根目录
OUT_ROOT = HERE.parent               # module2/

# 赛题提供的网表（默认输入）
DEFAULT_INPUT = (ROOT / "extracted" / "赛题数据本身" / "netlist" / "OPA_loopgain.netlist")

# 本次实际使用的约减规则（会写进事实包，模型必须逐条解释）
REDUCTION_RULES = [
    {"rule": "R1", "desc": "Dummy 器件（两端接同一节点 / 全端子同网）的尺寸参数移出优化变量清单，"
                           "只保留符号供仿真读初值"},
    {"rule": "R2", "desc": "共用同一变量名的器件（如 poly 电阻的串联分段）天然共享变量，归为同一组"},
    {"rule": "R3", "desc": "对称对（差分端口对换下的图自同构 σ，**已通过全局校验**：每个器件都有"
                           "镜像对象）共享全部尺寸 w/l/m"},
    {"rule": "R4", "desc": "工艺匹配对（差分对 + 两臂对应网上的同位器件，如共模反馈误差放大器的"
                           "输入对及其镜像负载/共源共栅）共享全部尺寸 w/l/m。这类匹配**不是**图对称"
                           "（两侧栅极接的是不同信号），因此与 R3 分开判定"},
    {"rule": "R5", "desc": "电流镜组（同型号、同栅、同源）内各管共享 w/l，"
                           "各支路电流比值由 m 承担，m 保持独立"},
]


# ---------- 基础工具 ----------

def load_config() -> dict:
    with open(HERE / "config.json", "r", encoding="utf-8") as f:
        return json.load(f)


def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8").strip()


def strip_code_fence(text: str) -> str:
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    i, j = t.find("{"), t.rfind("}")
    if i != -1 and j > i:
        t = t[i:j + 1]
    return t


def resolve_input() -> Path:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    return Path(args[0]).resolve() if args else DEFAULT_INPUT


# ---------- 事实包：给大模型的唯一信息源 ----------

def build_facts(cir, res: dict) -> dict:
    return {
        "circuit": {
            "subckt": res["subckt"],
            "ports": res["ports"],
            "device_count": res["device_count"],
        },
        "variable_stats": {
            "raw": res["raw_variable_count"],
            "reduced": res["reduced_variable_count"],
            "removed": res["raw_variable_count"] - res["reduced_variable_count"],
            "reduction_pct": round(
                100 * (1 - res["reduced_variable_count"] / res["raw_variable_count"]), 1),
            "by_category": res["reduced_by_category"],
        },
        "modules": [{"id": m["id"], "type": m["type"], "name_zh": m["name_zh"],
                     "devices": m["devices"], "evidence": m["evidence"]}
                    for m in res["modules"]],
        "pairing": res["pairing"],
        "symmetry": {
            "verified": res["symmetry_verified"],
            "pairs": res["pairing"],
            "missing_images": res["symmetry_missing_images"],
            "rejected": res["symmetry_rejected"],
            "note": "对称对由差分端口对换下的图自同构 σ 判定，并通过全局校验"
                    "（每个器件都有镜像对象）；校验不通过的配对会被回退，不出现在 pairs 里",
        },
        "matching_pairs": res["match_pairs"],
        "mirror_groups": [{"id": m["id"], "type": m["type"], "reference": m["reference"],
                           "gate": m["gate"], "source": m["source"],
                           "devices": m["devices"], "confidence": m.get("confidence")}
                          for m in res["mirror_groups"]],
        "dummies": res["dummies"],
        "diode_connected": res["diode_connected"],
        "segment_groups": {k: v for k, v in res["segment_groups"].items()},
        "output_pair": res["output_pair"],
        "cm_sense_node": res["cm_sense_node"],
        "seeds": res["seeds"],
        "reduction_rules": REDUCTION_RULES,
        "fixed_variables": res["fixed_variables"],
        "reduced_variables": [
            {"var": r["var"], "param": r["param"], "kind": r["kind"],
             "devices": r["devices"], "merged_from": r["merged_from"]}
            for r in res["reduced_variables"]
        ],
    }


# ---------- 大模型：只生成"为什么" ----------

def ask_model(client, cfg, system_prompt, facts: dict, feedback: str = "") -> str:
    user = ("【事实包】\n" + json.dumps(facts, ensure_ascii=False, indent=1)
            + "\n\n请按系统提示词要求，只输出那段 JSON。")
    if feedback:
        user += f"\n\n【上一次输出不合格，请修正后重新只输出 JSON】\n{feedback}"
    resp = client.chat.completions.create(
        model=cfg["model"],
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user", "content": user}],
        temperature=cfg.get("temperature", 0.2),
        max_tokens=cfg.get("max_tokens", 4096),
        timeout=cfg.get("timeout_s", 120),
    )
    return resp.choices[0].message.content or ""


def validate_reasoning(obj: dict, facts: dict) -> list[str]:
    """校验模型输出：结构齐全 + 没有编造器件名。返回问题清单（空=通过）。"""
    problems = []
    for k in ("topology", "module_reasons", "reduction_strategy",
              "variable_notes", "risks"):
        if k not in obj:
            problems.append(f"缺少字段 {k}")

    known_ids = {m["id"] for m in facts["modules"]}
    known_vars = {v["var"] for v in facts["reduced_variables"]}
    known_devs = set()
    for m in facts["modules"]:
        known_devs.update(m["devices"])
    for p in facts["pairing"]:
        known_devs.update((p["a"], p["b"]))

    for i, mr in enumerate(obj.get("module_reasons") or []):
        if mr.get("id") not in known_ids:
            problems.append(f"module_reasons[{i}].id={mr.get('id')} 不在识别结果中")
    for i, vn in enumerate(obj.get("variable_notes") or []):
        if vn.get("var") not in known_vars:
            problems.append(f"variable_notes[{i}].var={vn.get('var')} 不是约减后变量")

    # 编造器件名检测：文中出现的、形如 XX12 的标识符必须真实存在
    text = json.dumps(obj, ensure_ascii=False)
    for tok in set(re.findall(r"\b[A-Z]{2,3}\d+[A-Za-z_]*\b", text)):
        base = tok.split("_")[0]
        if base not in {n.split("_")[0] for n in known_devs} and base not in {"R0", "R3"}:
            problems.append(f"文本中出现未知器件名 {tok}")
    rules = {r["rule"] for r in facts["reduction_rules"]}
    said = {s.get("rule") for s in (obj.get("reduction_strategy") or [])}
    missed = rules - said
    if missed:
        problems.append(f"reduction_strategy 未覆盖规则 {sorted(missed)}")
    return problems


def fallback_reasoning(res: dict) -> dict:
    """无大模型（或调用失败）时的规则兜底文案：保证交付物永远完整可交。"""
    return {
        "topology": "由确定性解析器判定的全差分运放："
                    + "、".join(m["name_zh"] for m in res["modules"] if m["type"] != "matching"),
        "module_reasons": [{"id": m["id"], "reason": m["evidence"]} for m in res["modules"]],
        "reduction_strategy": [{"rule": r["rule"], "reason": r["desc"]}
                               for r in REDUCTION_RULES],
        "variable_notes": [],
        "risks": ["本次未启用大模型解释，各条依据直接取自确定性判据，风险点需人工复核",
                  "对称对（自同构 σ）已通过全局校验；工艺匹配对（差分对/两臂对应）"
                  "只在两条臂内部成立、**不冒充图对称**，其匹配依据来自版图工程要求，"
                  "建议在仿真中对齐验证",
                  "镜像组内 W/L 合并后，各支路电流只能靠 m 调节；"
                  "若某镜像管进入非饱和区，匹配关系失效"],
        "_source": "rule_fallback",
    }


# ---------- 运行时自检 ----------

def preflight(cfg, in_path: Path) -> int:
    print(f"Python    : {sys.executable}")
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    print(f"虚拟环境  : {'是 (.venv 生效)' if in_venv else '否（正在用系统 Python！请先激活 .venv）'}")
    print(f"模型      : {cfg['model']}")
    print(f"接口      : {cfg['base_url']}")

    need_llm = "--no-llm" not in sys.argv and "--check" not in sys.argv
    key = os.getenv(cfg["api_key_env"], "")
    if key:
        print(f"API Key   : 已设置（长度 {len(key)}，不打印内容）")
    elif need_llm:
        print(f"[错误] 环境变量 {cfg['api_key_env']} 没设置。")
        print('请在 PowerShell 里执行：$env:DASHSCOPE_API_KEY = "sk-你的Key"')
        print("或者加 --no-llm 只跑确定性流程。")
        return 1
    else:
        print("API Key   : 未设置（本次不需要）")

    if not in_path.exists():
        print(f"[错误] 找不到网表文件：{in_path}")
        return 1
    print(f"网表文件  : {in_path}")
    return 0


# ---------- 主流程 ----------

def main():
    cfg = load_config()
    in_path = resolve_input()

    if preflight(cfg, in_path) != 0:
        sys.exit(1)
    if "--check" in sys.argv:
        print("\n[自检通过] 环境没问题，去掉 --check 就能正式跑。")
        return

    out_dir = (HERE / cfg["output_dir"]).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    trace_path = out_dir / f"trace_{stamp}.jsonl"

    def trace(rec: dict):
        rec["time"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(trace_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print("-" * 64)

    # ---------- 第 1 段：确定性解析 ----------
    cir = parse_netlist(in_path)
    trace({"step": "1_parse", "input": str(in_path), "subckt": cir.subckt,
           "ports": cir.ports, "device_count": len(cir.devices),
           "top_device_count": len(cir.top_devices),
           "raw_variables": cir.all_variables})
    print(f"[1/4] 解析完成：{cir.subckt}，内部器件 {len(cir.devices)} 个，"
          f"原始变量 {len(cir.all_variables)} 个")

    # ---------- 第 2 段：确定性识别与约减 ----------
    res = analyze(cir)
    trace({"step": "2_analyze",
           "modules": [{"id": m["id"], "type": m["type"],
                        "devices": m["devices"], "evidence": m["evidence"]}
                       for m in res["modules"]],
           "pairing": res["pairing"], "seeds": res["seeds"],
           "symmetry_verified": res["symmetry_verified"],
           "symmetry_missing_images": res["symmetry_missing_images"],
           "symmetry_rejected": res["symmetry_rejected"],
           "match_pairs": res["match_pairs"],
           "dummies": res["dummies"], "cm_sense_node": res["cm_sense_node"],
           "sigma_conflicts": res["sigma_conflicts"],
           "raw_variable_count": res["raw_variable_count"],
           "reduced_variable_count": res["reduced_variable_count"]})
    print(f"[2/4] 识别完成：功能模块 {len(res['modules'])} 个，"
          f"对称对 {len(res['pairing'])} 对"
          f"（σ 全局校验{'通过' if res['symmetry_verified'] else '失败'}），"
          f"工艺匹配对 {len(res['match_pairs'])} 对，Dummy {len(res['dummies'])} 个")
    print(f"      参数约减：{res['raw_variable_count']} -> {res['reduced_variable_count']} "
          f"（约减 {100 * (1 - res['reduced_variable_count'] / res['raw_variable_count']):.1f}%）")

    facts = build_facts(cir, res)

    # ---------- 第 3 段：大模型生成决策依据 ----------
    reasoning = None
    if "--no-llm" not in sys.argv:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv(cfg["api_key_env"]), base_url=cfg["base_url"])
        system_prompt = read_text((HERE / cfg["prompt_file"]).resolve())
        problems: list[str] = []
        for attempt in range(1, cfg.get("max_retries", 3) + 1):
            print(f"[3/4] 第 {attempt} 次调用模型生成决策依据 ...")
            try:
                raw = ask_model(client, cfg, system_prompt, facts,
                                feedback="; ".join(problems))
            except Exception as e:
                print(f"      调用失败：{e}")
                trace({"step": "3_llm", "attempt": attempt, "error": str(e)})
                time.sleep(2)
                continue
            trace({"step": "3_llm", "attempt": attempt, "model": cfg["model"],
                   "raw_output": raw})
            try:
                obj = json.loads(strip_code_fence(raw))
            except json.JSONDecodeError as e:
                problems = [f"输出不是合法 JSON：{e}"]
                print(f"      JSON 解析失败：{e}")
                continue
            problems = validate_reasoning(obj, facts)
            if not problems:
                reasoning = obj
                print("      校验通过")
                break
            print(f"      校验不通过：{problems}")
        if reasoning is None:
            print("[3/4] 模型未能给出合格输出，改用规则兜底文案（交付物仍然完整）")
            trace({"step": "3_llm_fallback", "problems": problems})
    else:
        print("[3/4] --no-llm：跳过大模型，使用规则兜底文案")

    if reasoning is None:
        reasoning = fallback_reasoning(res)
    trace({"step": "3_reasoning", "reasoning": reasoning})

    # ---------- 第 4 段：落盘交付物 ----------
    report = {
        "circuit": facts["circuit"],
        "variable_stats": facts["variable_stats"],
        "modules": res["modules"],
        "pairing": res["pairing"],
        "symmetry": {
            "verified": res["symmetry_verified"],
            "missing_images": res["symmetry_missing_images"],
            "rejected": res["symmetry_rejected"],
            "multifold_classes": res.get("multifold_classes", []),
        },
        "matching_pairs": res["match_pairs"],
        "pairing_relation": res["pairing_relation"],
        "mirror_groups": res["mirror_groups"],
        "seeds": res["seeds"],
        "dummies": res["dummies"],
        "diode_connected": res["diode_connected"],
        "segment_groups": res["segment_groups"],
        "output_pair": res["output_pair"],
        "cm_sense_node": res["cm_sense_node"],
        "reduction_rules": REDUCTION_RULES,
        "reduced_variables": res["reduced_variables"],
        "fixed_variables": res["fixed_variables"],
        "reasoning": reasoning,
    }
    report_path = OUT_ROOT / "module_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    (out_dir / f"module_report_{stamp}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # CSV：参数约减后的变量统计列表（赛题"变量统计列表"交付项）
    rel_by_pair = {tuple(sorted((pr["a"], pr["b"]))): pr["relation"]
                   for pr in res["pairing_relation"]}

    def note_for(v: dict) -> str:
        if len(v["devices"]) <= 1:
            return "独立变量"
        kinds = set()
        devs = v["devices"]
        for i, a in enumerate(devs):
            for b in devs[i + 1:]:
                r = rel_by_pair.get(tuple(sorted((a, b))))
                if r:
                    kinds.add(r)
        if kinds:
            return "共享(" + "/".join(sorted(kinds)) + ")"
        if v["param"] in ("w", "l", "segL", "segW"):
            return "电流镜组共享 w/l"
        return "同名变量共享（电阻分段）"

    csv_path = OUT_ROOT / "var_reduction.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["变量名", "参数", "类型", "单位", "涉及器件", "合并来源", "说明"])
        for v in res["reduced_variables"]:
            w.writerow([v["var"], v["param"], v["kind"], v["unit"],
                        "|".join(v["devices"]), "|".join(v["merged_from"]), note_for(v)])
        for v in res["fixed_variables"]:
            w.writerow([v["var"], v["param"], "fixed", "-", v["device"], "", v["reason"]])

    # 参数清单：供 PyAether 流程的 --param_file 使用
    initial = {}
    for cand in (in_path.parent / "extractcdfVal_0.txt", OUT_ROOT / "extractcdfVal_0.txt"):
        if cand.exists():
            for line in cand.read_text(encoding="utf-8", errors="replace").splitlines():
                if "=" in line:
                    k, _, val = line.partition("=")
                    initial[k.strip()] = val.strip()
            break
    param_path = OUT_ROOT / "param_list_reduced.txt"
    missing = 0
    with open(param_path, "w", encoding="utf-8") as f:
        for v in res["reduced_variables"]:
            val = initial.get(v["var"], "")
            if not val:
                missing += 1
            f.write(f"{v['var']}={val}\n")

    # 约减后网表
    net_path = OUT_ROOT / f"{in_path.stem}_reduced.netlist"
    net_path.write_text(emit_reduced_netlist(cir, res), encoding="utf-8")

    print("[4/4] 交付物已生成")
    print("-" * 64)
    print(f"识别与约减报告 : {report_path}")
    print(f"变量统计列表   : {csv_path}")
    print(f"约减后网表     : {net_path}")
    print(f"参数清单       : {param_path}"
          + (f"   （{missing} 个变量缺初值，需 extractcdfVal_0.txt 提供）" if missing else ""))
    print(f"推理链日志     : {trace_path}")
    print("-" * 64)
    print(f"原始优化变量 {res['raw_variable_count']} -> 约减后 "
          f"{res['reduced_variable_count']}")
    print(f"决策依据来源   : {reasoning.get('_source', '大模型生成并通过校验')}")
    print(f"\n拓扑概括：{reasoning.get('topology', '')}")


if __name__ == "__main__":
    main()
