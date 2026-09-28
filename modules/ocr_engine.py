"""Page-aware PDF text extraction with OCR fallback.

This version keeps backward compatibility with the original ``extract_pdf_text``
result while also returning page-level metadata needed to segment complex JORT
bulletins into individual announcements.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any

import fitz
import pytesseract
from PIL import Image

from config import OCR_TEXT_DIR, TESSERACT_LANG

MIN_DIRECT_TEXT_CHARS = 100
MIN_DIRECT_QUALITY = 0.58
OCR_DPI = 300


def calculate_quality(text: str) -> float:
    """Estimate extraction legibility, not legal/semantic correctness."""
    text = (text or "").strip()
    if not text:
        return 0.0

    visible = [char for char in text if not char.isspace()]
    if not visible:
        return 0.0

    alpha = sum(char.isalpha() for char in visible) / len(visible)
    digits = sum(char.isdigit() for char in visible) / len(visible)
    replacement = sum(char in {"�", "□", "■"} for char in visible) / len(visible)
    control = sum(ord(char) < 32 for char in visible) / len(visible)

    words = re.findall(r"\S+", text)
    normal_words = sum(1 for word in words if 1 < len(word) <= 35)
    word_score = normal_words / max(1, len(words))
    length_score = min(1.0, len(text) / 500)

    score = (
        0.42 * min(1.0, alpha + digits)
        + 0.28 * word_score
        + 0.20 * length_score
        + 0.10 * (1.0 - min(1.0, replacement * 10 + control * 10))
    )
    return round(max(0.0, min(1.0, score)), 3)


def _extract_direct_page(page: fitz.Page) -> str:
    # Keep the PDF creator's content-stream order. In JORT bulletins this is
    # usually column-aware (LTR for French, RTL for Arabic) and is safer than
    # globally sorting every line by x/y coordinates.
    return page.get_text("text").strip()


def _ocr_page(page: fitz.Page) -> str:
    zoom = OCR_DPI / 72
    pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    image = Image.open(io.BytesIO(pixmap.tobytes("png")))
    return pytesseract.image_to_string(
        image,
        lang=TESSERACT_LANG,
        config="--oem 3 --psm 3",
    ).strip()


def _select_page_text(page: fitz.Page, page_number: int) -> dict[str, Any]:
    direct_text = _extract_direct_page(page)
    direct_quality = calculate_quality(direct_text)

    if (
        len(direct_text) >= MIN_DIRECT_TEXT_CHARS
        and direct_quality >= MIN_DIRECT_QUALITY
    ):
        return {
            "page_number": page_number,
            "text": direct_text,
            "method": "direct_text",
            "ocr_quality": direct_quality,
            "error": "",
        }

    try:
        ocr_text = _ocr_page(page)
        ocr_quality = calculate_quality(ocr_text)
        # Keep whichever extraction is objectively stronger. This avoids
        # replacing a short but clean digital page with worse OCR.
        if ocr_quality >= direct_quality or len(direct_text) < 30:
            return {
                "page_number": page_number,
                "text": ocr_text,
                "method": "tesseract_ocr",
                "ocr_quality": ocr_quality,
                "error": "",
            }
    except Exception as exc:  # noqa: BLE001 - returned to the UI as metadata
        return {
            "page_number": page_number,
            "text": direct_text,
            "method": "direct_text_after_ocr_error",
            "ocr_quality": direct_quality,
            "error": str(exc),
        }

    return {
        "page_number": page_number,
        "text": direct_text,
        "method": "direct_text_low_quality",
        "ocr_quality": direct_quality,
        "error": "",
    }


def save_extracted_text(pdf_path: Path, pages: list[dict[str, Any]]) -> Path:
    OCR_TEXT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OCR_TEXT_DIR / f"{pdf_path.stem}.txt"
    content = "\n\n".join(
        f"[[PAGE:{page['page_number']}]]\n{page['text']}" for page in pages
    )
    output_path.write_text(content, encoding="utf-8")
    return output_path


def extract_pdf_text(pdf_path: Path, *, persist: bool = True) -> dict[str, Any]:
    """Extract every page independently and OCR only pages that need it."""
    pdf_path = Path(pdf_path)
    pages: list[dict[str, Any]] = []

    with fitz.open(pdf_path) as document:
        for page_number, page in enumerate(document, start=1):
            pages.append(_select_page_text(page, page_number))

    combined_text = "\n\n".join(page["text"] for page in pages if page["text"])
    text_path = save_extracted_text(pdf_path, pages) if persist else None

    weighted_length = sum(max(1, len(page["text"])) for page in pages)
    overall_quality = (
        sum(
            float(page["ocr_quality"]) * max(1, len(page["text"]))
            for page in pages
        )
        / weighted_length
        if pages
        else 0.0
    )

    methods = {page["method"] for page in pages}
    if methods == {"direct_text"}:
        overall_method = "direct_text"
    elif methods == {"tesseract_ocr"}:
        overall_method = "tesseract_ocr"
    else:
        overall_method = "mixed_page_extraction"

    errors = [
        {"page_number": page["page_number"], "error": page["error"]}
        for page in pages
        if page.get("error")
    ]

    return {
        "text": combined_text,
        "method": overall_method,
        "ocr_quality": round(max(0.0, min(1.0, overall_quality)), 3),
        "text_path": str(text_path) if text_path else "",
        "page_count": len(pages),
        "pages": pages,
        "direct_pages": sum(
            1 for page in pages if page["method"].startswith("direct_text")
        ),
        "ocr_pages": sum(1 for page in pages if page["method"] == "tesseract_ocr"),
        "errors": errors,
    }
