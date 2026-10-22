@echo off
rem Runs the server in this window so you can try it out. Close the window (or Ctrl+C) to stop.
rem For 24/7 running, use install_autostart.bat instead.
cd /d "%~dp0.."
.venv\Scripts\python serve.py
pause
