from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from OpenEduVoice.config.constants import (
    AUTO_CLAMP_BOUNDS,
    AUTO_DEADBAND_RATIO,
    AUTO_DEADBAND_SEC,
)
from OpenEduVoice.core.audio.audio_converter import convert_audio_to_wav
from OpenEduVoice.core.audio.transcriber import transcribe_audio_files
from OpenEduVoice.core.audio.tts_generator import text_to_speech
from OpenEduVoice.core.extraction.slide_text_extractor import (
    extract_audio_from_pptx,
    extract_slide_text,
)
from OpenEduVoice.core.reintegration.reintegrator_all import reintegrate_text_and_audio
from OpenEduVoice.core.translation.markdown_translator import translate_markdown
from OpenEduVoice.core.translation.pdf_translator import translate_pdf
from OpenEduVoice.core.translation.translator_interface import (
    translate_text_files,
    translate_transcript_files,
)

if TYPE_CHECKING:
    from OpenEduVoice.gui.main_window import App


DOCUMENT_STEPS = ("Translate PDF", "Translate Markdown")


class WorkflowController:
    def __init__(self, app: App) -> None:
        self.app = app

    def _run_task(self, task: Callable[[], None]) -> None:
        threading.Thread(target=task, daemon=True).start()

    def _run_step(
        self,
        context: str,
        action: Callable[[], None],
        on_complete: Callable[[], None] | None,
    ) -> None:
        def task() -> None:
            try:
                action()
            except Exception as exc:
                self.app.handle_exception(context, exc)
            else:
                if on_complete:
                    self.app.root.after(0, on_complete)

        self._run_task(task)

    def run_selected_steps(self) -> None:
        app = self.app
        if not getattr(app, "acknowledge_var", None) or not app.acknowledge_var.get():
            app.log_and_output(
                "[WARN] Please confirm the acknowledgement checkbox before running any steps."
            )
            return

        app.progress_bar["value"] = 0
        selected_steps = [
            (name, method)
            for name, (var, method) in app.steps_vars.items()
            if var.get()
        ]
        if not selected_steps:
            app.log_and_output("[WARN] Select at least one step to run.")
            return

        try:
            if any(name == "Translate PDF" for name, _ in selected_steps):
                app.get_output_directory(app.pdf_output_dir, Path(app.pdf_path.get()))
            if any(name == "Translate Markdown" for name, _ in selected_steps):
                app.get_output_directory(
                    app.markdown_output_dir, Path(app.markdown_path.get())
                )
            if any(name not in DOCUMENT_STEPS for name, _ in selected_steps):
                app.get_output_directory(
                    app.pptx_output_dir, Path(app.pptx_path.get())
                )
        except ValueError as exc:
            app.handle_exception("Output folder", exc)
            return

        app.progress_bar["maximum"] = len(selected_steps)
        app.ui_progress(0)

        def run_step(index: int = 0) -> None:
            if index >= len(selected_steps):
                app.done("All selected steps completed.")
                return

            name, method = selected_steps[index]
            app.log_and_output(f"Starting: {name}")
            method(lambda: run_step(index + 1))

        run_step()

    def extract_and_convert_audio(
        self, on_complete: Callable[[], None] | None = None
    ) -> None:
        app = self.app

        def action() -> None:
            pptx_path = Path(app.pptx_path.get())
            base_dir = app.get_base_path()
            media_dir = base_dir / "media"
            wav_dir = base_dir / "converted_wav"

            extracted = extract_audio_from_pptx(
                pptx_path, base_dir, log_fn=app.log_and_output
            )
            app.log_and_output(f"Extracted {len(extracted)} audio files to: {media_dir}")

            converted = convert_audio_to_wav(
                media_dir, wav_dir, log_fn=app.log_and_output
            )
            app.log_and_output(
                f"Converted {len(converted)} audio files to WAV in: {wav_dir}"
            )
            app.increment_progress()

        self._run_step("Extract + Convert Audio", action, on_complete)

    def translate_pdf_document(
        self, on_complete: Callable[[], None] | None = None
    ) -> None:
        app = self.app

        def action() -> None:
            source_lang, target_lang = app.get_translation_languages()
            pdf_path = Path(app.pdf_path.get())
            result = translate_pdf(
                pdf_path,
                source_lang,
                target_lang,
                log_fn=app.log_and_output,
                output_dir=app.get_output_directory(app.pdf_output_dir, pdf_path),
            )
            app.log_and_output(f"Translated PDF saved to: {result.translated_pdf}")
            app.log_and_output(
                "Extracted and translated PDF text saved to: "
                f"{result.extracted_text_files[0].parent.parent}"
            )
            app.increment_progress()

        self._run_step("Translate PDF", action, on_complete)

    def translate_markdown_document(
        self, on_complete: Callable[[], None] | None = None
    ) -> None:
        app = self.app

        def action() -> None:
            source_lang, target_lang = app.get_translation_languages()
            markdown_path = Path(app.markdown_path.get())
            result = translate_markdown(
                markdown_path,
                source_lang,
                target_lang,
                log_fn=app.log_and_output,
                output_dir=app.get_output_directory(
                    app.markdown_output_dir, markdown_path
                ),
            )
            app.log_and_output(
                f"Translated Markdown saved to: {result.translated_markdown}"
            )
            app.log_and_output(
                "Extracted and translated Markdown text saved to: "
                f"{result.extracted_text_files[0].parent.parent}"
            )
            app.increment_progress()

        self._run_step("Translate Markdown", action, on_complete)

    def extract_slide_text_txt(
        self, on_complete: Callable[[], None] | None = None
    ) -> None:
        app = self.app

        def action() -> None:
            output_dir = app.get_subdir("slide_text_txt")
            extracted = extract_slide_text(Path(app.pptx_path.get()), output_dir)
            app.log_and_output(f"Extracted {len(extracted)} text files to: {output_dir}")
            app.increment_progress()

        self._run_step("Extract Slide Text", action, on_complete)

    def transcribe_audio(
        self, on_complete: Callable[[], None] | None = None
    ) -> None:
        app = self.app

        def action() -> None:
            input_dir = app.get_subdir("converted_wav")
            output_dir = app.get_subdir("transcripts")
            transcribed = transcribe_audio_files(
                input_dir, output_dir, log_fn=app.log_and_output
            )
            app.log_and_output(
                f"{len(transcribed)} files transcribed and saved in: {output_dir}"
            )
            app.increment_progress()

        self._run_step("Transcribe Audio", action, on_complete)

    def translate_text(
        self, on_complete: Callable[[], None] | None = None
    ) -> None:
        app = self.app

        def action() -> None:
            input_dir = app.get_subdir("transcripts")
            output_dir = app.get_subdir("translated_text")
            source_lang, target_lang = app.get_translation_languages()
            translated = translate_transcript_files(
                input_dir,
                output_dir,
                source_lang,
                target_lang,
                app.log_and_output,
                app.log_and_output,
            )
            app.log_and_output(
                f"Translated {len(translated)} transcript files to: {output_dir}"
            )
            app.increment_progress()

        self._run_step("Translate Audio Transcripts", action, on_complete)

    def translate_slide_text_txt(
        self, on_complete: Callable[[], None] | None = None
    ) -> None:
        app = self.app

        def action() -> None:
            input_dir = app.get_subdir("slide_text_txt")
            output_dir = app.get_subdir("translated_text_txt")
            source_lang, target_lang = app.get_translation_languages()
            translated = translate_text_files(
                input_dir,
                output_dir,
                source_lang,
                target_lang,
                app.log_and_output,
                app.log_and_output,
            )
            app.log_and_output(
                f"Translated {len(translated)} slide text files to: {output_dir}"
            )
            app.increment_progress()

        self._run_step("Translate Slide Text", action, on_complete)

    def generate_tts(
        self, on_complete: Callable[[], None] | None = None
    ) -> None:
        app = self.app

        def action() -> None:
            base_dir = app.get_base_path()
            input_dir = app.get_subdir("translated_text")
            output_dir = app.get_subdir("tts_audio")
            _, target_lang = app.get_translation_languages()

            candidates = [
                base_dir / "media",
                base_dir / "converted_wav",
                base_dir / "original_audio",
                base_dir / "audio",
            ]
            original_audio_dir = next(
                (candidate for candidate in candidates if candidate.exists()), None
            )
            if original_audio_dir is None:
                app.log_and_output(
                    "[INFO] No original audio folder found (media/, converted_wav/, "
                    "original_audio/, audio/). Auto-tempo will be skipped."
                )

            audio_files = text_to_speech(
                text_dir=input_dir,
                output_dir=output_dir,
                target_lang=target_lang,
                model_map=app.language_model_map,
                log=app.log_and_output,
                output=app.log_and_output,
                original_audio_dir=original_audio_dir,
                auto_deadband_sec=AUTO_DEADBAND_SEC,
                auto_deadband_ratio=AUTO_DEADBAND_RATIO,
                auto_clamp_bounds=AUTO_CLAMP_BOUNDS,
                tts_lang=app.language.get(),
            )
            app.log_and_output(
                f"Generated {len(audio_files)} TTS audio files to: {output_dir}"
            )
            app.increment_progress()

        self._run_step("Generate TTS Audio", action, on_complete)

    def reintegrate_text_and_audio_combined(
        self, on_complete: Callable[[], None] | None = None
    ) -> None:
        app = self.app

        def action() -> None:
            pptx_path = Path(app.pptx_path.get())
            base_dir = app.get_base_path()
            output_path = app.get_output_directory(
                app.pptx_output_dir, pptx_path
            ) / f"{pptx_path.stem}_final_combined.pptx"

            reintegrate_text_and_audio(
                pptx_path,
                base_dir / "translated_text_txt",
                base_dir / "tts_audio",
                output_path,
                log_fn=app.log_and_output,
            )
            app.log_and_output(
                f"Combined reintegrated PPTX saved to: {output_path}"
            )
            app.increment_progress()

        self._run_step("Reintegrate Text and Audio", action, on_complete)
