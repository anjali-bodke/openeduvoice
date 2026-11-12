# OpenEduVoice

<p align="center">
  <img src="assets/logo.png" alt="Project Logo" width="200"/>
</p>

An **offline Windows desktop application** for translating educational documents.
Its PowerPoint workflow handles embedded audio and slide text; its PDF workflow
translates digital and scanned documents, and Markdown mode translates `.md` and
`.markdown` files while preserving common Markdown structure.

---

## Overview

The **OpenEduVoice** supports:

- PowerPoint audio extraction, transcription, translation, text-to-speech, and reintegration
- German-English translation of digital and scanned PDFs
- German-English Markdown translation with code and link targets preserved

First-time installation downloads dependencies and the default models. Processing
can run offline after setup succeeds; selecting a different model may require a
further download.

### Default models

The Windows installer downloads these models into the project-local `models`
directory:

| Purpose | Model |
| --- | --- |
| Translation | `facebook/nllb-200-distilled-600M` on CPU or GPUs with less than 16 GiB VRAM; `facebook/nllb-200-3.3B` on CUDA GPUs with at least 16 GiB VRAM |
| Transcription | Faster-Whisper `medium` |
| English speech | Coqui `tts_models/en/ljspeech/fast_pitch` with `vocoder_models/en/ljspeech/hifigan_v2` |
| German speech | Coqui `tts_models/de/thorsten/vits` (no separate vocoder) |

Model selection can change with available hardware or an explicitly requested
model; a different selection may require another download.

## Documentation

- [PDF translation: setup, decisions, and limitations](docs/PDF_TRANSLATION.md)
- [Markdown translation: usage, outputs, and limitations](docs/MARKDOWN_TRANSLATION.md)
- [Project idea, technical walkthrough, known risks, and debugging](docs/PROJECT_GUIDE.md)
- [Developer runbook: source setup, dependency installation, checks, and launch](docs/RUNBOOK.md)
- [NVIDIA GPU setup](docs/NvidiaCuda_Installation.md)
- [Documentation index](docs/README.md)

---

## Features

- Windows GUI application (Tkinter)
- Step-by-step processing pipeline
- Offline transcription, translation, and TTS
- Markdown translation with code blocks and link destinations preserved
- Handles large presentations with embedded audio
- Modular, extensible architecture
- No cloud processing or external APIs; internet access is required during setup to download dependencies and models

---

## Processing Pipeline

1. **Extract**
   - Embedded audio
   - Slide text (paragraph-level)
2. **Convert**
   - Audio normalization and WAV conversion
3. **Transcribe**
   - Speech-to-text using Faster-Whisper
4. **Translate**
   - Text translation using NLLB (offline)
5. **Generate TTS**
   - Speech synthesis using Coqui TTS
6. **Reintegrate**
   - Replace slide text and audio in the original PPTX

---

## System Architecture (High Level)

The application separates its Tkinter GUI from document extraction, translation,
audio processing, and reintegration modules. For the file-by-file walkthrough and
workflow details, see the [project guide](docs/PROJECT_GUIDE.md).

---

## Reproduce & Run OpenEduVoice (Windows)

### Prerequisites

1. **Python v3.11**
   - Only **Python 3.11.x** is supported.
   - Download installer:  
     https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe  
   - During installation, **check “Add Python to PATH”**.

2. **NVIDIA GPU + Driver**  
   - Strongly recommended for faster transcription and TTS.
   - CPU mode is supported but significantly slower.

Once you ensure prerequisites are fullfilled.

---

### 1. Clone the Repository

#### Option A: Using Git(If git is preinstalled in the system)
```bash
git clone https://github.com/anjali-bodke/openeduvoice.git
```

#### Option B: If Git not present on Computer
- Click the Code button on the repository page.
- Select Download ZIP and extract the folder.

- (Optional) Install Git for future use: https://github.com/git-for-windows/git/releases/download/v2.52.0.windows.1/Git-2.52.0-64-bit.exe

### 2. Install and launch

Open the `scripts` folder and double-click **install_OpenEduVoice.bat**. When
installation succeeds, double-click **run_OpenEduVoice.bat** to start the app.
The installer downloads several gigabytes of models and dependencies, installs
Tesseract, and requires an internet connection and sufficient disk space.

The installer selects CPU or NVIDIA CUDA automatically. To choose explicitly,
run `.\scripts\install_OpenEduVoice.bat cpu` or `.\scripts\install_OpenEduVoice.bat cuda` from
PowerShell. If an existing virtual environment was installed in a different mode,
the installer stops rather than deleting it; back up or remove `venv` manually
before switching. Models are stored under `models`, Python packages under `venv`,
and FFmpeg and Tesseract under `tools`. Python itself and the NVIDIA driver
remain system prerequisites.

Direct Python dependencies are declared in `pyproject.toml`; the Windows installer
uses `requirements.lock.txt` and separately selects CPU or CUDA PyTorch wheels.
The installer uses the UB Mannheim Windows build of Tesseract for scanned PDFs;
see the [PDF setup guide](docs/PDF_TRANSLATION.md).

### 3. Utilize GUI to test out the project

1. Select a `.pptx` or `.pdf` file and choose the translation direction.
   Optionally, use **Save to** to select an existing output folder. Leave it
   empty to save beside the source file. Each mode has its own folder setting.

2. Use **Select PDF workflow** or **Select PPTX + audio workflow** to choose
   steps, or select individual steps manually. The PPTX preset includes audio
   processing and is intended for presentations with embedded audio.

3. Confirm the AI acknowledgement and select **Run Selected Steps**. Inspect the
   log and review the generated document; layout preservation is approximate.

PowerPoint intermediate output is stored in the chosen folder (or beside the
presentation by default):
```
YourFile_transcript/
├── media/                                   # Extracted audio
├── converted_wav/                           # Converted .wav files
├── transcripts/                             # Whisper transcripts
├── slide_text_txt/                          # Extracted slide paragraphs
├── translated_text/                         # Translated audio transcripts
├── translated_text_txt/                     # Translated slide paragraphs
├── tts_audio/                               # Coqui-regenerated speech
```
The final presentation is saved in the same output folder as
`{original_name}_final_combined.pptx`. PDF output locations are described in the
[PDF guide](docs/PDF_TRANSLATION.md). Existing outputs with the same names may
be replaced.
---

For GPU setup, see the [NVIDIA GPU guide](docs/NvidiaCuda_Installation.md).