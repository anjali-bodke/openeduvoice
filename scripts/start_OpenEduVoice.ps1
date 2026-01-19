# scripts/start_OpenEduVoice.ps1
# One-click setup + run (Python is prerequisite). Adds local-bundled FFmpeg if missing.

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# -------------------------
# Paths
# -------------------------
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$ToolsDir = Join-Path $RepoRoot "tools"
$FfmpegRoot = Join-Path $ToolsDir "ffmpeg"
$FfmpegZip = Join-Path $FfmpegRoot "ffmpeg-release-essentials.zip"

$VenvDir = Join-Path $RepoRoot "venv"
$ReqCore = Join-Path $RepoRoot "requirements.txt"
$ReqML = Join-Path $RepoRoot "requirements-ml.txt"
$ReqTTS = Join-Path $RepoRoot "requirements-tts.txt"

# Your FFmpeg source (Windows ZIP). "Essentials" includes ffmpeg/ffprobe binaries.
$FfmpegUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

function Write-Info($msg) { Write-Host "[INFO] $msg" }
function Write-Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "[ERROR] $msg" -ForegroundColor Red }

function Test-CommandExists([string]$name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Add-ToPath([string]$dir) {
    if (-not (Test-Path $dir)) { throw "PATH add failed, directory not found: $dir" }
    $current = $env:Path.Split(";") | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
    if ($current -contains $dir) { return }
    $env:Path = "$dir;$env:Path"
    Write-Info "Added to PATH (session): $dir"
}

function Ensure-Tls12() {
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    } catch {
        # ignore; newer PowerShell may not need it
    }
}

function Ensure-FFmpegLocal() {
    $hasFfmpeg = Test-CommandExists "ffmpeg"
    $hasFfprobe = Test-CommandExists "ffprobe"

    if ($hasFfmpeg -and $hasFfprobe) {
        Write-Info "FFmpeg already available on PATH."
        return
    }

    Write-Warn "FFmpeg/ffprobe not found. Installing local FFmpeg bundle into tools/ffmpeg ..."

    New-Item -ItemType Directory -Force -Path $FfmpegRoot | Out-Null

    # Download zip if not present
    if (-not (Test-Path $FfmpegZip)) {
        Ensure-Tls12
        Write-Info "Downloading: $FfmpegUrl"
        Invoke-WebRequest -Uri $FfmpegUrl -OutFile $FfmpegZip -UseBasicParsing
        Write-Info "Downloaded FFmpeg zip to: $FfmpegZip"
    } else {
        Write-Info "FFmpeg zip already present: $FfmpegZip"
    }

    # Extract to a versioned folder under tools/ffmpeg/
    $ExtractDir = Join-Path $FfmpegRoot "extracted"
    if (Test-Path $ExtractDir) {
        Remove-Item -Recurse -Force $ExtractDir
    }
    New-Item -ItemType Directory -Force -Path $ExtractDir | Out-Null

    Write-Info "Extracting FFmpeg zip ..."
    Expand-Archive -Path $FfmpegZip -DestinationPath $ExtractDir -Force

    # Locate ffmpeg.exe bin directory
    $ffmpegExe = Get-ChildItem -Path $ExtractDir -Recurse -Filter "ffmpeg.exe" -File | Select-Object -First 1
    $ffprobeExe = Get-ChildItem -Path $ExtractDir -Recurse -Filter "ffprobe.exe" -File | Select-Object -First 1

    if (-not $ffmpegExe -or -not $ffprobeExe) {
        throw "FFmpeg extraction completed, but ffmpeg.exe/ffprobe.exe not found under: $ExtractDir"
    }

    $binDir = Split-Path -Parent $ffmpegExe.FullName
    Add-ToPath $binDir

    # Verify
    Write-Info "Verifying FFmpeg..."
    & ffmpeg -version | Out-Host
    & ffprobe -version | Out-Host
    Write-Info "FFmpeg local bundle ready."
}

function Ensure-Python311() {
    if (-not (Test-CommandExists "py")) {
        throw "Python launcher 'py' not found. Install Python 3.11 and ensure it's on PATH (README prerequisite)."
    }
    # quick smoke check
    & py -3.11 -c "import sys; print(sys.version)" | Out-Host
}

function Ensure-Venv() {
    if (-not (Test-Path $VenvDir)) {
        Write-Info "Creating venv at: $VenvDir"
        & py -3.11 -m venv $VenvDir
    } else {
        Write-Info "venv already exists: $VenvDir"
    }
}

function Activate-Venv() {
    $activate = Join-Path $VenvDir "Scripts\Activate.ps1"
    if (-not (Test-Path $activate)) { throw "venv activation script not found: $activate" }
    . $activate
    Write-Info "Activated venv."
}

function Install-Dependencies() {
    if (-not (Test-Path $ReqCore)) { throw "Missing requirements file: $ReqCore" }
    if (-not (Test-Path $ReqML))   { throw "Missing requirements file: $ReqML" }
    if (-not (Test-Path $ReqTTS))  { throw "Missing requirements file: $ReqTTS" }

    Write-Info "Upgrading pip..."
    python -m pip install --upgrade pip

    Write-Info "Installing core requirements: $ReqCore"
    pip install -r $ReqCore

    Write-Info "Installing ML requirements: $ReqML"
    pip install -r $ReqML

    Write-Info "Installing TTS requirements: $ReqTTS"
    pip install -r $ReqTTS
}

function Launch-App() {
    Write-Info "Launching OpenEduVoice GUI..."
    python -m src.gui.main_window
}

# -------------------------
# Main
# -------------------------
try {
    Push-Location $RepoRoot

    Ensure-Python311
    Ensure-FFmpegLocal
    Ensure-Venv
    Activate-Venv
    Install-Dependencies
    Launch-App

} catch {
    Write-Err $_.Exception.Message
    Write-Err "Setup failed. Please scroll up for details."
    Exit 1
} finally {
    Pop-Location | Out-Null
}
