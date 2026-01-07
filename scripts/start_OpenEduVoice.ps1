$ErrorActionPreference = "Stop"

try {
  # Always run from repo root
  $repoRoot = Split-Path -Parent $PSScriptRoot
  Set-Location $repoRoot

  $venvActivate = Join-Path $repoRoot ".venv\Scripts\Activate.ps1"
  if (-not (Test-Path $venvActivate)) {
    throw "Missing venv activation script: $venvActivate"
  }

  & $venvActivate

  # Install only if module isn't importable in this venv
  $installed = python -c "import importlib.util; print('1' if importlib.util.find_spec('OpenEduVoice') else '0')"
  if ($installed -ne "1") {
    Write-Host "[Setup] Installing OpenEduVoice (editable)..." -ForegroundColor Cyan
    python -m pip install --upgrade pip setuptools wheel
    python -m pip install -e .
    Write-Host "[Setup] Done." -ForegroundColor Green
  }

  python -m OpenEduVoice
}
catch {
  Write-Host "[Error] OpenEduVoice failed to start." -ForegroundColor Red
  Write-Host $_.Exception.Message -ForegroundColor Red
  pause
  exit 1
}
