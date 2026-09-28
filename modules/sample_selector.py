"""Generic announcement sample selection for LegalTech PDFs.

This module never relies on a PDF filename, publication reference, company name,
or a fixed announcement position. It selects a diversified sample from whatever
legal events are actually detected in the uploaded document.
"""

from __future__ import annotations

from typing import Any

from modules.fact_validator import infer_primary_event


SAMPLE_SELECTOR_VERSION = "diverse_event_sampler_v1"


def _segment_text(segment: dict[str, Any]) -> str:
    return str(segment.get("text", "") or "").strip()


def select_first_segments(
    segments: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    """Return the first ``limit`` segments without mutating the input list."""
    safe_limit = max(1, int(limit))
    return list(segments[:safe_limit])


def select_diverse_segments(
    segments: list[dict[str, Any]],
    max_segments: int = 9,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Select a generic event-diversified sample.

    The first segment found for each distinct deterministically detected event
    is selected. If the PDF contains fewer distinct event types than requested,
    the remaining slots are filled in document order. This makes the method
    compatible with any PDF while preserving reproducibility.
    """
    safe_limit = max(1, int(max_segments))
    selected: list[dict[str, Any]] = []
    selected_object_ids: set[int] = set()
    detected_codes: list[str] = []
    seen_codes: set[str] = set()

    classified: list[tuple[dict[str, Any], str]] = []
    for segment in segments:
        event_code, _ = infer_primary_event(_segment_text(segment), "")
        classified.append((segment, event_code))

    # Prefer one representative of every recognised event type.
    for segment, event_code in classified:
        if event_code == "AUTRE" or event_code in seen_codes:
            continue
        selected.append(segment)
        selected_object_ids.add(id(segment))
        detected_codes.append(event_code)
        seen_codes.add(event_code)
        if len(selected) >= safe_limit:
            return selected, detected_codes

    # Keep one unclassified example when room remains, because it is useful for
    # testing the manual-review/fallback branch on any document.
    for segment, event_code in classified:
        if event_code != "AUTRE" or id(segment) in selected_object_ids:
            continue
        selected.append(segment)
        selected_object_ids.add(id(segment))
        detected_codes.append(event_code)
        break

    # Fill remaining slots in original document order; never depend on a known
    # reference, company, page number, or source file.
    for segment, _ in classified:
        if len(selected) >= safe_limit:
            break
        if id(segment) in selected_object_ids:
            continue
        selected.append(segment)
        selected_object_ids.add(id(segment))

    return selected, detected_codes
