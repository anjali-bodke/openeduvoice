# Markdown translation

## Purpose and scope

Markdown mode translates German-English `.md` and `.markdown` documents with the
existing offline NLLB model. It preserves common document structure rather than
translating raw Markdown syntax. Translation runs locally after dependencies and
the selected model have been installed; initial setup requires internet access.

## Using the feature

1. Select **Markdown Mode** and browse for a Markdown file.
2. Optionally select an existing output folder with **Save to**. Leave it empty
   to save beside the source file.
3. Select **German to English** or **English to German**.
4. Select **Translate Markdown**, acknowledge the AI disclaimer, and run the step.
5. Review the translated document and its source/translation text files.

## Output

For `lesson.md`, the workflow writes `lesson_translated.md` and:

```text
lesson_translation/
├── extracted_text/
│   └── lesson.txt
└── translated_text/
    └── lesson.txt
```

The translated file and companion folder are created in the selected output
folder, or beside the input when no folder is selected. Existing outputs with
the same names may be replaced.

## Structure and limitations

- The first `---`-delimited front matter block is copied without translation.
- Fenced code blocks, horizontal rules, reference definitions, and lines that
  begin with HTML are left unchanged.
- Headings, list and blockquote prefixes, and table delimiters are retained.
- Inline code, HTML tags, URLs, link destinations, and emphasis markers are
  protected while surrounding prose is translated.
- Formatting preservation is heuristic, not a complete Markdown parser.
  Complex nested syntax, raw HTML, unusual inline constructs, and malformed
  documents may not retain their intended meaning or formatting. Review the
  generated Markdown before using it.
- If translation fails or yields no text, the step stops with an error. Existing
  output files from an earlier run are not removed.

The workflow is implemented in
[`markdown_translator.py`](../src/OpenEduVoice/core/translation/markdown_translator.py)
and covered by the focused tests in
[`test_markdown_translation.py`](../tests/test_markdown_translation.py).
