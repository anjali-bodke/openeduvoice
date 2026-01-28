@echo off
setlocal

REM Always run from repo root
cd /d "%~dp0"

REM One-click default: auto-detect (NVIDIA GPU + driver -> CUDA, else CPU)
REM Optional override:
REM   install_OpenEduVoice.bat cpu
REM   install_OpenEduVoice.bat cuda
set "ACCEL=%~1"
if "%ACCEL%"=="" set "ACCEL=auto"

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
