@echo off
rem ============================================================
rem  Module 1 - one click runner
rem  PURE ASCII on purpose: CMD parses .bat with the ANSI codepage
rem  (GBK on zh-CN Windows), so non-ASCII bytes become garbage.
rem  Chinese text lives in run_module1.ps1 instead.
rem ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0agent"

rem ---- console UTF-8 so Chinese output is not garbled ----
chcp 65001 >nul 2>nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

rem ---- locate a WORKING python ------------------------------------
rem NOTE: do NOT trust "where python" - it often resolves to the
rem Microsoft Store stub (WindowsApps\python.exe) which only prints
rem an install hint. We must actually RUN each candidate.
set PY=
set CAND1=C:\Users\Lenovo\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe
set CAND2=%LOCALAPPDATA%\Programs\Python\Python312\python.exe
set CAND3=%LOCALAPPDATA%\Programs\Python\Python311\python.exe
set CAND4=C:\Python312\python.exe
set CAND5=C:\Python311\python.exe

for %%c in (python python3 "%CAND1%" "%CAND2%" "%CAND3%" "%CAND4%" "%CAND5%") do (
    if not defined PY (
        %%~c --version >nul 2>nul
        if !errorlevel! equ 0 set PY=%%~c
    )
)

if not defined PY (
    echo [FAILED] no working Python found.
    echo   tried: python python3
    echo          %CAND1%
    echo          %CAND2%
    echo   If you have Python elsewhere, edit PY= in this file,
    echo   or run run_module1.ps1 from PowerShell instead.
    pause
    exit /b 1
)

echo ============================================================
echo  Module 1 agent
echo  Python : %PY%
if defined DASHSCOPE_API_KEY (
    echo  API Key: SET - calls real Qwen3.8-Max
) else (
    echo  API Key: NOT SET - offline tool chain, same output
    echo           to use real model:  set DASHSCOPE_API_KEY=sk-xxx
)
echo ============================================================
echo.

rem ---- locate requirement file (wildcards only: no non-ASCII here) ----
rem Priority: module1\requirement.txt  >  ..\extracted\*\*.txt  >  ..\*.txt
set REQ=
if exist "..\requirement.txt" set REQ=..\requirement.txt

if not defined REQ (
    for /f "delims=" %%f in ('dir /b /s "..\..\extracted\*.txt" 2^>nul') do (
        if "!REQ!"=="" set REQ=%%f
    )
)
if not defined REQ (
    for /f "delims=" %%f in ('dir /b /s "..\extracted\*.txt" 2^>nul') do (
        if "!REQ!"=="" set REQ=%%f
    )
)
if not defined REQ (
    echo [WARN] requirement file not found.
    echo        put it at module1\requirement.txt and rerun.
    pause
    exit /b 1
)
echo Requirement: %REQ%
echo.

"%PY%" agent.py spec --input "%REQ%" --out spec_case1.json --trace-dir output

if %errorlevel% neq 0 (
    echo.
    echo [FAILED] send the error above to your teammate.
    pause
    exit /b 1
)

copy /y "spec_case1.json" "..\spec_case1.json" >nul

rem ---- report whether the real model was used ----
echo.
echo ============================================================
echo  DONE
echo    (1) ..\spec_case1.json          - Spec JSON
echo    (5) output\trace_spec.jsonl     - reasoning trace
echo.
findstr /c:"\"used_llm\": true" output\trace_spec.jsonl >nul 2>nul
if %errorlevel%==0 (
    echo  used_llm = true   - real Qwen3.8-Max was called
) else (
    echo  used_llm = false  - ran OFFLINE ^(no API key^)
    echo    set DASHSCOPE_API_KEY=sk-xxx  then rerun
)
echo ============================================================
pause
