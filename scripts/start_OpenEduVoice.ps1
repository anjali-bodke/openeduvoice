$ErrorActionPreference = "Stop"

Write-Host "RUNNING PS1: $PSCommandPath" -ForegroundColor Magenta

# Locate Python 3.11
$py311 = py -3.11 -c "import sys; print(sys.executable)"
$py311 = $py311.Trim()

if (-not (Test-Path $py311)) {
    throw "Python 3.11 not found"
}

Write-Host "Using Python: $py311"

# Repo root
$repoRoot = Split-Path $PSScriptRoot -Parent
Set-Location $repoRoot
Write-Host "Repo root: $repoRoot"

# Create venv (THIS IS THE CRITICAL LINE)
$venvPath = Join-Path $repoRoot "venv"
if (-not (Test-Path $venvPath)) {
    Write-Host "Creating venv..."
    & $py311 -m venv $venvPath
}

$venvPy = Join-Path $venvPath "Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    throw "venv was not created"
}

Write-Host "Venv OK: $venvPy"

# Upgrade pip
& $venvPy -m pip install --upgrade pip setuptools wheel

# Install deps
& $venvPy -m pip install -r requirements.txt
& $venvPy -m pip install -e ".[ml,tts,cuda12]"

# Run app
& $venvPy -m OpenEduVoice
