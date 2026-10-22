@echo off
rem One-time setup: installs the Python libraries, runs the tests, and sets the admin password.
rem Double-click this file, or run it from a terminal.
cd /d "%~dp0.."
echo.
echo === TimeClock first-time setup ===
echo Folder: %cd%
echo.

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo Python was not found. Install it from https://www.python.org/downloads/
    echo and tick "Add python.exe to PATH" during install. Then run this again.
    goto fail
)

if not exist .venv\Scripts\python.exe (
    echo Creating the .venv folder for this project's libraries...
    %PY% -m venv .venv || goto fail
)

echo Installing libraries (Flask, Waitress)...
.venv\Scripts\python -m pip install --disable-pip-version-check -r requirements.txt || goto fail

echo.
echo Running automated tests...
.venv\Scripts\python -m unittest discover -s tests -v || goto fail

echo.
.venv\Scripts\python set_password.py || goto fail

echo.
echo === Setup complete ===
echo Next: double-click windows\test_run.bat to try it, or follow SETUP.md.
echo.
pause
exit /b 0

:fail
echo.
echo *** Setup did not finish. Read the messages above for the reason. ***
pause
exit /b 1
