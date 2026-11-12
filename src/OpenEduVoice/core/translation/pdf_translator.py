from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

import fitz

from OpenEduVoice.core.extraction.pdf_text_extractor import (
    extract_pdf_text_blocks,
)
from OpenEduVoice.core.reintegration.pdf_reintegrator import (
    TranslatedPDFBlock,
    reintegrate_pdf_text,
)
from OpenEduVoice.utils.logging_utils import safe_log


NLLB_LANGUAGE_MAP = {"de": "deu_Latn", "en": "eng_Latn"}


class TextTranslator(Protocol):
    def translate(self, text: str, log: Callable[[str], None] | None = None) -> str: ...


@dataclass(frozen=True)
class PDFTranslationResult:
    translated_pdf: Path
    extracted_text_files: list[Path]
    translated_text_files: list[Path]
    translated_block_count: int


def _create_nllb_translator(
    source_lang: str,
    target_lang: str,
    log_fn: Callable[[str], None],
) -> TextTranslator:
    from OpenEduVoice.core.translation.nllb_model import NLLBTranslator

    return NLLBTranslator(source_lang, target_lang, log=log_fn)


def _page_text(blocks: list[TranslatedPDFBlock], page_number: int, translated: bool) -> str:
    texts = [
        block.translated_text if translated else block.source.text
        for block in blocks
        if block.source.page_number == page_number
    ]
    return "\n\n".join(texts)


def translate_pdf(
    pdf_path: Path,
    source_lang: str,
    target_lang: str,
    log_fn: Callable[[str], None] = print,
    *,
    output_dir: Path | None = None,
) -> PDFTranslationResult:
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file() or pdf_path.suffix.lower() != ".pdf":
        raise ValueError("Select an existing PDF file.")
    if source_lang not in NLLB_LANGUAGE_MAP or target_lang not in NLLB_LANGUAGE_MAP:
        raise ValueError("PDF translation supports German and English only.")
    if source_lang == target_lang:
        raise ValueError("The source and target languages must be different.")

    destination = Path(output_dir) if output_dir is not None else pdf_path.parent
    if not destination.is_dir():
        raise ValueError(f"Output folder does not exist or is not a directory: {destination}")
    text_dir = destination / f"{pdf_path.stem}_translation"
    extracted_dir = text_dir / "extracted_text"
    translated_dir = text_dir / "translated_text"
    output_pdf = destination / f"{pdf_path.stem}_translated.pdf"

    with fitz.open(pdf_path) as document:
        if document.is_encrypted:
            raise ValueError("Password-protected PDFs are not supported.")
        source_blocks = extract_pdf_text_blocks(document, source_lang, log_fn)

    if not source_blocks:
        raise ValueError(
            "No readable text was found in the PDF. Check that the PDF contains "
            "selectable text or that Tesseract can read its scanned pages."
        )

    translator = _create_nllb_translator(
        NLLB_LANGUAGE_MAP[source_lang],
        NLLB_LANGUAGE_MAP[target_lang],
        log_fn,
    )
    translated_blocks: list[TranslatedPDFBlock] = []
    for index, source_block in enumerate(source_blocks, start=1):
        safe_log(
            log_fn,
            f"[INFO] Translating PDF page {source_block.page_number}, "
            f"block {index}/{len(source_blocks)}",
        )
        translated_text = translator.translate(source_block.text, log=log_fn).strip()
        if not translated_text:
            raise RuntimeError(
                f"Translation returned no text for PDF page {source_block.page_number}."
            )
        translated_blocks.append(
            TranslatedPDFBlock(source=source_block, translated_text=translated_text)
        )

    extracted_dir.mkdir(parents=True, exist_ok=True)
    translated_dir.mkdir(parents=True, exist_ok=True)
    page_numbers = sorted({block.source.page_number for block in translated_blocks})
    extracted_files: list[Path] = []
    translated_files: list[Path] = []
    for page_number in page_numbers:
        filename = f"page_{page_number:04d}.txt"
        extracted_file = extracted_dir / filename
        translated_file = translated_dir / filename
        extracted_file.write_text(
            _page_text(translated_blocks, page_number, translated=False),
            encoding="utf-8",
        )
        translated_file.write_text(
            _page_text(translated_blocks, page_number, translated=True),
            encoding="utf-8",
        )
        extracted_files.append(extracted_file)
        translated_files.append(translated_file)

    reintegrate_pdf_text(pdf_path, translated_blocks, output_pdf, log_fn)
    safe_log(
        log_fn,
        f"[DONE] Translated {len(translated_blocks)} PDF text block(s) "
        f"using {source_lang} -> {target_lang}.",
    )
    return PDFTranslationResult(
        translated_pdf=output_pdf,
        extracted_text_files=extracted_files,
        translated_text_files=translated_files,
        translated_block_count=len(translated_blocks),
    )
