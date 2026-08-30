@echo off
setlocal
cd /d "%~dp0"

echo ===================================================
echo === Task 1: Cluster Assessment Streamlit Dashboard
echo ===================================================
echo.

if exist "%LocalAppData%\Programs\Python\Python37\python.exe" (
  set "PY=%LocalAppData%\Programs\Python\Python37\python.exe"
) else if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
  set "PY=%LocalAppData%\Programs\Python\Python312\python.exe"
) else (
  set "PY=python"
)

echo [1/3] Checking offline Python dependencies (pandas, rapidfuzz, streamlit)...
%PY% -c "import pandas, rapidfuzz, streamlit" >nul 2>&1
if %ERRORLEVEL% neq 0 (
  echo Required packages are missing. Please ensure pandas, rapidfuzz, and streamlit are installed.
  pause
  exit /b 1
)
for /f "delims=" %%A in ('%PY% -c "import struct; print(struct.calcsize('P')*8)"') do set "PY_BITS=%%A"
if not "%PY_BITS%"=="64" (
  echo Unsupported Python architecture: %PY_BITS%-bit. Please use 64-bit Python.
  pause
  exit /b 1
)

echo [2/3] Running deterministic data pipeline...
cd /d "%~dp0"
set PYTHONPATH=%~dp0
if not exist output mkdir output
del /q output\*.json output\*.csv >nul 2>&1
%PY% run_pipeline.py
if %ERRORLEVEL% neq 0 (
  echo Pipeline execution failed.
  pause
  exit /b 1
)

echo [3/3] Launching Streamlit dashboard on http://localhost:8501 ...
set PYTHONPATH=%~dp0
%PY% -m streamlit run app.py --server.port 8501 --server.headless false --browser.gatherUsageStats false

pause
