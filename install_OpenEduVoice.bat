@echo off
setlocal

REM Always run from repo root
cd /d "%~dp0"

REM Optional: allow "cuda" as first argument.
REM Usage:
REM   install_OpenEduVoice.bat        -> CPU (default)
REM   install_OpenEduVoice.bat cuda   -> GPU/CUDA path
set "ACCEL=%~1"
if "%ACCEL%"=="" set "ACCEL=cpu"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_OpenEduVoice.ps1" -Accel "%ACCEL%"
set exitcode=%errorlevel%

if not %exitcode%==0 (
  echo.
  echo [ERROR] Installation failed with exit code %exitcode%.
  pause
  exit /b %exitcode%
)

echo.
echo [INFO] Installation completed successfully.
echo [INFO] You can now start the app using: run_OpenEduVoice.bat
pause
exit /b 0
