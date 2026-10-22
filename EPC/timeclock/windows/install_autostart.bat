@echo off
rem Starts the server now and on every boot. Run once after first_time_setup.bat.
rem Windows will ask for admin permission.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0server_control.ps1" install
