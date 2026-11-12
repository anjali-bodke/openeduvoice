"""
main_window.py

Tkinter-based GUI for the OpenEduVoice Translation Tool.
Supports PDF, PPTX and Markdown translation with audio extraction, transcription, and TTS.
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
from OpenEduVoice.core.translation.markdown_translator import translate_markdown
from OpenEduVoice.core.translation.pdf_translator import translate_pdf
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


DOCUMENT_STEPS = ("Translate PDF", "Translate Markdown")


class App:
    """
    GUI Controller for the OpenEduVoice Translation Tool.
    Supports PDF, PPTX and Markdown workflows with mode selection.
    """

    def __init__(self, root):
        self.root = root
        self.root.title("OpenEduVoice - Document Translation Tool")
        width = min(900, max(640, self.root.winfo_screenwidth() - 80))
        height = min(800, max(520, self.root.winfo_screenheight() - 100))
        self.root.geometry(f"{width}x{height}")
        self.root.minsize(640, 520)

        self.pptx_path = tk.StringVar()
        self.pdf_path = tk.StringVar()
        self.pptx_output_dir = tk.StringVar()
        self.pdf_output_dir = tk.StringVar()
        self.markdown_path = tk.StringVar()
        self.markdown_output_dir = tk.StringVar()
        self.language = tk.StringVar(value="English")
        self.translation_direction = tk.StringVar(value="German to English")
        self.acknowledge_var = tk.BooleanVar(value=False)
        self.current_mode = tk.StringVar(value="pptx")

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
        pptx = Path(self.pptx_path.get())
        return self.get_output_directory(self.pptx_output_dir, pptx) / f"{pptx.stem}_transcript"

    def get_output_directory(self, output_var: tk.StringVar, source: Path) -> Path:
        selected = output_var.get().strip()
        destination = Path(selected) if selected else source.parent
        if not destination.is_dir():
            raise ValueError(f"Output folder does not exist or is not a directory: {destination}")
        return destination

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
        self.root.configure(bg="#f1f5f9")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=4)
        self.root.rowconfigure(3, weight=1)

        header_frame = tk.Frame(self.root, bg="#1e3a5f")
        header_frame.grid(row=0, column=0, sticky="ew")
        title_label = tk.Label(
            header_frame,
            text="OpenEduVoice - Document Translation",
            font=("Segoe UI", 16, "bold"),
            bg="#1e3a5f",
            fg="white"
        )
        title_label.pack(anchor="w", padx=20, pady=(10, 4))

        mode_frame = tk.Frame(header_frame, bg="#1e3a5f")
        mode_frame.pack(anchor="w", padx=20, pady=(0, 10))

        tk.Label(mode_frame, text="Select mode:", font=("Segoe UI", 10), bg="#1e3a5f", fg="white").pack(side="left", padx=(0, 10))

        pptx_btn = tk.Button(
            mode_frame,
            text="PPTX Mode",
            command=lambda: self.switch_mode("pptx"),
            font=("Segoe UI", 10, "bold"),
            bg="#2563a6",
            fg="white",
            activebackground="#1d4f85",
            activeforeground="white",
            relief="flat",
            width=12,
            padx=10,
            pady=4
        )
        pptx_btn.pack(side="left", padx=(0, 6))
        self.pptx_mode_btn = pptx_btn

        pdf_btn = tk.Button(
            mode_frame,
            text="PDF Mode",
            command=lambda: self.switch_mode("pdf"),
            font=("Segoe UI", 10, "bold"),
            bg="#526b86",
            fg="white",
            activebackground="#1d4f85",
            activeforeground="white",
            relief="flat",
            width=12,
            padx=10,
            pady=4
        )
        pdf_btn.pack(side="left", padx=(0, 6))
        self.pdf_mode_btn = pdf_btn

        markdown_btn = tk.Button(
            mode_frame,
            text="Markdown Mode",
            command=lambda: self.switch_mode("markdown"),
            font=("Segoe UI", 10, "bold"),
            bg="#526b86",
            fg="white",
            activebackground="#1d4f85",
            activeforeground="white",
            relief="flat",
            width=14,
            padx=10,
            pady=4
        )
        markdown_btn.pack(side="left")
        self.markdown_mode_btn = markdown_btn

        content_frame = tk.Frame(self.root, bg="#f1f5f9")
        content_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(8, 0))
        content_frame.rowconfigure(0, weight=1)
        content_frame.columnconfigure(0, weight=1)

        self.pptx_frame = tk.Frame(content_frame, bg="#f1f5f9")
        self.pdf_frame = tk.Frame(content_frame, bg="#f1f5f9")
        self.pptx_frame.grid(row=0, column=0, sticky="nsew")
        self.pdf_frame.grid(row=0, column=0, sticky="nsew")
        self.markdown_frame = tk.Frame(content_frame, bg="#f1f5f9")
        self.markdown_frame.grid(row=0, column=0, sticky="nsew")

        # Setup both tabs
        self.setup_pptx_tab()
        self.setup_pdf_tab()
        self.setup_markdown_tab()

        control_frame = tk.Frame(self.root, bg="#e2eaf3")
        control_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(8, 0))
        control_frame.columnconfigure(1, weight=1)

        left_btn_frame = tk.Frame(control_frame, bg="#e2eaf3")
        left_btn_frame.grid(row=0, column=0, padx=10, pady=8)

        tk.Button(
            left_btn_frame,
            text="Run Selected Steps",
            command=self.run_selected_steps,
            font=("Segoe UI", 11, "bold"),
            bg="#2563a6",
            fg="white",
            activebackground="#1d4f85",
            activeforeground="white",
            padx=12,
            pady=6,
            relief="flat"
        ).pack(side="left", padx=5)

        tk.Button(
            left_btn_frame,
            text="Exit",
            command=self.root.quit,
            font=("Segoe UI", 10),
            bg="#d4dfe9",
            fg="#1e3a5f",
            activebackground="#c4d2e0",
            activeforeground="#1e3a5f",
            padx=10,
            pady=6,
            relief="flat"
        ).pack(side="left", padx=5)

        ack_text = (
            "I understand this software uses AI tools/technology for translation. "
            "After processing, I will manually verify all generated documents before intended use."
        )

        acknowledgement = tk.Checkbutton(
            control_frame,
            text=ack_text,
            variable=self.acknowledge_var,
            font=("Segoe UI", 9),
            bg="#e2eaf3",
            fg="#1e293b",
            wraplength=400,
            justify="left",
            anchor="w",
            activebackground="#e2eaf3",
            activeforeground="#1e293b",
            selectcolor="white"
        )
        acknowledgement.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=8)
        acknowledgement.bind(
            "<Configure>",
            lambda event: acknowledgement.configure(wraplength=max(100, event.width - 30))
        )

        # ===== Shared Bottom Section =====
        self.bottom_frame = tk.Frame(self.root, bg="#f1f5f9")
        self.bottom_frame.grid(row=3, column=0, sticky="nsew", padx=10, pady=(6, 10))

        # Progress section
        progress_lbl = tk.Label(self.bottom_frame, text="Progress", font=("Segoe UI", 10, "bold"), bg="#f1f5f9", fg="#1e3a5f")
        progress_lbl.pack(anchor="w", pady=(5, 2))

        self.progress_bar = ttk.Progressbar(self.bottom_frame, orient="horizontal", mode="determinate", length=400)
        self.progress_bar.pack(fill="x", pady=(0, 10))

        # Tabs for Log and Output
        output_notebook = ttk.Notebook(self.bottom_frame)
        output_notebook.pack(fill="both", expand=True, pady=5)

        # Log Tab
        log_frame = ttk.Frame(output_notebook)
        output_notebook.add(log_frame, text="Log")

        self.log_text = tk.Text(log_frame, height=5, bg="white", fg="#1e293b", font=("Consolas", 9), wrap="word")
        log_scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        log_scrollbar.pack(side="right", fill="y")
        self.log_text.pack(fill="both", expand=True, padx=(5, 0), pady=5)
        self.log_text.config(yscrollcommand=log_scrollbar.set)

        # Output Summary Tab
        output_frame = ttk.Frame(output_notebook)
        output_notebook.add(output_frame, text="Output Summary")

        self.output_text = tk.Text(output_frame, height=5, bg="white", fg="#1e293b", wrap="word", font=("Consolas", 9))
        output_scrollbar = ttk.Scrollbar(output_frame, command=self.output_text.yview)
        output_scrollbar.pack(side="right", fill="y")
        self.output_text.pack(fill="both", expand=True, padx=(5, 0), pady=5)
        self.output_text.config(yscrollcommand=output_scrollbar.set)

        self.switch_mode("pptx")

    def _create_workflow_area(self, parent):
        canvas = tk.Canvas(parent, bg="#f1f5f9", highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="#f1f5f9")
        window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        scrollable_frame.bind(
            "<Configure>",
            lambda event: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(window, width=event.width)
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        return scrollable_frame

    def _add_output_folder_row(self, parent, output_var):
        tk.Label(parent, text="Save to:", font=("Segoe UI", 10), bg="white").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        tk.Entry(parent, textvariable=output_var, font=("Segoe UI", 10)).grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        tk.Button(
            parent, text="Browse", command=lambda: self.browse_output_folder(output_var),
            bg="#2563a6", fg="white", activebackground="#1d4f85",
            activeforeground="white", relief="flat", padx=10
        ).grid(row=1, column=2, padx=5, pady=5)
        tk.Label(parent, text="Leave empty to save beside the source file.", font=("Segoe UI", 9), bg="white", fg="#475569").grid(row=2, column=1, sticky="w", padx=5, pady=(0, 5))

    def setup_pptx_tab(self):
        """Setup PPTX workflow tab."""
        default_font = ("Segoe UI", 10)

        scrollable_frame = self._create_workflow_area(self.pptx_frame)

        # 1. File selection
        file_frame = tk.LabelFrame(scrollable_frame, text="Step 1: Select PowerPoint File", font=("Segoe UI", 11, "bold"), bg="white")
        file_frame.pack(fill="x", padx=4, pady=4)
        tk.Label(file_frame, text="File Path:", font=default_font, bg="white").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        tk.Entry(file_frame, textvariable=self.pptx_path, font=default_font).grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        tk.Button(file_frame, text="Browse", command=self.browse_file, bg="#2563a6", fg="white", activebackground="#1d4f85", activeforeground="white", relief="flat", padx=10).grid(row=0, column=2, padx=5, pady=5)
        self._add_output_folder_row(file_frame, self.pptx_output_dir)
        file_frame.columnconfigure(1, weight=1)

        # 2. Steps selection
        step_frame = tk.LabelFrame(scrollable_frame, text="Step 2: Select Workflow Steps", font=("Segoe UI", 11, "bold"), bg="white")
        step_frame.pack(fill="x", padx=4, pady=4)

        pptx_steps = [
            ("Extract + Convert Audio", self.extract_and_convert_audio),
            ("Extract Slide Text (.txt)", self.extract_slide_text_txt),
            ("Transcribe Audio", self.transcribe_audio),
            ("Translate Audio Transcripts", self.translate_text),
            ("Translate Slide Text (.txt)", self.translate_slide_text_txt),
            ("Generate TTS Audio", self.generate_tts),
            ("Reintegrate Text and Audio", self.reintegrate_text_and_audio_combined),
        ]

        for i, (label, method) in enumerate(pptx_steps):
            var = tk.BooleanVar()
            chk = tk.Checkbutton(step_frame, text=label, variable=var, font=default_font, bg="white")
            chk.grid(row=i // 2, column=i % 2, sticky="w", padx=10, pady=5)
            self.steps_vars[label] = (var, method)
        step_frame.columnconfigure(0, weight=1)
        step_frame.columnconfigure(1, weight=1)

        # Preset buttons
        preset_frame = tk.Frame(step_frame, bg="white")
        preset_frame.grid(row=4, column=0, columnspan=2, sticky="w", padx=10, pady=5)
        tk.Button(preset_frame, text="Quick: Full PPTX Workflow", command=self.select_pptx_workflow, bg="#2563a6", fg="white", activebackground="#1d4f85", activeforeground="white", relief="flat", padx=8, font=("Segoe UI", 9, "bold")).pack(side="left", padx=3)

        # 3. Language settings
        lang_frame = tk.LabelFrame(scrollable_frame, text="Step 3: Language & Translation", font=("Segoe UI", 11, "bold"), bg="white")
        lang_frame.pack(fill="x", padx=4, pady=4)

        tk.Label(lang_frame, text="TTS Language:", font=default_font, bg="white").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        ttk.Combobox(
            lang_frame,
            textvariable=self.language,
            values=list(self.language_model_map.keys()),
            state="readonly",
            font=default_font,
        ).grid(row=0, column=1, sticky="ew", padx=5, pady=5)

        tk.Label(lang_frame, text="Translation Direction:", font=default_font, bg="white").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        dir_combo = ttk.Combobox(
            lang_frame,
            textvariable=self.translation_direction,
            values=["English to German", "German to English"],
            state="readonly",
            font=default_font,
        )
        dir_combo.grid(row=1, column=1, sticky="ew", padx=5, pady=5)

        info_label = tk.Label(
            lang_frame,
            text="Flow: German → English (translate German docs to English)\n       English → German (translate English docs to German)",
            font=("Segoe UI", 9),
            bg="#e2eaf3",
            justify="left",
            wraplength=400
        )
        info_label.grid(row=2, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

        lang_frame.columnconfigure(1, weight=1)

    def setup_pdf_tab(self):
        """Setup PDF workflow tab."""
        default_font = ("Segoe UI", 10)

        scrollable_frame = self._create_workflow_area(self.pdf_frame)

        # 1. File selection
        file_frame = tk.LabelFrame(scrollable_frame, text="Step 1: Select PDF File", font=("Segoe UI", 11, "bold"), bg="white")
        file_frame.pack(fill="x", padx=4, pady=4)
        tk.Label(file_frame, text="PDF Path:", font=default_font, bg="white").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        tk.Entry(file_frame, textvariable=self.pdf_path, font=default_font).grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        tk.Button(file_frame, text="Browse", command=self.browse_pdf_file, bg="#2563a6", fg="white", activebackground="#1d4f85", activeforeground="white", relief="flat", padx=10).grid(row=0, column=2, padx=5, pady=5)
        self._add_output_folder_row(file_frame, self.pdf_output_dir)
        file_frame.columnconfigure(1, weight=1)

        # 2. Workflow step
        step_frame = tk.LabelFrame(scrollable_frame, text="Step 2: Select Workflow", font=("Segoe UI", 11, "bold"), bg="white")
        step_frame.pack(fill="x", padx=4, pady=4)

        var = tk.BooleanVar()
        chk = tk.Checkbutton(step_frame, text="Translate PDF", variable=var, font=default_font, bg="white")
        chk.pack(anchor="w", padx=10, pady=10)
        self.steps_vars["Translate PDF"] = (var, self.translate_pdf_document)

        preset_frame = tk.Frame(step_frame, bg="white")
        preset_frame.pack(anchor="w", padx=10, pady=5)
        tk.Button(preset_frame, text="Quick: Translate PDF", command=self.select_pdf_workflow, bg="#2563a6", fg="white", activebackground="#1d4f85", activeforeground="white", relief="flat", padx=8, font=("Segoe UI", 9, "bold")).pack(side="left")

        # 3. Language settings
        lang_frame = tk.LabelFrame(scrollable_frame, text="Step 3: Translation Settings", font=("Segoe UI", 11, "bold"), bg="white")
        lang_frame.pack(fill="x", padx=4, pady=4)

        tk.Label(lang_frame, text="Translation Direction:", font=default_font, bg="white").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        dir_combo = ttk.Combobox(
            lang_frame,
            textvariable=self.translation_direction,
            values=["English to German", "German to English"],
            state="readonly",
            font=default_font,
        )
        dir_combo.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

        info_label = tk.Label(
            lang_frame,
            text="Flow: German → English (translate German PDF to English)\n       English → German (translate English PDF to German)",
            font=("Segoe UI", 9),
            bg="#e2eaf3",
            justify="left",
            wraplength=400
        )
        info_label.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

        lang_frame.columnconfigure(1, weight=1)

    def setup_markdown_tab(self):
        """Setup Markdown workflow tab."""
        default_font = ("Segoe UI", 10)

        scrollable_frame = self._create_workflow_area(self.markdown_frame)

        # 1. File selection
        file_frame = tk.LabelFrame(scrollable_frame, text="Step 1: Select Markdown File", font=("Segoe UI", 11, "bold"), bg="white")
        file_frame.pack(fill="x", padx=4, pady=4)
        tk.Label(file_frame, text="Markdown Path:", font=default_font, bg="white").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        tk.Entry(file_frame, textvariable=self.markdown_path, font=default_font).grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        tk.Button(file_frame, text="Browse", command=self.browse_markdown_file, bg="#2563a6", fg="white", activebackground="#1d4f85", activeforeground="white", relief="flat", padx=10).grid(row=0, column=2, padx=5, pady=5)
        self._add_output_folder_row(file_frame, self.markdown_output_dir)
        file_frame.columnconfigure(1, weight=1)

        # 2. Workflow step
        step_frame = tk.LabelFrame(scrollable_frame, text="Step 2: Select Workflow", font=("Segoe UI", 11, "bold"), bg="white")
        step_frame.pack(fill="x", padx=4, pady=4)

        var = tk.BooleanVar()
        chk = tk.Checkbutton(step_frame, text="Translate Markdown", variable=var, font=default_font, bg="white")
        chk.pack(anchor="w", padx=10, pady=10)
        self.steps_vars["Translate Markdown"] = (var, self.translate_markdown_document)

        preset_frame = tk.Frame(step_frame, bg="white")
        preset_frame.pack(anchor="w", padx=10, pady=5)
        tk.Button(preset_frame, text="Quick: Translate Markdown", command=self.select_markdown_workflow, bg="#2563a6", fg="white", activebackground="#1d4f85", activeforeground="white", relief="flat", padx=8, font=("Segoe UI", 9, "bold")).pack(side="left")

        # 3. Language settings
        lang_frame = tk.LabelFrame(scrollable_frame, text="Step 3: Translation Settings", font=("Segoe UI", 11, "bold"), bg="white")
        lang_frame.pack(fill="x", padx=4, pady=4)

        tk.Label(lang_frame, text="Translation Direction:", font=default_font, bg="white").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        dir_combo = ttk.Combobox(
            lang_frame,
            textvariable=self.translation_direction,
            values=["English to German", "German to English"],
            state="readonly",
            font=default_font,
        )
        dir_combo.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

        info_label = tk.Label(
            lang_frame,
            text="Flow: German → English (translate German Markdown to English)\n       English → German (translate English Markdown to German)",
            font=("Segoe UI", 9),
            bg="#e2eaf3",
            justify="left",
            wraplength=400
        )
        info_label.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

        lang_frame.columnconfigure(1, weight=1)

    def switch_mode(self, mode: str):
        """Switch between PPTX, PDF and Markdown modes."""
        self.current_mode.set(mode)
        frames = {
            "pptx": self.pptx_frame,
            "pdf": self.pdf_frame,
            "markdown": self.markdown_frame,
        }
        buttons = {
            "pptx": self.pptx_mode_btn,
            "pdf": self.pdf_mode_btn,
            "markdown": self.markdown_mode_btn,
        }
        frames[mode].tkraise()
        for name, button in buttons.items():
            if name == mode:
                button.config(bg="#2563a6", relief="sunken")
            else:
                button.config(bg="#526b86", relief="flat")

    # ====== UI Actions ======

    def select_pdf_workflow(self):
        """Select only the PDF translation step."""
        for name, (var, _) in self.steps_vars.items():
            var.set(name == "Translate PDF")

    def select_markdown_workflow(self):
        """Select only the Markdown translation step."""
        for name, (var, _) in self.steps_vars.items():
            var.set(name == "Translate Markdown")

    def select_pptx_workflow(self):
        """Select the full PPTX workflow."""
        for name, (var, _) in self.steps_vars.items():
            if name not in DOCUMENT_STEPS:
                var.set(True)
            else:
                var.set(False)

    def browse_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("PowerPoint files", "*.pptx")])
        if file_path:
            self.pptx_path.set(file_path)
            self.log_and_output(f"Selected file: {file_path}")

    def browse_pdf_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if file_path:
            self.pdf_path.set(file_path)
            self.log_and_output(f"Selected PDF: {file_path}")

    def browse_markdown_file(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("Markdown files", "*.md *.markdown")]
        )
        if file_path:
            self.markdown_path.set(file_path)
            self.log_and_output(f"Selected Markdown: {file_path}")

    def browse_output_folder(self, output_var: tk.StringVar):
        folder = filedialog.askdirectory(parent=self.root, title="Choose output folder", mustexist=True)
        if folder:
            output_var.set(folder)
            self.log_and_output(f"Selected output folder: {folder}")

    # ====== Run Steps ======

    def run_selected_steps(self):
        
        # Must acknowledge disclaimer before running
        if not getattr(self, "acknowledge_var", tk.BooleanVar(value=False)).get():
            self.log_and_output("[WARN] Please confirm the acknowledgement checkbox before running any steps.")
            return
        
        self.progress_bar["value"] = 0
        selected_steps = [(name, method) for name, (var, method) in self.steps_vars.items() if var.get()]
        if not selected_steps:
            self.log_and_output("[WARN] Select at least one step to run.")
            return
        try:
            if any(name == "Translate PDF" for name, _ in selected_steps):
                self.get_output_directory(self.pdf_output_dir, Path(self.pdf_path.get()))
            if any(name == "Translate Markdown" for name, _ in selected_steps):
                self.get_output_directory(self.markdown_output_dir, Path(self.markdown_path.get()))
            if any(name not in DOCUMENT_STEPS for name, _ in selected_steps):
                self.get_output_directory(self.pptx_output_dir, Path(self.pptx_path.get()))
        except ValueError as e:
            self.handle_exception("Output folder", e)
            return
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
            else:
                if on_complete:
                    self.root.after(0, on_complete)

        self._run_task(task)

    def translate_pdf_document(self, on_complete=None):
        def task():
            try:
                src, tgt = self.get_translation_languages()
                result = translate_pdf(
                    Path(self.pdf_path.get()),
                    src,
                    tgt,
                    log_fn=self.log_and_output,
                    output_dir=self.get_output_directory(self.pdf_output_dir, Path(self.pdf_path.get())),
                )
                self.log_and_output(f"Translated PDF saved to: {result.translated_pdf}")
                self.log_and_output(
                    f"Extracted and translated PDF text saved to: "
                    f"{result.extracted_text_files[0].parent.parent}"
                )
                self.increment_progress()
            except Exception as e:
                self.handle_exception("Translate PDF", e)
            else:
                if on_complete:
                    self.root.after(0, on_complete)

        self._run_task(task)

    def translate_markdown_document(self, on_complete=None):
        def task():
            try:
                src, tgt = self.get_translation_languages()
                result = translate_markdown(
                    Path(self.markdown_path.get()),
                    src,
                    tgt,
                    log_fn=self.log_and_output,
                    output_dir=self.get_output_directory(self.markdown_output_dir, Path(self.markdown_path.get())),
                )
                self.log_and_output(f"Translated Markdown saved to: {result.translated_markdown}")
                self.log_and_output(
                    f"Extracted and translated Markdown text saved to: "
                    f"{result.extracted_text_files[0].parent.parent}"
                )
                self.increment_progress()
            except Exception as e:
                self.handle_exception("Translate Markdown", e)
            else:
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
            else:
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
            else:
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
            else:
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
            else:
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
            else:
                if on_complete:
                    self.root.after(0, on_complete)

        self._run_task(task)

    def reintegrate_text_and_audio_combined(self, on_complete=None):
        def task():
            try:
                pptx = Path(self.pptx_path.get())
                base = self.get_base_path()
                output = self.get_output_directory(self.pptx_output_dir, pptx) / f"{pptx.stem}_final_combined.pptx"

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
            else:
                if on_complete:
                    self.root.after(0, on_complete)

        self._run_task(task)


# ====== Main Loop ======

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
