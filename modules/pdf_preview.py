"""Read-only raster previews; never alter a source document."""
from functools import lru_cache
from pathlib import Path


def page_preview(filename, page=1):
    path = Path(filename).resolve()
    stat = path.stat()
    return _render(str(path), stat.st_mtime_ns, stat.st_size, int(page))


@lru_cache(maxsize=12)
def _render(filename, modified, size, page):
    import fitz
    with fitz.open(filename) as document:
        if document.needs_pass:
            raise ValueError("Le PDF est protégé par un mot de passe.")
        if not document.page_count:
            raise ValueError("Le PDF ne contient aucune page.")
        number = max(1, min(page, document.page_count))
        source = document.load_page(number - 1)
        scale = min(2, 1400 / max(source.rect.width, source.rect.height))
        pixmap = source.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        return {"image": pixmap.tobytes("png"), "page": number, "pages": document.page_count}
