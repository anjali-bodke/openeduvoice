Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Info($m) { Write-Host "[INFO]  $m" }
function Warn($m) { Write-Host "[WARN]  $m" -ForegroundColor Yellow }
function Err ($m) { Write-Host "[ERROR] $m" -ForegroundColor Red }

$RepoRoot  = Resolve-Path (Join-Path $PSScriptRoot "..")
$VenvDir   = Join-Path $RepoRoot "venv"

$FfmpegBin = Join-Path $RepoRoot "tools\ffmpeg\bin"
$ffmpegExe = Join-Path $FfmpegBin "ffmpeg.exe"
$ffprobeExe = Join-Path $FfmpegBin "ffprobe.exe"

function VenvPython() {
  $py = Join-Path $VenvDir "Scripts\python.exe"
  if (-not (Test-Path $py)) { throw "venv not found. Run install_OpenEduVoice.bat first." }
  return $py
}

function Add-ToPath([string]$dir) {
  if (-not (Test-Path $dir)) { throw "PATH add failed, dir not found: $dir" }
  $parts = $env:Path.Split(";") | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
  if ($parts -contains $dir) { return }
  $env:Path = "$dir;$env:Path"
}

function Ensure-FFmpegAvailable() {
  if ((Test-Path $ffmpegExe) -and (Test-Path $ffprobeExe)) {
    Add-ToPath $FfmpegBin
    Info "Using local FFmpeg: $FfmpegBin"
    return
  }
  throw "FFmpeg not installed locally. Run install_OpenEduVoice.bat first."
}

function SmokeCheckImports([string]$py) {
  Info "Checking OpenEduVoice import..."
  & $py -c "import OpenEduVoice; print('OpenEduVoice import OK')" | Out-Host
}

function Launch([string]$py) {
  Info "Launching GUI..."
  & $py -m OpenEduVoice
}

try {
  Push-Location $RepoRoot

  $py = VenvPython
  Ensure-FFmpegAvailable
  SmokeCheckImports $py
  Launch $py

  exit 0
}
catch {
  Err $_.Exception.Message
  Warn "If this is a fresh machine, run: install_OpenEduVoice.bat"
  exit 1
}
finally {
  Pop-Location | Out-Null
}
