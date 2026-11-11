from __future__ import annotations

import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import fitz
import pytesseract
from PIL import Image, ImageDraw

from OpenEduVoice.core.extraction.pdf_text_extractor import (
    PDFTextBlock,
    _extract_ocr_blocks,
    extract_pdf_text_blocks,
)
from OpenEduVoice.core.reintegration.pdf_reintegrator import (
    TranslatedPDFBlock,
    reintegrate_pdf_text,
)
from OpenEduVoice.core.translation import pdf_translator
from OpenEduVoice.utils.preprocessing import split_text_by_sentences


class PDFExtractionTests(unittest.TestCase):
    def test_extracts_selectable_text_without_running_ocr(self) -> None:
        document = fitz.open()
        page = document.new_page(width=300, height=200)
        page.insert_text((30, 50), "Hallo Welt")

        with patch("pytesseract.get_languages") as get_languages:
            blocks = extract_pdf_text_blocks(document, "de", log_fn=lambda _: None)

        get_languages.assert_not_called()
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].text, "Hallo Welt")
        self.assertFalse(blocks[0].from_ocr)
        document.close()

    def test_ocr_groups_words_by_paragraph_and_maps_coordinates(self) -> None:
        document = fitz.open()
        page = document.new_page(width=300, height=200)
        data = {
            "text": ["Hello", "world"],
            "conf": ["96", "97"],
            "block_num": ["1", "1"],
            "par_num": ["1", "1"],
            "line_num": ["1", "1"],
            "word_num": ["1", "2"],
            "left": ["30", "120"],
            "top": ["40", "40"],
            "width": ["70", "70"],
            "height": ["20", "20"],
        }

        with (
            patch("pytesseract.get_languages", return_value=["eng"]),
            patch("pytesseract.image_to_data", return_value=data),
        ):
            blocks = _extract_ocr_blocks(page, 1, "en")

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].text, "Hello world")
        self.assertTrue(blocks[0].from_ocr)
        self.assertGreater(blocks[0].bbox[2], blocks[0].bbox[0])
        document.close()

    def test_missing_tesseract_language_data_is_reported(self) -> None:
        document = fitz.open()
        page = document.new_page()
        with (
            patch("pytesseract.get_languages", return_value=["eng"]),
            self.assertRaisesRegex(RuntimeError, "deu"),
        ):
            _extract_ocr_blocks(page, 1, "de")
        document.close()

    def test_missing_tesseract_executable_is_reported(self) -> None:
        document = fitz.open()
        page = document.new_page()
        with (
            patch(
                "pytesseract.get_languages",
                side_effect=pytesseract.TesseractNotFoundError(),
            ),
            self.assertRaisesRegex(RuntimeError, "Tesseract OCR was not found"),
        ):
            _extract_ocr_blocks(page, 1, "en")
        document.close()


class PDFTranslationTests(unittest.TestCase):
    def test_creates_translated_pdf_and_text_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_pdf = Path(temp_dir) / "lesson.pdf"
            document = fitz.open()
            page = document.new_page(width=300, height=200)
            page.insert_text((30, 50), "Hallo Welt")
            image_bytes = BytesIO()
            Image.new("RGB", (10, 10), (255, 0, 0)).save(image_bytes, format="PNG")
            page.insert_image(
                fitz.Rect(200, 20, 260, 80),
                stream=image_bytes.getvalue(),
            )
            document.save(source_pdf)
            document.close()

            class FakeTranslator:
                def __init__(self, source_lang: str, target_lang: str, log=None) -> None:
                    self.source_lang = source_lang
                    self.target_lang = target_lang
                    self.log = log

                def translate(self, text: str, log=None) -> str:
                    if log:
                        log("mock translation")
                    return "Hello world" if text else text

            with patch.object(
                pdf_translator,
                "_create_nllb_translator",
                return_value=FakeTranslator("deu_Latn", "eng_Latn"),
            ):
                result = pdf_translator.translate_pdf(
                    source_pdf, "de", "en", log_fn=lambda _: None
                )

            self.assertTrue(result.translated_pdf.is_file())
            self.assertEqual(result.translated_block_count, 1)
            self.assertEqual(
                result.extracted_text_files[0].read_text(encoding="utf-8"),
                "Hallo Welt",
            )
            self.assertEqual(
                result.translated_text_files[0].read_text(encoding="utf-8"),
                "Hello world",
            )

            with fitz.open(result.translated_pdf) as translated_document:
                translated_page = translated_document[0]
                translated_text = translated_page.get_text()
                page_images = translated_page.get_images()
            self.assertIn("Hello world", translated_text)
            self.assertNotIn("Hallo Welt", translated_text)
            self.assertTrue(page_images)

    def test_reintegrates_ocr_text_over_a_page_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_pdf = Path(temp_dir) / "scan.pdf"
            image_bytes = BytesIO()
            scan = Image.new("RGB", (300, 200), "white")
            ImageDraw.Draw(scan).text((30, 40), "Scanned source", fill="black")
            scan.save(image_bytes, format="PNG")

            document = fitz.open()
            page = document.new_page(width=300, height=200)
            page.insert_image(fitz.Rect(0, 0, 300, 200), stream=image_bytes.getvalue())
            document.save(source_pdf)
            document.close()

            source_block = PDFTextBlock(
                page_number=1,
                bbox=(25.0, 35.0, 120.0, 60.0),
                text="Scanned source",
                from_ocr=True,
                font_size=10.0,
                color=(0.0, 0.0, 0.0),
            )
            output_pdf = Path(temp_dir) / "scan_translated.pdf"
            reintegrate_pdf_text(
                source_pdf,
                [TranslatedPDFBlock(source_block, "Translated source")],
                output_pdf,
                log_fn=lambda _: None,
            )

            with fitz.open(output_pdf) as translated_document:
                page = translated_document[0]
                translated_text = page.get_text()
                page_images = page.get_images()
            self.assertIn("Translated source", translated_text)
            self.assertTrue(page_images)

    def test_rejects_source_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_pdf = Path(temp_dir) / "source.pdf"
            document = fitz.open()
            page = document.new_page()
            page.insert_text((30, 50), "Original")
            document.save(source_pdf)
            document.close()

            with fitz.open(source_pdf) as document:
                blocks = extract_pdf_text_blocks(document, "en")

            translated_blocks = [
                TranslatedPDFBlock(source=block, translated_text="Translated")
                for block in blocks
            ]
            with self.assertRaisesRegex(ValueError, "overwrite"):
                reintegrate_pdf_text(
                    source_pdf,
                    translated_blocks,
                    source_pdf,
                    log_fn=lambda _: None,
                )


class TranslationChunkingTests(unittest.TestCase):
    def test_long_sentence_is_split_without_losing_text(self) -> None:
        text = "word " * 120

        chunks = split_text_by_sentences(text, max_chars=40)

        self.assertTrue(all(len(chunk) <= 40 for chunk in chunks))
        self.assertEqual(" ".join(chunks), text.strip())


if __name__ == "__main__":
    unittest.main()
