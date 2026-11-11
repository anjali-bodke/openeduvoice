from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import fitz

from OpenEduVoice.core.extraction.pdf_text_extractor import PDFTextBlock
from OpenEduVoice.utils.logging_utils import safe_log


@dataclass(frozen=True)
class TranslatedPDFBlock:
    source: PDFTextBlock
    translated_text: str


def _bounded_rect(page: fitz.Page, block: PDFTextBlock) -> fitz.Rect:
    rect = fitz.Rect(block.bbox)
    rect.x0 -= 0.5
    rect.y0 -= 0.5
    rect.x1 += 0.5
    rect.y1 += 0.5
    return rect & page.rect


def _visible_color(color: tuple[float, float, float]) -> tuple[float, float, float]:
    if min(color) > 0.9:
        return (0.0, 0.0, 0.0)
    return color


def _insert_fitted_text(
    page: fitz.Page,
    rect: fitz.Rect,
    block: TranslatedPDFBlock,
) -> bool:
    font_size = min(18.0, max(4.0, block.source.font_size))
    minimum_size = 4.0
    while font_size >= minimum_size:
        spare_height = page.insert_textbox(
            rect,
            block.translated_text,
            fontname="helv",
            fontsize=font_size,
            color=_visible_color(block.source.color),
            lineheight=1.1,
            overlay=True,
        )
        if spare_height >= 0:
            return True
        font_size = round(font_size - 0.5, 2)
    return False


def reintegrate_pdf_text(
    input_pdf: Path,
    translated_blocks: list[TranslatedPDFBlock],
    output_pdf: Path,
    log_fn: Callable[[str], None] = print,
) -> Path:
    input_pdf = Path(input_pdf)
    output_pdf = Path(output_pdf)
    if input_pdf.resolve() == output_pdf.resolve():
        raise ValueError("The translated PDF must not overwrite the source PDF.")
    if not translated_blocks:
        raise ValueError("No translated PDF text blocks were supplied.")

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_pdf.stem}_",
        suffix=".pdf",
        dir=output_pdf.parent,
    )
    os.close(file_descriptor)
    temporary_pdf = Path(temporary_name)

    try:
        with fitz.open(input_pdf) as document:
            if document.is_encrypted:
                raise ValueError("Password-protected PDFs are not supported.")

            page_blocks: dict[int, list[tuple[fitz.Rect, TranslatedPDFBlock]]] = {}
            for block in translated_blocks:
                if not block.translated_text.strip():
                    raise ValueError(
                        f"Translation is empty on PDF page {block.source.page_number}."
                    )
                page_index = block.source.page_number - 1
                if page_index < 0 or page_index >= len(document):
                    raise ValueError(
                        f"Invalid page number in translation block: {block.source.page_number}"
                    )
                page = document[page_index]
                rect = _bounded_rect(page, block.source)
                if rect.is_empty:
                    raise ValueError(
                        f"Text block has an empty bounding box on PDF page "
                        f"{block.source.page_number}."
                    )

                if block.source.from_ocr:
                    page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)
                else:
                    page.add_redact_annot(rect, fill=(1, 1, 1), cross_out=False)
                page_blocks.setdefault(page_index, []).append((rect, block))

            for page_index in page_blocks:
                document[page_index].apply_redactions(
                    images=fitz.PDF_REDACT_IMAGE_NONE,
                    graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                    text=fitz.PDF_REDACT_TEXT_REMOVE,
                )

            overflow_count = 0
            for page_index, blocks in page_blocks.items():
                page = document[page_index]
                for rect, block in blocks:
                    if not _insert_fitted_text(page, rect, block):
                        overflow_count += 1
                        safe_log(
                            log_fn,
                            f"[WARN] Translated text did not fit on PDF page "
                            f"{block.source.page_number}; see the translated text file.",
                        )

            document.save(temporary_pdf, garbage=4, deflate=True)

        os.replace(temporary_pdf, output_pdf)
        if overflow_count:
            safe_log(
                log_fn,
                f"[WARN] {overflow_count} translated block(s) could not fit in their "
                "original text areas.",
            )
        safe_log(log_fn, f"[DONE] Saved translated PDF: {output_pdf}")
    except Exception:
        temporary_pdf.unlink(missing_ok=True)
        raise

    return output_pdf
