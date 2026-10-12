# ============================================================
#  模块一 · 一键运行脚本（PowerShell 版）
#
#  用法（在 PowerShell 里，或右键「使用 PowerShell 运行」）：
#      powershell -ExecutionPolicy Bypass -File .\run_module1.ps1
#
#  本文件必须以 **UTF-8 with BOM** 保存：
#  Windows PowerShell 5.1 默认按 ANSI(GBK) 解析 .ps1，无 BOM 的中文会乱码报错。
# ============================================================

$ErrorActionPreference = "Continue"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$agentDir = Join-Path $here "agent"
Set-Location $agentDir

# ---- 找可用的 Python -------------------------------------------
# 注意：不能用 Get-Command python 判断！它常解析到微软商店占位存根
#       (WindowsApps\python.exe)，那个东西只会打印安装提示、跑不了代码。
#       必须**实际执行**并看退出码（存根返回非 0）。
$candidates = @(
    "python",
    "python3",
    "C:\Users\Lenovo\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe",
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"),
    "C:\Python312\python.exe",
    "C:\Python311\python.exe"
)
$py = $null
foreach ($c in $candidates) {
    if (-not $c) { continue }
    if ($c -match '[\\/]' -and -not (Test-Path $c)) { continue }
    $null = & $c --version 2>&1
    if ($LASTEXITCODE -eq 0) { $py = $c; break }
}
if (-not $py) {
    Write-Host "❌ 没找到可用的 Python。试过这些：" -ForegroundColor Red
    $candidates | Where-Object { $_ } | ForEach-Object { Write-Host "   $_" }
    Write-Host "   如果你装了 Python，请把路径加到本脚本的 `$candidates 里，"
    Write-Host "   或者直接用 run_module1.bat（它会自动找）。"
    exit 1
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " 模块一 · 智能体运行" -ForegroundColor Cyan
Write-Host " Python : $py"
if ($env:DASHSCOPE_API_KEY) {
    Write-Host " API Key: 已设置 → 将调用真实 Qwen3.8-Max" -ForegroundColor Green
} else {
    Write-Host " API Key: 未设置 → 走确定性工具链（产物完全一致）" -ForegroundColor Yellow
    Write-Host "          如需调用真实模型： `$env:DASHSCOPE_API_KEY = 'sk-你的Key'" -ForegroundColor Yellow
}
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# ---- 找需求文件（优先 module1\requirement.txt）------------------
$reqCandidates = @(
    (Join-Path $here "requirement.txt"),
    (Join-Path $here "..\extracted\赛题数据本身\全差分运放设计需求.txt"),
    (Join-Path $here "..\..\extracted\赛题数据本身\全差分运放设计需求.txt")
)
$req = $reqCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $req) {
    # 再兜一层：递归找 extracted 下任意 .txt
    $hit = Get-ChildItem -Path (Join-Path $here "..") -Filter "*.txt" -Recurse `
                          -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($hit) { $req = $hit.FullName }
}
if (-not $req) {
    Write-Host "❌ 找不到需求文件，试过这些路径：" -ForegroundColor Red
    $reqCandidates | ForEach-Object { Write-Host "   $_" }
    Write-Host "   请把需求文本放到 module1\requirement.txt 后重试。"
    exit 1
}
Write-Host "需求文件: $req`n" -ForegroundColor Gray

# ---- 让 Python 的输出用 UTF-8，避免中文在 GBK 控制台里乱码 ----
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
try { [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false) } catch { }

# ---- 跑模块一 ---------------------------------------------------
& $py agent.py spec --input $req --out spec_case1.json --trace-dir output

if ($LASTEXITCODE -ne 0) {
    Write-Host "`n❌ 运行失败，把上面的报错发出来排查。" -ForegroundColor Red
    exit 1
}

# ---- 结果复制到 module1 根目录（交付物①的位置）------------------
Copy-Item "spec_case1.json" (Join-Path $here "spec_case1.json") -Force

# ---- 汇总 -------------------------------------------------------
$trace = "output\trace_spec.jsonl"
$usedLlm = "unknown"
if (Test-Path $trace) {
    $firstLine = Get-Content $trace -TotalCount 1 -Encoding UTF8
    if ($firstLine -match '"used_llm":\s*(true|false)') { $usedLlm = $Matches[1] }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " 完成！交付物：" -ForegroundColor Green
Write-Host "   ① $(Join-Path $here 'spec_case1.json')"
Write-Host "   ⑤ $(Join-Path $agentDir $trace)"
Write-Host ""
if ($usedLlm -eq "true") {
    Write-Host " used_llm = true  ✅ 已调用真实 Qwen3.8-Max" -ForegroundColor Green
} else {
    Write-Host " used_llm = $usedLlm  ⚠️ 未调用模型（离线工具链）" -ForegroundColor Yellow
    Write-Host "   设上 Key 后重跑即可： `$env:DASHSCOPE_API_KEY = 'sk-你的Key'" -ForegroundColor Yellow
}
Write-Host "============================================================" -ForegroundColor Cyan
