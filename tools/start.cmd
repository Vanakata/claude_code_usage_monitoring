@echo off
REM Стартер за refresh loop-а (точката, която Task Scheduler вика).
REM Отива в repo root и пуска venv python-а на run.py, логва в work\run.log.
cd /d "%~dp0.."
".venv\Scripts\python.exe" run.py >> "work\run.log" 2>&1
