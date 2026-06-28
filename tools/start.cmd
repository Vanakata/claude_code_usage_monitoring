@echo off
REM Стартер за refresh loop-а (точката, която Task Scheduler вика).
REM Отива в repo root и пуска venv python-а на run.py, логва в work\run.log.
REM both = кара и Turing (serial), и SmallTV (HTTP) от един процес/едно /usage викане.
cd /d "%~dp0.."
set CLAUDE_USAGE_TARGET=both
REM set CLAUDE_USAGE_SMALLTV_IP=192.168.100.15
".venv\Scripts\python.exe" run.py >> "work\run.log" 2>&1
