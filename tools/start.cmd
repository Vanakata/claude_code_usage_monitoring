@echo off
REM Стартер за refresh loop-а (точката, която Task Scheduler вика).
REM Отива в repo root и пуска venv python-а на run.py, логва в work\run.log.
REM
REM Hostname-based target switch — един файл, два хоста:
REM   VANAKATADESKTOP (личен PC) -> SmallTV (HTTP/WiFi)
REM   всички други (вкл. служебен лаптоп) -> Turing only (serial)
REM SmallTV-то е last-write-wins; затова САМО единият хост го кара по едно и също време.
cd /d "%~dp0.."
if /i "%COMPUTERNAME%"=="VANAKATADESKTOP" (
    set CLAUDE_USAGE_TARGET=smalltv
) else (
    set CLAUDE_USAGE_TARGET=turing
)
set CLAUDE_USAGE_SMALLTV_IP=192.168.100.3
REM Log rotation: над ~5MB -> завърти в run.log.1 (иначе расте вечно)
for %%A in ("work\run.log") do if %%~zA gtr 5242880 move /y "work\run.log" "work\run.log.1" >nul
".venv\Scripts\python.exe" run.py >> "work\run.log" 2>&1
