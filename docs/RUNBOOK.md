# Developer runbook (Windows)

This guide covers getting the source code, installing dependencies, checking
the checkout and installation, and launching OpenEduVoice. Use PowerShell from
the repository folder. Python 3.11 and an internet connection are required for
the first dependency and model downloads.

## 1. Get the source code

Clone the repository and enter its folder:

```powershell
git clone https://github.com/anjali-bodke/openeduvoice.git
cd openeduvoice
```

Alternatively, download the repository ZIP from GitHub, extract it, and open
PowerShell in the extracted folder.

## 2. Confirm Python

```powershell
py -3.11 --version
```

The command should report Python 3.11.x.

## 3. Install dependencies

The installer creates the `venv` virtual environment, installs the locked Python
dependencies and project, installs local FFmpeg and Tesseract, and downloads the
default translation, transcription, and speech models. This needs several
gigabytes of disk space and an internet connection. CPU mode is the simplest
option for a developer check:

```powershell
.\scripts\install_OpenEduVoice.bat cpu
```

For NVIDIA mode, use `.\scripts\install_OpenEduVoice.bat cuda` instead. If `venv` already
exists in the other mode, back it up or remove it manually before switching; the
installer will not replace it. The installer selects the required PyTorch
variant for the requested mode.

## 4. Check dependencies and source before launch

Run these commands from the repository folder:

```powershell
.\venv\Scripts\python.exe -m pip check
.\venv\Scripts\python.exe -m compileall -q src tests
.\venv\Scripts\python.exe -m unittest discover -s tests -v
.\tools\ffmpeg\bin\ffmpeg.exe -version
.\tools\ffmpeg\bin\ffprobe.exe -version
.\tools\tesseract\tesseract.exe --list-langs
```

- `pip check` reports incompatible or missing installed package requirements.
- `compileall` checks Python source and test files for syntax errors. This Python
  application does not need a separate native compile step.
- The test suite checks the behavior covered by automated tests; it does not
  guarantee that every document or model result is correct.
- FFmpeg and FFprobe should print their version information. If either executable
  is missing, rerun the installer and review its error output.
- Tesseract should list both `eng` and `deu`.

The installer sets up project-local Tesseract OCR and English/German trained
data; see the [PDF translation guide](PDF_TRANSLATION.md).
The UB Mannheim installer can update Windows installation metadata even when
installed locally. Its uninstaller removes the entire Tesseract installation
directory; do not keep unrelated files there. The setup checks the published
installer's SHA-256 before running it.

## 5. Launch

```powershell
.\scripts\run_OpenEduVoice.bat
```

The installer downloads default models into `models`; alternate models may
still need a download. Try a small
copy of a PPTX or PDF, then inspect the application log and generated files to
evaluate the output. See the [project guide](PROJECT_GUIDE.md) for workflow
details and limitations.
