import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


def _stub_module(name, attribute):
    module = types.ModuleType(name)
    setattr(module, attribute, Mock())
    return module


class TranslationGuiTests(unittest.TestCase):
    def setUp(self):
        modules = {
            "OpenEduVoice.core.audio.transcriber": "transcribe_audio_files",
            "OpenEduVoice.core.audio.tts_generator": "text_to_speech",
            "OpenEduVoice.core.audio.audio_converter": "convert_audio_to_wav",
            "OpenEduVoice.core.reintegration.reintegrator_all": "reintegrate_text_and_audio",
        }
        self.patcher = patch.dict(
            sys.modules,
            {name: _stub_module(name, attribute) for name, attribute in modules.items()},
        )
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        sys.modules.pop("OpenEduVoice.gui.main_window", None)
        self.addCleanup(sys.modules.pop, "OpenEduVoice.gui.main_window", None)
        self.module = importlib.import_module("OpenEduVoice.gui.main_window")
        self.app = self.module.App.__new__(self.module.App)
        self.app.root = Mock()
        self.app.root.after.side_effect = lambda delay, callback: callback()
        self.app._run_task = lambda task: task()
        self.app.pdf_path = Mock()
        self.app.pdf_path.get.return_value = "lesson.pdf"
        self.app.get_translation_languages = lambda: ("de", "en")
        self.app.log_and_output = Mock()
        self.app.handle_exception = Mock()
        self.app.increment_progress = Mock()

    def test_failed_pdf_step_does_not_run_next_step(self):
        callback = Mock()
        with patch.object(self.module, "translate_pdf", side_effect=ValueError("failed")):
            self.app.translate_pdf_document(callback)
        callback.assert_not_called()
        self.app.handle_exception.assert_called_once()
        self.app.increment_progress.assert_not_called()

    def test_successful_pdf_step_runs_next_step(self):
        callback = Mock()
        result = Mock(
            translated_pdf=Path("translated.pdf"),
            extracted_text_files=[Path("output") / "extracted" / "page.txt"],
        )
        with patch.object(self.module, "translate_pdf", return_value=result):
            self.app.translate_pdf_document(callback)
        callback.assert_called_once()
        self.app.handle_exception.assert_not_called()

    def test_workflow_presets_only_change_step_selection(self):
        pdf, text, audio = Mock(), Mock(), Mock()
        self.app.steps_vars = {
            "Translate PDF": (pdf, Mock()),
            "Translate Slide Text (.txt)": (text, Mock()),
            "Transcribe": (audio, Mock()),
        }
        self.app.select_pdf_workflow()
        pdf.set.assert_called_with(True)
        text.set.assert_called_with(False)
        audio.set.assert_called_with(False)
        self.app.select_pptx_workflow()
        pdf.set.assert_called_with(False)
        text.set.assert_called_with(True)
        audio.set.assert_called_with(True)


if __name__ == "__main__":
    unittest.main()
