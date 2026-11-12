import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from OpenEduVoice.core.translation import markdown_translator
from OpenEduVoice.core.translation.markdown_translator import (
    translate_markdown,
    translate_markdown_text,
)


class FakeTranslator:
    def translate(self, text, log=None):
        return text.upper()


class MarkdownTranslationTests(unittest.TestCase):
    def test_structure_code_and_links_are_preserved(self):
        source = (
            "---\ntitle: Hallo\n---\n"
            "# Titel\n\n"
            "Erster Satz mit `code` und [Link](http://x.de/a).\nZweite Zeile.\n\n"
            "- [ ] Aufgabe\n"
            "> Zitat\n\n"
            "```python\nprint('hallo')\n```\n\n"
            "| Name | Wert |\n| --- | --- |\n| eins | 1 |\n"
        )
        result, sources, _ = translate_markdown_text(source, FakeTranslator())
        self.assertEqual(
            result,
            "---\ntitle: Hallo\n---\n"
            "# TITEL\n\n"
            "ERSTER SATZ MIT `code` UND [LINK](http://x.de/a). ZWEITE ZEILE.\n\n"
            "- [ ] AUFGABE\n"
            "> ZITAT\n\n"
            "```python\nprint('hallo')\n```\n\n"
            "| NAME | WERT |\n| --- | --- |\n| EINS | 1 |\n",
        )
        self.assertIn("Titel", sources)

    def test_translate_markdown_writes_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "notes.md"
            path.write_text("# Hallo\n\nWelt\n", encoding="utf-8")
            with patch.object(
                markdown_translator, "_create_nllb_translator", return_value=FakeTranslator()
            ):
                result = translate_markdown(path, "de", "en", log_fn=lambda _: None)
            self.assertEqual(
                result.translated_markdown.read_text(encoding="utf-8"), "# HALLO\n\nWELT\n"
            )
            self.assertTrue(result.extracted_text_files[0].is_file())
            self.assertTrue(result.translated_text_files[0].is_file())

    def test_validation_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "notes.md"
            path.write_text("Hallo\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                translate_markdown(path, "de", "de")
            with self.assertRaises(ValueError):
                translate_markdown(path, "fr", "en")
            with self.assertRaises(ValueError):
                translate_markdown(Path(folder) / "notes.txt", "de", "en")


if __name__ == "__main__":
    unittest.main()
