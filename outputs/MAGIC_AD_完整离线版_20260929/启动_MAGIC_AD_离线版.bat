@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul && (py -3 start_offline.py & goto :eof)
where python >nul 2>nul && (python start_offline.py & goto :eof)
echo 未找到 Python，无法启动本地网页服务。
echo 请安装 Python 3 后重试。
pause
