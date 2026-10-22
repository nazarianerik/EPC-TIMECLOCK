@echo off
rem Keeps the time clock server running: if it ever stops, it starts again after 5 seconds.
rem Task Scheduler runs this at boot (set up by install_autostart.bat). You don't run it yourself.
cd /d "%~dp0.."
if not exist data mkdir data
set PYTHONUNBUFFERED=1

:loop
echo [%date% %time%] Starting server>> data\server.log
".venv\Scripts\python.exe" serve.py >> data\server.log 2>&1
echo [%date% %time%] Server stopped (exit code %errorlevel%). Restarting in 5 seconds...>> data\server.log
rem "ping" is used as a 5 second pause because "timeout" doesn't work in a background task.
ping -n 6 127.0.0.1 > nul
goto loop
