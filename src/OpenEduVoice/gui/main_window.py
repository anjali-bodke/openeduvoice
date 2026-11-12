"""
main_window.py

Tkinter-based GUI for the OpenEduVoice Translation Tool.
Supports PDF, PPTX and Markdown translation with audio extraction, transcription, and TTS.
"""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk

from OpenEduVoice.gui.workflow_tabs import (
    setup_markdown_tab,
    setup_pdf_tab,
    setup_pptx_tab,
)
from OpenEduVoice.gui.workflow_controller import (
    DOCUMENT_STEPS,
    WorkflowController,
)
from OpenEduVoice.config.constants import TTS_LANGUAGE_MODEL_MAP
from OpenEduVoice.utils.logging_utils import safe_log


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
        self.workflow_controller = WorkflowController(self)
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
        setup_pptx_tab(self)
        setup_pdf_tab(self)
        setup_markdown_tab(self)

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
            lambda event: acknowledgement.configure(wraplength=max(100, event.width - 30)),
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
        self.workflow_controller.run_selected_steps()

    def extract_and_convert_audio(self, on_complete=None):
        self.workflow_controller.extract_and_convert_audio(on_complete)

    def translate_pdf_document(self, on_complete=None):
        self.workflow_controller.translate_pdf_document(on_complete)

    def translate_markdown_document(self, on_complete=None):
        self.workflow_controller.translate_markdown_document(on_complete)

    def extract_slide_text_txt(self, on_complete=None):
        self.workflow_controller.extract_slide_text_txt(on_complete)

    def transcribe_audio(self, on_complete=None):
        self.workflow_controller.transcribe_audio(on_complete)

    def translate_text(self, on_complete=None):
        self.workflow_controller.translate_text(on_complete)

    def translate_slide_text_txt(self, on_complete=None):
        self.workflow_controller.translate_slide_text_txt(on_complete)

    def generate_tts(self, on_complete=None):
        self.workflow_controller.generate_tts(on_complete)

    def reintegrate_text_and_audio_combined(self, on_complete=None):
        self.workflow_controller.reintegrate_text_and_audio_combined(on_complete)


# ====== Main Loop ======

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
