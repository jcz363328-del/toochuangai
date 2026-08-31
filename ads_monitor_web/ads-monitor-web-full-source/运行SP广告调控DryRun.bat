@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" "sellfox_sp_adjust_demo.py" --verify-mcp
pause
