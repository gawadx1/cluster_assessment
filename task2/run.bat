@echo off
setlocal
cd /d "%~dp0"

echo ==============================================================================
echo Task 2: Tomorrow's Dispatch Plan - Route Viewer
echo ==============================================================================
echo Running deterministic plan generator pipeline...
python generate_plans.py

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Plan generation failed. Please check Python environment.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo Launching local Route Viewer on http://localhost:8502 ...
echo Press Ctrl+C in this console to stop the server.
echo.

streamlit run app.py --server.port 8502 --server.headless false

pause
