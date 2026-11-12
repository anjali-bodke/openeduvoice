from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from OpenEduVoice.core.translation.pdf_translator import (
    NLLB_LANGUAGE_MAP,
    TextTranslator,
    _create_nllb_translator,
)
from OpenEduVoice.utils.logging_utils import safe_log


MARKDOWN_SUFFIXES = (".md", ".markdown")

_FENCE = re.compile(r"^\s{0,3}(```+|~~~+|\$\$)")
_RULE = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$|^\s{0,3}(=+|-+)\s*$")
_REFERENCE_DEF = re.compile(r"^\s{0,3}\[[^\]]+\]:\s+\S+")
_LINE_PREFIX = re.compile(
    r"^(?P<prefix>(?:\s*>)*\s*(?:#{1,6}\s+|[-*+]\s+(?:\[[ xX]\]\s+)?|\d+[.)]\s+)?)(?P<body>.*)$"
)
_HEADING_CLOSER = re.compile(r"(\s+#+\s*)$")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$")
_PROTECTED = re.compile(
    r"`+[^`]*`+"
    r"|<[^>\s][^>]*>"
    r"|\]\([^)]*\)"
    r"|\]\[[^\]]*\]"
    r"|https?://[^\s)>\]]+"
    r"|!?\["
    r"|\]"
    r"|\*\*|__|~~|\*"
    r"|&\w+;"
)
_LETTER = re.compile(r"[^\W\d_]")


@dataclass(frozen=True)
class MarkdownTranslationResult:
    translated_markdown: Path
    extracted_text_files: list[Path]
    translated_text_files: list[Path]
    translated_block_count: int


def _translate_inline(
    text: str, translator: TextTranslator, log_fn: Callable[[str], None]
) -> str:
    """Translate prose while leaving code spans, links, URLs, tags and emphasis markers intact."""
    parts: list[tuple[str, str]] = []
    position = 0
    for match in _PROTECTED.finditer(text):
        parts.append(("T", text[position:match.start()]))
        parts.append(("P", match.group(0)))
        position = match.end()
    parts.append(("T", text[position:]))
    result: list[str] = []
    for kind, chunk in parts:
        if kind == "P" or not _LETTER.search(chunk):
            result.append(chunk)
            continue
        leading = chunk[: len(chunk) - len(chunk.lstrip())]
        trailing = chunk[len(chunk.rstrip()):]
        translated = translator.translate(chunk.strip(), log=log_fn).strip()
        if not translated:
            raise RuntimeError("Translation returned no text for a Markdown block.")
        result.append(f"{leading}{translated}{trailing}")
    return "".join(result)


def _split_table_cells(line: str) -> list[str]:
    return re.split(r"(?<!\\)\|", line)


def translate_markdown_text(
    text: str,
    translator: TextTranslator,
    log_fn: Callable[[str], None] = print,
) -> tuple[str, list[str], list[str]]:
    """Translate Markdown text, returning (markdown, source blocks, translated blocks)."""
    lines = text.splitlines()
    output: list[str] = []
    sources: list[str] = []
    translations: list[str] = []

    def translate_block(body: str) -> str:
        total_hint = len(sources) + 1
        safe_log(log_fn, f"[INFO] Translating Markdown block {total_hint}")
        translated = _translate_inline(body, translator, log_fn)
        sources.append(body)
        translations.append(translated)
        return translated

    index = 0
    if lines and lines[0].strip() == "---":
        for end in range(1, len(lines)):
            if lines[end].strip() in ("---", "..."):
                output.extend(lines[: end + 1])
                index = end + 1
                break

    fence_marker: str | None = None
    paragraph: list[str] = []
    paragraph_prefix = ""

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            body = " ".join(part.strip() for part in paragraph)
            output.append(paragraph_prefix + translate_block(body))
            paragraph = []

    while index < len(lines):
        line = lines[index]
        index += 1
        fence = _FENCE.match(line)
        if fence_marker is not None:
            output.append(line)
            if fence and fence.group(1)[:3] == fence_marker[:3]:
                fence_marker = None
            continue
        if fence:
            flush_paragraph()
            fence_marker = fence.group(1)
            output.append(line)
            continue
        if (
            not line.strip()
            or _RULE.match(line)
            or _REFERENCE_DEF.match(line)
            or line.startswith(("    ", "\t"))
            and not paragraph
            or line.lstrip().startswith("<")
        ):
            flush_paragraph()
            output.append(line)
            continue
        if line.lstrip().startswith("|"):
            flush_paragraph()
            if _TABLE_SEPARATOR.match(line):
                output.append(line)
                continue
            cells = _split_table_cells(line)
            output.append(
                "|".join(
                    (
                        f"{cell[: len(cell) - len(cell.lstrip())]}"
                        f"{translate_block(cell.strip())}"
                        f"{cell[len(cell.rstrip()):]}"
                    )
                    if _LETTER.search(cell)
                    else cell
                    for cell in cells
                )
            )
            continue

        match = _LINE_PREFIX.match(line)
        prefix, body = match.group("prefix"), match.group("body")
        if prefix.replace(">", "").strip():
            flush_paragraph()
            closer = ""
            if prefix.lstrip(" >").startswith("#"):
                closing = _HEADING_CLOSER.search(body)
                if closing:
                    closer, body = closing.group(1), body[: closing.start()]
            if _LETTER.search(body):
                output.append(prefix + translate_block(body) + closer)
            else:
                output.append(line)
            continue
        if paragraph and paragraph_prefix != prefix:
            flush_paragraph()
        if not paragraph:
            paragraph_prefix = prefix
        if _LETTER.search(body) or paragraph:
            paragraph.append(body)
        else:
            output.append(line)
    flush_paragraph()
    return "\n".join(output) + "\n", sources, translations


def translate_markdown(
    markdown_path: Path,
    source_lang: str,
    target_lang: str,
    log_fn: Callable[[str], None] = print,
    *,
    output_dir: Path | None = None,
) -> MarkdownTranslationResult:
    markdown_path = Path(markdown_path)
    if not markdown_path.is_file() or markdown_path.suffix.lower() not in MARKDOWN_SUFFIXES:
        raise ValueError("Select an existing Markdown (.md or .markdown) file.")
    if source_lang not in NLLB_LANGUAGE_MAP or target_lang not in NLLB_LANGUAGE_MAP:
        raise ValueError("Markdown translation supports German and English only.")
    if source_lang == target_lang:
        raise ValueError("The source and target languages must be different.")

    destination = Path(output_dir) if output_dir is not None else markdown_path.parent
    if not destination.is_dir():
        raise ValueError(f"Output folder does not exist or is not a directory: {destination}")
    text_dir = destination / f"{markdown_path.stem}_translation"
    extracted_file = text_dir / "extracted_text" / f"{markdown_path.stem}.txt"
    translated_file = text_dir / "translated_text" / f"{markdown_path.stem}.txt"
    output_markdown = destination / f"{markdown_path.stem}_translated{markdown_path.suffix}"

    try:
        text = markdown_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("The Markdown file must be UTF-8 encoded.") from exc
    if not text.strip():
        raise ValueError("The Markdown file is empty.")

    translator = _create_nllb_translator(
        NLLB_LANGUAGE_MAP[source_lang],
        NLLB_LANGUAGE_MAP[target_lang],
        log_fn,
    )
    translated_markdown, sources, translations = translate_markdown_text(
        text, translator, log_fn
    )
    if not sources:
        raise ValueError("No translatable text was found in the Markdown file.")

    extracted_file.parent.mkdir(parents=True, exist_ok=True)
    translated_file.parent.mkdir(parents=True, exist_ok=True)
    extracted_file.write_text("\n\n".join(sources), encoding="utf-8")
    translated_file.write_text("\n\n".join(translations), encoding="utf-8")
    output_markdown.write_text(translated_markdown, encoding="utf-8")
    safe_log(
        log_fn,
        f"[DONE] Translated {len(sources)} Markdown text block(s) "
        f"using {source_lang} -> {target_lang}.",
    )
    return MarkdownTranslationResult(
        translated_markdown=output_markdown,
        extracted_text_files=[extracted_file],
        translated_text_files=[translated_file],
        translated_block_count=len(sources),
    )
