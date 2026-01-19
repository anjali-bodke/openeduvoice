"""
main_window.py

Tkinter-based GUI for the Audio PowerPoint Automation Tool.
Supports extraction, translation, transcription, TTS, and reintegration.
"""

from __future__ import annotations

import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk

# Core pipeline modules
from OpenEduVoice.core.extraction.slide_text_extractor import (
    extract_audio_from_pptx,
    extract_slide_text,
)
from OpenEduVoice.core.audio.transcriber import transcribe_audio_files
from OpenEduVoice.core.translation.translator_interface import (
    translate_transcript_files,
    translate_text_files,
)
from OpenEduVoice.core.audio.tts_generator import text_to_speech
from OpenEduVoice.core.audio.audio_converter import convert_audio_to_wav
from OpenEduVoice.core.reintegration.reintegrator_all import reintegrate_text_and_audio
from OpenEduVoice.utils.logging_utils import safe_log
from OpenEduVoice.config.constants import (
    TTS_LANGUAGE_MODEL_MAP,
    AUTO_DEADBAND_SEC,
    AUTO_DEADBAND_RATIO,
    AUTO_CLAMP_BOUNDS,
)


class App:
    """
    GUI Controller for the Audio PowerPoint Automation Tool.
    """

    def __init__(self, root):
        self.root = root
        self.root.title("Audio PowerPoint Automation Tool")
        self.root.geometry("700x750")

        self.pptx_path = tk.StringVar()
        self.language = tk.StringVar(value="English")
        self.translation_direction = tk.StringVar(value="German to English")
        self.acknowledge_var = tk.BooleanVar(value=False)

        self.language_model_map = TTS_LANGUAGE_MODEL_MAP.copy()

        self.steps_vars: dict[str, tuple[tk.BooleanVar, callable]] = {}
        self.setup_ui()

    # ====== Thread-safe UI helpers ======

    def _ui(self, fn, *args, **kwargs):
        """Schedule any Tk widget call on the main thread."""
        self.root.after(0, lambda: fn(*args, **kwargs))

    def ui_set_text(self, widget, text: str, replace: bool = False):
        """Thread-safe: set/append text in Text/Entry/Label-like widgets."""
        if hasattr(widget, "insert"):  # Text widget
            if replace:
                self._ui(widget.delete, "1.0", "end")
            self._ui(widget.insert, "end", text)
            self._ui(widget.see, "end")
        elif hasattr(widget, "configure"):  # Label-like
            self._ui(widget.configure, text=text)

    def ui_progress(self, value: float):
        """Thread-safe: update progress bar [0..100]."""
        if hasattr(self, "progress_bar"):
            self._ui(self.progress_bar.configure, value=value)

    def ui_log(self, message: str):
        """Thread-safe: log to the log panel only."""
        if hasattr(self, "log_text"):
            self.ui_set_text(self.log_text, (message.rstrip() + "\n"))

    def ui_output(self, message: str, replace: bool = False):
        """Thread-safe: update output summary panel only."""
        if hasattr(self, "output_text"):
            self.ui_set_text(self.output_text, (message.rstrip() + "\n"), replace=replace)

    def log_and_output(self, message: str):
        """Central logging: file/console + GUI log + GUI output."""
        try:
            safe_log(self.log_text, message)  # matches existing safe_log signature
        except Exception:
            print(message)  # fallback if widget not ready
        self.ui_log(message)

        # Only mirror summaries to Output
        summary_prefixes = ("[DONE]", "Combined", "Generated", "Translated",
                            "Saved", "Selected", "Starting", "[WARN]", "[ERROR]")
        if message.startswith(summary_prefixes):
            self.ui_output(message)


    def tick(self, delta: float = 1.0, note: str | None = None):
        """Thread-safe: bump progress a bit and optionally log."""
        try:
            current = float(self.progress_bar["value"])
        except Exception:
            current = 0.0
        self.ui_progress(current + delta)
        if note:
            self.log_and_output(note)

    def done(self, note: str = "✔ Done"):
        """Thread-safe: mark 100% and log a note."""
        self.ui_progress(100.0)
        self.log_and_output(note)

    # ====== Helpers ======

    def get_base_path(self) -> Path:
        return Path(self.pptx_path.get()).with_name(
            Path(self.pptx_path.get()).stem + "_transcript"
        )

    def get_subdir(self, name: str) -> Path:
        """Returns a subdirectory under the base path."""
        return self.get_base_path() / name

    def get_translation_languages(self) -> tuple[str, str]:
        return (
            ("de", "en")
            if self.translation_direction.get() == "German to English"
            else ("en", "de")
        )

    def handle_exception(self, context: str, e: Exception):
        self.log_and_output(f"[ERROR] {context}: {e}")

    def _run_task(self, task):
        threading.Thread(target=task, daemon=True).start()

    def increment_progress(self):
        try:
            current = float(self.progress_bar["value"])
        except Exception:
            current = 0.0
        self.ui_progress(current + 1.0)

    # ====== UI Layout ======

    def setup_ui(self):
        default_font = ("Segoe UI", 10)

        # 1. File selection
        file_frame = tk.LabelFrame(self.root, text="1. Select PowerPoint File", font=default_font)
        file_frame.pack(fill="x", padx=10, pady=10)
        tk.Label(file_frame, text="File Path:", font=default_font).grid(row=0, column=0, sticky="w", padx=5, pady=5)
        tk.Entry(file_frame, textvariable=self.pptx_path, font=default_font).grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        tk.Button(file_frame, text="Browse", command=self.browse_file).grid(row=0, column=2, padx=5, pady=5)
        file_frame.columnconfigure(1, weight=1)

        # 2. Steps
        step_frame = tk.LabelFrame(self.root, text="2. Select Steps to Run", font=default_font)
        step_frame.pack(fill="x", padx=10, pady=5)
        for i, (label, method) in enumerate(
            [
                ("Extract + Convert Audio", self.extract_and_convert_audio),
                ("Extract Slide Text (.txt)", self.extract_slide_text_txt),
                ("Transcribe", self.transcribe_audio),
                ("Translate Audio Transcripts", self.translate_text),
                ("Translate Slide Text (.txt)", self.translate_slide_text_txt),
                ("Generate TTS Audio", self.generate_tts),
                ("Reintegrate Text and Audio (Combined)", self.reintegrate_text_and_audio_combined),
            ]
        ):
            var = tk.BooleanVar()
            chk = tk.Checkbutton(step_frame, text=label, variable=var, font=default_font)
            chk.grid(row=i // 2, column=i % 2, sticky="w", padx=10, pady=2)
            self.steps_vars[label] = (var, method)

        # 3. Language & TTS settings
        lang_frame = tk.LabelFrame(self.root, text="3. Language Settings", font=default_font)
        lang_frame.pack(fill="x", padx=10, pady=5)

        tk.Label(lang_frame, text="TTS Language:", font=default_font).grid(row=0, column=0, sticky="w", padx=5, pady=5)
        ttk.Combobox(
            lang_frame,
            textvariable=self.language,
            values=list(self.language_model_map.keys()),
            state="readonly",
            font=default_font,
        ).grid(row=0, column=1, sticky="ew", padx=5, pady=5)

        tk.Label(lang_frame, text="Translation Direction:", font=default_font).grid(row=1, column=0, sticky="w", padx=5, pady=5)
        ttk.Combobox(
            lang_frame,
            textvariable=self.translation_direction,
            values=["German to English", "English to German"],
            state="readonly",
            font=default_font,
        ).grid(row=1, column=1, sticky="ew", padx=5, pady=5)

        # 4. Control buttons
        control_frame = tk.Frame(self.root)
        control_frame.pack(fill="x", padx=10, pady=10)

        tk.Button(
            control_frame,
            text="Run Selected Steps",
            command=self.run_selected_steps,
            font=default_font,
        ).pack(side="left", padx=5)

        ack_text = (
            "I understand this software uses AI tools/technology for translation. "
            "After all steps are completed, I will manually verify all slides before intended use."
        )

        tk.Checkbutton(
            control_frame,
            text=ack_text,
            variable=self.acknowledge_var,
            font=default_font,
            wraplength=430,   # keeps it readable next to the button
            justify="left",
        ).pack(side="left", padx=10)

        tk.Button(
            control_frame,
            text="Exit",
            command=self.root.quit,
            font=default_font,
        ).pack(side="left", padx=5)

        # 5. Progress bar
        progress_frame = tk.LabelFrame(self.root, text="4. Progress", font=default_font)
        progress_frame.pack(fill="x", padx=10, pady=5)
        self.progress_bar = ttk.Progressbar(progress_frame, orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill="x", padx=10, pady=5)

        # 6. Log output
        log_frame = tk.LabelFrame(self.root, text="5. Log", font=default_font)
        log_frame.pack(fill="both", expand=False, padx=10, pady=5)
        self.log_text = tk.Text(log_frame, height=7, bg="#f0f0f0", font=("Courier", 9))
        self.log_text.pack(fill="x", padx=5, pady=5)

        # 7. Output summary
        output_frame = tk.LabelFrame(self.root, text="6. Output Summary", font=default_font)
        output_frame.pack(fill="both", expand=False, padx=10, pady=10)
        self.output_text = tk.Text(output_frame, height=5, bg="#f8f8f8", fg="black", wrap="word", font=("Courier", 9))
        self.output_text.pack(fill="x", padx=5, pady=5)

    # ====== UI Actions ======

    def browse_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("PowerPoint files", "*.pptx")])
        if file_path:
            self.pptx_path.set(file_path)
            self.log_and_output(f"Selected file: {file_path}")

    # ====== Run Steps ======

    def run_selected_steps(self):
        
        # Must acknowledge disclaimer before running
        if not getattr(self, "acknowledge_var", tk.BooleanVar(value=False)).get():
            self.log_and_output("[WARN] Please confirm the acknowledgement checkbox before running any steps.")
            return
        
        self.progress_bar["value"] = 0
        selected_steps = [(name, method) for name, (var, method) in self.steps_vars.items() if var.get()]
        total = max(1, len(selected_steps))
        self.progress_bar["maximum"] = total
        self.ui_progress(0)

        def run_step(index=0):
            if index >= len(selected_steps):
                self.done("All selected steps completed.")
                return
            name, method = selected_steps[index]
            self.log_and_output(f"Starting: {name}")
            method(lambda: run_step(index + 1))

        run_step()

    # ====== Pipeline Functions ======

    def extract_and_convert_audio(self, on_complete=None):
        def task():
            try:
                pptx_path = Path(self.pptx_path.get())
                base_dir = self.get_base_path()
                media_dir = base_dir / "media"
                wav_dir = base_dir / "converted_wav"

                extracted = extract_audio_from_pptx(pptx_path, base_dir, log_fn=self.log_and_output)
                self.log_and_output(f"Extracted {len(extracted)} audio files to: {media_dir}")

                converted = convert_audio_to_wav(media_dir, wav_dir, log_fn=self.log_and_output)
                self.log_and_output(f"Converted {len(converted)} audio files to WAV in: {wav_dir}")
                self.increment_progress()
            except Exception as e:
                self.handle_exception("Extract + Convert Audio", e)
            finally:
                if on_complete:
                    self.root.after(0, on_complete)

        self._run_task(task)

    def extract_slide_text_txt(self, on_complete=None):
        def task():
            try:
                pptx_path = Path(self.pptx_path.get())
                output_dir = self.get_subdir("slide_text_txt")
                extracted = extract_slide_text(pptx_path, output_dir)
                self.log_and_output(f"Extracted {len(extracted)} text files to: {output_dir}")
                self.increment_progress()
            except Exception as e:
                self.handle_exception("Extract Slide Text", e)
            finally:
                if on_complete:
                    self.root.after(0, on_complete)

        self._run_task(task)

    def transcribe_audio(self, on_complete=None):
        def task():
            try:
                input_dir = self.get_subdir("converted_wav")
                output_dir = self.get_subdir("transcripts")
                transcribed = transcribe_audio_files(input_dir, output_dir, log_fn=self.log_and_output)
                self.log_and_output(f"{len(transcribed)} files transcribed and saved in: {output_dir}")
                self.increment_progress()
            except Exception as e:
                self.handle_exception("Transcribe Audio", e)
            finally:
                if on_complete:
                    self.root.after(0, on_complete)

        self._run_task(task)

    def translate_text(self, on_complete=None):
        def task():
            try:
                input_dir = self.get_subdir("transcripts")
                output_dir = self.get_subdir("translated_text")
                src, tgt = self.get_translation_languages()
                translated = translate_transcript_files(input_dir, output_dir, src, tgt, self.log_and_output, self.log_and_output)
                self.log_and_output(f"Translated {len(translated)} transcript files to: {output_dir}")
                self.increment_progress()
            except Exception as e:
                self.handle_exception("Translate Audio Transcripts", e)
            finally:
                if on_complete:
                    self.root.after(0, on_complete)

        self._run_task(task)

    def translate_slide_text_txt(self, on_complete=None):
        def task():
            try:
                input_dir = self.get_subdir("slide_text_txt")
                output_dir = self.get_subdir("translated_text_txt")
                src, tgt = self.get_translation_languages()
                translated = translate_text_files(input_dir, output_dir, src, tgt, self.log_and_output, self.log_and_output)
                self.log_and_output(f"Translated {len(translated)} slide text files to: {output_dir}")
                self.increment_progress()
            except Exception as e:
                self.handle_exception("Translate Slide Text", e)
            finally:
                if on_complete:
                    self.root.after(0, on_complete)

        self._run_task(task)

    def generate_tts(self, on_complete=None):
        def task():
            try:
                base_dir = self.get_base_path()
                input_dir = self.get_subdir("translated_text")
                output_dir = self.get_subdir("tts_audio")
                src, tgt = self.get_translation_languages()

                candidates = [
                    base_dir / "media",
                    base_dir / "converted_wav",
                    base_dir / "original_audio",
                    base_dir / "audio",
                ]
                original_audio_dir = next((c for c in candidates if c.exists()), None)
                if original_audio_dir is None:
                    self.log_and_output(
                        "[INFO] No original audio folder found (media/, converted_wav/, "
                        "original_audio/, audio/). Auto-tempo will be skipped."
                    )

                tts_lang = self.language.get()

                audio_files = text_to_speech(
                    text_dir=input_dir,
                    output_dir=output_dir,
                    source_lang=src,
                    target_lang=tgt,
                    model_map=self.language_model_map,
                    log=self.log_and_output,
                    output=self.log_and_output,
                    original_audio_dir=original_audio_dir,
                    auto_deadband_sec=AUTO_DEADBAND_SEC,
                    auto_deadband_ratio=AUTO_DEADBAND_RATIO,
                    auto_clamp_bounds=AUTO_CLAMP_BOUNDS,
                    tts_lang=tts_lang,
                )

                self.log_and_output(f"Generated {len(audio_files)} TTS audio files to: {output_dir}")
                self.increment_progress()
            except Exception as e:
                self.handle_exception("Generate TTS Audio", e)
            finally:
                if on_complete:
                    self.root.after(0, on_complete)

        self._run_task(task)

    def reintegrate_text_and_audio_combined(self, on_complete=None):
        def task():
            try:
                pptx = Path(self.pptx_path.get())
                base = self.get_base_path()
                output = pptx.with_name(pptx.stem + "_final_combined.pptx")

                reintegrate_text_and_audio(
                    pptx,
                    base / "translated_text_txt",
                    base / "tts_audio",
                    output,
                    log_fn=self.log_and_output,
                    output_fn=self.log_and_output,
                )
                self.log_and_output(f"Combined reintegrated PPTX saved to: {output}")
                self.increment_progress()
            except Exception as e:
                self.handle_exception("Reintegrate Text and Audio", e)
            finally:
                if on_complete:
                    self.root.after(0, on_complete)

        self._run_task(task)


# ====== Main Loop ======

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
