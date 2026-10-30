@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto install
where py >nul 2>nul
if errorlevel 1 goto usepython
py -3 -m venv .venv
goto checkvenv
:usepython
python -m venv .venv
:checkvenv
if not exist ".venv\Scripts\python.exe" (
  echo Install Python 3.10 or newer, then run this file again.
  pause
  exit /b 1
)
:install
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo Package installation did not finish. Check your internet connection.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" run_demo.py
if errorlevel 1 pause
