from __future__ import annotations

import tkinter as tk
from tkinter import ttk

def _create_workflow_area(parent):
    canvas = tk.Canvas(parent, bg="#f1f5f9", highlightthickness=0)
    scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
    scrollable_frame = tk.Frame(canvas, bg="#f1f5f9")
    window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    scrollable_frame.bind(
        "<Configure>",
        lambda _event: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    canvas.bind(
        "<Configure>",
        lambda event: canvas.itemconfigure(window, width=event.width)
    )
    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    return scrollable_frame

def _add_output_folder_row(app, parent, output_var):
    tk.Label(parent, text="Save to:", font=("Segoe UI", 10), bg="white").grid(row=1, column=0, sticky="w", padx=5, pady=5)
    tk.Entry(parent, textvariable=output_var, font=("Segoe UI", 10)).grid(row=1, column=1, sticky="ew", padx=5, pady=5)
    tk.Button(
        parent, text="Browse", command=lambda: app.browse_output_folder(output_var),
        bg="#2563a6", fg="white", activebackground="#1d4f85",
        activeforeground="white", relief="flat", padx=10
    ).grid(row=1, column=2, padx=5, pady=5)
    tk.Label(parent, text="Leave empty to save beside the source file.", font=("Segoe UI", 9), bg="white", fg="#475569").grid(row=2, column=1, sticky="w", padx=5, pady=(0, 5))

def setup_pptx_tab(app):
    """Setup PPTX workflow tab."""
    default_font = ("Segoe UI", 10)

    scrollable_frame = _create_workflow_area(app.pptx_frame)

    # 1. File selection
    file_frame = tk.LabelFrame(scrollable_frame, text="Step 1: Select PowerPoint File", font=("Segoe UI", 11, "bold"), bg="white")
    file_frame.pack(fill="x", padx=4, pady=4)
    tk.Label(file_frame, text="File Path:", font=default_font, bg="white").grid(row=0, column=0, sticky="w", padx=5, pady=5)
    tk.Entry(file_frame, textvariable=app.pptx_path, font=default_font).grid(row=0, column=1, sticky="ew", padx=5, pady=5)
    tk.Button(file_frame, text="Browse", command=app.browse_file, bg="#2563a6", fg="white", activebackground="#1d4f85", activeforeground="white", relief="flat", padx=10).grid(row=0, column=2, padx=5, pady=5)
    _add_output_folder_row(app, file_frame, app.pptx_output_dir)
    file_frame.columnconfigure(1, weight=1)

    # 2. Steps selection
    step_frame = tk.LabelFrame(scrollable_frame, text="Step 2: Select Workflow Steps", font=("Segoe UI", 11, "bold"), bg="white")
    step_frame.pack(fill="x", padx=4, pady=4)

    pptx_steps = [
        ("Extract + Convert Audio", app.extract_and_convert_audio),
        ("Extract Slide Text (.txt)", app.extract_slide_text_txt),
        ("Transcribe Audio", app.transcribe_audio),
        ("Translate Audio Transcripts", app.translate_text),
        ("Translate Slide Text (.txt)", app.translate_slide_text_txt),
        ("Generate TTS Audio", app.generate_tts),
        ("Reintegrate Text and Audio", app.reintegrate_text_and_audio_combined),
    ]

    for i, (label, method) in enumerate(pptx_steps):
        var = tk.BooleanVar()
        chk = tk.Checkbutton(step_frame, text=label, variable=var, font=default_font, bg="white")
        chk.grid(row=i // 2, column=i % 2, sticky="w", padx=10, pady=5)
        app.steps_vars[label] = (var, method)
    step_frame.columnconfigure(0, weight=1)
    step_frame.columnconfigure(1, weight=1)

    # Preset buttons
    preset_frame = tk.Frame(step_frame, bg="white")
    preset_frame.grid(row=4, column=0, columnspan=2, sticky="w", padx=10, pady=5)
    tk.Button(preset_frame, text="Quick: Full PPTX Workflow", command=app.select_pptx_workflow, bg="#2563a6", fg="white", activebackground="#1d4f85", activeforeground="white", relief="flat", padx=8, font=("Segoe UI", 9, "bold")).pack(side="left", padx=3)

    # 3. Language settings
    lang_frame = tk.LabelFrame(scrollable_frame, text="Step 3: Language & Translation", font=("Segoe UI", 11, "bold"), bg="white")
    lang_frame.pack(fill="x", padx=4, pady=4)

    tk.Label(lang_frame, text="TTS Language:", font=default_font, bg="white").grid(row=0, column=0, sticky="w", padx=5, pady=5)
    ttk.Combobox(
        lang_frame,
        textvariable=app.language,
        values=list(app.language_model_map.keys()),
        state="readonly",
        font=default_font,
    ).grid(row=0, column=1, sticky="ew", padx=5, pady=5)

    tk.Label(lang_frame, text="Translation Direction:", font=default_font, bg="white").grid(row=1, column=0, sticky="w", padx=5, pady=5)
    dir_combo = ttk.Combobox(
        lang_frame,
        textvariable=app.translation_direction,
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

def setup_pdf_tab(app):
    """Setup PDF workflow tab."""
    default_font = ("Segoe UI", 10)

    scrollable_frame = _create_workflow_area(app.pdf_frame)

    # 1. File selection
    file_frame = tk.LabelFrame(scrollable_frame, text="Step 1: Select PDF File", font=("Segoe UI", 11, "bold"), bg="white")
    file_frame.pack(fill="x", padx=4, pady=4)
    tk.Label(file_frame, text="PDF Path:", font=default_font, bg="white").grid(row=0, column=0, sticky="w", padx=5, pady=5)
    tk.Entry(file_frame, textvariable=app.pdf_path, font=default_font).grid(row=0, column=1, sticky="ew", padx=5, pady=5)
    tk.Button(file_frame, text="Browse", command=app.browse_pdf_file, bg="#2563a6", fg="white", activebackground="#1d4f85", activeforeground="white", relief="flat", padx=10).grid(row=0, column=2, padx=5, pady=5)
    _add_output_folder_row(app, file_frame, app.pdf_output_dir)
    file_frame.columnconfigure(1, weight=1)

    # 2. Workflow step
    step_frame = tk.LabelFrame(scrollable_frame, text="Step 2: Select Workflow", font=("Segoe UI", 11, "bold"), bg="white")
    step_frame.pack(fill="x", padx=4, pady=4)

    var = tk.BooleanVar()
    chk = tk.Checkbutton(step_frame, text="Translate PDF", variable=var, font=default_font, bg="white")
    chk.pack(anchor="w", padx=10, pady=10)
    app.steps_vars["Translate PDF"] = (var, app.translate_pdf_document)

    preset_frame = tk.Frame(step_frame, bg="white")
    preset_frame.pack(anchor="w", padx=10, pady=5)
    tk.Button(preset_frame, text="Quick: Translate PDF", command=app.select_pdf_workflow, bg="#2563a6", fg="white", activebackground="#1d4f85", activeforeground="white", relief="flat", padx=8, font=("Segoe UI", 9, "bold")).pack(side="left")

    # 3. Language settings
    lang_frame = tk.LabelFrame(scrollable_frame, text="Step 3: Translation Settings", font=("Segoe UI", 11, "bold"), bg="white")
    lang_frame.pack(fill="x", padx=4, pady=4)

    tk.Label(lang_frame, text="Translation Direction:", font=default_font, bg="white").grid(row=0, column=0, sticky="w", padx=5, pady=5)
    dir_combo = ttk.Combobox(
        lang_frame,
        textvariable=app.translation_direction,
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

def setup_markdown_tab(app):
    """Setup Markdown workflow tab."""
    default_font = ("Segoe UI", 10)

    scrollable_frame = _create_workflow_area(app.markdown_frame)

    # 1. File selection
    file_frame = tk.LabelFrame(scrollable_frame, text="Step 1: Select Markdown File", font=("Segoe UI", 11, "bold"), bg="white")
    file_frame.pack(fill="x", padx=4, pady=4)
    tk.Label(file_frame, text="Markdown Path:", font=default_font, bg="white").grid(row=0, column=0, sticky="w", padx=5, pady=5)
    tk.Entry(file_frame, textvariable=app.markdown_path, font=default_font).grid(row=0, column=1, sticky="ew", padx=5, pady=5)
    tk.Button(file_frame, text="Browse", command=app.browse_markdown_file, bg="#2563a6", fg="white", activebackground="#1d4f85", activeforeground="white", relief="flat", padx=10).grid(row=0, column=2, padx=5, pady=5)
    _add_output_folder_row(app, file_frame, app.markdown_output_dir)
    file_frame.columnconfigure(1, weight=1)

    # 2. Workflow step
    step_frame = tk.LabelFrame(scrollable_frame, text="Step 2: Select Workflow", font=("Segoe UI", 11, "bold"), bg="white")
    step_frame.pack(fill="x", padx=4, pady=4)

    var = tk.BooleanVar()
    chk = tk.Checkbutton(step_frame, text="Translate Markdown", variable=var, font=default_font, bg="white")
    chk.pack(anchor="w", padx=10, pady=10)
    app.steps_vars["Translate Markdown"] = (var, app.translate_markdown_document)

    preset_frame = tk.Frame(step_frame, bg="white")
    preset_frame.pack(anchor="w", padx=10, pady=5)
    tk.Button(preset_frame, text="Quick: Translate Markdown", command=app.select_markdown_workflow, bg="#2563a6", fg="white", activebackground="#1d4f85", activeforeground="white", relief="flat", padx=8, font=("Segoe UI", 9, "bold")).pack(side="left")

    # 3. Language settings
    lang_frame = tk.LabelFrame(scrollable_frame, text="Step 3: Translation Settings", font=("Segoe UI", 11, "bold"), bg="white")
    lang_frame.pack(fill="x", padx=4, pady=4)

    tk.Label(lang_frame, text="Translation Direction:", font=default_font, bg="white").grid(row=0, column=0, sticky="w", padx=5, pady=5)
    dir_combo = ttk.Combobox(
        lang_frame,
        textvariable=app.translation_direction,
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
