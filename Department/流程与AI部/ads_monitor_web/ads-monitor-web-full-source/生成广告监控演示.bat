@echo off
chcp 65001 >nul
setlocal
pushd "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo 未找到 .venv\Scripts\python.exe，请先安装 Python 运行环境。
  set "task_exit_code=2"
  goto :finish
)

".venv\Scripts\python.exe" "sellfox_ads_monitor.py" --demo --preview ^
  --database "data\sellfox_ads_demo.sqlite3" ^
  --output-dir "outputs\ads_monitor_demo"
set "task_exit_code=%errorlevel%"

:finish
echo.
if not "%task_exit_code%"=="0" (
  echo 演示报表生成失败。
) else (
  echo 演示报表已生成到 outputs\ads_monitor_demo 下的范围子目录
)
pause
popd
exit /b %task_exit_code%
