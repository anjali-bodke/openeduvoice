@echo off
setlocal

REM Pass through args to PowerShell (e.g., --reinstall)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_OpenEduVoice.ps1" %*
pause