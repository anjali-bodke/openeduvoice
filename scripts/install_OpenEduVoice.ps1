param(
  [ValidateSet("cpu","cuda")]
  [string]$Accel = "cpu"
)

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

function Remove-CudaWheels([string]$py) {
  Info "Ensuring CPU mode: removing CUDA runtime wheels if present..."
  $pkgs = @("nvidia-cuda-runtime-cu12","nvidia-cublas-cu12","nvidia-cudnn-cu12")
  foreach ($p in $pkgs) {
    try {
      & $py -m pip uninstall -y $p | Out-Null
    } catch {}
  }
}

function Install-CudaWheels([string]$py) {
  Info "Installing CUDA runtime wheels (only for CUDA mode)..."
  & $py -m pip install nvidia-cuda-runtime-cu12 nvidia-cublas-cu12 nvidia-cudnn-cu12
}

function Force-InstallTorch([string]$py, [string]$mode) {
  # We force torch install AFTER requirements to end up in a consistent state.
  if ($mode -eq "cpu") {
    Info "Forcing CPU PyTorch from official CPU index..."
    & $py -m pip install --upgrade --force-reinstall torch torchaudio --index-url https://download.pytorch.org/whl/cpu
  } else {
    # NOTE: using cu121 index. This is a packaging choice; it assumes NVIDIA driver supports CUDA 12.1 wheels.
    Info "Forcing CUDA PyTorch from official cu121 index..."
    & $py -m pip install --upgrade --force-reinstall torch torchaudio --index-url https://download.pytorch.org/whl/cu121
  }
}

function Smoke-CheckTorch([string]$py) {
  Info "Verifying torch + CUDA availability..."
  & $py -c "import torch; print('torch', torch.__version__); print('cuda_available', torch.cuda.is_available()); print('cuda_version', torch.version.cuda)" | Out-Host
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

  if ($Accel -eq "cpu") {
    Remove-CudaWheels $py
  } else {
    Install-CudaWheels $py
  }

  Force-InstallTorch $py $Accel
  Smoke-CheckTorch $py

  Info "Installing project (editable)..."
  & $py -m pip install -e .

  Info "Running pip check..."
  & $py -m pip check
}

try {
  Push-Location $RepoRoot

  Info "Requested accelerator mode: $Accel"
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