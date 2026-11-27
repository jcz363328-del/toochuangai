@echo off
chcp 65001 >nul
setlocal
pushd "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo 未找到 .venv\Scripts\python.exe，请先安装 Python 运行环境。
  set "task_exit_code=2"
  goto :finish
)

".venv\Scripts\python.exe" "sellfox_ads_monitor.py" --once
set "task_exit_code=%errorlevel%"

:finish
echo.
if not "%task_exit_code%"=="0" (
  echo 广告监控运行失败，请查看 %%LOCALAPPDATA%%\SellfoxTK\logs\sellfox_ads_monitor.log
) else (
  echo 广告监控完成，网页数据已更新；结果位于 outputs\ads_monitor 下的范围子目录
)
pause
popd
exit /b %task_exit_code%
