# PDF translation

## Purpose and scope

PDF translation is a document-only workflow. It translates text in selectable-text
PDFs and scanned/image PDFs using the existing offline NLLB translator. It does not
run transcription, text-to-speech, or audio reintegration.

Supported directions are German to English and English to German. Scanned pages
use Tesseract OCR with the source-language model. The output aims to retain page
order, images, and approximate layout, not to reproduce the original typography
exactly.

## Using the feature

1. Select a PDF in **PDF Translation Input**.
2. Select the desired direction in **Translation Direction**.
3. Select **Translate PDF** and run the selected step.
4. Review the translated PDF and the accompanying per-page text files.

For scanned documents, install Tesseract OCR separately on Windows, make
`tesseract.exe` available on `PATH`, and install both English (`eng`) and German
(`deu`) trained data. The app reports an actionable error if the executable or
requested language data is unavailable. Selectable-text PDFs do not require Tesseract.

## Output

For an input named `lesson.pdf`, the workflow writes:

```text
lesson_translated.pdf
lesson_translation/
├── extracted_text/
│   ├── page_0001.txt
│   └── ...
└── translated_text/
    ├── page_0001.txt
    └── ...
```

The translated PDF is created beside the input PDF. Text files contain source and
translated text grouped by page and extracted block.

## Processing and implementation

The GUI's `Translate PDF` action calls
[`translate_pdf`](../src/OpenEduVoice/core/translation/pdf_translator.py).
That workflow:

1. Validates the input, language direction, and password-protection status.
2. Opens the PDF with PyMuPDF and extracts text blocks and page bounding boxes.
3. Uses Tesseract at 300 DPI for pages with no selectable text, mapping OCR word
   coordinates back to page coordinates.
4. Creates one NLLB translator for the document and translates each block. Long
   text is split into bounded chunks by the shared preprocessing helper.
5. Writes the per-page source and translated text files.
6. Reopens the source PDF, replaces digital text with redactions, covers OCR text
   on scanned-page images with white rectangles, then inserts translated text.
7. Saves the translated PDF through a temporary file before replacing the output.

Key modules:

- [`pdf_text_extractor.py`](../src/OpenEduVoice/core/extraction/pdf_text_extractor.py)
  extracts selectable text and performs OCR fallback.
- [`pdf_translator.py`](../src/OpenEduVoice/core/translation/pdf_translator.py)
  orchestrates language mapping, NLLB translation, and text outputs.
- [`pdf_reintegrator.py`](../src/OpenEduVoice/core/reintegration/pdf_reintegrator.py)
  replaces text and writes the translated PDF.
- [`test_pdf_translation.py`](../tests/test_pdf_translation.py) exercises digital
  extraction, mocked OCR behavior, output generation, and overwrite protection.

## Decisions and rationale

| Decision | Rationale |
|---|---|
| Reuse NLLB and the existing German-English direction | Keeps translation offline and aligned with the current PPTX workflow. |
| Support both selectable text and image scans | Use native PDF text when available and OCR only when a page has no selectable text. |
| Use Tesseract rather than bundling an OCR model | Avoids a large OCR model download inside Python setup; makes OCR an explicit Windows prerequisite. |
| Keep PDF input separate from PPTX input | PDF translation does not use PPTX audio/TTS steps and should not depend on the presentation path. |
| Produce both PDF and text-file outputs | The PDF is convenient to read; text files allow extraction and translation to be checked independently. |
| Preserve page elements where practical | Images and line art remain in place; exact typography and layout cannot be guaranteed after translation. |
| Initialize the NLLB model once per PDF | Avoids repeatedly loading a large model for every block. |
| Reject source/output path collisions | Protects the source PDF from accidental overwrite. |

## Limitations and risks

- **Layout is approximate.** Longer translations can overflow their original text
  areas. The reintegrator tries smaller font sizes down to a minimum and logs blocks
  that still do not fit; those blocks are available in the translated text files.
- **Text appearance can change.** The inserted text uses a standard PDF font, not
  necessarily the source font, weight, or exact styling.
- **Complex text and unusual fonts need review.** Font encoding, right-to-left text,
  rotated text, columns, annotations, and unusual reading order may not be preserved.
- **A mixed digital/scanned page is only partially handled.** OCR runs only when a
  page contains no selectable text blocks. Scanned regions on a page that also has
  selectable text may be missed.
- **Poor scans can produce poor translations.** OCR quality depends on scan clarity,
  skew, language data, and image resolution. No confidence threshold currently asks
  the user to confirm uncertain OCR.
- **OCR replaces the scan region with a white patch.** Background texture or
  graphics beneath scanned text are not reconstructed.
- **A large page rendered at 300 DPI uses significant memory.** Very large or
  unusually long PDFs may be slow or memory intensive.
- **Password-protected PDFs are unsupported.**
- **Per-page text files are written before PDF reintegration.** If PDF writing fails,
  the text files may exist even though no translated PDF was produced.

Always inspect the output PDF visually and compare it to the translated text files
before relying on it.

## Troubleshooting

### Tesseract executable not found

Install Tesseract OCR for Windows and ensure a fresh terminal can resolve
`tesseract.exe` on `PATH`. Restart OpenEduVoice after changing `PATH`.

### Tesseract language data missing

Install `deu.traineddata` and `eng.traineddata` in Tesseract's `tessdata` directory.
The requested source language determines which language model OCR uses.

### No text found

Confirm that the PDF is valid and that the scan is readable. For image-only PDFs,
verify Tesseract and the correct source-language data. For unusual or protected
files, test with a small unprotected sample.

### Translated text is absent or clipped

Check `translated_text/page_XXXX.txt` first. If the text is present there, inspect
the application log for a "did not fit" warning. A very small source box, long
translation, overlapping blocks, or a complex layout may require manual editing.

### Translation or model initialization fails

Check the full application log for the NLLB error. On first use, the model may
need to download; after that, inference can run offline. Confirm that the selected
language direction is German-English and that the Python environment has the
locked project dependencies installed.

## Validation

From PowerShell at the repository root:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
python -m compileall -q src tests
```

The tests generate real PDF fixtures for selectable text, styled spans, image-only
scans, mixed content, multiple pages, rotated pages, encrypted inputs, and text
overflow. OCR responses and NLLB translations are mocked, so the suite does not prove
OCR quality on real scans or validate model translations. Test representative PDFs
with Tesseract installed and visually inspect their outputs.
