from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests


CMF_COLLECTOR_VERSION = "cmf_collector_v1_2"
CMF_BASE_URL = "https://www.cmf.tn"
CMF_AVIS_URL = "https://www.cmf.tn/avis-et-d-cisions-du-cmf"
CMF_BULLETINS_URL = "https://www.cmf.tn/bulletin-officiel"
_ALLOWED_HOSTS = {"cmf.tn", "www.cmf.tn"}

_ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")
_DATE_TIME_RE = re.compile(r"\b(\d{2}/\d{2}/\d{4}\s+\d{1,2}:\d{2})\b")
_BULLETIN_RE = re.compile(
    r"Bulletin\s+officiel\s+du\s+CMF\s+N[°º]?\s*(\d+)\s+"
    r"(\d{1,2})\s+([A-Za-zÀ-ÿ]+)\s+(\d{4})",
    flags=re.I,
)

_MONTHS = {
    "janvier": 1,
    "fevrier": 2,
    "février": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "aout": 8,
    "août": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "decembre": 12,
    "décembre": 12,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(value: str) -> str:
    return " ".join(unescape(str(value or "")).replace("\xa0", " ").split()).strip()


def _safe_cmf_url(url: str) -> str:
    parsed = urlparse(str(url or ""))
    if parsed.scheme not in {"http", "https"} or (parsed.hostname or "").casefold() not in _ALLOWED_HOSTS:
        raise ValueError(f"URL CMF refusée : {url}")
    return url


def _paged(url: str, page_index: int) -> str:
    if page_index <= 0:
        return url
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["page"] = str(page_index)
    return urlunparse(parsed._replace(query=urlencode(query)))


class _TokenParser(HTMLParser):
    BLOCK = {
        "p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6",
        "section", "article", "main", "header", "footer", "br", "tr", "td", "th"
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tokens: list[dict[str, str]] = []
        self._skip = 0
        self._in_a = False
        self._a_href = ""
        self._a_parts: list[str] = []
        self._text_parts: list[str] = []

    def _flush_text(self) -> None:
        text = _clean(" ".join(self._text_parts))
        self._text_parts = []
        if text:
            self.tokens.append({"kind": "text", "text": text, "href": ""})

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip += 1
            return
        if self._skip:
            return
        if tag in self.BLOCK:
            self._flush_text()
        if tag == "a":
            self._flush_text()
            self._in_a = True
            self._a_parts = []
            self._a_href = dict(attrs).get("href") or ""

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag in {"script", "style", "noscript", "svg"} and self._skip:
            self._skip -= 1
            return
        if self._skip:
            return
        if tag == "a" and self._in_a:
            text = _clean(" ".join(self._a_parts))
            if text or self._a_href:
                self.tokens.append({"kind": "link", "text": text, "href": self._a_href})
            self._in_a = False
            self._a_parts = []
            self._a_href = ""
        if tag in self.BLOCK:
            self._flush_text()

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if self._in_a:
            self._a_parts.append(data)
        else:
            self._text_parts.append(data)

    def close(self) -> None:
        super().close()
        self._flush_text()


def _tokens(html_text: str) -> list[dict[str, str]]:
    parser = _TokenParser()
    parser.feed(html_text)
    parser.close()
    return parser.tokens


def _title_language(title: str) -> str:
    return "ar" if _ARABIC_RE.search(title) else "fr"


def _priority(title: str) -> str:
    folded = title.casefold()
    high_terms = (
        "suspension", "reprise de cotation", "sanction", "interdiction",
        "rappel des obligations", "offre publique", "bloc de contrôle",
        "blanchiment", "financement du terrorisme", "cybersécur",
        "تعليق", "عقوبة", "التزامات", "غسل الأموال", "تمويل الإرهاب",
    )
    return "Non classée"  # Priority is resolved by explicit service policies, not source identity.


def _category(title: str) -> str:
    folded = title.casefold()
    if "communiqué" in folded or "بلاغ" in folded:
        return "Communiqué officiel"
    if any(term in folded for term in ("obligation", "règlement", "réglement", "cotation", "marché", "السوق")):
        return "Réglementation / marché"
    return "Avis / communiqué"


def _uid(section: str, title: str, published_at: str, detail_url: str) -> str:
    canonical = "|".join(
        [section, _clean(title).casefold(), str(published_at).strip(), str(detail_url).strip()]
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def _normalize_datetime(value: str) -> str:
    try:
        return datetime.strptime(value, "%d/%m/%Y %H:%M").isoformat()
    except ValueError:
        return value


def _candidate_title(text: str) -> bool:
    folded = _clean(text).casefold()
    if len(folded) < 8:
        return False
    banned = {
        "accueil", "contact", "plan du site", "mentions légales", "recherche",
        "bulletins officiels", "avis et communiqués du cmf", "suivant", "précédent",
        "facebook", "linkedin", "youtube", "twitter",
    }
    if folded in banned:
        return False
    if re.fullmatch(r"\d+", folded):
        return False
    return True


def _extract_avis(html_text: str, page_url: str) -> list[dict[str, Any]]:
    tokens = _tokens(html_text)
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    for index, token in enumerate(tokens):
        if token["kind"] != "link" or not _candidate_title(token["text"]):
            continue

        date_text = ""
        for previous in reversed(tokens[max(0, index - 8):index]):
            matches = _DATE_TIME_RE.findall(previous["text"])
            if matches:
                date_text = matches[-1]
                break
        if not date_text:
            continue

        title = _clean(token["text"])
        href = str(token.get("href") or "").strip()
        target = urljoin(page_url, href) if href else page_url
        try:
            target = _safe_cmf_url(target)
        except ValueError:
            continue

        pdf_url = target if ".pdf" in urlparse(target).path.casefold() else ""
        detail_url = page_url if pdf_url else target
        published_at = _normalize_datetime(date_text)
        uid = _uid("avis", title, published_at, detail_url)
        if uid in seen:
            continue
        seen.add(uid)
        items.append(
            {
                "uid": uid,
                "section": "avis",
                "title": title,
                "published_at": published_at,
                "detail_url": detail_url,
                "pdf_url": pdf_url,
                "language": _title_language(title),
                "category": _category(title),
                "priority": _priority(title),
                "service": "compliance",
                "raw_excerpt": "",
            }
        )

    return items


def _visible_text(tokens: list[dict[str, str]]) -> str:
    return " ".join(_clean(token["text"]) for token in tokens if _clean(token["text"]))


def _extract_bulletins(html_text: str, page_url: str) -> list[dict[str, Any]]:
    tokens = _tokens(html_text)
    text = _visible_text(tokens)
    anchors = [token for token in tokens if token["kind"] == "link"]
    items: list[dict[str, Any]] = []
    seen_numbers: set[str] = set()
    # Current CMF filenames contain publication dates, not bulletin numbers.
    # Associate a PDF only within the same official listing row as its title.
    row_pdfs = {}
    for block in re.split(r'(?=<div\s+class=[\"\x27]views-row\b)', html_text, flags=re.I):
        block_tokens = _tokens(block)
        numbers = list(_BULLETIN_RE.finditer(_visible_text(block_tokens)))
        if len(numbers) != 1:
            continue
        for anchor in block_tokens:
            href = str(anchor.get("href") or "")
            if anchor.get("kind") == "link" and ".pdf" in urlparse(href).path.casefold():
                try:
                    row_pdfs[numbers[0].group(1)] = _safe_cmf_url(urljoin(page_url, href))
                    break
                except ValueError:
                    continue

    for match in _BULLETIN_RE.finditer(text):
        number, day, month_name, year = match.groups()
        if number in seen_numbers:
            continue
        seen_numbers.add(number)

        month = _MONTHS.get(month_name.casefold())
        if not month:
            continue
        published_at = f"{int(year):04d}-{month:02d}-{int(day):02d}"
        title = f"Bulletin officiel du CMF N°{number}"
        pdf_url = ""
        detail_url = page_url

        for anchor in anchors:
            href = str(anchor.get("href") or "").strip()
            text_value = _clean(anchor.get("text") or "")
            if not re.search(rf"(?<!\d){re.escape(number)}(?!\d)", text_value):
                continue
            candidate = urljoin(page_url, href)
            try:
                candidate = _safe_cmf_url(candidate)
            except ValueError:
                continue
            if ".pdf" in urlparse(candidate).path.casefold():
                pdf_url = candidate
                break
            if detail_url == page_url:
                detail_url = candidate

        pdf_url = row_pdfs.get(number, "") or pdf_url
        uid = sha256(f"cmf-bulletin|{number}".encode("utf-8")).hexdigest()
        items.append(
            {
                "uid": uid,
                "section": "bulletin",
                "title": title,
                "published_at": published_at,
                "detail_url": detail_url,
                "pdf_url": pdf_url,
                "language": "fr",
                "category": "Bulletin officiel",
                "priority": "Non classée",
                "service": "compliance",
                "raw_excerpt": "",
            }
        )

    return items


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/151 Safari/537.36 "
                "UGFS-CMF-Compliance/1.2"
            ),
            "Accept-Language": "fr-FR,fr;q=0.9,ar;q=0.8,en;q=0.6",
        }
    )
    return session


def _get_html(session: requests.Session, url: str, timeout: int) -> str:
    _safe_cmf_url(url)
    response = session.get(url, timeout=timeout, allow_redirects=True)
    response.raise_for_status()
    if "pdf" in str(response.headers.get("Content-Type") or "").casefold():
        raise ValueError("La source reçue est un PDF, pas une page HTML.")
    response.encoding = response.apparent_encoding or response.encoding or "utf-8"
    return response.text


def collect_cmf(*, max_pages: int = 1, timeout: int = 25) -> dict[str, Any]:
    """Collect official CMF notices + official bulletins and normalize them for Conformité."""
    started_at = _now()
    session = _session()
    errors: list[str] = []
    collected: list[dict[str, Any]] = []

    page_count = max(1, min(int(max_pages), 10))
    for page_index in range(page_count):
        avis_url = _paged(CMF_AVIS_URL, page_index)
        try:
            collected.extend(_extract_avis(_get_html(session, avis_url, timeout), avis_url))
        except Exception as exc:
            errors.append(f"Avis/Communiqués page {page_index + 1}: {exc}")

        bulletins_url = _paged(CMF_BULLETINS_URL, page_index)
        try:
            collected.extend(
                _extract_bulletins(_get_html(session, bulletins_url, timeout), bulletins_url)
            )
        except Exception as exc:
            errors.append(f"Bulletins page {page_index + 1}: {exc}")

    unique: dict[str, dict[str, Any]] = {}
    for item in collected:
        unique[item["uid"]] = item
    items = list(unique.values())
    items.sort(key=lambda item: str(item.get("published_at") or ""), reverse=True)

    return {
        "started_at": started_at,
        "finished_at": _now(),
        "items": items,
        "errors": errors,
        "avis_count": sum(item["section"] == "avis" for item in items),
        "bulletin_count": sum(item["section"] == "bulletin" for item in items),
        "pages_requested": page_count,
        "collector_version": CMF_COLLECTOR_VERSION,
    }


class _ReadableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.main_depth = 0
        self.seen_main = False
        self.all_parts: list[str] = []
        self.main_parts: list[str] = []
        self.content_depth = 0
        self.content_parts: list[str] = []
        self.document_pdf = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        if tag == "div":
            if dict(attrs).get("id") == "block-system-main":
                self.content_depth = 1
            elif self.content_depth:
                self.content_depth += 1
        if self.content_depth and tag in {"p", "div", "li", "br", "h1", "h2", "h3", "h4", "tr"}:
            self.content_parts.append("\n")
        if self.content_depth and tag in {"object", "embed", "iframe", "a"}:
            attrs_map = dict(attrs)
            candidate = attrs_map.get("data") or attrs_map.get("src") or attrs_map.get("href") or ""
            if not self.document_pdf and ".pdf" in urlparse(candidate).path.casefold():
                self.document_pdf = candidate.split("#", 1)[0]
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip += 1
        if tag in {"main", "article"}:
            self.main_depth += 1
            self.seen_main = True
        if tag in {"p", "div", "li", "br", "h1", "h2", "h3", "h4", "tr"}:
            self.all_parts.append("\n")
            if self.main_depth:
                self.main_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag == "div" and self.content_depth:
            self.content_depth -= 1
        if tag in {"script", "style", "noscript", "svg"} and self.skip:
            self.skip -= 1
        if tag in {"main", "article"} and self.main_depth:
            self.main_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.skip:
            return
        self.all_parts.append(data)
        if self.content_depth:
            self.content_parts.append(data)
        if self.main_depth:
            self.main_parts.append(data)

    def text(self) -> str:
        parts = self.content_parts or (self.main_parts if self.seen_main and self.main_parts else self.all_parts)
        lines = []
        for raw in "".join(parts).replace("\r", "\n").split("\n"):
            clean = _clean(raw)
            if clean:
                lines.append(clean)
        return "\n".join(lines)


def fetch_detail_content(url: str, *, max_chars: int = 14000, timeout: int = 25) -> dict:
    url = _safe_cmf_url(url)
    session = _session()
    response = session.get(url, timeout=timeout, allow_redirects=True)
    response.raise_for_status()
    content_type = str(response.headers.get("Content-Type") or "").casefold()
    if "pdf" in content_type or response.content.startswith(b"%PDF"):
        return {"text": "", "pdf_url": _safe_cmf_url(response.url)}

    response.encoding = response.apparent_encoding or response.encoding or "utf-8"
    parser = _ReadableParser()
    parser.feed(response.text)
    text = parser.text()
    if not text:
        raise ValueError("Aucun texte exploitable n'a été extrait de la page CMF.")
    pdf_url = _safe_cmf_url(urljoin(response.url, parser.document_pdf)) if parser.document_pdf else ""
    return {"text": text[:max(500, int(max_chars))], "pdf_url": pdf_url}


def fetch_detail_excerpt(url: str, *, max_chars: int = 14000, timeout: int = 25) -> str:
    content = fetch_detail_content(url, max_chars=max_chars, timeout=timeout)
    if content["pdf_url"]:
        raise ValueError("Cette publication contient un PDF. Lancez l’analyse pour extraire le document officiel, ou ouvrez la source.")
    return content["text"]
