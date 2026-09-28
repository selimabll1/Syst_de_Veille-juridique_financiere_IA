"""Usage: python -m scripts.test_pipeline_validation path/to/document.pdf"""

from __future__ import annotations

import json
import sys
from pathlib import Path



PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.document_segmenter import segment_legal_document
from modules.ocr_engine import extract_pdf_text
from modules.pipeline_validator import validation_summary, validate_extraction_and_segments


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.test_pipeline_validation path/to/document.pdf")
        return 2

    pdf_path = Path(sys.argv[1])
    if not pdf_path.exists():
        print(f"PDF not found: {pdf_path}")
        return 2

    extraction = extract_pdf_text(pdf_path)
    segments = segment_legal_document(extraction)
    report = validate_extraction_and_segments(extraction, segments)

    print(validation_summary(report))
    print("-" * 90)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    return 0 if report["can_analyze"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
