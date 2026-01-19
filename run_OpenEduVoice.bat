@echo off
setlocal

REM Always run from repo root
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_OpenEduVoice.ps1"
set exitcode=%errorlevel%

if not %exitcode%==0 (
  echo.
  echo [ERROR] App start failed with exit code %exitcode%.
  pause
  exit /b %exitcode%
)

exit /b 0
