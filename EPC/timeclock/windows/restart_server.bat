@echo off
rem Restarts the background server (e.g. after updating code or editing data\config.json).
rem Windows will ask for admin permission.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0server_control.ps1" restart
