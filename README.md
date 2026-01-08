# OpenEduVoice

<p align="center">
  <img src="assets/logo.png" alt="Project Logo" width="200"/>
</p>

An **offline Windows desktop application** that automates **audio extraction, transcription, translation, text-to-speech (TTS), and reintegration** for PowerPoint (`.pptx`) files.  
Designed for **educational use** and **non-technical users**.

---

## Overview

The **OpenEduVoice** enables multilingual transformation of PowerPoint presentations by:

- Extracting embedded audio and slide text
- Transcribing spoken content using Whisper
- Translating text using NLLB models
- Regenerating speech via TTS
- Reintegrating translated text and audio back into the original presentation

All processing is **fully offline** once models are downloaded.

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

- **GUI Layer**
  - Handles user interaction and step control
- **Core Pipeline**
  - Extraction, transcription, translation, TTS, reintegration
- **Utilities**
  - Logging, preprocessing, cleanup, FFmpeg helpers
- **Packaging Layer**
  - Python package and Windows executable (in progress)

---

## Reproduce & Run OpenEduVoice (Windows)

**Prerequisite** 
1. **Python**
 - Python v3.11.x (No other versions are supported).
2. **NVIDIA GPU + Driver**  
 - Optional but recommended for fast transcription/TTS.

Once you ensure prerequisites are fullfilled.

### 1. Clone the Repository
```bash
git clone https://github.com/anjali-bodke/openeduvoice.git
```

### 2. Open the Project files
- single click on **start_OpenEduVoice.bat**, It will require some time to install and configure everything.
-  Successfull installation will open the GUI.

### 3. Utilize GUI to test out the project

1. Select a `.pptx` file

2. Click each step in sequence:
   - Extract Audio
   - Convert to WAV
   - Transcribe
   - Translate Text
   - Generate TTS Audio
   - Reintegrate Audio

All output will be stored in:
```
YourFile_transcript/
├── media/             # Extracted audio
├── converted_wav/     # Converted .wav files
├── transcripts/       # Whisper transcripts
├── translated/        # NLLB-200 based translated text
├── tts_audio/         # Coqui-regenerated speech
└── {original_name}_combined.pptx  #Presentation with translated Audio
```
---