from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import fitz
from PIL import Image

from OpenEduVoice.utils.logging_utils import safe_log


OCR_LANGUAGE_MAP = {"de": "deu", "en": "eng"}
OCR_DPI = 300


def _bbox_tuple(rect: fitz.Rect) -> tuple[float, float, float, float]:
    return (float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1))


@dataclass(frozen=True)
class PDFTextBlock:
    page_number: int
    bbox: tuple[float, float, float, float]
    text: str
    from_ocr: bool
    font_size: float
    color: tuple[float, float, float]


def _span_color(value: int) -> tuple[float, float, float]:
    return (
        ((value >> 16) & 255) / 255,
        ((value >> 8) & 255) / 255,
        (value & 255) / 255,
    )


def _extract_digital_blocks(page: fitz.Page, page_number: int) -> list[PDFTextBlock]:
    extracted: list[PDFTextBlock] = []
    for raw_block in page.get_text("dict")["blocks"]:
        if raw_block.get("type") != 0:
            continue

        lines: list[str] = []
        spans: list[dict] = []
        for line in raw_block.get("lines", []):
            line_spans = line.get("spans", [])
            spans.extend(line_spans)
            text = "".join(span.get("text", "") for span in line_spans).strip()
            if text:
                lines.append(text)

        text = "\n".join(lines).strip()
        bbox = raw_block.get("bbox")
        if not text or not bbox or len(bbox) != 4:
            continue

        first_span = spans[0] if spans else {}
        extracted.append(
            PDFTextBlock(
                page_number=page_number,
                bbox=(
                    float(bbox[0]),
                    float(bbox[1]),
                    float(bbox[2]),
                    float(bbox[3]),
                ),
                text=text,
                from_ocr=False,
                font_size=max(4.0, float(first_span.get("size", 10.0))),
                color=_span_color(int(first_span.get("color", 0))),
            )
        )
    return extracted


def _extract_ocr_blocks(
    page: fitz.Page,
    page_number: int,
    source_lang: str,
) -> list[PDFTextBlock]:
    try:
        import pytesseract
    except ImportError as exc:
        raise RuntimeError(
            "Scanned PDF pages require pytesseract. Install the project dependencies "
            "and Tesseract OCR for Windows."
        ) from exc

    ocr_language = OCR_LANGUAGE_MAP[source_lang]
    try:
        available_languages = set(pytesseract.get_languages(config=""))
    except Exception as exc:
        raise RuntimeError(
            "Tesseract OCR was not found or could not start. Install Tesseract OCR "
            "for Windows, add it to PATH, and install its German/English language data."
        ) from exc

    if ocr_language not in available_languages:
        raise RuntimeError(
            f"Tesseract language data '{ocr_language}' is missing. Install the "
            f"'{ocr_language}' traineddata file to process scanned PDFs in {source_lang}."
        )

    scale = OCR_DPI / 72
    pixmap = page.get_pixmap(
        matrix=fitz.Matrix(scale, scale),
        colorspace=fitz.csRGB,
        alpha=False,
    )
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)

    try:
        data = pytesseract.image_to_data(
            image,
            lang=ocr_language,
            output_type=pytesseract.Output.DICT,
            config="--psm 3",
        )
    except Exception as exc:
        raise RuntimeError(
            f"Tesseract OCR failed on PDF page {page_number}: {exc}"
        ) from exc

    grouped_words: dict[tuple[int, int], list[tuple[int, int, str, int, int, int, int]]] = {}
    for index, raw_text in enumerate(data.get("text", [])):
        text = str(raw_text).strip()
        if not text:
            continue
        try:
            if float(data["conf"][index]) < 0:
                continue
            key = (int(data["block_num"][index]), int(data["par_num"][index]))
            word = (
                int(data["line_num"][index]),
                int(data["word_num"][index]),
                text,
                int(data["left"][index]),
                int(data["top"][index]),
                int(data["width"][index]),
                int(data["height"][index]),
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise RuntimeError("Tesseract returned incomplete word-position data.") from exc
        grouped_words.setdefault(key, []).append(word)

    page_rect = page.rect
    scale_x = page_rect.width / pixmap.width
    scale_y = page_rect.height / pixmap.height
    extracted: list[PDFTextBlock] = []

    for words in grouped_words.values():
        words.sort(key=lambda word: (word[0], word[1]))
        lines_by_number: dict[int, list[str]] = {}
        left = min(word[3] for word in words)
        top = min(word[4] for word in words)
        right = max(word[3] + word[5] for word in words)
        bottom = max(word[4] + word[6] for word in words)
        for line_number, _, text, *_ in words:
            lines_by_number.setdefault(line_number, []).append(text)
        text = "\n".join(" ".join(line) for line in lines_by_number.values()).strip()
        if not text:
            continue

        bbox = fitz.Rect(
            left * scale_x,
            top * scale_y,
            right * scale_x,
            bottom * scale_y,
        )
        if page.rotation:
            bbox *= page.derotation_matrix
        extracted.append(
            PDFTextBlock(
                page_number=page_number,
                bbox=_bbox_tuple(bbox),
                text=text,
                from_ocr=True,
                font_size=10.0,
                color=(0.0, 0.0, 0.0),
            )
        )

    return extracted


def extract_pdf_text_blocks(
    document: fitz.Document,
    source_lang: str,
    log_fn: Callable[[str], None] = print,
) -> list[PDFTextBlock]:
    if source_lang not in OCR_LANGUAGE_MAP:
        raise ValueError(f"Unsupported PDF source language: {source_lang}")

    extracted: list[PDFTextBlock] = []
    for page_number, page in enumerate(document, start=1):
        page_blocks = _extract_digital_blocks(page, page_number)
        if not page_blocks:
            safe_log(log_fn, f"[INFO] No selectable text on page {page_number}; running OCR.")
            page_blocks = _extract_ocr_blocks(page, page_number, source_lang)
        safe_log(log_fn, f"[INFO] PDF page {page_number}: {len(page_blocks)} text block(s)")
        extracted.extend(page_blocks)
    return extracted
