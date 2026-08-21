@echo off
REM Стартер за refresh loop-а (точката, която Task Scheduler вика).
REM Отива в repo root и пуска venv python-а на run.py, логва в work\run.log.
REM
REM Target приоритет: аргумент %1 (от autostart task) > CLAUDE_USAGE_TARGET env > hostname switch.
REM Hostname switch — един файл, два хоста:
REM   VANAKATADESKTOP (личен PC) -> SmallTV (HTTP/WiFi)
REM   всички други (вкл. служебен лаптоп) -> Turing (serial)
REM SmallTV-то е last-write-wins — само ЕДИН хост да го кара по едно и също време.
cd /d "%~dp0.."
REM UTF-8 stdout — иначе кирилицата в run.log излиза като \uXXXX / '?' mojibake.
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
if not "%~1"=="" set CLAUDE_USAGE_TARGET=%~1
if "%CLAUDE_USAGE_TARGET%"=="" (
    if /i "%COMPUTERNAME%"=="VANAKATADESKTOP" (
        set CLAUDE_USAGE_TARGET=smalltv
    ) else (
        set CLAUDE_USAGE_TARGET=turing
    )
)
REM CLAUDE_USAGE_SMALLTV_IP НЕ се закова — display_smalltv.py auto-discover-ва
REM устройството по мрежата. Задай env var само ако искаш да прескочиш scan-а.
REM Log rotation: над ~5MB -> завърти в run.log.1 (иначе расте вечно)
for %%A in ("work\run.log") do if %%~zA gtr 5242880 move /y "work\run.log" "work\run.log.1" >nul
".venv\Scripts\python.exe" run.py >> "work\run.log" 2>&1
