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
dependencies and project, and downloads local FFmpeg. CPU mode is the simplest
option for a developer check:

```powershell
.\install_OpenEduVoice.bat cpu
```

For NVIDIA mode, use `.\install_OpenEduVoice.bat cuda` instead. If `venv` already
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
```

- `pip check` reports incompatible or missing installed package requirements.
- `compileall` checks Python source and test files for syntax errors. This Python
  application does not need a separate native compile step.
- The test suite checks the behavior covered by automated tests; it does not
  guarantee that every document or model result is correct.
- FFmpeg and FFprobe should print their version information. If either executable
  is missing, rerun the installer and review its error output.

Scanned-PDF workflows also require Tesseract OCR and the relevant trained data;
see the [PDF translation guide](PDF_TRANSLATION.md).

## 5. Launch

```powershell
.\run_OpenEduVoice.bat
```

On first use, translation and speech models may need to download. Try a small
copy of a PPTX or PDF, then inspect the application log and generated files to
evaluate the output. See the [project guide](PROJECT_GUIDE.md) for workflow
details and limitations.
