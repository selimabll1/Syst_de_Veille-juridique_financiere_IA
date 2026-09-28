from __future__ import annotations

from hashlib import sha256
from typing import Any
import re

ALERT_IDENTITY_VERSION = "alert_identity_v29_1"


def _norm(value: Any) -> str:
    text = " ".join(str(value or "").split()).strip().casefold()
    return text


def stable_alert_uid(alert: dict[str, Any]) -> str:
    """Stable identity independent from sync-run or notification-card keys.

    LegalTech source + article_id is preferred because article_id survives
    repeated synchronizations. doc_id/date/title are deterministic fallbacks.
    """
    source = _norm(alert.get("source") or alert.get("source_label"))
    article_id = _norm(alert.get("article_id"))
    doc_id = _norm(alert.get("doc_id"))
    card_date = _norm(alert.get("card_date"))
    card_title = _norm(alert.get("card_title") or alert.get("detail_title"))
    article_url = _norm(alert.get("article_url"))

    if source and article_id and not article_id.startswith("network-"):
        raw = f"article|{source}|{article_id}"
    elif source and doc_id:
        raw = f"doc|{source}|{doc_id}|{card_title}|{card_date}"
    elif article_url:
        # Strip a volatile query-ordering issue while retaining document ids.
        raw = f"url|{article_url}"
    else:
        raw = f"fallback|{source}|{card_date}|{card_title}"

    return sha256(raw.encode("utf-8")).hexdigest()


def stable_notification_uid(item: dict[str, Any]) -> str:
    """Stable identity for the left-side LegalTech notification card."""
    company = _norm(item.get("company_or_query"))
    date = _norm(item.get("notification_date"))
    raw = _norm(item.get("raw_text"))

    # Date + company are preferred: result count can change in raw_text.
    if company or date:
        seed = f"notification|{company}|{date}"
    else:
        seed = f"notification|{raw}"
    return sha256(seed.encode("utf-8")).hexdigest()


def confirmed_capture_aliases(alerts, protected=()):
    """Read-only aliases for an ES hit and its identifier-less source capture.

    Require the complete source/document/title/date tuple and a unique real
    article identity. Never merge separate real articles or protected records.
    Existing identifiers and database records are not rewritten.
    """
    from collections import defaultdict
    groups = defaultdict(list)
    protected = {str(uid).removeprefix('legaltech:') for uid in protected}
    for alert in alerts:
        key = tuple(_norm(alert.get(k)) for k in ('source', 'doc_id', 'card_title', 'card_date'))
        if all(key):
            groups[key].append(alert)
    aliases = {}
    for variants in groups.values():
        real = {stable_alert_uid(a) for a in variants
                if _norm(a.get('article_id')) and not _norm(a.get('article_id')).startswith('network-')}
        if len(real) != 1:
            continue
        for alert in variants:
            uid = stable_alert_uid(alert)
            if uid in real or uid in protected or str(alert.get('alert_key', '')) in protected:
                continue
            aliases[uid] = next(iter(real))
    return aliases
