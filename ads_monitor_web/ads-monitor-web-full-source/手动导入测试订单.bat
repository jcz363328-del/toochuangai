@echo off
chcp 65001 >nul
pushd "%~dp0"
".venv\Scripts\python.exe" "sellfox_import.py" --once --date-type purchase --lookback-days 7
set "task_exit_code=%errorlevel%"
echo.
if not "%task_exit_code%"=="0" (
  echo 导入失败，请查看上面的错误或本地日志。
) else (
  echo 导入完成。
)
pause
popd
exit /b %task_exit_code%
