# OpenEduVoice

<p align="center">
  <img src="assets/logo.png" alt="Project Logo" width="200"/>
</p>

An **offline Windows desktop application** for translating educational documents.
Its PowerPoint workflow handles embedded audio and slide text; its PDF workflow
translates digital and scanned documents.

---

## Overview

The **OpenEduVoice** supports:

- PowerPoint audio extraction, transcription, translation, text-to-speech, and reintegration
- German-English translation of digital and scanned PDFs

First-time installation downloads all the dependencies/models; after that, processing runs offline.
All the processing is **fully offline** once models are downloaded.

## Documentation

- [PDF translation: setup, decisions, and limitations](docs/PDF_TRANSLATION.md)
- [Project idea, technical walkthrough, known risks, and debugging](docs/PROJECT_GUIDE.md)
- [Documentation index](docs/README.md)

---

## Features

- Windows GUI application (Tkinter)
- Step-by-step processing pipeline
- Offline transcription, translation, and TTS
- Handles large presentations with embedded audio
- Modular, extensible architecture
- No cloud services or external APIs

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

### 2. Launch the Application.
- Open the project folder
- There are two files.
   - File 1. **install_OpenEduVoice.bat**. Please click on this file, if you have dowloaded the porgram for first time. This file will ensure all dependecies are installed.
   - File 2. **run_OpenEduVoice.bat**. This file will give a final check, run the application and then open the GUI.

### 3. Utilize GUI to test out the project

1. Select a `.pptx` or `.pdf` file and choose the translation direction.

2. Use **Select PDF workflow** or **Select PPTX + audio workflow** to choose
   steps, or select individual steps manually. The PPTX preset includes audio
   processing and is intended for presentations with embedded audio.

3. Confirm the AI acknowledgement and select **Run Selected Steps**. Inspect the
   log and review the generated document; layout preservation is approximate.

All output will be stored in:
```
YourFile_transcript/
├── media/                                   # Extracted audio
├── converted_wav/                           # Converted .wav files
├── transcripts/                             # Whisper transcripts
├── translated/                              # NLLB-200 based translated text
├── tts_audio/                               # Coqui-regenerated speech
└── {original_name}_combined.pptx            #Presentation with translated Audio
```
---

## Initially, If you don't have a Nvidia GPU or CUDA toolkit installed it will work only on CPU.
## Inorder to install CUDA toolkit and use GPU for the software please follow the instructions [Nvidia-Toolkit Installation Guide](NvidiaCuda_Installation.md)