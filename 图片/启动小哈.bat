@echo off
setlocal
cd /d "%~dp0"

start "XiaoHa Watchdog" powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Minimized -File "%~dp0xiaoha_watchdog.ps1" -OpenBrowser
