"""
nllb_model.py

NLLB-200-based translation functionality using HuggingFace Transformers.

Key goals for this project:
- Be reliable on typical consumer GPUs (e.g., 8GB VRAM laptops).
- Use CUDA when it is actually safe to do so; otherwise fall back to CPU automatically.
- Avoid peak-memory spikes during model load and generation.

Notes:
- The full `facebook/nllb-200-3.3B` model generally does NOT fit on 8GB VRAM.
  On such GPUs we automatically switch to `facebook/nllb-200-distilled-600M` unless
  a different model is explicitly requested.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Callable, Optional

import torch
from transformers import NllbTokenizer, AutoModelForSeq2SeqLM


# Good default for most laptops. Users with larger GPUs can override via config/UI.
DEFAULT_MODEL_SMALL = "facebook/nllb-200-distilled-600M"
DEFAULT_MODEL_LARGE = "facebook/nllb-200-3.3B"


@dataclass(frozen=True)
class NLLBConfig:
    source_lang: str = "deu_Latn"
    target_lang: str = "eng_Latn"
    model_name: Optional[str] = None  # None => auto-select
    max_chars: int = 400


def _cuda_total_gib() -> float:
    try:
        if not torch.cuda.is_available():
            return 0.0
        props = torch.cuda.get_device_properties(0)
        return float(props.total_memory) / (1024 ** 3)
    except Exception:
        return 0.0


def _pick_model_name(requested: Optional[str]) -> str:
    if requested:
        return requested

    # Heuristic: 3.3B on CUDA generally needs more than 8GB VRAM.
    # Keep it conservative for reliability.
    vram_gib = _cuda_total_gib()
    if vram_gib >= 16.0:
        return DEFAULT_MODEL_LARGE
    return DEFAULT_MODEL_SMALL


def _choose_device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def _set_allocator_hints() -> None:
    """
    Helps reduce CUDA fragmentation issues in some workloads.
    Safe no-op if CUDA isn't used.
    """
    # Only set if not already set by user/system
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")


class NLLBTranslator:
    """
    Wrapper around the NLLB-200 model for translating text between supported languages.
    Automatically loads the tokenizer and model and moves it to the appropriate device (CUDA/CPU).
    """

    def __init__(
        self,
        source_lang: str = "deu_Latn",
        target_lang: str = "eng_Latn",
        model_name: Optional[str] = None,
        log: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.source_lang = source_lang
        self.target_lang = target_lang

        self.device = _choose_device()

        # Choose model sensibly for the available device/VRAM.
        chosen_model = _pick_model_name(model_name)

        # If user explicitly requested the 3.3B model but VRAM is small, prefer CPU for safety.
        if chosen_model == DEFAULT_MODEL_LARGE and self.device.type == "cuda" and _cuda_total_gib() < 16.0:
            if log:
                log(
                    "[WARN] NLLB model 'facebook/nllb-200-3.3B' is too large for this GPU. "
                    "Falling back to CPU to avoid CUDA OOM."
                )
            self.device = torch.device("cpu")

        if self.device.type == "cuda":
            _set_allocator_hints()
            # Avoid stale memory from earlier GPU work.
            try:
                torch.cuda.empty_cache()
            except Exception:
                pass

        self.model_name = chosen_model
        if log:
            log(f"[INFO] NLLB model selected: {self.model_name} (device={self.device.type})")

        # Tokenizer is small; keep it on CPU.
        self.tokenizer = NllbTokenizer.from_pretrained(self.model_name)

        # Reduce peak memory during load.
        model_kwargs = {"low_cpu_mem_usage": True}
        if self.device.type == "cuda":
            model_kwargs["torch_dtype"] = torch.float16

        self.model = AutoModelForSeq2SeqLM.from_pretrained(self.model_name, **model_kwargs)
        self.model.to(self.device)
        self.model.eval()

    def _split_by_sentences(self, text: str, max_chars: int = 400) -> list[str]:
        """
        Splits text into ~max_chars chunks using sentence boundaries.
        """
        sentences = re.split(r"(?<=[.!?])\s+", (text or "").strip())
        chunks: list[str] = []
        current = ""

        for sentence in sentences:
            if not sentence:
                continue
            if len(current) + len(sentence) <= max_chars:
                current = (current + " " + sentence).strip() if current else sentence
            else:
                if current:
                    chunks.append(current.strip())
                current = sentence

        if current:
            chunks.append(current.strip())

        return chunks

    def translate(self, text: str, max_chars: int = 400, log: Optional[Callable[[str], None]] = None) -> str:
        """
        Translates text using NLLB, chunked by sentence for stability.
        """
        chunks = self._split_by_sentences(text, max_chars=max_chars)
        if not chunks:
            return ""

        results: list[str] = []
        self.tokenizer.src_lang = self.source_lang
        forced_id = self.tokenizer.convert_tokens_to_ids(self.target_lang)

        for idx, chunk in enumerate(chunks, start=1):
            if log:
                log(f"[INFO] Translating chunk {idx}/{len(chunks)}")

            inputs = self.tokenizer(
                chunk,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=512,
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            # Inference-only path: lower memory than grad-enabled.
            with torch.inference_mode():
                generated = self.model.generate(
                    **inputs,
                    forced_bos_token_id=forced_id,
                    max_new_tokens=256,
                    num_beams=4,
                    early_stopping=True,
                    no_repeat_ngram_size=3,
                    length_penalty=1.05,
                    repetition_penalty=1.1,
                )

            translated = self.tokenizer.batch_decode(generated, skip_special_tokens=True)[0]
            results.append((translated or "").strip())

            # Proactively free temporary tensors (helps on small VRAM GPUs).
            del inputs, generated
            if self.device.type == "cuda":
                try:
                    torch.cuda.empty_cache()
                except Exception:
                    pass

        return "\n".join(results)