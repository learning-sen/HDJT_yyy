# -*- coding: utf-8 -*-
"""
模块一：自然语言 Spec 解析智能体
运行方式（必须先激活虚拟环境，见教程第 3 步）：
    python agent.py                              # 用默认的需求文件
    python agent.py "C:\\path\\需求.txt"          # 指定需求文件
    python agent.py --check                       # 只检查环境，不调模型
"""
import json
import os
import re
import sys
import time
from pathlib import Path

from openai import OpenAI

HERE = Path(__file__).resolve().parent

# 赛题提供的需求文件（默认输入）
DEFAULT_INPUT = HERE.parent.parent / "extracted" / "赛题数据本身" / "全差分运放设计需求.txt"

# 指标 -> 默认单位（模型漏了单位时按这个补，补了会记进日志）
UNIT_DEFAULT = {
    "DC_Gain": "dB", "UGB": "MHz", "Phase_Margin": "deg", "Gain_Margin": "dB",
    "I_OPA": "mA", "Area": "um^2", "Slew_Rate": "V/us", "Power": "mW",
    "Output_Swing": "V", "Input_CM_Range": "V", "CMRR": "dB", "PSRR": "dB",
    "Noise": "nV/sqrt(Hz)", "Offset": "mV",
}


def load_config() -> dict:
    with open(HERE / "config.json", "r", encoding="utf-8") as f:
        return json.load(f)


def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8").strip()


def strip_code_fence(text: str) -> str:
    """模型有时会把 JSON 包在 ```json ... ``` 里，剥掉它。"""
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    i, j = t.find("{"), t.rfind("}")
    if i != -1 and j > i:
        t = t[i:j + 1]
    return t


def check_spec(spec: dict) -> list:
    """检查评分要求的字段是否齐全，返回缺失项列表（空=通过）。"""
    missing = []
    for k in ("design_type", "constraints", "objectives", "pvt_condition", "worst_case"):
        if k not in spec:
            missing.append(k)
    for i, c in enumerate(spec.get("constraints") or []):
        for k in ("name", "op", "value", "unit", "type", "priority"):
            if k not in c:
                missing.append(f"constraints[{i}].{k}")
    for i, o in enumerate(spec.get("objectives") or []):
        for k in ("name", "direction", "unit", "priority"):
            if k not in o:
                missing.append(f"objectives[{i}].{k}")
    return missing


def autofill(spec: dict) -> list:
    """把模型漏掉的字段补上，返回补了哪些（会写进日志，报告里要交代）。"""
    filled = []
    for i, c in enumerate(spec.get("constraints") or []):
        if "unit" not in c:
            c["unit"] = UNIT_DEFAULT.get(c.get("name"), "")
            filled.append(f"constraints[{i}].unit -> {c['unit']}")
        if "type" not in c:
            c["type"] = "hard"
            filled.append(f"constraints[{i}].type -> hard")
        if "priority" not in c:
            c["priority"] = i + 1
            filled.append(f"constraints[{i}].priority -> {i + 1}")
    for i, o in enumerate(spec.get("objectives") or []):
        if "unit" not in o:
            o["unit"] = UNIT_DEFAULT.get(o.get("name"), "")
            filled.append(f"objectives[{i}].unit -> {o['unit']}")
        if "priority" not in o:
            o["priority"] = i + 1
            filled.append(f"objectives[{i}].priority -> {i + 1}")
    return filled


def ask_model(client, cfg, system_prompt, requirement, feedback=""):
    user = f"【设计需求】\n{requirement}"
    if feedback:
        user += f"\n\n【上一次输出不合法，请修正后重新只输出 JSON】\n{feedback}"
    resp = client.chat.completions.create(
        model=cfg["model"],
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user},
        ],
        temperature=cfg.get("temperature", 0.2),
        max_tokens=cfg.get("max_tokens", 4096),
        timeout=cfg.get("timeout_s", 120),
    )
    return resp.choices[0].message.content or ""


def resolve_input() -> Path:
    """取需求文件路径：忽略 --check 这类开关，只认第一个非 -- 开头的参数。"""
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    return Path(args[0]).resolve() if args else DEFAULT_INPUT


def preflight(cfg, in_path: Path) -> int:
    """跑模型之前先自检环境：解释器、依赖、Key、需求文件。"""
    print(f"Python    : {sys.executable}")
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    print(f"虚拟环境  : {'是 (.venv 生效)' if in_venv else '否（正在用系统 Python！请先激活 .venv）'}")
    print(f"模型      : {cfg['model']}")
    print(f"接口      : {cfg['base_url']}")

    key = os.getenv(cfg["api_key_env"], "")
    if not key:
        print(f"[错误] 环境变量 {cfg['api_key_env']} 没设置。")
        print('请在 PowerShell 里执行：$env:DASHSCOPE_API_KEY = "sk-你的Key"')
        return 1
    print(f"API Key   : 已设置（长度 {len(key)}，不打印内容）")

    if not in_path.exists():
        print(f"[错误] 找不到需求文件：{in_path}")
        return 1
    print(f"需求文件  : {in_path}")
    return 0


def main():
    cfg = load_config()
    in_path = resolve_input()

    # 0) 环境自检
    if preflight(cfg, in_path) != 0:
        sys.exit(1)
    if "--check" in sys.argv:
        print("\n[自检通过] 环境没问题，去掉 --check 就能真正调用模型。")
        return

    key = os.getenv(cfg["api_key_env"])
    client = OpenAI(api_key=key, base_url=cfg["base_url"])
    system_prompt = read_text((HERE / cfg["prompt_file"]).resolve())

    # 1) 取输入
    requirement = read_text(in_path)
    print("-" * 60)

    # 2) 调用 + 校验 + 重试
    out_dir = (HERE / cfg["output_dir"]).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    trace_path = out_dir / f"trace_{stamp}.jsonl"

    spec, filled, missing, raw = None, [], [], ""
    for attempt in range(1, cfg.get("max_retries", 3) + 1):
        print(f"[第 {attempt} 次调用] ...")
        try:
            raw = ask_model(client, cfg, system_prompt, requirement,
                            feedback="; ".join(missing))
        except Exception as e:
            print(f"  调用失败：{e}")
            with open(trace_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"attempt": attempt, "error": str(e)},
                                   ensure_ascii=False) + "\n")
            time.sleep(2)
            continue

        with open(trace_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "attempt": attempt, "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "model": cfg["model"], "input": requirement, "raw_output": raw,
            }, ensure_ascii=False) + "\n")

        try:
            spec = json.loads(strip_code_fence(raw))
        except json.JSONDecodeError as e:
            missing = [f"输出不是合法 JSON：{e}"]
            print(f"  JSON 解析失败：{e}")
            continue

        missing = check_spec(spec)
        if not missing:
            break
        print(f"  缺字段：{missing}")

    if spec is None or missing:
        print("\n[失败] 重试用完仍未拿到完整 JSON，请把上面的错误信息发我。")
        sys.exit(1)

    filled = autofill(spec)

    # 3) 落盘
    spec_file = out_dir / f"spec_{stamp}.json"
    spec_file.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    # 同时写一份固定名，方便直接当交付物
    (out_dir / "spec_case1.json").write_text(
        json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    (HERE.parent / "spec_case1.json").write_text(
        json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")

    if filled:
        with open(trace_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"autofill": filled}, ensure_ascii=False) + "\n")

    print("-" * 60)
    print(f"[成功] 解析结果：{spec_file}")
    print(f"       推理日志：{trace_path}")
    if filled:
        print(f"       自动补全了 {len(filled)} 个字段（已记入日志）")
    print("\n--- JSON 预览 ---")
    print(json.dumps(spec, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
