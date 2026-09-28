"""Deterministic document scope and child-publication helpers.

Composite bulletins remain one central source record.  These helpers create
ephemeral child contexts for analysis; they never duplicate or mutate source
registries.
"""
from __future__ import annotations

from typing import Any


def classify_scope(text: str, *, source_kind: str = "", section: str = "") -> str:
    if source_kind.casefold() == "cmf" and "bulletin" in section.casefold():
        return "MULTIPLE_EVENTS"
    markers = ("[[PUBLICATION:", "bulletin officiel n°", "avis n°")
    lowered = str(text or "").casefold()
    return "MULTIPLE_EVENTS" if sum(lowered.count(marker.casefold()) for marker in markers) > 1 else "SINGLE_EVENT"


def segment_children(extraction: dict[str, Any], *, parent_id: str, parent_title: str = "", pdf_url: str = "") -> list[dict[str, Any]]:
    from modules.document_segmenter import segment_legal_document

    children = []
    for segment in segment_legal_document(extraction):
        reference = segment.get("announcement_id") or f"segment-{segment['segment_index']}"
        child_id = f"{parent_id}::{reference}"
        children.append({
            "child_publication_id": child_id,
            "parent_source_record_id": parent_id,
            "parent_title": parent_title,
            "title": reference if not parent_title else f"{parent_title} · {reference}",
            "text": segment["text"],
            "page_start": segment.get("page_start"),
            "page_end": segment.get("page_end"),
            "pdf_url": pdf_url,
            "boundary_method": segment.get("boundary_method"),
            "source_evidence": {"page_start": segment.get("page_start"), "page_end": segment.get("page_end")},
        })
    return children
