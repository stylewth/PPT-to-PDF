@echo off
cd /d "%~dp0"
python .\app\backend\env_check.py
if errorlevel 1 (
  echo Environment check failed. Install missing dependencies or free port 8765 first.
  pause
  exit /b 1
)
echo Starting Slide2Study at http://127.0.0.1:8765
python .\app\backend\server.py
