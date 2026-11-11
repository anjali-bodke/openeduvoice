import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from OpenEduVoice.core.extraction.slide_text_extractor import extract_slide_text
from OpenEduVoice.core.translation import translator_interface
from OpenEduVoice.utils.cleanup import apply_glossary_cleanup_with_source


class FakeTranslator:
    def __init__(self):
        self.inputs = []

    def translate(self, text, log=None):
        self.inputs.append(text)
        return "translated\ntext"


class SlideTranslationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.input_dir = self.root / "input"
        self.output_dir = self.root / "output"
        self.input_dir.mkdir()
        self.translator = FakeTranslator()
        self.factory = patch.object(
            translator_interface, "_create_translator", return_value=self.translator
        )
        self.factory_mock = self.factory.start()
        self.addCleanup(self.factory.stop)

    def translate(self):
        return translator_interface.translate_text_files(
            self.input_dir, self.output_dir, "de", "en", log=lambda _: None
        )

    def test_preserves_line_count_and_untranslated_content(self):
        source = ["Hallo", "123", "https://example.org/a/b/c", "", ""]
        (self.input_dir / "slide1.txt").write_text(
            "\n".join(source) + "\n", encoding="utf-8"
        )
        result = self.translate()
        self.assertEqual(len(result), 1)
        self.assertEqual(
            result[0].read_text(encoding="utf-8").splitlines(),
            ["translated text", *source[1:]],
        )
        self.assertEqual(self.translator.inputs, ["Hallo"])

    def test_long_lines_are_translated(self):
        text = "Langeswort " * 50
        (self.input_dir / "slide1.txt").write_text(text, encoding="utf-8")
        self.translate()
        self.assertEqual(self.translator.inputs, [text.strip()])

    def test_model_failure_does_not_write_slide(self):
        (self.input_dir / "slide1.txt").write_text("Hallo\n", encoding="utf-8")
        self.translator.translate = lambda *args, **kwargs: ""
        with self.assertRaisesRegex(RuntimeError, "slide1.txt line 1"):
            self.translate()
        self.assertFalse((self.output_dir / "slide1.txt").exists())

    def test_initialization_failure_is_propagated(self):
        (self.input_dir / "slide1.txt").write_text("Hallo\n", encoding="utf-8")
        with patch.object(translator_interface, "_create_translator", side_effect=RuntimeError("model")):
            with self.assertRaisesRegex(RuntimeError, "model"):
                self.translate()

    def test_missing_and_empty_input_are_errors_before_model_load(self):
        with self.assertRaisesRegex(ValueError, "No slide text"):
            self.translate()
        self.factory_mock.assert_not_called()
        self.input_dir.rmdir()
        with self.assertRaisesRegex(ValueError, "does not exist"):
            self.translate()

    def test_extraction_preserves_trailing_empty_paragraphs(self):
        slide = b'''<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
            xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
            <p:sp><p:txBody><a:p><a:r><a:t>Hallo</a:t></a:r></a:p>
            <a:p/><a:p/></p:txBody></p:sp></p:sld>'''
        pptx = self.root / "input.pptx"
        with zipfile.ZipFile(pptx, "w") as archive:
            archive.writestr("ppt/slides/slide1.xml", slide)
        files = extract_slide_text(pptx, self.output_dir, log_fn=lambda _: None)
        self.assertEqual(files[0].read_text(encoding="utf-8").splitlines(), ["Hallo", "", ""])

    def test_hallucination_filter_preserves_source_line_alignment(self):
        source = ["Literatur", "Original reference", "Another reference"]
        translated = [
            "References ISBN 2020",
            "This appropriation is intended to cover something",
            "Another reference",
        ]
        result = apply_glossary_cleanup_with_source(source, translated)
        self.assertEqual(len(result), len(source))
        self.assertEqual(result[1], source[1])

    def test_transcript_translation_failure_is_propagated(self):
        (self.input_dir / "audio.txt").write_text("Hallo", encoding="utf-8")
        self.translator.translate = lambda *args, **kwargs: ""
        with self.assertRaisesRegex(ValueError, "returned no text"):
            translator_interface.translate_transcript_files(
                self.input_dir, self.output_dir, "de", "en", log=lambda _: None
            )
        self.assertFalse((self.output_dir / "audio.txt").exists())


if __name__ == "__main__":
    unittest.main()
