# OpenEduVoice project guide

## Project idea

OpenEduVoice is an offline-first Windows desktop application for making educational
content more accessible across languages. Its original workflow transforms
PowerPoint presentations by extracting embedded audio and slide text, transcribing
and translating speech, generating translated speech, and reintegrating text and
audio into a presentation.

PDF translation extends the same local translation capability to digital and
scanned documents. It is intentionally a separate workflow: PDFs do not enter the
PPTX audio or TTS stages.

The project favors local processing after dependencies and models have been
installed. Translation and speech models are resource intensive, so CPU operation
is supported but may be slow.

## Technical walkthrough

### Application entry point and GUI

- [`__main__.py`](../src/OpenEduVoice/__main__.py) delegates to the package entry
  point.
- [`app.py`](../src/OpenEduVoice/app.py) creates the Tk root and starts the event
  loop.
- [`main_window.py`](../src/OpenEduVoice/gui/main_window.py) presents input fields,
  translation direction, workflow checkboxes, progress, and logs. Long-running
  actions run in background threads; callbacks schedule UI updates on Tk's main
  thread.

The selected-step runner calls one workflow at a time and advances using each
workflow's success callback. An exception raised by a step is logged and stops the
selected sequence. Audio conversion, transcription, and TTS file failures raise
instead of allowing the sequence to report success; optional tempo-matching
failures remain warnings and keep the unmodified synthesized audio.

For a quick test, use **Select PDF workflow**, **Select Markdown workflow**, or
**Select PPTX + audio workflow**, choose the corresponding input and language
direction, acknowledge the AI disclaimer, and select **Run Selected Steps**.
Presets only select checkboxes; they do not start processing. The PPTX preset
includes audio extraction, transcription, translation, and TTS: it is intended
for presentations with embedded audio. Users can change the selected steps
before running.

### PowerPoint workflow

1. [`slide_text_extractor.py`](../src/OpenEduVoice/core/extraction/slide_text_extractor.py)
   reads slide XML and writes one text file per slide. Each line corresponds to a
   paragraph so slide text can be mapped back during reintegration. It also
   extracts embedded audio.
2. [`audio_converter.py`](../src/OpenEduVoice/core/audio/audio_converter.py) uses
   pydub/FFmpeg to normalize extracted audio to WAV.
3. [`transcriber.py`](../src/OpenEduVoice/core/audio/transcriber.py) uses
   Faster-Whisper to produce transcript files.
4. [`translator_interface.py`](../src/OpenEduVoice/core/translation/translator_interface.py)
   translates slide text line by line or transcript files as full text. It uses
   [`nllb_model.py`](../src/OpenEduVoice/core/translation/nllb_model.py).
5. [`tts_generator.py`](../src/OpenEduVoice/core/audio/tts_generator.py) generates
   speech from translated transcript files and may use FFmpeg to match duration.
6. [`reintegrator_all.py`](../src/OpenEduVoice/core/reintegration/reintegrator_all.py)
   patches PPTX slide XML and replaces matching embedded audio.

Outputs are organized under a sibling `{presentation}_transcript` directory.
PPTX slide text, translated transcripts, and generated audio use separate directories.

#### PowerPoint translation decisions and limitations

- Each extracted paragraph is represented by one line, including trailing empty
  paragraphs. Model output is kept on one line to avoid shifting later paragraphs.
- Long slide text is sent to the translator, which performs its own bounded
  chunking. Non-alphabetic lines and path-like text intentionally skipped by the
  existing heuristic retain their original content; path-like skips are logged.
- Model initialization, empty translations, and per-file translation failures now
  stop the step instead of writing an empty translation. Existing output from an
  earlier run is not removed on failure; do not treat it as a new result.
- Bibliography hallucination filtering retains a source line in place of a
  rejected translation so later paragraphs do not shift.
- Extraction and reintegration currently use different XML traversal strategies,
  and reintegration chooses between run and paragraph matching heuristically.
  Complex slides, tables, styled runs, bullets, line breaks, and math may therefore
  be mapped incorrectly or lose formatting. Review every output presentation;
  layout and styling preservation are not guaranteed. No end-to-end PPTX
  reintegration or real-model quality test is currently provided.

### PDF workflow

The PDF workflow starts from its own GUI file field and `Translate PDF` checkbox.
It uses PyMuPDF for PDF text extraction and editing, Tesseract for scanned-page OCR,
and the existing NLLB model for German-English translation. It writes a translated
PDF beside the input and per-page source/translated text files into a companion
directory.

PDF processing decisions, outputs, prerequisites, limitations, and focused
troubleshooting steps are documented in [PDF translation](PDF_TRANSLATION.md).

### Markdown workflow

The Markdown workflow uses
[`markdown_translator.py`](../src/OpenEduVoice/core/translation/markdown_translator.py)
and the shared NLLB model. It writes a translated Markdown file and companion
source/translated text files. It protects common Markdown structure with
heuristics, not a full parser; review the output for complex syntax. Usage,
outputs, and limitations are documented in
[Markdown translation](MARKDOWN_TRANSLATION.md).

### Shared utilities and setup

- [`preprocessing.py`](../src/OpenEduVoice/utils/preprocessing.py) normalizes and
  segments text, including bounded chunks for long translation input.
- [`logging_utils.py`](../src/OpenEduVoice/utils/logging_utils.py) centralizes
  safe log callbacks.
- [`constants.py`](../src/OpenEduVoice/config/constants.py) contains shared TTS
  and pipeline settings.
- [`install_OpenEduVoice.ps1`](../scripts/install_OpenEduVoice.ps1) installs the
  pinned dependencies from [`requirements.lock.txt`](../requirements.lock.txt),
  selects CPU/CUDA PyTorch wheels, installs the project and Tesseract, and
  downloads the default models.
- [`run_OpenEduVoice.ps1`](../scripts/run_OpenEduVoice.ps1) checks the venv and
  FFmpeg and application imports, configures model caches and CUDA DLL paths,
  and launches the GUI.
- [`runtime_environment.ps1`](../scripts/runtime_environment.ps1) sets local
  cache paths consistently for installation and launch.
- The supported Python version is 3.11, as specified by
  [`pyproject.toml`](../pyproject.toml) and the installer.

## Potential bugs and behavior to watch

These are known risks to consider during changes and debugging; some are current
design limitations rather than confirmed failures in every document.

### Optional audio tempo matching can fail independently

Audio conversion, transcription, and TTS file failures stop the selected
sequence. Automatic tempo matching is optional: if FFmpeg is unavailable or
adjustment fails, the warning is logged and the generated audio is kept
unmodified. Check the logs and inspect generated outputs.

### Document input state is independent between modes

The GUI has separate PPTX, PDF, and Markdown paths, but shared workflow
checkboxes. Select only steps appropriate for the selected input; choosing a mode
does not populate the other input paths.

### PDF block detection and reading order

PyMuPDF's block order is not guaranteed to match human reading order for every
multi-column or complex layout. OCR runs only when the page contains no selectable
text blocks, so a partially scanned page that also has digital text may leave the
scanned region unprocessed.

### PDF text replacement can affect nearby content

Digital text replacement redacts each extracted block rectangle; blocks that
overlap or group separate content can cover nearby text. OCR replacement paints
white rectangles over scanned text and cannot restore a textured background.
Translated text may not fit. Review the per-page text files and the final PDF.

### OCR and model setup are separate from Python packages

`pytesseract` is a Python wrapper, not the Tesseract executable or trained data.
The installer installs the Windows Tesseract build and language data separately
and downloads the default NLLB, Whisper, and speech models into `models`.
Check each dependency independently when initialization fails. Changing the
hardware or selecting a different model can require additional downloads.

### Dependency files and accelerator mode

[`pyproject.toml`](../pyproject.toml) declares direct package dependencies;
[`requirements.lock.txt`](../requirements.lock.txt) pins the non-PyTorch
installation set. The installer separately pins PyTorch and torchaudio in
`install_OpenEduVoice.ps1` because CPU and CUDA wheels use different package
indexes. The lock is not a complete, hash-verified lock for all platforms.
When updating dependencies, validate the manifest, the lock, and both accelerator
wheel selections together. The installer refuses to replace an existing virtual
environment when its recorded accelerator mode differs: back it up or remove it
manually before switching.

## Debugging steps

1. **Check the Git state first.** Run `git status --short --branch`; preserve
   unrelated or pre-existing changes.
2. **Reproduce with a small input.** Use a copy of a one- or two-page PDF or a
   minimal PPTX, and keep source files unchanged.
3. **Run the focused tests.** From PowerShell at the repository root:

   ```powershell
   $env:PYTHONPATH = "src"
   python -m unittest discover -s tests -v
   ```

4. **Compile the package.**

   ```powershell
   python -m compileall -q src tests
   ```

5. **For PDF OCR failures**, verify the executable and language data in a new
   PowerShell window:

   ```powershell
   .\tools\tesseract\tesseract.exe --list-langs
   ```

   Confirm `eng` and `deu` appear and that the selected direction's source language
   is installed.
6. **For PDF extraction errors**, compare the extracted text files with the
   original. Determine whether the page has selectable text, is image-only, or
   mixes the two. Check page number and OCR logs.
7. **For PDF layout issues**, inspect the translated text file first, then check
   logs for overflow warnings. Compare the affected block with the source page:
   bbox, block grouping, font size, and overlap are the first points to investigate.
8. **For translation errors**, verify source/target codes, model initialization
   logs, available memory/device, and model download state. Avoid reloading NLLB
   for each paragraph; it is expensive.
9. **For PPTX mapping issues**, compare the extracted slide text line count/order
   with the slide XML and inspect reintegration logs. Preserve the one-line-per-
   paragraph contract when changing extraction or translation.
10. **Distinguish step completion from success.** Some underlying audio steps
    can log an error without raising it. Verify that
    the expected output files exist and inspect their contents.

## Change checklist

- Keep document-specific workflows isolated where their inputs/outputs differ.
- Preserve the PPTX one-line-per-paragraph mapping contract.
- Keep long NLLB inputs chunked and create a translator once per document/workflow.
- Report missing executables, language data, and model failures explicitly.
- Update the project manifest, installer-consumed lock, and accelerator wheel
  versions together when applicable.
- Add focused tests for extraction, translation orchestration, output generation,
  and failure paths.
- Review generated documents visually; text-only unit tests cannot validate layout.
