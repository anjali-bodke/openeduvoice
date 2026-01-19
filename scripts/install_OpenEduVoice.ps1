Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Info($m) { Write-Host "[INFO]  $m" }
function Warn($m) { Write-Host "[WARN]  $m" -ForegroundColor Yellow }
function Err ($m) { Write-Host "[ERROR] $m" -ForegroundColor Red }

$RepoRoot   = Resolve-Path (Join-Path $PSScriptRoot "..")
$VenvDir    = Join-Path $RepoRoot "venv"
$ToolsDir   = Join-Path $RepoRoot "tools"
$FfmpegDir  = Join-Path $ToolsDir "ffmpeg"
$FfmpegBin  = Join-Path $FfmpegDir "bin"
$FfmpegZip  = Join-Path $FfmpegDir "ffmpeg-release-essentials.zip"

$ReqCore = Join-Path $RepoRoot "requirements.txt"
$ReqML   = Join-Path $RepoRoot "requirements-ml.txt"
$ReqTTS  = Join-Path $RepoRoot "requirements-tts.txt"
$PyProj  = Join-Path $RepoRoot "pyproject.toml"

$FfmpegUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

function Test-Command([string]$name) {
  return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Ensure-Tls12() {
  try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}
}

function Ensure-Python311() {
  # Python is a prerequisite (Option B), but we still validate clearly.
  if (-not (Test-Command "python")) {
    throw "Python not found on PATH. Install Python 3.11 and ensure it's added to PATH."
  }
  $ver = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
  if ($ver -ne "3.11") {
    throw "Python 3.11 is required. Found: $ver"
  }
  Info "Python OK: $ver"
}

function Ensure-Venv() {
  if (-not (Test-Path $VenvDir)) {
    Info "Creating venv..."
    & python -m venv $VenvDir
  } else {
    Info "venv already exists."
  }
}

function VenvPython() {
  $py = Join-Path $VenvDir "Scripts\python.exe"
  if (-not (Test-Path $py)) { throw "venv python not found: $py" }
  return $py
}

function Ensure-FFmpegLocal() {
  # If ffmpeg is already on PATH we still bundle locally (optional).
  # We only bundle if local bin is missing.
  $ffmpegExe = Join-Path $FfmpegBin "ffmpeg.exe"
  $ffprobeExe = Join-Path $FfmpegBin "ffprobe.exe"

  if ((Test-Path $ffmpegExe) -and (Test-Path $ffprobeExe)) {
    Info "Local FFmpeg already present: $FfmpegBin"
    return
  }

  Warn "Local FFmpeg not found. Downloading and extracting..."

  New-Item -ItemType Directory -Force -Path $FfmpegDir | Out-Null
  New-Item -ItemType Directory -Force -Path $FfmpegBin | Out-Null

  if (-not (Test-Path $FfmpegZip)) {
    Ensure-Tls12
    Info "Downloading FFmpeg zip..."
    Invoke-WebRequest -Uri $FfmpegUrl -OutFile $FfmpegZip -UseBasicParsing
    Info "Downloaded: $FfmpegZip"
  } else {
    Info "FFmpeg zip already exists: $FfmpegZip"
  }

  $tmpExtract = Join-Path $FfmpegDir "_tmp_extract"
  if (Test-Path $tmpExtract) { Remove-Item -Recurse -Force $tmpExtract }
  New-Item -ItemType Directory -Force -Path $tmpExtract | Out-Null

  Info "Extracting FFmpeg..."
  Expand-Archive -Path $FfmpegZip -DestinationPath $tmpExtract -Force

  $foundFfmpeg = Get-ChildItem -Path $tmpExtract -Recurse -Filter "ffmpeg.exe" -File | Select-Object -First 1
  $foundFfprobe = Get-ChildItem -Path $tmpExtract -Recurse -Filter "ffprobe.exe" -File | Select-Object -First 1

  if (-not $foundFfmpeg -or -not $foundFfprobe) {
    throw "FFmpeg extracted but ffmpeg.exe/ffprobe.exe not found."
  }

  Copy-Item -Force $foundFfmpeg.FullName $ffmpegExe
  Copy-Item -Force $foundFfprobe.FullName $ffprobeExe

  Remove-Item -Recurse -Force $tmpExtract

  Info "Local FFmpeg ready: $FfmpegBin"
}

function Ensure-RequirementsFiles() {
  foreach ($f in @($ReqCore, $ReqML, $ReqTTS, $PyProj)) {
    if (-not (Test-Path $f)) { throw "Missing required file: $f" }
  }
}

function Install-PythonDeps() {
  $py = VenvPython

  Info "Upgrading pip..."
  & $py -m pip install --upgrade pip

  Info "Installing core requirements..."
  & $py -m pip install -r $ReqCore

  Info "Installing ML requirements..."
  & $py -m pip install -r $ReqML

  Info "Installing TTS requirements..."
  & $py -m pip install -r $ReqTTS

  Info "Installing project (editable)..."
  & $py -m pip install -e .

  Info "Running pip check..."
  & $py -m pip check
}

try {
  Push-Location $RepoRoot

  Ensure-Python311
  Ensure-RequirementsFiles
  Ensure-FFmpegLocal
  Ensure-Venv
  Install-PythonDeps

  Info "Install step finished."
  exit 0
}
catch {
  Err $_.Exception.Message
  exit 1
}
finally {
  Pop-Location | Out-Null
}