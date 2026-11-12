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


def _create_pdf(path: Path, pages: int = 1) -> fitz.Document:
    document = fitz.open()
    for _ in range(pages):
        document.new_page(width=300, height=200)
    document.save(path)
    document.close()
    return fitz.open(path)


def _make_ocr_data(words: list[str], *, left: int = 125, top: int = 167) -> dict[str, list[str]]:
    count = len(words)
    return {
        "text": words,
        "conf": ["96"] * count,
        "block_num": ["1"] * count,
        "par_num": ["1"] * count,
        "line_num": ["1"] * count,
        "word_num": [str(index + 1) for index in range(count)],
        "left": [str(left + index * 333) for index in range(count)],
        "top": [str(top)] * count,
        "width": ["290"] * count,
        "height": ["83"] * count,
    }


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

    def test_extracts_multiple_digital_blocks_in_page_order(self) -> None:
        document = fitz.open()
        page = document.new_page(width=300, height=200)
        page.insert_text((30, 50), "First block")
        page.insert_text((30, 100), "Second block")

        blocks = extract_pdf_text_blocks(document, "en", log_fn=lambda _: None)

        self.assertEqual([block.text for block in blocks], ["First block", "Second block"])
        self.assertEqual([block.page_number for block in blocks], [1, 1])
        document.close()

    def test_selectable_text_page_does_not_trigger_ocr(self) -> None:
        document = fitz.open()
        page = document.new_page()
        page.insert_text((30, 50), "Digital page")
        with patch(
            "OpenEduVoice.core.extraction.pdf_text_extractor._extract_ocr_blocks"
        ) as ocr:
            blocks = extract_pdf_text_blocks(document, "en", log_fn=lambda _: None)
        ocr.assert_not_called()
        self.assertEqual(blocks[0].text, "Digital page")
        document.close()

    def test_mixed_digital_and_scanned_page_only_extracts_selectable_text(self) -> None:
        document = fitz.open()
        page = document.new_page(width=300, height=200)
        page.insert_text((30, 50), "Selectable text")
        image_bytes = BytesIO()
        Image.new("RGB", (100, 100), "white").save(image_bytes, format="PNG")
        page.insert_image(fitz.Rect(150, 50, 250, 150), stream=image_bytes.getvalue())

        with patch(
            "OpenEduVoice.core.extraction.pdf_text_extractor._extract_ocr_blocks"
        ) as ocr:
            blocks = extract_pdf_text_blocks(document, "en", log_fn=lambda _: None)

        ocr.assert_not_called()
        self.assertEqual([block.text for block in blocks], ["Selectable text"])
        document.close()

    def test_blank_page_triggers_ocr_fallback(self) -> None:
        document = fitz.open()
        document.new_page()
        with patch(
            "OpenEduVoice.core.extraction.pdf_text_extractor._extract_ocr_blocks",
            return_value=[
                PDFTextBlock(1, (10, 10, 100, 30), "Scanned text", True, 10, (0, 0, 0))
            ],
        ) as ocr:
            blocks = extract_pdf_text_blocks(document, "en", log_fn=lambda _: None)
        ocr.assert_called_once()
        self.assertEqual(blocks[0].text, "Scanned text")
        self.assertTrue(blocks[0].from_ocr)
        document.close()

    def test_rejects_unsupported_source_language(self) -> None:
        document = fitz.open()
        document.new_page()
        with self.assertRaisesRegex(ValueError, "Unsupported PDF source language"):
            extract_pdf_text_blocks(document, "fr")
        document.close()

    def test_preserves_spaces_between_styled_spans(self) -> None:
        document = fitz.open()
        page = document.new_page(width=300, height=100)
        page.insert_htmlbox(
            fitz.Rect(20, 20, 280, 80),
            "<span>Hello </span><b>world</b>",
        )

        blocks = extract_pdf_text_blocks(document, "en", log_fn=lambda _: None)

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].text, "Hello world")
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

    def test_ocr_preserves_line_boundaries_and_word_order(self) -> None:
        document = fitz.open()
        page = document.new_page(width=300, height=200)
        data = _make_ocr_data(["second", "line", "first"])
        data["line_num"] = ["2", "2", "1"]
        data["word_num"] = ["2", "3", "1"]

        with (
            patch("pytesseract.get_languages", return_value=["eng"]),
            patch("pytesseract.image_to_data", return_value=data),
        ):
            blocks = _extract_ocr_blocks(page, 1, "en")

        self.assertEqual(blocks[0].text, "first\nsecond line")
        document.close()

    def test_ocr_rotated_page_coordinates_map_back_inside_page(self) -> None:
        document = fitz.open()
        page = document.new_page(width=200, height=100)
        page.set_rotation(90)
        data = _make_ocr_data(["Rotated"], left=50, top=100)
        data["width"] = ["100"]
        data["height"] = ["50"]

        with (
            patch("pytesseract.get_languages", return_value=["eng"]),
            patch("pytesseract.image_to_data", return_value=data),
        ):
            block = _extract_ocr_blocks(page, 1, "en")[0]

        self.assertGreaterEqual(block.bbox[0], page.cropbox.x0)
        self.assertGreaterEqual(block.bbox[1], page.cropbox.y0)
        self.assertLessEqual(block.bbox[2], page.cropbox.x1)
        self.assertLessEqual(block.bbox[3], page.cropbox.y1)
        document.close()

    def test_ocr_failure_reports_page_number(self) -> None:
        document = fitz.open()
        page = document.new_page()
        with (
            patch("pytesseract.get_languages", return_value=["eng"]),
            patch("pytesseract.image_to_data", side_effect=RuntimeError("OCR crash")),
            self.assertRaisesRegex(RuntimeError, "page 4"),
        ):
            _extract_ocr_blocks(page, 4, "en")
        document.close()

    def test_incomplete_ocr_data_is_reported(self) -> None:
        document = fitz.open()
        page = document.new_page()
        with (
            patch("pytesseract.get_languages", return_value=["eng"]),
            patch(
                "pytesseract.image_to_data",
                return_value={"text": ["hello"], "conf": ["95"]},
            ),
            self.assertRaisesRegex(RuntimeError, "incomplete word-position data"),
        ):
            _extract_ocr_blocks(page, 1, "en")
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
    def test_rejects_missing_and_non_pdf_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing.pdf"
            non_pdf = Path(temp_dir) / "notes.txt"
            non_pdf.write_text("not a PDF", encoding="utf-8")
            for path in (missing, non_pdf):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    pdf_translator.translate_pdf(path, "de", "en")

    def test_rejects_unsupported_and_identical_languages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.pdf"
            document = _create_pdf(source)
            document.close()
            for source_lang, target_lang in (("fr", "en"), ("de", "de")):
                with (
                    self.subTest(source=source_lang, target=target_lang),
                    self.assertRaises(ValueError),
                ):
                    pdf_translator.translate_pdf(source, source_lang, target_lang)

    def test_rejects_password_protected_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "locked.pdf"
            document = fitz.open()
            document.new_page()
            document.save(
                source,
                encryption=fitz.PDF_ENCRYPT_AES_256,
                owner_pw="owner",
                user_pw="user",
            )
            document.close()
            with self.assertRaisesRegex(ValueError, "Password-protected"):
                pdf_translator.translate_pdf(source, "de", "en")

    def test_rejects_pdf_with_no_extractable_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "blank.pdf"
            document = _create_pdf(source)
            document.close()
            with (
                patch(
                    "OpenEduVoice.core.extraction.pdf_text_extractor._extract_ocr_blocks",
                    return_value=[],
                ),
                self.assertRaisesRegex(ValueError, "No readable text"),
            ):
                pdf_translator.translate_pdf(source, "en", "de")

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
            self.assertEqual(result.translated_pdf, source_pdf.with_name("lesson_translated.pdf"))
            self.assertEqual(result.extracted_text_files[0].parent.parent, source_pdf.with_name("lesson_translation"))
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

    def test_selected_output_directory_contains_pdf_and_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "lesson.pdf"
            destination = Path(temp_dir) / "results"
            destination.mkdir()
            document = fitz.open()
            page = document.new_page()
            page.insert_text((30, 50), "Hello")
            document.save(source)
            document.close()

            class FakeTranslator:
                def translate(self, text: str, log=None) -> str:
                    return "Hallo"

            with patch.object(pdf_translator, "_create_nllb_translator", return_value=FakeTranslator()):
                result = pdf_translator.translate_pdf(
                    source, "en", "de", log_fn=lambda _: None, output_dir=destination
                )

            self.assertEqual(result.translated_pdf, destination / "lesson_translated.pdf")
            self.assertTrue(result.translated_pdf.is_file())
            self.assertEqual(result.extracted_text_files[0].parent.parent, destination / "lesson_translation")
            self.assertEqual(result.translated_text_files[0].read_text(encoding="utf-8"), "Hallo")
            self.assertFalse(source.with_name("lesson_translated.pdf").exists())

    def test_rejects_missing_output_directory_before_translation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "lesson.pdf"
            _create_pdf(source).close()
            with (
                patch.object(pdf_translator, "_create_nllb_translator") as factory,
                self.assertRaisesRegex(ValueError, "Output folder does not exist"),
            ):
                pdf_translator.translate_pdf(source, "en", "de", output_dir=Path(temp_dir) / "missing")
            factory.assert_not_called()

    def test_translates_multipage_pdf_with_one_model_and_ordered_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "multipage.pdf"
            document = fitz.open()
            for page_number in range(1, 4):
                page = document.new_page(width=300, height=200)
                page.insert_text((30, 50), f"Source page {page_number}")
            document.save(source)
            document.close()

            class FakeTranslator:
                def __init__(self) -> None:
                    self.calls: list[str] = []

                def translate(self, text: str, log=None) -> str:
                    self.calls.append(text)
                    return text.replace("Source", "Translated")

            translator = FakeTranslator()
            with patch.object(
                pdf_translator,
                "_create_nllb_translator",
                return_value=translator,
            ) as factory:
                result = pdf_translator.translate_pdf(source, "en", "de", lambda _: None)

            factory.assert_called_once_with("eng_Latn", "deu_Latn", unittest.mock.ANY)
            self.assertEqual(
                translator.calls,
                ["Source page 1", "Source page 2", "Source page 3"],
            )
            self.assertEqual(
                [path.name for path in result.extracted_text_files],
                ["page_0001.txt", "page_0002.txt", "page_0003.txt"],
            )
            self.assertEqual(
                [path.read_text(encoding="utf-8") for path in result.translated_text_files],
                ["Translated page 1", "Translated page 2", "Translated page 3"],
            )

    def test_scanned_pdf_simulation_uses_ocr_then_translation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "scan.pdf"
            image_bytes = BytesIO()
            Image.new("RGB", (300, 200), "white").save(image_bytes, format="PNG")
            document = fitz.open()
            document.new_page(width=300, height=200).insert_image(
                fitz.Rect(0, 0, 300, 200), stream=image_bytes.getvalue()
            )
            document.save(source)
            document.close()

            class FakeTranslator:
                def translate(self, text: str, log=None) -> str:
                    return "Simulated translation"

            with (
                patch("pytesseract.get_languages", return_value=["eng"]),
                patch(
                    "pytesseract.image_to_data",
                    return_value=_make_ocr_data(["Simulated", "source"]),
                ),
                patch.object(
                    pdf_translator,
                    "_create_nllb_translator",
                    return_value=FakeTranslator(),
                ),
            ):
                result = pdf_translator.translate_pdf(source, "en", "de", lambda _: None)

            self.assertEqual(result.translated_block_count, 1)
            self.assertEqual(
                result.extracted_text_files[0].read_text(encoding="utf-8"),
                "Simulated source",
            )
            with fitz.open(result.translated_pdf) as translated_document:
                self.assertIn(
                    "Simulated translation",
                    translated_document[0].get_text(),
                )

    def test_multipage_pdf_uses_ocr_only_for_scanned_pages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "mixed_pages.pdf"
            image_bytes = BytesIO()
            Image.new("RGB", (300, 200), "white").save(image_bytes, format="PNG")
            document = fitz.open()
            document.new_page(width=300, height=200).insert_text((30, 50), "Digital page")
            document.new_page(width=300, height=200).insert_image(
                fitz.Rect(0, 0, 300, 200), stream=image_bytes.getvalue()
            )
            document.save(source)
            document.close()

            class FakeTranslator:
                def translate(self, text: str, log=None) -> str:
                    return f"Translated {text}"

            with (
                patch("pytesseract.get_languages", return_value=["eng"]) as languages,
                patch(
                    "pytesseract.image_to_data",
                    return_value=_make_ocr_data(["Scanned", "page"]),
                ) as ocr,
                patch.object(
                    pdf_translator,
                    "_create_nllb_translator",
                    return_value=FakeTranslator(),
                ),
            ):
                result = pdf_translator.translate_pdf(source, "en", "de", lambda _: None)

            languages.assert_called_once()
            ocr.assert_called_once()
            self.assertEqual(result.translated_block_count, 2)
            self.assertEqual(
                [path.read_text(encoding="utf-8") for path in result.extracted_text_files],
                ["Digital page", "Scanned page"],
            )

    def test_translation_failure_does_not_create_translated_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "failure.pdf"
            document = fitz.open()
            document.new_page().insert_text((30, 50), "Source text")
            document.save(source)
            document.close()

            class FakeTranslator:
                def translate(self, text: str, log=None) -> str:
                    raise RuntimeError("model failed")

            with patch.object(
                pdf_translator,
                "_create_nllb_translator",
                return_value=FakeTranslator(),
            ):
                with self.assertRaisesRegex(RuntimeError, "model failed"):
                    pdf_translator.translate_pdf(source, "en", "de", lambda _: None)

            self.assertFalse(Path(temp_dir, "failure_translated.pdf").exists())

    def test_source_pdf_is_unchanged_after_translation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.pdf"
            document = fitz.open()
            document.new_page().insert_text((30, 50), "Original")
            document.save(source)
            document.close()
            original_bytes = source.read_bytes()

            class FakeTranslator:
                def translate(self, text: str, log=None) -> str:
                    return "Translated"

            with patch.object(
                pdf_translator,
                "_create_nllb_translator",
                return_value=FakeTranslator(),
            ):
                pdf_translator.translate_pdf(source, "en", "de", lambda _: None)

            self.assertEqual(source.read_bytes(), original_bytes)

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

    def test_reintegrates_rotated_page_text_using_unrotated_coordinates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "rotated.pdf"
            document = fitz.open()
            page = document.new_page(width=200, height=100)
            page.insert_text((140, 50), "Right side source")
            page.set_rotation(90)
            document.save(source)
            document.close()

            with fitz.open(source) as document:
                blocks = extract_pdf_text_blocks(document, "en")
            output = Path(temp_dir) / "rotated_translated.pdf"

            reintegrate_pdf_text(
                source,
                [TranslatedPDFBlock(blocks[0], "Right side translated")],
                output,
                log_fn=lambda _: None,
            )

            with fitz.open(output) as translated_document:
                self.assertIn(
                    "Right side translated",
                    translated_document[0].get_text(),
                )

    def test_rejects_empty_translation_and_invalid_page_without_leaking_temp_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.pdf"
            document = fitz.open()
            document.new_page().insert_text((30, 50), "Source")
            document.save(source)
            document.close()
            output = Path(temp_dir) / "output.pdf"
            source_block = PDFTextBlock(
                1, (20, 20, 100, 60), "Source", False, 10, (0, 0, 0)
            )

            with self.assertRaisesRegex(ValueError, "No translated"):
                reintegrate_pdf_text(source, [], output, log_fn=lambda _: None)
            with self.assertRaisesRegex(ValueError, "empty"):
                reintegrate_pdf_text(
                    source,
                    [TranslatedPDFBlock(source_block, " ")],
                    output,
                    log_fn=lambda _: None,
                )
            with self.assertRaisesRegex(ValueError, "Invalid page"):
                reintegrate_pdf_text(
                    source,
                    [TranslatedPDFBlock(
                        PDFTextBlock(2, source_block.bbox, "Source", False, 10, (0, 0, 0)),
                        "Translation",
                    )],
                    output,
                    log_fn=lambda _: None,
                )
            self.assertEqual(list(Path(temp_dir).iterdir()), [source])

    def test_rejects_out_of_page_bbox_and_cleans_temporary_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.pdf"
            document = fitz.open()
            document.new_page()
            document.save(source)
            document.close()
            invalid_block = PDFTextBlock(
                1, (1000, 1000, 1100, 1100), "Outside", False, 10, (0, 0, 0)
            )
            output = Path(temp_dir) / "output.pdf"

            with self.assertRaisesRegex(ValueError, "empty bounding box"):
                reintegrate_pdf_text(
                    source,
                    [TranslatedPDFBlock(invalid_block, "Translated")],
                    output,
                    log_fn=lambda _: None,
                )

            self.assertFalse(output.exists())
            self.assertEqual(list(Path(temp_dir).iterdir()), [source])

    def test_atomic_output_failure_preserves_source_and_cleans_temp_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.pdf"
            document = fitz.open()
            document.new_page().insert_text((30, 50), "Source")
            document.save(source)
            document.close()
            original_bytes = source.read_bytes()
            with fitz.open(source) as document:
                source_block = extract_pdf_text_blocks(document, "en")[0]
            output = Path(temp_dir) / "translated.pdf"

            with patch(
                "OpenEduVoice.core.reintegration.pdf_reintegrator.os.replace",
                side_effect=OSError("disk failure"),
            ):
                with self.assertRaisesRegex(OSError, "disk failure"):
                    reintegrate_pdf_text(
                        source,
                        [TranslatedPDFBlock(source_block, "Translated")],
                        output,
                        log_fn=lambda _: None,
                    )

            self.assertEqual(source.read_bytes(), original_bytes)
            self.assertFalse(output.exists())
            self.assertEqual(list(Path(temp_dir).iterdir()), [source])

    def test_reports_text_that_cannot_fit_and_still_writes_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "tiny-box.pdf"
            document = fitz.open()
            document.new_page(width=100, height=100).insert_text((10, 20), "Source")
            document.save(source)
            document.close()
            block = PDFTextBlock(
                1, (10, 10, 15, 13), "Source", False, 10, (0, 0, 0)
            )
            logs: list[str] = []
            output = Path(temp_dir) / "tiny-box_translated.pdf"

            reintegrate_pdf_text(
                source,
                [TranslatedPDFBlock(block, "A long translation that cannot fit")],
                output,
                log_fn=logs.append,
            )

            self.assertTrue(output.is_file())
            self.assertTrue(any("did not fit" in message for message in logs))

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

    def test_splits_sentences_without_losing_punctuation(self) -> None:
        chunks = split_text_by_sentences(
            "First sentence. Second sentence! Third sentence?",
            max_chars=25,
        )
        self.assertEqual(
            chunks,
            ["First sentence.", "Second sentence!", "Third sentence?"],
        )

    def test_empty_text_returns_no_chunks(self) -> None:
        self.assertEqual(split_text_by_sentences(" \n\t "), [])

    def test_rejects_nonpositive_chunk_size(self) -> None:
        for size in (0, -1):
            with self.subTest(size=size), self.assertRaises(ValueError):
                split_text_by_sentences("text", max_chars=size)

    def test_splits_unbroken_tokens_without_losing_characters(self) -> None:
        text = "x" * 101
        chunks = split_text_by_sentences(text, max_chars=20)
        self.assertTrue(all(len(chunk) <= 20 for chunk in chunks))
        self.assertEqual("".join(chunks), text)


if __name__ == "__main__":
    unittest.main()
