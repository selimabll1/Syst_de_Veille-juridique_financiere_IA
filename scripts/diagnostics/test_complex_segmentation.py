"""Usage: python scripts/test_complex_segmentation.py path/to/document.pdf"""

from __future__ import annotations

import sys
from pathlib import Path

from modules.document_segmenter import segment_legal_document
from modules.ocr_engine import extract_pdf_text


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/test_complex_segmentation.py path/to/document.pdf")
        return 2

    pdf_path = Path(sys.argv[1])

    if not pdf_path.exists():
        print(f"PDF not found: {pdf_path}")
        return 2

    extraction = extract_pdf_text(pdf_path)
    segments = segment_legal_document(extraction)

    print(f"PDF: {pdf_path.name}")
    print(f"Pages: {extraction['page_count']}")
    print(f"Direct pages: {extraction['direct_pages']}")
    print(f"OCR pages: {extraction['ocr_pages']}")
    print(f"Overall extraction quality: {extraction['ocr_quality']}")
    print(f"Announcements detected: {len(segments)}")
    print("-" * 90)

    for segment in segments[:15]:
        preview = " ".join(segment["text"].split())[:180]

        print(
            f"#{segment['segment_index']:03d} | "
            f"ref={segment['announcement_id'] or '-'} | "
            f"pages={segment['page_start']}-{segment['page_end']} | "
            f"chars={segment['character_count']} | {preview}"
        )

    if len(segments) > 15:
        print(f"... {len(segments) - 15} more announcement(s)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
