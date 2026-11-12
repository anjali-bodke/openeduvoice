import importlib
import sys
import tempfile
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
        self.app.pptx_path = Mock()
        self.app.pptx_path.get.return_value = "lesson.pptx"
        self.app.pdf_output_dir = Mock()
        self.app.pdf_output_dir.get.return_value = ""
        self.app.pptx_output_dir = Mock()
        self.app.pptx_output_dir.get.return_value = ""
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
        with patch.object(self.module, "translate_pdf", return_value=result) as translate:
            self.app.translate_pdf_document(callback)
        self.assertEqual(translate.call_args.kwargs["output_dir"], Path("."))
        callback.assert_called_once()
        self.app.handle_exception.assert_not_called()

    def test_selected_pdf_folder_is_passed_to_translation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self.app.pdf_output_dir.get.return_value = temp_dir
            result = Mock(
                translated_pdf=Path(temp_dir) / "lesson_translated.pdf",
                extracted_text_files=[Path(temp_dir) / "lesson_translation" / "extracted" / "page.txt"],
            )
            with patch.object(self.module, "translate_pdf", return_value=result) as translate:
                self.app.translate_pdf_document()
            translate.assert_called_once_with(
                Path("lesson.pdf"), "de", "en", log_fn=self.app.log_and_output,
                output_dir=Path(temp_dir),
            )
            self.app.handle_exception.assert_not_called()

    def test_pptx_output_folder_is_used_for_intermediate_and_final_files(self):
        self.assertEqual(self.app.get_base_path(), Path("lesson_transcript"))
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir)
            self.app.pptx_output_dir.get.return_value = temp_dir
            self.assertEqual(self.app.get_base_path(), destination / "lesson_transcript")
            with patch.object(self.module, "reintegrate_text_and_audio") as reintegrate:
                self.app.reintegrate_text_and_audio_combined()
            reintegrate.assert_called_once_with(
                Path("lesson.pptx"),
                destination / "lesson_transcript" / "translated_text_txt",
                destination / "lesson_transcript" / "tts_audio",
                destination / "lesson_final_combined.pptx",
                log_fn=self.app.log_and_output,
                output_fn=self.app.log_and_output,
            )
            self.app.handle_exception.assert_not_called()

    def test_output_folder_picker_preserves_selection_on_cancel(self):
        output_var = Mock()
        with patch.object(self.module.filedialog, "askdirectory", side_effect=["chosen", ""]):
            self.app.browse_output_folder(output_var)
            self.app.browse_output_folder(output_var)
        output_var.set.assert_called_once_with("chosen")

    def test_invalid_selected_folder_stops_workflow(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            for name, output_var in (
                ("Translate PDF", self.app.pdf_output_dir),
                ("Extract Slide Text (.txt)", self.app.pptx_output_dir),
            ):
                with self.subTest(step=name):
                    output_var.get.return_value = str(Path(temp_dir) / "missing")
                    step = Mock()
                    self.app.steps_vars = {name: (Mock(get=Mock(return_value=True)), step)}
                    self.app.acknowledge_var = Mock(get=Mock(return_value=True))
                    self.app.progress_bar = {}
                    with patch.object(self.module.tk, "BooleanVar"):
                        self.app.run_selected_steps()
                    step.assert_not_called()
                    self.app.handle_exception.assert_called_once()
                    self.app.handle_exception.reset_mock()
                    output_var.get.return_value = ""

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

    def test_window_starts_and_switches_modes(self):
        try:
            root = self.module.tk.Tk()
        except self.module.tk.TclError as error:
            self.skipTest(f"Tk display unavailable: {error}")
        self.addCleanup(root.destroy)
        root.withdraw()

        app = self.module.App(root)
        root.geometry("640x520")
        root.deiconify()
        root.update()
        self.assertEqual(app.current_mode.get(), "pptx")
        for mode, button, frame in (
            ("pdf", app.pdf_mode_btn, app.pdf_frame),
            ("pptx", app.pptx_mode_btn, app.pptx_frame),
        ):
            button.invoke()
            root.update()
            self.assertEqual(app.current_mode.get(), mode)
            self.assertGreaterEqual(button.winfo_height(), button.winfo_reqheight())
            canvas = next(child for child in frame.winfo_children()
                          if isinstance(child, self.module.tk.Canvas))
            content = canvas.nametowidget(canvas.itemcget(canvas.find_all()[0], "window"))
            self.assertEqual(content.winfo_width(), canvas.winfo_width())
            self.assertGreater(canvas.winfo_height(), 100)
            self.assertGreater(app.log_text.winfo_height(), 40)
            file_frame = content.winfo_children()[0]
            browse = file_frame.grid_slaves(row=1, column=2)[0]
            with patch.object(self.module.filedialog, "askdirectory", return_value=mode):
                browse.invoke()
            self.assertEqual(getattr(app, f"{mode}_output_dir").get(), mode)
            canvas.yview_moveto(1)
            root.update()
            self.assertAlmostEqual(canvas.yview()[1], 1.0)

        self.assertEqual(app.pdf_output_dir.get(), "pdf")
        self.assertEqual(app.pptx_output_dir.get(), "pptx")
        root.geometry("900x700")
        root.update()
        canvas = next(child for child in app.pptx_frame.winfo_children()
                      if isinstance(child, self.module.tk.Canvas))
        content = canvas.nametowidget(canvas.itemcget(canvas.find_all()[0], "window"))
        self.assertEqual(content.winfo_width(), canvas.winfo_width())


if __name__ == "__main__":
    unittest.main()
