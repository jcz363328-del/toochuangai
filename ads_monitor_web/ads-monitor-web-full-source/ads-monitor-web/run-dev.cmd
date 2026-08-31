@echo off
cd /d "%~dp0"
if not exist ".logs" mkdir ".logs"
npm.cmd run dev -- --host 0.0.0.0 --port 4173 --strictPort > ".logs\vite.out.log" 2> ".logs\vite.err.log"
