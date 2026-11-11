@echo off
title OpenEduVoice - Run
cd /d "%~dp0.."

echo ==========================================
echo   OpenEduVoice Launcher
echo ==========================================
echo.

REM --- Check venv ---
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] OpenEduVoice is not installed.
    echo.
    echo Please run:
    echo   install_OpenEduVoice.bat
    echo.
    pause
    exit /b 1
)

echo [INFO] Virtual environment found.
echo [INFO] Starting OpenEduVoice...
echo.

REM --- Run PowerShell runner ---
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_OpenEduVoice.ps1"
set "exitcode=%errorlevel%"

echo.
echo ==========================================
echo OpenEduVoice finished with exit code %exitcode%.
echo ==========================================
pause
exit /b %exitcode%
