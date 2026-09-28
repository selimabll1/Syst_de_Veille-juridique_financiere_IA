"""Split long LegalTech/JORT bulletins into individual legal announcements.

The JORT legal-announcement PDFs contain many notices in the same PDF. Each
notice normally ends with a stable 15-character publication reference, for
example ``2026R01364SANB2`` or ``2026401567SRLB2``. This module uses those
references as the primary boundary and separator lines as a fallback.

The public entry point accepts the dictionary returned by
``modules.ocr_engine.extract_pdf_text`` and returns one dictionary per notice.
"""

from __future__ import annotations

import re
from typing import Any

# Examples observed in the JORT corpus:
# 2026R01364SANB2, 2026401567SRLB2, 2026S00603SODB1
ANNOUNCEMENT_ID_RE = re.compile(
    r"(?<![A-Z0-9])(?P<announcement_id>20\d{2}[A-Z0-9]{6}[A-Z]{4}\d)(?![A-Z0-9])"
)
SEPARATOR_RE = re.compile(r"(?m)^\s*[_\-—–]{4,}\s*$")
PAGE_MARKER_RE = re.compile(r"(?m)^\[\[PAGE:(\d+)\]\]\s*$")
LEADING_BOUNDARY_RE = re.compile(
    r"\A(?:(?:\s*\[\[PAGE:\d+\]\]\s*)|(?:\s*[_\-—–]{4,}\s*)|\s+)+"
)

MIN_SEGMENT_CHARS = 100

# Repeated page furniture. We only remove whole lines to avoid deleting legal
# content that happens to mention the Journal Officiel in a sentence.
NOISE_LINE_PATTERNS = [
    re.compile(r"^\s*Journal Officiel de la République Tunisienne.*$", re.I),
    re.compile(r"^\s*Annonces Légales, Réglementaires et Judiciaires.*$", re.I),
    re.compile(r"^\s*TRADUCTION Française\s*$", re.I),
    re.compile(r"^\s*N[°º]\s*\d+\s*$", re.I),
    re.compile(r"^\s*Page\s+\d+\s*$", re.I),
    re.compile(r"^\s*صفح(?:ة|ـة)\s*\d+\s*$"),
    re.compile(r"^\s*ع(?:ــ)?دد\s*\d+\s*$"),
    re.compile(r"^\s*الرائد الرسمي للجمهورية التونسية.*$"),
    re.compile(r"^\s*إع[ﻼلا]نات قانونية.*$"),
]


def _normalize_text(text: str) -> str:
    text = (text or "").replace("\u00ad", "").replace("\ufeff", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _private_use_ratio(text: str) -> float:
    if not text:
        return 0.0
    private = sum(0xE000 <= ord(char) <= 0xF8FF for char in text)
    return private / len(text)


def _clean_page_text(text: str) -> str:
    cleaned_lines: list[str] = []
    for raw_line in _normalize_text(text).splitlines():
        line = raw_line.strip()
        if not line:
            cleaned_lines.append("")
            continue
        if any(pattern.match(line) for pattern in NOISE_LINE_PATTERNS):
            continue
        # Some Arabic cover headings use embedded private-use fonts that are
        # not meaningful Unicode text. Dropping those lines is safer than
        # sending unreadable glyph codes to the LLM.
        private_ratio = _private_use_ratio(line)
        if private_ratio > 0.80 or (len(line) >= 4 and private_ratio > 0.55):
            continue
        cleaned_lines.append(line)
    return _normalize_text("\n".join(cleaned_lines))


def _is_front_matter(page_text: str) -> bool:
    normalized = page_text.casefold()
    has_toc = "sommaire" in normalized or "الفهرس" in normalized
    has_reference = bool(ANNOUNCEMENT_ID_RE.search(page_text))
    has_disclaimer = (
        "décline toute responsabilité" in normalized
        or "ﻻ تتحمل اﻹدارة أية مسؤولية" in page_text
        or "لا تتحمل الإدارة أية مسؤولية" in page_text
    )
    unreadable_cover = _private_use_ratio(page_text) > 0.02
    return (has_toc or has_disclaimer or unreadable_cover) and not has_reference


def _pages_from_extraction(extraction: dict[str, Any]) -> list[dict[str, Any]]:
    pages = extraction.get("pages")
    normalized_pages: list[dict[str, Any]] = []

    if isinstance(pages, list) and pages:
        for index, page in enumerate(pages, start=1):
            if not isinstance(page, dict):
                continue
            text = _clean_page_text(str(page.get("text", "")))
            normalized_pages.append(
                {
                    "page_number": int(page.get("page_number", index)),
                    "text": text,
                    "ocr_quality": float(
                        page.get("ocr_quality", extraction.get("ocr_quality", 0.0)) or 0.0
                    ),
                    "method": str(page.get("method", extraction.get("method", "unknown"))),
                }
            )
    else:
        # Backward compatibility with the original OCR engine.
        text = _clean_page_text(str(extraction.get("text", "")))
        normalized_pages.append(
            {
                "page_number": 1,
                "text": text,
                "ocr_quality": float(extraction.get("ocr_quality", 0.0) or 0.0),
                "method": str(extraction.get("method", "unknown")),
            }
        )

    while normalized_pages and _is_front_matter(normalized_pages[0]["text"]):
        normalized_pages.pop(0)

    return normalized_pages


def _build_marked_text(pages: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for page in pages:
        text = page["text"].strip()
        if not text:
            continue
        parts.append(f"[[PAGE:{page['page_number']}]]\n{text}")
    return "\n\n".join(parts)


def _page_markers(marked_text: str) -> list[tuple[int, int]]:
    return [
        (match.start(), int(match.group(1)))
        for match in PAGE_MARKER_RE.finditer(marked_text)
    ]


def _page_at_offset(
    markers: list[tuple[int, int]], offset: int, default: int = 1
) -> int:
    page = default
    for marker_offset, marker_page in markers:
        if marker_offset > offset:
            break
        page = marker_page
    return page


def _quality_for_range(
    pages: list[dict[str, Any]], page_start: int, page_end: int
) -> float:
    selected = [
        page for page in pages if page_start <= int(page["page_number"]) <= page_end
    ]
    if not selected:
        return 0.0
    total_weight = sum(max(1, len(page["text"])) for page in selected)
    score = sum(
        float(page["ocr_quality"]) * max(1, len(page["text"])) for page in selected
    ) / total_weight
    return round(max(0.0, min(1.0, score)), 3)


def _methods_for_range(
    pages: list[dict[str, Any]], page_start: int, page_end: int
) -> str:
    methods = {
        str(page["method"])
        for page in pages
        if page_start <= int(page["page_number"]) <= page_end
    }
    return "+".join(sorted(methods)) if methods else "unknown"


def _clean_segment(marked_text: str) -> str:
    text = PAGE_MARKER_RE.sub("", marked_text)
    text = SEPARATOR_RE.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return _normalize_text(text)


def _segment_by_references(marked_text: str) -> list[tuple[str, int, int]]:
    matches = list(ANNOUNCEMENT_ID_RE.finditer(marked_text))
    if not matches:
        return []

    segments: list[tuple[str, int, int]] = []
    start = 0
    for match in matches:
        end = match.end()
        segments.append((match.group("announcement_id"), start, end))
        start = end
    return segments


def _segment_by_separators(marked_text: str) -> list[tuple[str, int, int]]:
    separators = list(SEPARATOR_RE.finditer(marked_text))
    if not separators:
        return [("", 0, len(marked_text))]
    segments: list[tuple[str, int, int]] = []
    start = 0
    for separator in separators:
        segments.append(("", start, separator.start()))
        start = separator.end()
    segments.append(("", start, len(marked_text)))
    return segments


def segment_legal_document(extraction: dict[str, Any]) -> list[dict[str, Any]]:
    """Return one structured chunk per legal announcement.

    Args:
        extraction: Result from ``extract_pdf_text``. The enhanced OCR engine
            provides a ``pages`` list, but the old full-text result is accepted.

    Returns:
        A list of dictionaries containing ``text``, publication reference,
        source page range, OCR quality and extraction method.
    """
    pages = _pages_from_extraction(extraction)
    marked_text = _build_marked_text(pages)
    if not marked_text.strip():
        return []

    raw_segments = _segment_by_references(marked_text)
    boundary_method = "publication_reference"
    if not raw_segments:
        raw_segments = _segment_by_separators(marked_text)
        boundary_method = "separator_fallback"

    output: list[dict[str, Any]] = []
    seen_references: set[str] = set()

    markers = _page_markers(marked_text)

    for announcement_id, segment_start, segment_end in raw_segments:
        marked_segment = marked_text[segment_start:segment_end]
        text = _clean_segment(marked_segment)
        if len(text) < MIN_SEGMENT_CHARS:
            continue
        if announcement_id and announcement_id in seen_references:
            continue

        leading_boundary = LEADING_BOUNDARY_RE.match(marked_segment)
        content_start = segment_start + (
            leading_boundary.end() if leading_boundary else 0
        )
        page_start = _page_at_offset(markers, content_start)
        page_end = _page_at_offset(
            markers, max(content_start, segment_end - 1), page_start
        )
        output.append(
            {
                "segment_index": len(output) + 1,
                "announcement_id": announcement_id,
                "text": text,
                "page_start": page_start,
                "page_end": page_end,
                "ocr_quality": _quality_for_range(pages, page_start, page_end),
                "extraction_method": _methods_for_range(pages, page_start, page_end),
                "boundary_method": boundary_method,
                "character_count": len(text),
            }
        )
        if announcement_id:
            seen_references.add(announcement_id)

    # Ordinary single-announcement PDFs often have no JORT reference/separator.
    if not output:
        text = _clean_segment(marked_text)
        if len(text) >= MIN_SEGMENT_CHARS:
            markers = _page_markers(marked_text)
            page_start = _page_at_offset(markers, 0)
            page_end = _page_at_offset(markers, max(0, len(marked_text) - 1), page_start)
            output.append(
                {
                    "segment_index": 1,
                    "announcement_id": "",
                    "text": text,
                    "page_start": page_start,
                    "page_end": page_end,
                    "ocr_quality": _quality_for_range(pages, page_start, page_end),
                    "extraction_method": _methods_for_range(pages, page_start, page_end),
                    "boundary_method": "single_document_fallback",
                    "character_count": len(text),
                }
            )

    return output
