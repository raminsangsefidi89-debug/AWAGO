@echo off
rem AWAGO launcher for Windows.
rem Usage: run.bat [--no-browser] [--port 8001] ...
setlocal
cd /d "%~dp0"

set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py -3"
if not defined PY_CMD where python >nul 2>nul && set "PY_CMD=python"

if not defined PY_CMD (
  echo ERROR: Python 3.10+ is required but was not found.
  echo Install it from https://python.org and make sure "Add python.exe to PATH" is checked.
  exit /b 1
)

%PY_CMD% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
  echo ERROR: Python 3.10+ is required. Please upgrade Python from https://python.org
  exit /b 1
)

%PY_CMD% run.py %*
endlocal
