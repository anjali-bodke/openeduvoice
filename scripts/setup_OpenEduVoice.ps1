$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
  throw "Venv not found. Create it first: python -m venv .venv"
}

& $venvPython -m pip install --upgrade pip setuptools wheel
& $venvPython -m pip install -e .
Write-Host "Setup complete. Start with: start_OpenEduVoice.bat"
