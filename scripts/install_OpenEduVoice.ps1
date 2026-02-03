param(
  [ValidateSet("auto","cpu","cuda")]
  [string]$Accel = "auto"
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
$FfmpegUrl  = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

$ReqLock = Join-Path $RepoRoot "requirements.lock.txt"
$ReqCore = Join-Path $RepoRoot "requirements.txt"
$ReqML   = Join-Path $RepoRoot "requirements-ml.txt"
$ReqTTS  = Join-Path $RepoRoot "requirements-tts.txt"
$PyProj  = Join-Path $RepoRoot "pyproject.toml"

$ModeMarker = Join-Path $VenvDir ".openeduvoice_mode.txt"

# PyTorch wheel channels
$TorchIndexCPU  = "https://download.pytorch.org/whl/cpu"
$TorchIndexCUDA = "https://download.pytorch.org/whl/cu126"   # keep consistent with CUDA 12.1 wheels

# Minimum safe torch version due to CVE-2025-32434
$MinTorchVersion = "2.6.0"

function Test-Command([string]$name) {
  return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Ensure-Tls12() {
  try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}
}

function Detect-Accel() {
  # Simple for non-tech users: if nvidia-smi exists and reports GPU -> cuda else cpu
  if (Test-Command "nvidia-smi") {
    try {
      $out = & nvidia-smi -L 2>$null
      if ($LASTEXITCODE -eq 0 -and $out -and ($out -match "GPU")) { return "cuda" }
    } catch {}
  }
  return "cpu"
}

function Ensure-Python311() {
  if (-not (Test-Command "python")) {
    throw "Python not found on PATH. Install Python 3.11 and ensure it's added to PATH."
  }
  $ver = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
  if ($ver -ne "3.11") { throw "Python 3.11 is required. Found: $ver" }
  Info "Python OK: $ver"
}

function Ensure-RequirementsFiles() {
  foreach ($f in @($ReqLock, $ReqCore, $ReqML, $ReqTTS, $PyProj)) {
    if (-not (Test-Path $f)) { throw "Missing required file: $f" }
  }
}

function Validate-LockFile() {
  Info "Validating requirements.lock.txt (must be CPU-safe)..."

  $content = Get-Content -Path $ReqLock -ErrorAction Stop

  # 1) Must NOT contain torch family (installed via PyTorch index-url later)
  $badTorch = $content | Where-Object { $_ -match '^(torch|torchaudio|torchvision)=='}
  if ($badTorch) {
    throw "requirements.lock.txt must NOT pin torch/torchaudio/torchvision. Remove these lines from the lock file."
  }

  # 2) Must NOT contain CUDA wheel packages (installed only in cuda mode)
  $badNvidia = $content | Where-Object { $_ -match '^nvidia-.*=='}
  if ($badNvidia) {
    throw "requirements.lock.txt must NOT include nvidia-* CUDA wheels. Those are installed only in CUDA mode by the installer."
  }

  # 3) Must pin the critical ones (sanity)
  if (-not ($content | Where-Object { $_ -match '^ctranslate2=='})) {
    throw "requirements.lock.txt must include a pinned ctranslate2==... line."
  }
  if (-not ($content | Where-Object { $_ -match '^faster-whisper=='})) {
    throw "requirements.lock.txt must include a pinned faster-whisper==... line."
  }

  #4) Block editable content
  if ($content -match '^-e\s+') {
    Write-Error "requirements.lock.txt must not contain editable (-e) installs."
    exit 1
  }

  if ($content -match '^OpenEduVoice==') {
    Write-Error "requirements.lock.txt must not contain the project itself (OpenEduVoice)."
    exit 1
  }


  Info "Lock file validation OK."
}

function Ensure-FFmpegLocal() {
  $ffmpegExe  = Join-Path $FfmpegBin "ffmpeg.exe"
  $ffprobeExe = Join-Path $FfmpegBin "ffprobe.exe"

  if ((Test-Path $ffmpegExe) -and (Test-Path $ffprobeExe)) {
    Info "Local FFmpeg already present: $FfmpegBin"
    return
  }

  Warn "Local FFmpeg not found. Downloading and extracting..."
  New-Item -ItemType Directory -Force -Path $FfmpegDir | Out-Null
  New-Item -ItemType Directory -Force -Path $FfmpegBin | Out-Null

  function Download-FFmpegZip() {
    Ensure-Tls12
    Info "Downloading FFmpeg zip..."
    Invoke-WebRequest -Uri $FfmpegUrl -OutFile $FfmpegZip -UseBasicParsing
    Info "Downloaded: $FfmpegZip"
  }

  if (-not (Test-Path $FfmpegZip)) {
    Download-FFmpegZip
  } else {
    Info "FFmpeg zip already exists: $FfmpegZip"
  }

  $tmpExtract = Join-Path $FfmpegDir "_tmp_extract"
  if (Test-Path $tmpExtract) { Remove-Item -Recurse -Force $tmpExtract }
  New-Item -ItemType Directory -Force -Path $tmpExtract | Out-Null

  Info "Extracting FFmpeg..."
  $extractedOk = $false

  try {
    Expand-Archive -Path $FfmpegZip -DestinationPath $tmpExtract -Force
    $extractedOk = $true
  } catch {
    Warn "FFmpeg zip extraction failed (zip may be corrupt). Deleting zip and re-downloading..."
    try { Remove-Item -Force $FfmpegZip } catch {}
    Download-FFmpegZip

    # Retry exactly once
    if (Test-Path $tmpExtract) { Remove-Item -Recurse -Force $tmpExtract }
    New-Item -ItemType Directory -Force -Path $tmpExtract | Out-Null

    Expand-Archive -Path $FfmpegZip -DestinationPath $tmpExtract -Force
    $extractedOk = $true
  }

  if (-not $extractedOk) {
    throw "Failed to extract FFmpeg zip."
  }

  $foundFfmpeg  = Get-ChildItem -Path $tmpExtract -Recurse -Filter "ffmpeg.exe"  -File | Select-Object -First 1
  $foundFfprobe = Get-ChildItem -Path $tmpExtract -Recurse -Filter "ffprobe.exe" -File | Select-Object -First 1

  if (-not $foundFfmpeg -or -not $foundFfprobe) {
    throw "FFmpeg extracted but ffmpeg.exe/ffprobe.exe not found."
  }

  Copy-Item -Force $foundFfmpeg.FullName  $ffmpegExe
  Copy-Item -Force $foundFfprobe.FullName $ffprobeExe

  Remove-Item -Recurse -Force $tmpExtract
  Info "Local FFmpeg ready: $FfmpegBin"
}

function VenvPython() {
  $py = Join-Path $VenvDir "Scripts\python.exe"
  if (-not (Test-Path $py)) { throw "venv python not found: $py" }
  return $py
}

function Read-ExistingVenvMode() {
  if (Test-Path $ModeMarker) {
    try { return (Get-Content -Raw $ModeMarker).Trim() } catch {}
  }
  return ""
}

function Write-VenvMode([string]$mode) {
  New-Item -ItemType Directory -Force -Path $VenvDir | Out-Null
  Set-Content -Encoding UTF8 -Path $ModeMarker -Value $mode
}

function Ensure-Venv([string]$mode) {
  $needRecreate = $false

  if (Test-Path $VenvDir) {
    $py = Join-Path $VenvDir "Scripts\python.exe"
    if (-not (Test-Path $py)) {
      Warn "Existing venv is broken (python.exe missing). Will recreate."
      $needRecreate = $true
    } else {
      $oldMode = Read-ExistingVenvMode
      if ($oldMode -and ($oldMode -ne $mode)) {
        Warn "Existing venv mode '$oldMode' != requested '$mode'. Will recreate."
        $needRecreate = $true
      }
    }
  }

  if ($needRecreate -and (Test-Path $VenvDir)) {
    Warn "Removing existing venv..."
    Remove-Item -Recurse -Force $VenvDir
  }

  if (-not (Test-Path $VenvDir)) {
    Info "Creating venv..."
    & python -m venv $VenvDir
  } else {
    Info "venv already exists."
  }

  Write-VenvMode $mode
}

function Pip-Upgrade([string]$py) {
  Info "Upgrading pip..."
  & $py -m pip install --upgrade pip
  if ($LASTEXITCODE -ne 0) { throw "pip failed (exit code $LASTEXITCODE)" }
}

function Install-Locked([string]$py) {
  Info "Installing locked dependencies from requirements.lock.txt..."
  & $py -m pip install -r $ReqLock
  if ($LASTEXITCODE -ne 0) { throw "pip failed (exit code $LASTEXITCODE)" }
}

function Install-CudaWheels([string]$py) {
  Info "Installing CUDA runtime wheels (for CUDA mode)..."
  & $py -m pip install nvidia-cuda-runtime-cu12 nvidia-cublas-cu12 nvidia-cudnn-cu12
  if ($LASTEXITCODE -ne 0) { throw "pip failed (exit code $LASTEXITCODE)" }
}

function Remove-CudaWheels([string]$py) {
  Info "Ensuring CPU mode: removing CUDA runtime wheels if present..."
  $pkgs = @("nvidia-cuda-runtime-cu12","nvidia-cublas-cu12","nvidia-cudnn-cu12")
  foreach ($p in $pkgs) {
    try { & $py -m pip uninstall -y $p | Out-Null } catch {}
  }
}

function Install-TorchForMode([string]$py, [string]$mode) {
  if ($mode -eq "cpu") {
    Info "Installing torch/torchaudio (CPU) from official PyTorch index..."
    & $py -m pip install --upgrade --force-reinstall `
      "torch>=$MinTorchVersion" "torchaudio>=$MinTorchVersion" `
      --index-url $TorchIndexCPU
      if ($LASTEXITCODE -ne 0) { throw "pip failed (exit code $LASTEXITCODE)" }
  } else {
    Info "Installing torch/torchaudio (CUDA) from official PyTorch cu126 index..."
    & $py -m pip install --upgrade --force-reinstall `
      "torch>=$MinTorchVersion" "torchaudio>=$MinTorchVersion" `
      --index-url $TorchIndexCUDA
      if ($LASTEXITCODE -ne 0) { throw "pip failed (exit code $LASTEXITCODE)" }
  }
}

function Torch-Smoke([string]$py) {
  Info "Torch smoke-check..."
  & $py -c "import torch; print('torch', torch.__version__); print('cuda_available', torch.cuda.is_available()); print('cuda_version', torch.version.cuda)" | Out-Host
}

function Torch-CudaAvailable([string]$py) {
  try {
    $out = & $py -c "import torch; print('1' if torch.cuda.is_available() else '0')"
    return ($out.Trim() -eq "1")
  } catch { return $false }
}

function Install-Project([string]$py) {
  Info "Installing project (editable)..."
  & $py -m pip install -e .
  if ($LASTEXITCODE -ne 0) { throw "pip failed (exit code $LASTEXITCODE)" }

  Info "Running pip check..."
  & $py -m pip check
}

try {
  Push-Location $RepoRoot

  if ($Accel -eq "auto") {
    $Accel = Detect-Accel
    Info "Auto-detected accelerator mode: $Accel"
  } else {
    Info "Requested accelerator mode: $Accel"
  }

  Ensure-Python311
  Ensure-RequirementsFiles
  Validate-LockFile
  Ensure-FFmpegLocal
  Ensure-Venv $Accel

  $py = VenvPython

  Pip-Upgrade $py

  Install-Locked $py

  if ($Accel -eq "cuda") {
    Install-CudaWheels $py
    Install-TorchForMode $py "cuda"

    Torch-Smoke $py

    # If CUDA torch still not available, fallback automatically to CPU torch so the app runs.
    if (-not (Torch-CudaAvailable $py)) {
      Warn "CUDA was detected, but torch.cuda.is_available() is still False after CUDA torch install."
      Warn "Falling back to CPU torch so the app can run."
      Remove-CudaWheels $py
      Install-TorchForMode $py "cpu"
      Write-VenvMode "cpu"
      Torch-Smoke $py
    }
  } else {
    Remove-CudaWheels $py
    Install-TorchForMode $py "cpu"
    Torch-Smoke $py
  }

  Install-Project $py

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