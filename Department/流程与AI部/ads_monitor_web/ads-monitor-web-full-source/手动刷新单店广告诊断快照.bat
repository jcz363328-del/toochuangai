@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" sellfox_ad_diagnostic_refresh.py %*
) else (
  python sellfox_ad_diagnostic_refresh.py %*
)
pause
