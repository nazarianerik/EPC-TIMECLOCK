@echo off
rem Stops the background server until the next reboot (or until you run restart_server.bat).
rem Windows will ask for admin permission.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0server_control.ps1" stop
