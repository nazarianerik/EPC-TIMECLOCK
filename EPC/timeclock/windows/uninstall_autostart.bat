@echo off
rem Stops the server and removes the auto-start and firewall rule. Your data is kept.
rem Windows will ask for admin permission.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0server_control.ps1" uninstall
