"""Validation checks for the PDF -> extraction -> segmentation pipeline.

The validator does not decide whether a legal analysis is semantically correct.
It checks whether the technical preparation is safe enough before sending each
announcement to the LLM and exporting one row per announcement.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from modules.document_segmenter import ANNOUNCEMENT_ID_RE

SHORT_SEGMENT_CHARS = 250
LONG_SEGMENT_CHARS = 12_000
LOW_DOCUMENT_QUALITY = 0.70
CRITICAL_DOCUMENT_QUALITY = 0.50
LOW_PAGE_QUALITY = 0.65


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _issue(code: str, message: str, **details: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"code": code, "message": message}
    if details:
        result["details"] = details
    return result


def validate_extraction_and_segments(
    extraction: dict[str, Any],
    segments: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate extraction and announcement segmentation.

    Returns a serializable report with ``status`` equal to ``PASS``,
    ``WARNING`` or ``FAIL``. ``FAIL`` means LLM analysis should be blocked for
    that PDF; ``WARNING`` means analysis may continue but the PDF should be
    visibly flagged for human review.
    """
    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    text = str(extraction.get("text", "") or "")
    pages = extraction.get("pages", [])
    if not isinstance(pages, list):
        pages = []

    all_reference_matches = [
        match.group("announcement_id")
        for match in ANNOUNCEMENT_ID_RE.finditer(text)
    ]
    reference_counts = Counter(all_reference_matches)
    unique_references = list(reference_counts)
    duplicate_references = sorted(
        reference for reference, count in reference_counts.items() if count > 1
    )

    segment_references = [
        str(segment.get("announcement_id", "") or "").strip()
        for segment in segments
        if str(segment.get("announcement_id", "") or "").strip()
    ]
    segment_reference_counts = Counter(segment_references)
    duplicate_segment_references = sorted(
        reference
        for reference, count in segment_reference_counts.items()
        if count > 1
    )

    missing_references = sorted(set(unique_references) - set(segment_references))
    unexpected_references = sorted(set(segment_references) - set(unique_references))

    page_count = _safe_int(extraction.get("page_count"), len(pages))
    direct_pages = _safe_int(extraction.get("direct_pages"), 0)
    ocr_pages = _safe_int(extraction.get("ocr_pages"), 0)
    overall_quality = _safe_float(extraction.get("ocr_quality"), 0.0)

    if page_count <= 0:
        errors.append(_issue("NO_PAGES", "No PDF page was extracted."))

    if len(text.strip()) < 50:
        errors.append(
            _issue(
                "TEXT_TOO_SHORT",
                "The extracted document text is empty or too short.",
                character_count=len(text.strip()),
            )
        )

    if overall_quality < CRITICAL_DOCUMENT_QUALITY:
        errors.append(
            _issue(
                "CRITICAL_EXTRACTION_QUALITY",
                "Overall extraction quality is critically low.",
                quality=round(overall_quality, 3),
                threshold=CRITICAL_DOCUMENT_QUALITY,
            )
        )
    elif overall_quality < LOW_DOCUMENT_QUALITY:
        warnings.append(
            _issue(
                "LOW_EXTRACTION_QUALITY",
                "Overall extraction quality is below the recommended threshold.",
                quality=round(overall_quality, 3),
                threshold=LOW_DOCUMENT_QUALITY,
            )
        )

    if ocr_pages > 0:
        warnings.append(
            _issue(
                "OCR_USED",
                "One or more pages required Tesseract OCR.",
                ocr_pages=ocr_pages,
                page_count=page_count,
            )
        )

    low_quality_pages = []
    ocr_page_numbers = []
    extraction_error_pages = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        page_number = _safe_int(page.get("page_number"), 0)
        method = str(page.get("method", "") or "")
        quality = _safe_float(page.get("ocr_quality"), 0.0)
        error = str(page.get("error", "") or "").strip()

        if method == "tesseract_ocr":
            ocr_page_numbers.append(page_number)
        if quality < LOW_PAGE_QUALITY:
            low_quality_pages.append(
                {"page": page_number, "quality": round(quality, 3), "method": method}
            )
        if error:
            extraction_error_pages.append({"page": page_number, "error": error})

    if low_quality_pages:
        warnings.append(
            _issue(
                "LOW_QUALITY_PAGES",
                "Some pages have low extraction quality.",
                pages=low_quality_pages[:20],
                total=len(low_quality_pages),
            )
        )

    if extraction_error_pages:
        errors.append(
            _issue(
                "PAGE_EXTRACTION_ERRORS",
                "One or more pages produced extraction errors.",
                pages=extraction_error_pages[:20],
                total=len(extraction_error_pages),
            )
        )

    if not segments:
        errors.append(
            _issue(
                "NO_SEGMENTS",
                "No legal announcement segment was produced.",
            )
        )

    if unique_references and len(unique_references) != len(segments):
        errors.append(
            _issue(
                "REFERENCE_SEGMENT_COUNT_MISMATCH",
                "The number of unique publication references does not match the number of segments.",
                unique_reference_count=len(unique_references),
                segment_count=len(segments),
            )
        )

    if duplicate_references:
        warnings.append(
            _issue(
                "DUPLICATE_REFERENCES_IN_TEXT",
                "The same publication reference appears more than once in extracted text.",
                references=duplicate_references[:20],
                total=len(duplicate_references),
            )
        )

    if duplicate_segment_references:
        errors.append(
            _issue(
                "DUPLICATE_SEGMENT_REFERENCES",
                "Two or more segments share the same publication reference.",
                references=duplicate_segment_references[:20],
                total=len(duplicate_segment_references),
            )
        )

    if missing_references:
        errors.append(
            _issue(
                "MISSING_REFERENCES",
                "Some publication references were not preserved in segments.",
                references=missing_references[:20],
                total=len(missing_references),
            )
        )

    if unexpected_references:
        errors.append(
            _issue(
                "UNEXPECTED_SEGMENT_REFERENCES",
                "Some segment references were not present in the extracted document text.",
                references=unexpected_references[:20],
                total=len(unexpected_references),
            )
        )

    short_segments = []
    long_segments = []
    invalid_page_ranges = []
    missing_id_segments = []

    for segment in segments:
        index = _safe_int(segment.get("segment_index"), 0)
        announcement_id = str(segment.get("announcement_id", "") or "").strip()
        character_count = _safe_int(
            segment.get("character_count"), len(str(segment.get("text", "") or ""))
        )
        page_start = _safe_int(segment.get("page_start"), 0)
        page_end = _safe_int(segment.get("page_end"), 0)

        if character_count < SHORT_SEGMENT_CHARS:
            short_segments.append(
                {
                    "segment": index,
                    "reference": announcement_id,
                    "characters": character_count,
                }
            )
        if character_count > LONG_SEGMENT_CHARS:
            long_segments.append(
                {
                    "segment": index,
                    "reference": announcement_id,
                    "characters": character_count,
                }
            )
        if page_start <= 0 or page_end < page_start or (page_count and page_end > page_count):
            invalid_page_ranges.append(
                {
                    "segment": index,
                    "reference": announcement_id,
                    "page_start": page_start,
                    "page_end": page_end,
                }
            )
        if unique_references and not announcement_id:
            missing_id_segments.append(index)

    if short_segments:
        warnings.append(
            _issue(
                "SHORT_SEGMENTS",
                "Some segments are unusually short and should be reviewed.",
                segments=short_segments[:20],
                total=len(short_segments),
                threshold=SHORT_SEGMENT_CHARS,
            )
        )

    if long_segments:
        warnings.append(
            _issue(
                "LONG_SEGMENTS",
                "Some segments exceed the LLM input safety limit and may be truncated.",
                segments=long_segments[:20],
                total=len(long_segments),
                threshold=LONG_SEGMENT_CHARS,
            )
        )

    if invalid_page_ranges:
        errors.append(
            _issue(
                "INVALID_PAGE_RANGES",
                "Some segments have invalid source page metadata.",
                segments=invalid_page_ranges[:20],
                total=len(invalid_page_ranges),
            )
        )

    if missing_id_segments:
        errors.append(
            _issue(
                "SEGMENTS_WITHOUT_REFERENCE",
                "A reference-based bulletin produced segments without publication references.",
                segment_indexes=missing_id_segments[:20],
                total=len(missing_id_segments),
            )
        )

    if errors:
        status = "FAIL"
    elif warnings:
        status = "WARNING"
    else:
        status = "PASS"

    return {
        "status": status,
        "can_analyze": not errors,
        "metrics": {
            "page_count": page_count,
            "direct_pages": direct_pages,
            "ocr_pages": ocr_pages,
            "ocr_page_numbers": ocr_page_numbers,
            "overall_extraction_quality": round(overall_quality, 3),
            "reference_occurrences": len(all_reference_matches),
            "unique_references": len(unique_references),
            "segments": len(segments),
            "short_segments": len(short_segments),
            "long_segments": len(long_segments),
            "low_quality_pages": len(low_quality_pages),
        },
        "warnings": warnings,
        "errors": errors,
    }


def validation_summary(report: dict[str, Any]) -> str:
    """Build a concise human-readable summary for terminal or Streamlit."""
    metrics = report.get("metrics", {})
    return (
        f"Status={report.get('status', 'UNKNOWN')} | "
        f"Pages={metrics.get('page_count', 0)} | "
        f"References={metrics.get('unique_references', 0)} | "
        f"Segments={metrics.get('segments', 0)} | "
        f"OCR pages={metrics.get('ocr_pages', 0)} | "
        f"Quality={metrics.get('overall_extraction_quality', 0)} | "
        f"Warnings={len(report.get('warnings', []))} | "
        f"Errors={len(report.get('errors', []))}"
    )
