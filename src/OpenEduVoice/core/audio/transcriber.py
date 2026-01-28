"""
Handles audio transcription using faster-whisper.
- Safe CUDA path patching on Windows virtualenvs with pip `nvidia/*` packages.
- Robust model init with fallback compute types (float16 -> float32 -> int8).
- Consistent logging that never raises.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable, List, Optional

from OpenEduVoice.utils.logging_utils import safe_log

DEFAULT_WHISPER_MODEL = "medium"
UNSAFE_LARGE_MODELS = {"large", "large-v2"}

try:
    from faster_whisper import WhisperModel  # type: ignore
except Exception:  # pragma: no cover
    WhisperModel = None  # allow tests to monkeypatch

def _cuda_wheels_present() -> bool:
    """
    Returns True if pip-installed NVIDIA CUDA wheel DLL dirs exist in this venv.
    On Windows this is a strong signal that cublas/cudnn DLLs can actually be loaded.
    """
    if os.name != "nt":
        return False

    try:
        venv_base = Path(sys.executable).parent.parent
        nvidia_path = venv_base / "Lib" / "site-packages" / "nvidia"
        candidates = [
            nvidia_path / "cuda_runtime" / "bin",
            nvidia_path / "cublas" / "bin",
            nvidia_path / "cudnn" / "bin",
        ]
        return any(p.exists() for p in candidates)
    except Exception:
        return False


def _torch_cuda_available() -> bool:
    """
    Returns True only when torch reports CUDA is available.
    Works safely for CPU-only torch builds (returns False).
    """
    try:
        import torch  # local import to avoid hard dependency issues in edge cases
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _select_device_and_compute(model_name: str) -> tuple[str, str]:
    """
    CPU-first default. Only use CUDA when BOTH:
      - torch says CUDA is available, AND
      - CUDA wheel DLL folders exist in this venv (Windows)
    """
    cuda_ok = _torch_cuda_available()
    if cuda_ok:
        # On CUDA, float16 is usually the right default for speed.
        return "cuda", "float16"

    # CPU fallback. int8 is typically fastest/most memory-friendly on CPU.
    return "cpu", "int8"

def set_cuda_paths(log_fn: Optional[Callable[[str], None]] = None) -> None:
    """
    On Windows venvs with pip-installed `nvidia/*` wheels, add DLL folders to PATH.
    No-ops on other platforms. Never raises.
    """
    if os.name != "nt":
        return

    try:
        venv_base = Path(sys.executable).parent.parent
        nvidia_path = venv_base / "Lib" / "site-packages" / "nvidia"
        candidates = [
            nvidia_path / "cuda_runtime" / "bin",
            nvidia_path / "cublas" / "bin",
            nvidia_path / "cudnn" / "bin",
        ]
        to_prepend = [str(p) for p in candidates if p.exists()]

        if not to_prepend:
            return

        # Prepend to PATH; do not clobber existing value
        current = os.environ.get("PATH", "")
        new_path = os.pathsep.join(to_prepend + ([current] if current else []))
        os.environ["PATH"] = new_path
        # Set CUDA_PATH env hints if not set
        for key in ("CUDA_PATH", "CUDA_PATH_V12_4"):
            if key not in os.environ:
                os.environ[key] = os.pathsep.join(to_prepend)
        safe_log(log_fn, f"[INFO] CUDA DLL paths appended: {to_prepend}")
    except Exception as e:
        safe_log(log_fn, f"[WARN] set_cuda_paths failed (continuing without): {e}")

def _init_model(model_size: str, log_fn: Optional[Callable[[str], None]]) -> "WhisperModel":
    """
    Initialize WhisperModel with:
    - Deterministic device selection:
        * Use CUDA only if torch reports CUDA available AND CUDA wheel DLLs exist (Windows).
        * Otherwise use CPU.
    - Safety guard: never run large/large-v2 on CUDA (fallback to DEFAULT_WHISPER_MODEL).
    - Graceful fallbacks for compute_type on the chosen device.
    """
    if WhisperModel is None:
        raise RuntimeError("faster-whisper is not installed or failed to import.")

    requested_model = model_size or DEFAULT_WHISPER_MODEL

    # Decide device once (do not "try cuda first" on CPU-only machines)
    device, preferred_compute = _select_device_and_compute(requested_model)

    # Apply large-model guard only for CUDA
    effective_model = requested_model
    if device == "cuda" and requested_model in UNSAFE_LARGE_MODELS:
        safe_log(
            log_fn,
            (
                f"[WARN] Whisper model '{requested_model}' on CUDA has been unstable "
                f"on this setup. Overriding to '{DEFAULT_WHISPER_MODEL}' for reliability."
            ),
        )
        effective_model = DEFAULT_WHISPER_MODEL

    # Only patch CUDA paths when we actually intend to use CUDA
    if device == "cuda":
        set_cuda_paths(log_fn)

    # Compute-type fallback sequence
    if device == "cuda":
        compute_candidates = [preferred_compute, "float32", "int8"]
    else:
        compute_candidates = [preferred_compute, "float32"]

    last_err: Optional[Exception] = None

    for compute_type in compute_candidates:
        # De-dupe in case preferred_compute == "float32" etc.
        if compute_candidates.count(compute_type) > 1:
            # We'll let duplicates slide, it's harmless; but you can de-dupe if you want.
            pass
        try:
            safe_log(
                log_fn,
                f"[INFO] Loading faster-whisper model '{effective_model}' "
                f"on device '{device}' (compute_type={compute_type})",
            )
            model = WhisperModel(effective_model, device=device, compute_type=compute_type)
            return model
        except Exception as e:
            last_err = e
            safe_log(
                log_fn,
                "[WARN] Model init failed with "
                f"device={device}, compute_type={compute_type}, "
                f"model='{effective_model}': {e}",
            )

    raise RuntimeError(
        f"Failed to initialize faster-whisper model '{requested_model}' "
        f"on device '{device}': {last_err}"
    )

def transcribe_audio_files(
    audio_dir: Path,
    output_dir: Path,
    model_size: str = DEFAULT_WHISPER_MODEL,
    log_fn: Callable[[str], None] = print,
) -> List[Path]:
    """
    Transcribes all .wav files in a directory using faster-whisper.

    Args:
        audio_dir: Directory containing WAV files.
        output_dir: Directory to save transcription .txt files.
        model_size: Whisper model variant (e.g., 'base', 'medium').
        log_fn: Logging function (GUI logger or print).

    Returns:
        List of saved .txt file paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Only patch CUDA paths if CUDA wheels exist (prevents misleading logs in CPU mode)
    if _cuda_wheels_present() and _torch_cuda_available():
        set_cuda_paths(log_fn)

    try:
        model = _init_model(model_size, log_fn)
    except Exception as e:
        safe_log(log_fn, f"[ERROR] Could not load Whisper model '{model_size}': {e}")
        return []

    transcribed_files: List[Path] = []
    wav_files = sorted(audio_dir.glob("*.wav"))
    if not wav_files:
        safe_log(log_fn, f"[INFO] No .wav files found in: {audio_dir}")
        return transcribed_files

    for wav_file in wav_files:
        try:
            segments, _ = model.transcribe(str(wav_file),
                                        language="de",
                                        beam_size=5,
                                        best_of=5,
                                        temperature=[0.0, 0.2, 0.4, 0.6, 0.8],
                                        vad_filter=True,
                                        condition_on_previous_text=True,                               
            )
            
            # Concatenate segment texts with spaces (simple, reliable)
            transcript = " ".join(getattr(s, "text", "") for s in segments).strip()
            out_path = output_dir / f"{wav_file.stem}.txt"
            out_path.write_text(transcript, encoding="utf-8")
            transcribed_files.append(out_path)
            safe_log(log_fn, f"[INFO] Transcribed: {wav_file.name} -> {out_path.name} ({len(transcript)} chars)")
        except Exception as e:
            safe_log(log_fn, f"[ERROR] Failed to transcribe {wav_file.name}: {e}")

    safe_log(log_fn, f"[INFO] Total transcripts written: {len(transcribed_files)}")
    return transcribed_files