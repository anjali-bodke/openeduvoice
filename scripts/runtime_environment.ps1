function Set-OpenEduVoiceEnvironment([string]$root) {
  $cache = Join-Path $root "models"
  $env:HF_HOME = Join-Path $cache "huggingface"
  $env:HF_HUB_CACHE = Join-Path $env:HF_HOME "hub"
  $env:HUGGINGFACE_HUB_CACHE = $env:HF_HUB_CACHE
  $env:TRANSFORMERS_CACHE = $env:HF_HUB_CACHE
  $env:TORCH_HOME = Join-Path $cache "torch"
  $env:TTS_HOME = Join-Path $cache "coqui"
  $env:XDG_CACHE_HOME = Join-Path $cache "cache"
  $env:PIP_CACHE_DIR = Join-Path $root "tools\pip-cache"

  $tesseract = Join-Path $root "tools\tesseract"
  if (Test-Path (Join-Path $tesseract "tesseract.exe")) {
    $env:Path = "$tesseract;$env:Path"
    $env:TESSDATA_PREFIX = Join-Path $tesseract "tessdata"
  }
}
