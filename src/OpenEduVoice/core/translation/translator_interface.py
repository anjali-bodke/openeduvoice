"""
Translation interfaces for slide text (line-aligned) and transcripts (full text).
Backed by NLLB-200 via src.core.translation.nllb_model.NLLBTranslator.

- Consistent, no-raise logging via safe_log
- Deterministic ordering of files
- Slide text preserves 1:1 line alignment for reintegration
"""

from __future__ import annotations

import re

from pathlib import Path
from typing import Callable, List

from OpenEduVoice.utils.logging_utils import safe_log
from OpenEduVoice.utils.preprocessing import segment_sentences

# ---- Optional glossary cleanup (can be disabled) ----
GLOSSARY_ON = True  # set to False to disable glossary-based cleanup

try:
    from OpenEduVoice.utils.cleanup import (
        apply_glossary_cleanup_to_lines,
        apply_glossary_cleanup_with_source,
    )
    _HAS_CLEANUP = True
except Exception:
    _HAS_CLEANUP = False
    GLOSSARY_ON = False


LANG_MAP = {
    "de": "deu_Latn",
    "en": "eng_Latn",
    # extend as needed
}

def _create_translator(source_lang: str, target_lang: str):
    from OpenEduVoice.core.translation.nllb_model import NLLBTranslator

    return NLLBTranslator(source_lang, target_lang)


def _norm_lang(code: str) -> str:
    return LANG_MAP.get(code, code)

def _is_bibliography_like(line: str) -> bool:
    """
    Heuristic: bibliography entries often contain multiple semicolon-separated fields,
    edition markers, ISBN, years, or publisher/city patterns.
    Conservative: triggers only when 2+ strong signals exist.
    """
    s = line or ""
    signals = 0

    # multiple semicolons usually indicates bibliographic fields
    if s.count(";") >= 2:
        signals += 1

    # edition markers
    if re.search(r"\b0*\d{1,2}\.\s*(Auflage|Aufl\.)\b", s, flags=re.IGNORECASE):
        signals += 1

    # ISBN / year-like
    if re.search(r"\bISBN\b", s, flags=re.IGNORECASE):
        signals += 1
    if re.search(r"\b(19|20)\d{2}\b", s):
        signals += 1

    # author-ish / editor-ish markers (optional)
    if re.search(r"\b(Hrsg\.|Herausgeber|Aufl\.)\b", s, flags=re.IGNORECASE):
        signals += 1

    return signals >= 2

def translate_text_files(
    input_dir: Path,
    output_dir: Path,
    source_lang: str,
    target_lang: str,
    log: Callable[[str], None] | None = print,
    output: Callable[[str], None] | None = None,
) -> List[Path]:
    """
    Translates slide text files **line-by-line** to preserve alignment.

    Returns:
        List of output .txt paths.
    """
    log = log or (lambda *_: None)
    output = output or (lambda *_: None)

    if not input_dir.is_dir():
        raise ValueError(f"Slide text input directory does not exist: {input_dir}")

    txt_files = sorted(input_dir.glob("*.txt"))
    if not txt_files:
        raise ValueError(f"No slide text files found in: {input_dir}")

    src = _norm_lang(source_lang)
    tgt = _norm_lang(target_lang)

    try:
        translator = _create_translator(src, tgt)
        safe_log(log, f"[INFO] NLLB translator initialized: {src} -> {tgt}")
    except Exception as e:
        safe_log(log, f"[ERROR] Failed to initialize NLLB translator {src}->{tgt}: {e}")
        raise

    translated_files: List[Path] = []
    output_dir.mkdir(parents=True, exist_ok=True)

    for txt_file in txt_files:
        try:
            src_lines = txt_file.read_text(encoding="utf-8").splitlines()
            out_lines: List[str] = []
            skipped_indices: list[int] = []
            total = len(src_lines)

            for i, line in enumerate(src_lines, start=1):
                clean = (line or "").strip()

                # Preserve source content that is intentionally not translated.
                if (
                    not clean
                    or not any(c.isalpha() for c in clean)
                    or (clean.count("/") >= 3 and not clean.endswith(".com"))
                ):
                    out_lines.append(line)
                    skipped_indices.append(i - 1)
                    if clean and any(c.isalpha() for c in clean):
                        safe_log(log, f"[WARN] Preserving untranslated line {i} in {txt_file.name}.")
                    continue

                safe_log(log, f"[INFO] Translating {txt_file.name} line {i}/{total}")

                try:
                    if _is_bibliography_like(clean):
                        sentences = [clean]
                    else:
                        sentences = segment_sentences(clean) or [clean]
                    translated_chunks: List[str] = []
                    for sent in sentences:
                        s = sent.strip()
                        if not s:
                            continue
                        chunk = translator.translate(s, log=None)
                        if not chunk or not chunk.strip():
                            raise ValueError("Translation returned no text")
                        translated_chunks.append(" ".join(chunk.split()))

                    translated_line = " ".join(ch for ch in translated_chunks if ch)
                    out_lines.append(translated_line.strip())
                except Exception as e:
                    raise RuntimeError(
                        f"Translation failed for {txt_file.name} line {i}: {e}"
                    ) from e

            # ---- Optional glossary + light cleanup ----
            if GLOSSARY_ON and _HAS_CLEANUP:
                try:
                    # Prefer the source-aware variant to correct mistranslated abbreviations
                    out_lines = apply_glossary_cleanup_with_source(
                        src_lines,
                        out_lines,
                        term_map_path=Path(__file__).parents[2] / "utils" / "term_map.json",
                        expand_exact_matches=True,
                    )
                except Exception:
                    # Fallback: attempt line-only cleanup
                    try:
                        out_lines = apply_glossary_cleanup_to_lines(
                            out_lines,
                            term_map_path=Path(__file__).parents[2] / "utils" / "term_map.json",
                            expand_exact_matches=True,
                        )
                    except Exception as e2:
                        safe_log(log, f"[WARN] Glossary cleanup skipped for {txt_file.name}: {e2}")

            if len(out_lines) != len(src_lines):
                raise RuntimeError(f"Translation changed the line count for {txt_file.name}.")
            for index in skipped_indices:
                out_lines[index] = src_lines[index]

            out_path = output_dir / txt_file.name
            out_path.write_text(
                "\n".join(out_lines) + ("\n" if out_lines else ""), encoding="utf-8"
            )
            translated_files.append(out_path)
            safe_log(log, f"[INFO] Saved: {out_path.name}")
        except Exception as e:
            safe_log(log, f"[ERROR] Failed to translate {txt_file.name}: {e}")
            raise

    safe_log(output, f"Translated {len(translated_files)} slide .txt files → {output_dir}")
    return translated_files


def translate_transcript_files(
    input_dir: Path,
    output_dir: Path,
    source_lang: str,
    target_lang: str,
    log: Callable[[str], None] | None = print,
    output: Callable[[str], None] | None = None,
) -> List[Path]:
    """
    Translates full transcript files (one block of text per file).
    (No glossary cleanup here to avoid altering free-form text; keep behavior unchanged.)
    """
    log = log or (lambda *_: None)
    output = output or (lambda *_: None)

    if not input_dir.is_dir():
        raise ValueError(f"Transcript input directory does not exist: {input_dir}")
    txt_files = sorted(input_dir.glob("*.txt"))
    if not txt_files:
        raise ValueError(f"No transcript files found in: {input_dir}")

    src = _norm_lang(source_lang)
    tgt = _norm_lang(target_lang)

    try:
        translator = _create_translator(src, tgt)
        safe_log(log, f"[INFO] NLLB translator initialized: {src} -> {tgt}")
    except Exception as e:
        safe_log(log, f"[ERROR] Failed to initialize NLLB translator {src}->{tgt}: {e}")
        raise

    translated_files: List[Path] = []
    output_dir.mkdir(parents=True, exist_ok=True)

    for txt_file in txt_files:
        try:
            text = txt_file.read_text(encoding="utf-8").strip()
            if not text or not any(c.isalpha() for c in text):
                out_path = output_dir / txt_file.name
                out_path.write_text(text, encoding="utf-8")
                translated_files.append(out_path)
                safe_log(log, f"[INFO] Skipped empty/non-alpha: {txt_file.name}")
                continue

            safe_log(log, f"[INFO] Translating {txt_file.name} (full file)")
            translated = (translator.translate(text) or "").strip()
            if not translated:
                raise ValueError(f"Translation returned no text for {txt_file.name}.")
            out_path = output_dir / txt_file.name
            out_path.write_text(translated, encoding="utf-8")
            translated_files.append(out_path)
            safe_log(log, f"[INFO] Saved: {out_path.name}")
        except Exception as e:
            safe_log(log, f"[ERROR] Failed to translate {txt_file.name}: {e}")
            raise

    safe_log(output, f"Translated {len(translated_files)} transcript files → {output_dir}")
    return translated_files
