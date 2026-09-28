"""Synchronisation LegalTech : annonces structurées d'abord, PDF optionnel.

Version v3 :
- le cœur du service stocke le texte/résumé et les métadonnées LegalTech ;
- le PDF est facultatif et un JWT expiré ne bloque jamais l'annonce ;
- les chaînes LegalTech de type ``['texte']`` sont nettoyées proprement ;
- l'empreinte métier ignore les variations cosmétiques de titre/catégories ;
- les anciennes annonces restent compatibles avec le registre v4.
"""

from __future__ import annotations

import ast
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import time
import unicodedata
from typing import Any, Iterator

from modules.legaltech_api_client_v2 import (
    LEGALTECH_API_CLIENT_VERSION,
    LegalTechAPIClient,
    LegalTechArticle,
    LegalTechTokenError,
)
from modules.legaltech_registry import LegalTechRegistry


LEGALTECH_SYNC_SERVICE_VERSION = "legaltech_sync_service_v4"

DEFAULT_CONFIG_PATH = Path("config/legaltech_collection.local.json")
DEFAULT_SESSION_PATH = Path("secrets/legaltech_session.local.json")
DEFAULT_TARGET_DIR = Path("data/pdf_raw")
DEFAULT_DATABASE_PATH = Path("data/legaltech_registry.sqlite3")
DEFAULT_LOCK_PATH = Path("data/.legaltech_sync.lock")


@dataclass(frozen=True)
class ArticlePreview:
    source_id: str
    reference: str
    title: str
    source: str
    language: str
    published_at: str
    categories: str
    summary: str
    already_known: bool


@dataclass(frozen=True)
class AccessTestResult:
    ok: bool
    mode: str
    articles_received: int
    pdf_tested: bool
    pdf_token_ok: bool
    sample_reference: str
    client_version: str
    message: str


@dataclass(frozen=True)
class PreviewResult:
    ok: bool
    mode: str
    articles_received: int
    selected: int
    new_count: int
    known_count: int
    articles: list[ArticlePreview]
    message: str


@dataclass(frozen=True)
class SyncItemResult:
    source_id: str
    reference: str
    source: str
    summary: str
    filename: str
    status: str
    detail_status: str
    pdf_status: str
    message: str


@dataclass(frozen=True)
class SyncResult:
    ok: bool
    mode: str
    articles_received: int
    selected: int
    collected: int
    updated: int
    known: int
    failed: int
    detail_enriched: int
    detail_failed: int
    detail_skipped: int
    pdf_collected: int
    pdf_unavailable: int
    pdf_skipped: int
    items: list[SyncItemResult]
    message: str


class _TextExtractor(HTMLParser):
    BLOCK_TAGS = {"br", "p", "div", "li", "tr", "td", "section", "article"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs
        if tag.casefold() in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _flatten_text_container(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, str):
        return value

    if isinstance(value, (list, tuple, set)):
        parts = [_flatten_text_container(item) for item in value]
        return "\n".join(part for part in parts if part.strip())

    if isinstance(value, dict):
        # articleText should normally not be an object, but if LegalTech changes
        # shape we keep readable values rather than displaying Python syntax.
        preferred_keys = (
            "text",
            "articleText",
            "summary",
            "resume",
            "content",
            "value",
        )
        for key in preferred_keys:
            if key in value:
                candidate = _flatten_text_container(value[key])
                if candidate.strip():
                    return candidate

        parts = [_flatten_text_container(item) for item in value.values()]
        return "\n".join(part for part in parts if part.strip())

    return str(value)


def _decode_serialized_container(raw: str) -> str:
    """Decode JSON/Python list strings such as ``['texte']`` safely."""
    stripped = raw.strip()
    if len(stripped) < 2:
        return stripped

    looks_serialized = (
        stripped[0] in "[({"
        and stripped[-1] in "])}"
    )
    if not looks_serialized:
        return stripped

    parsed: Any = None

    try:
        parsed = json.loads(stripped)
    except (json.JSONDecodeError, TypeError):
        try:
            parsed = ast.literal_eval(stripped)
        except (ValueError, SyntaxError):
            return stripped

    if isinstance(parsed, (list, tuple, set, dict)):
        return _flatten_text_container(parsed)

    return str(parsed) if parsed is not None else stripped


def clean_article_text(value: Any) -> str:
    """Return clean human-readable LegalTech text.

    Examples:
    - ``<mark>JORT</mark>`` -> ``JORT``
    - ``[' une annonce ']`` -> ``une annonce``
    - ``["texte 1", "texte 2"]`` -> two readable lines

    The original value remains stored separately as ``article_text_raw``.
    """
    raw = _flatten_text_container(value)
    raw = _decode_serialized_container(raw)
    raw = unescape(raw)

    parser = _TextExtractor()
    try:
        parser.feed(raw)
        parser.close()
        text = "".join(parser.parts)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", raw)

    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    lines = [
        re.sub(r"[ \t]+", " ", line).strip()
        for line in text.split("\n")
    ]
    cleaned = "\n".join(line for line in lines if line)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _normalize_datetime(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    candidate = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(candidate)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc)
        return dt.replace(microsecond=0).isoformat()
    except ValueError:
        return text


def _normalize_digest_text(value: str, *, casefold: bool = False) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text.casefold() if casefold else text


def _validate_local_files(config_path: Path, session_path: Path) -> None:
    del session_path
    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuration LegalTech manquante : {config_path}"
        )


def _client_and_registry(
    *,
    config_path: Path,
    session_path: Path,
    database_path: Path,
) -> tuple[LegalTechAPIClient, LegalTechRegistry]:
    _validate_local_files(config_path, session_path)
    return (
        LegalTechAPIClient.from_files(config_path, session_path),
        LegalTechRegistry(database_path),
    )


def _article_identifier(article: LegalTechArticle) -> str:
    explicit = (article.source_id or article.doc_id).strip()
    if explicit:
        return explicit

    fallback = "|".join(
        [
            article.reference,
            article.title,
            article.source,
            article.published_at,
            clean_article_text(article.article_text)[:500],
        ]
    )
    return "derived-" + sha256(fallback.encode("utf-8")).hexdigest()[:32]


def _safe_component(value: str, default: str = "annonce") -> str:
    cleaned = re.sub(
        r'[<>:"/\\|?*\x00-\x1f]',
        "_",
        value or default,
    ).strip(" ._")
    return (cleaned or default)[:100]


def _collection_filename(article: LegalTechArticle) -> str:
    label = _safe_component(
        article.reference or article.title or article.doc_id,
    )
    identifier = _article_identifier(article)
    suffix = sha256(identifier.encode("utf-8")).hexdigest()[:10]
    return f"{label}_{suffix}.pdf"


def _summary(article: LegalTechArticle, max_chars: int = 500) -> str:
    text = clean_article_text(article.article_text)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _content_digest(article: LegalTechArticle, clean_text: str) -> str:
    """Hash only the material legal content of an already identified result.

    ``source_id``/``doc_id`` identify the announcement itself. Title formatting,
    categories and other presentation metadata are intentionally excluded so
    cosmetic LegalTech changes do not create false UPDATED events.
    """
    canonical = json.dumps(
        {
            "reference": _normalize_digest_text(
                article.reference,
                casefold=True,
            ),
            "source": _normalize_digest_text(
                article.source,
                casefold=True,
            ),
            "published_at": _normalize_datetime(article.published_at),
            "page": article.page,
            "article_text": _normalize_digest_text(clean_text),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def _preview_article(
    article: LegalTechArticle,
    registry: LegalTechRegistry,
) -> ArticlePreview:
    identifier = _article_identifier(article)
    return ArticlePreview(
        source_id=identifier,
        reference=article.reference,
        title=article.title,
        source=article.source,
        language=article.language,
        published_at=article.published_at,
        categories=", ".join(article.categories),
        summary=_summary(article, 260),
        already_known=registry.has_announcement_source_id(identifier),
    )


@contextmanager
def _sync_lock(
    lock_path: Path = DEFAULT_LOCK_PATH,
    stale_after_seconds: int = 1800,
) -> Iterator[None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    if lock_path.exists():
        age = time.time() - lock_path.stat().st_mtime
        if age > stale_after_seconds:
            lock_path.unlink(missing_ok=True)

    try:
        descriptor = os.open(
            lock_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        )
    except FileExistsError as exc:
        raise RuntimeError(
            "Une synchronisation LegalTech est déjà en cours."
        ) from exc

    try:
        os.write(
            descriptor,
            f"pid={os.getpid()}\nstarted={time.time()}\n".encode("utf-8"),
        )
        os.close(descriptor)
        yield
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass
        lock_path.unlink(missing_ok=True)


def test_legaltech_access(
    *,
    limit: int = 1,
    verify_pdf_token: bool = False,
    config_path: Path = DEFAULT_CONFIG_PATH,
    session_path: Path = DEFAULT_SESSION_PATH,
    database_path: Path = DEFAULT_DATABASE_PATH,
) -> AccessTestResult:
    """Test article access; PDF auth is tested only when explicitly requested."""
    client, _ = _client_and_registry(
        config_path=config_path,
        session_path=session_path,
        database_path=database_path,
    )

    articles, _ = client.fetch_articles(limit=max(1, min(limit, 3)))
    if not articles:
        return AccessTestResult(
            ok=False,
            mode=client.mode,
            articles_received=0,
            pdf_tested=verify_pdf_token,
            pdf_token_ok=False,
            sample_reference="",
            client_version=LEGALTECH_API_CLIENT_VERSION,
            message="LegalTech est accessible, mais aucun article n'a été reçu.",
        )

    pdf_token_ok = False
    if verify_pdf_token:
        pdf_bytes = client.create_pdf_bytes(articles[0])
        pdf_token_ok = pdf_bytes.startswith(b"%PDF")
        del pdf_bytes

    reference = articles[0].reference or articles[0].title
    return AccessTestResult(
        ok=True,
        mode=client.mode,
        articles_received=len(articles),
        pdf_tested=verify_pdf_token,
        pdf_token_ok=pdf_token_ok,
        sample_reference=reference,
        client_version=LEGALTECH_API_CLIENT_VERSION,
        message=(
            "Accès LegalTech et génération PDF opérationnels."
            if verify_pdf_token
            else "Accès aux annonces LegalTech opérationnel. PDF non testé."
        ),
    )


def preview_legaltech_sync(
    *,
    limit: int = 5,
    max_items: int = 5,
    config_path: Path = DEFAULT_CONFIG_PATH,
    session_path: Path = DEFAULT_SESSION_PATH,
    database_path: Path = DEFAULT_DATABASE_PATH,
) -> PreviewResult:
    """Read LegalTech and classify announcements without generating PDFs."""
    client, registry = _client_and_registry(
        config_path=config_path,
        session_path=session_path,
        database_path=database_path,
    )

    safe_limit = max(1, min(int(limit), 50))
    safe_max = max(1, min(int(max_items), 50))
    articles, _ = client.fetch_articles(limit=safe_limit)
    selected = articles[:safe_max]
    previews = [_preview_article(article, registry) for article in selected]

    known = sum(item.already_known for item in previews)
    new = len(previews) - known

    return PreviewResult(
        ok=True,
        mode=client.mode,
        articles_received=len(articles),
        selected=len(previews),
        new_count=new,
        known_count=known,
        articles=previews,
        message=(
            f"{new} nouvelle(s) annonce(s), "
            f"{known} déjà connue(s). Aucun PDF généré."
        ),
    )


def _enrich_article_detail(
    *,
    client: LegalTechAPIClient,
    registry: LegalTechRegistry,
    article: LegalTechArticle,
    identifier: str,
) -> tuple[str, LegalTechArticle | None, str]:
    """Fetch and persist a richer LegalTech detail record.

    Returns ``(status, detail_article, error_message)``. A detail failure never
    turns a successfully collected announcement into a collection failure.
    """
    if not (
        str(article.source_id or "").strip()
        and str(article.source or "").strip()
        and str(article.doc_id or "").strip()
    ):
        registry.mark_announcement_detail_status(identifier, "SKIPPED")
        return "SKIPPED", None, "Identifiants de détail incomplets."

    try:
        detail, _payload = client.fetch_article_detail(article)
        detail_clean = clean_article_text(detail.article_text)
        registry.save_announcement_detail(
            source_id=identifier,
            reference=detail.reference or None,
            title=detail.title or None,
            language=detail.language or None,
            published_at=detail.published_at or None,
            page=detail.page,
            file_ref=detail.file or None,
            categories=list(detail.categories),
            article_text_raw=detail.article_text,
            article_text_clean=detail_clean,
            extras=detail.extras,
            metadata={
                "source_id": detail.source_id,
                "doc_id": detail.doc_id,
                "reference": detail.reference,
                "title": detail.title,
                "source": detail.source,
                "language": detail.language,
                "published_at": detail.published_at,
                "page": detail.page,
                "file": detail.file,
                "categories": list(detail.categories),
                "source_groups": list(detail.source_groups),
            },
        )
        return "ENRICHED", detail, ""
    except Exception as exc:
        registry.mark_announcement_detail_status(
            identifier,
            "FAILED",
            str(exc),
        )
        return "FAILED", None, str(exc)


def _save_optional_pdf(
    *,
    client: LegalTechAPIClient,
    registry: LegalTechRegistry,
    article: LegalTechArticle,
    identifier: str,
    target_dir: Path,
) -> tuple[str, str, bool]:
    """Return ``(pdf_status, filename, collected_now)``."""
    filename = _collection_filename(article)
    destination = target_dir / filename
    partial = destination.with_suffix(".pdf.part")

    try:
        pdf_bytes = client.create_pdf_bytes(article)
        digest = sha256(pdf_bytes).hexdigest()

        if registry.has_sha256(digest):
            registry.update_announcement_pdf_status(
                identifier,
                "DUPLICATE",
                filename,
            )
            return "DUPLICATE", filename, False

        partial.write_bytes(pdf_bytes)
        partial.replace(destination)

        inserted = registry.register(
            source_id=identifier,
            reference=article.reference or None,
            source_url=None,
            download_url=client.pdf_url,
            filename=destination.name,
            local_path=destination,
            sha256=digest,
            size_bytes=len(pdf_bytes),
            published_at=article.published_at or None,
            metadata={
                "title": article.title,
                "language": article.language,
                "source": article.source,
                "file": article.file,
                "page": article.page,
                "doc_id": article.doc_id,
                "categories": list(article.categories),
                "article_text_clean": clean_article_text(article.article_text),
            },
        )

        if inserted:
            registry.update_announcement_pdf_status(
                identifier,
                "COLLECTED",
                destination.name,
            )
            return "COLLECTED", destination.name, True

        destination.unlink(missing_ok=True)
        registry.update_announcement_pdf_status(
            identifier,
            "DUPLICATE",
            filename,
        )
        return "DUPLICATE", filename, False

    except LegalTechTokenError:
        partial.unlink(missing_ok=True)
        registry.update_announcement_pdf_status(identifier, "TOKEN_EXPIRED")
        return "TOKEN_EXPIRED", "", False
    except Exception:
        partial.unlink(missing_ok=True)
        registry.update_announcement_pdf_status(identifier, "UNAVAILABLE")
        return "UNAVAILABLE", "", False


def synchronize_legaltech(
    *,
    limit: int = 5,
    max_items: int = 5,
    enrich_details: bool = True,
    try_pdf: bool = False,
    config_path: Path = DEFAULT_CONFIG_PATH,
    session_path: Path = DEFAULT_SESSION_PATH,
    target_dir: Path = DEFAULT_TARGET_DIR,
    database_path: Path = DEFAULT_DATABASE_PATH,
    lock_path: Path = DEFAULT_LOCK_PATH,
) -> SyncResult:
    """Synchronize structured announcements; PDF generation is optional."""
    with _sync_lock(lock_path):
        client, registry = _client_and_registry(
            config_path=config_path,
            session_path=session_path,
            database_path=database_path,
        )

        safe_limit = max(1, min(int(limit), 50))
        safe_max = max(1, min(int(max_items), 50))
        articles, _ = client.fetch_articles(limit=safe_limit)
        selected = articles[:safe_max]
        target_dir.mkdir(parents=True, exist_ok=True)

        collected = 0
        updated = 0
        known = 0
        failed = 0
        detail_enriched = 0
        detail_failed = 0
        detail_skipped = 0
        pdf_collected = 0
        pdf_unavailable = 0
        pdf_skipped = 0
        item_results: list[SyncItemResult] = []

        for article in selected:
            identifier = _article_identifier(article)
            reference = article.reference or article.title or identifier
            clean_text = clean_article_text(article.article_text)
            content_digest = _content_digest(article, clean_text)

            try:
                announcement_status = registry.upsert_announcement(
                    source_id=identifier,
                    doc_id=article.doc_id or None,
                    reference=article.reference or None,
                    title=article.title or None,
                    source_name=article.source or None,
                    language=article.language or None,
                    published_at=article.published_at or None,
                    page=article.page,
                    file_ref=article.file or None,
                    categories=list(article.categories),
                    article_text_raw=article.article_text,
                    article_text_clean=clean_text,
                    content_sha256=content_digest,
                    metadata={
                        "raw_source_id": article.source_id,
                        "doc_id": article.doc_id,
                        "reference": article.reference,
                        "title": article.title,
                        "source": article.source,
                        "language": article.language,
                        "published_at": article.published_at,
                        "page": article.page,
                        "file": article.file,
                        "categories": list(article.categories),
                    },
                )

                if announcement_status == "NEW":
                    collected += 1
                elif announcement_status == "UPDATED":
                    updated += 1
                else:
                    known += 1

                detail_status = "NOT_FETCHED"
                detail_article: LegalTechArticle | None = None
                detail_error = ""

                if enrich_details:
                    detail_status, detail_article, detail_error = _enrich_article_detail(
                        client=client,
                        registry=registry,
                        article=article,
                        identifier=identifier,
                    )
                    if detail_status == "ENRICHED":
                        detail_enriched += 1
                    elif detail_status == "FAILED":
                        detail_failed += 1
                    else:
                        detail_skipped += 1
                else:
                    registry.mark_announcement_detail_status(
                        identifier,
                        "SKIPPED",
                    )
                    detail_status = "SKIPPED"
                    detail_skipped += 1

                display_article = detail_article or article
                display_reference = (
                    display_article.reference
                    or display_article.title
                    or reference
                )
                display_summary = _summary(display_article, 400)

                pdf_status = "NOT_REQUESTED"
                filename = ""

                if try_pdf:
                    pdf_status, filename, collected_pdf_now = _save_optional_pdf(
                        client=client,
                        registry=registry,
                        article=display_article,
                        identifier=identifier,
                        target_dir=target_dir,
                    )
                    if collected_pdf_now:
                        pdf_collected += 1
                    if pdf_status in {"TOKEN_EXPIRED", "UNAVAILABLE"}:
                        pdf_unavailable += 1
                else:
                    pdf_skipped += 1

                item_results.append(
                    SyncItemResult(
                        source_id=identifier,
                        reference=display_reference,
                        source=display_article.source or article.source,
                        summary=display_summary,
                        filename=filename,
                        status=announcement_status,
                        detail_status=detail_status,
                        pdf_status=pdf_status,
                        message=(
                            (
                                "Annonce structurée enregistrée."
                                if announcement_status == "NEW"
                                else (
                                    "Annonce réellement mise à jour."
                                    if announcement_status == "UPDATED"
                                    else "Annonce déjà connue, contenu inchangé."
                                )
                            )
                            + (
                                " Détail LegalTech enrichi."
                                if detail_status == "ENRICHED"
                                else (
                                    f" Détail indisponible : {detail_error}"
                                    if detail_status == "FAILED"
                                    else " Détail non enrichi."
                                )
                            )
                        ),
                    )
                )

            except Exception as exc:
                failed += 1
                item_results.append(
                    SyncItemResult(
                        source_id=identifier,
                        reference=reference,
                        source=article.source,
                        summary=_summary(article, 400),
                        filename="",
                        status="FAILED",
                        detail_status="NOT_FETCHED",
                        pdf_status="NOT_REQUESTED",
                        message=str(exc),
                    )
                )

        pdf_message = (
            (
                f"PDF : {pdf_collected} collecté(s), "
                f"{pdf_unavailable} indisponible(s)."
            )
            if try_pdf
            else f"PDF : {pdf_skipped} non demandé(s)."
        )

        return SyncResult(
            ok=(failed == 0),
            mode=client.mode,
            articles_received=len(articles),
            selected=len(selected),
            collected=collected,
            updated=updated,
            known=known,
            failed=failed,
            detail_enriched=detail_enriched,
            detail_failed=detail_failed,
            detail_skipped=detail_skipped,
            pdf_collected=pdf_collected,
            pdf_unavailable=pdf_unavailable,
            pdf_skipped=pdf_skipped,
            items=item_results,
            message=(
                f"{collected} nouvelle(s) annonce(s), "
                f"{updated} vraie(s) mise(s) à jour, "
                f"{known} déjà connue(s), "
                f"{failed} échec(s). "
                f"Détails : {detail_enriched} enrichi(s), "
                f"{detail_failed} indisponible(s), "
                f"{detail_skipped} ignoré(s). "
                f"{pdf_message}"
            ),
        )


def list_recent_announcements(
    limit: int = 200,
    database_path: Path = DEFAULT_DATABASE_PATH,
) -> list[dict[str, Any]]:
    return LegalTechRegistry(database_path).recent_announcements(limit=limit)


def result_to_dict(result: Any) -> dict[str, Any]:
    return asdict(result)
