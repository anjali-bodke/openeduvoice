param(
  [ValidateSet("auto","cpu","cuda")]
  [string]$Accel = "auto"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# In PS7+, native non-zero exit codes can become terminating errors depending on this flag.
# We explicitly disable that behavior so CPU-mode doesn't crash when optional CUDA checks fail.
try { $PSNativeCommandUseErrorActionPreference = $false } catch { }

function Info($m) { Write-Host "[INFO]  $m" }
function Warn($m) { Write-Host "[WARN]  $m" -ForegroundColor Yellow }
function Err ($m) { Write-Host "[ERROR] $m" -ForegroundColor Red }

$RepoRoot  = Resolve-Path (Join-Path $PSScriptRoot "..")
$VenvDir   = Join-Path $RepoRoot "venv"

$FfmpegBin  = Join-Path $RepoRoot "tools\ffmpeg\bin"
$ffmpegExe  = Join-Path $FfmpegBin "ffmpeg.exe"
$ffprobeExe = Join-Path $FfmpegBin "ffprobe.exe"

function VenvPython() {
  $py = Join-Path $VenvDir "Scripts\python.exe"
  if (-not (Test-Path $py)) {
    throw "venv python not found: $py. Run install_OpenEduVoice.bat first."
  }
  return $py
}

function Add-ToPath([string]$dir) {
  if (-not (Test-Path $dir)) { return }
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

function Add-CudaWheelDllsToPath([string]$py) {
  Info "Configuring CUDA runtime DLL paths (if present)..."

  $rtDir = Join-Path $RepoRoot "tools\_runtime"
  New-Item -ItemType Directory -Force -Path $rtDir | Out-Null
  $scriptPath = Join-Path $rtDir "detect_cuda_bins.py"

@'
import site
from pathlib import Path

sp = [Path(p) for p in site.getsitepackages() if p]
bins = set()

for base in sp:
    nvidia = base / "nvidia"
    if not nvidia.exists():
        continue
    for bin_dir in nvidia.rglob("bin"):
        if bin_dir.is_dir():
            bins.add(str(bin_dir.resolve()))

print(";".join(sorted(bins)))
'@ | Set-Content -Encoding UTF8 $scriptPath

  $dllDirs = & $py $scriptPath

  if ($dllDirs) {
    $parts = $dllDirs.Split(";") | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
    foreach ($d in $parts) { Add-ToPath $d }
    Info "CUDA DLL dirs added to PATH (session)."
    Info "CUDA DLL dirs: $dllDirs"
    return $true
  } else {
    Info "No CUDA wheel DLL dirs detected. (CPU mode will still work.)"
    return $false
  }
}

function SmokeCheckImports([string]$py) {
  Info "Checking OpenEduVoice import..."
  & $py -c "import OpenEduVoice; print('OpenEduVoice import OK')" | Out-Host
  if ($LASTEXITCODE -ne 0) {
    throw "OpenEduVoice is not installed in this virtual environment. Run install_OpenEduVoice.bat first."
  }
}

function TorchCudaAvailable([string]$py) {
  try {
    $out = & $py -c "import torch; print('1' if torch.cuda.is_available() else '0')"
    return ($out.Trim() -eq "1")
  } catch {
    return $false
  }
}

function Launch([string]$py) {
  Info "Launching GUI..."
  & $py -m OpenEduVoice
}

try {
  Push-Location $RepoRoot

  if ($Accel -eq "auto") {
    $detected = "cpu"
    try {
      $null = & nvidia-smi 2>$null
      if ($LASTEXITCODE -eq 0) { $detected = "cuda" }
    } catch { $detected = "cpu" }

    Info "AUTO mode: detected $detected"
    $Accel = $detected
  } else {
    Info "Requested mode: $Accel"
  }

  $py = VenvPython
  Ensure-FFmpegAvailable
  SmokeCheckImports $py

  if ($Accel -eq "cuda") {
    if (-not (TorchCudaAvailable $py)) {
      Warn "CUDA mode requested, but torch.cuda.is_available() is False in this venv."
    } else {
      Info "CUDA mode confirmed: torch.cuda.is_available() = True"
    }
    $null = Add-CudaWheelDllsToPath $py
  } else {
    Info "CPU mode requested."
  }

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