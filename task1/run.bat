@echo off
setlocal
cd /d "%~dp0"

echo === Task 1: Cluster Assessment ===
echo.

if exist "%LocalAppData%\Programs\Python\Python37\python.exe" (
  set "PY=%LocalAppData%\Programs\Python\Python37\python.exe"
) else if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
  set "PY=%LocalAppData%\Programs\Python\Python312\python.exe"
) else (
  set "PY=python"
)

echo [1/3] Checking offline Python dependencies...
%PY% -c "import pandas, flask, rapidfuzz" >nul 2>&1
if %ERRORLEVEL% neq 0 (
  echo Required packages are missing. Install them before running this offline assessment.
  pause
  exit /b 1
)
for /f "delims=" %%A in ('%PY% -c "import struct; print(struct.calcsize('P')*8)"') do set "PY_BITS=%%A"
if not "%PY_BITS%"=="64" (
  echo Unsupported Python architecture: %PY_BITS%-bit. Please use 64-bit Python.
  pause
  exit /b 1
)

echo [2/3] Running data pipeline...
cd /d "%~dp0"
set PYTHONPATH=%~dp0
if not exist output mkdir output
del /q output\*.json output\*.csv >nul 2>&1
%PY% run_pipeline.py
if %ERRORLEVEL% neq 0 (
  echo Pipeline failed.
  pause
  exit /b 1
)

echo [3/3] Starting website on http://127.0.0.1:5000 ...
set PYTHONPATH=%~dp0
cd web
start "" http://127.0.0.1:5000
%PY% app.py

pause
