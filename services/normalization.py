"""Pure source normalization extracted from the working UI; no UI or database imports."""
from __future__ import annotations
from datetime import date, datetime
import re
import html
from typing import Any

def _source_name(alert: dict[str, Any]) -> str:
    return str(
        alert.get("source_label")
        or alert.get("source")
        or "LegalTech"
    )


def _document_type(alert: dict[str, Any]) -> str:
    fields = alert.get("source_fields") or {}

    for key in (
        "type_modification",
        "type_publication",
        "type_reservation",
        "categorie_registre",
    ):
        value = fields.get(key)
        if value:
            return str(value)

    source = str(alert.get("source") or "").casefold()
    label = _source_name(alert).casefold()

    if source == "rne" or "registre national" in label:
        return "RNE"
    if source == "jort" or "journal officiel" in label:
        return "JORT"
    if source.startswith("jr") or label.startswith("journal"):
        return "Presse"
    return "Alerte"


def _date(alert: dict[str, Any]) -> str:
    raw = str(alert.get("card_date") or "").strip()
    if "T" in raw:
        raw = raw.split("T", 1)[0]
    return raw or "—"


def _notification_company(alert: dict[str, Any]) -> str:
    return str(
        alert.get("company_or_query")
        or alert.get("notification_company")
        or "—"
    )


def _analysis_text(alert: dict[str, Any]) -> str:
    return str(
        alert.get("detail_text")
        or alert.get("card_summary")
        or alert.get("card_text")
        or ""
    ).strip()

def _source_short(alert: dict) -> str:
    source = str(alert.get("source") or "").casefold()
    label = str(_source_name(alert) or "").casefold()
    if source == "rne" or "registre national" in label:
        return "RNE"
    if source == "jort" or "journal officiel" in label:
        return "JORT"
    if source.startswith("jr") or label.startswith("journal"):
        return "PRESSE"
    return str(_source_name(alert) or "SOURCE")[:18].upper()


def _reference(alert: dict) -> str:
    fields = alert.get("source_fields") or {}
    return str(
        fields.get("numero_publication")
        or fields.get("identifiant_unique")
        or alert.get("article_id")
        or alert.get("alert_key")
        or "—"
    )


def _analysis_value(analysis: dict | None, *keys: str, default: Any = "—") -> Any:
    if not analysis:
        return default
    for key in keys:
        value = analysis.get(key)
        if value not in (None, "", [], {}):
            return value
    return default


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _analysis_failed(analysis: dict | None) -> bool:
    if not analysis:
        return False
    summary = str(_analysis_value(analysis, "Résumé_IA", "resume", default="")).casefold()
    action = str(_analysis_value(analysis, "Action_Recommandée_IA", "action_recommandee", default="")).casefold()
    details = str(_analysis_value(analysis, "Détail_Score_Risque", default="")).casefold()
    patterns = [
        "analyse llm indisponible",
        "json invalide",
        "vérifier manuellement le document et la disponibilité d'ollama",
        "événement principal : autre",
    ]
    corpus = " | ".join([summary, action, details])
    return any(pattern in corpus for pattern in patterns)


def _clean_short_text(text: str, limit: int = 88) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


_GENERIC_ACTION_TEXTS = {
    "ajouter personne morale",
    "ajouter une personne morale",
    "télécharger",
    "telecharger",
    "ouvrir",
    "consulter",
    "voir",
    "voir détails",
    "voir details",
    "plus de détails",
    "plus de details",
    "détails",
    "details",
    "lire",
}


def _normalize_legaltech_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(
        r"\b(Télécharger|Telecharger|Ouvrir|Consulter|Voir détails|Voir details)\b",
        " ",
        text,
        flags=re.I,
    )
    return " ".join(text.split()).strip(" ·|-")


def _is_generic_legaltech_text(value: Any) -> bool:
    clean = _normalize_legaltech_text(value)
    if not clean:
        return True

    folded = clean.casefold().strip(" .:;-")
    if folded in _GENERIC_ACTION_TEXTS:
        return True

    if len(folded) <= 3:
        return True

    return False


def _iter_source_field_texts(value: Any, prefix: str = ""):
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key).casefold()
            if key_text in {
                "identifiant_unique",
                "numero_publication",
                "reference",
                "référence",
                "date",
                "date_evenement",
                "url",
                "href",
                "id",
            }:
                continue
            yield from _iter_source_field_texts(child, key_text)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _iter_source_field_texts(child, prefix)
    elif isinstance(value, (str, int, float)):
        clean = _normalize_legaltech_text(value)
        if not _is_generic_legaltech_text(clean):
            yield prefix, clean


def _alert_subject(alert: dict) -> str:
    fields = alert.get("source_fields") or {}
    legaltech_alert_title = _normalize_legaltech_text(fields.get("titre_alerte"))
    if legaltech_alert_title and not _is_generic_legaltech_text(legaltech_alert_title):
        return legaltech_alert_title
    company = _normalize_legaltech_text(_notification_company(alert)).casefold()

    preferred_field_keys = (
        "objet",
        "intitule",
        "intitulé",
        "titre",
        "libelle",
        "libellé",
        "nature_evenement",
        "nature",
        "type_evenement",
        "type_annonce",
        "operation",
        "opération",
        "decision",
        "décision",
    )

    candidates: list[str] = []
    for key in preferred_field_keys:
        if key in fields:
            candidates.append(_normalize_legaltech_text(fields.get(key)))

    candidates.extend(
        [
            _normalize_legaltech_text(alert.get("card_title")),
            _normalize_legaltech_text(alert.get("detail_title")),
        ]
    )

    for candidate in candidates:
        folded = candidate.casefold()
        if (
            candidate
            and not _is_generic_legaltech_text(candidate)
            and folded != company
            and len(candidate) <= 140
        ):
            return candidate

    source = _source_short(alert)
    source_fallbacks = {
        "JORT": "Publication au JORT",
        "RNE": "Publication au RNE",
        "PRESSE": "Publication presse",
    }
    return source_fallbacks.get(source, "Publication LegalTech")


def _legaltech_summary(alert: dict) -> str:
    """
    Return only text already collected from LegalTech.
    AI output is deliberately excluded from the 'Résumé' tab.
    """
    fields = alert.get("source_fields") or {}

    direct_candidates = [
        fields.get("resume"),
        fields.get("résumé"),
        fields.get("summary"),
        fields.get("description"),
        fields.get("objet_fr"),
        fields.get("objet"),
        fields.get("contenu"),
        fields.get("texte"),
        fields.get("details"),
        fields.get("détails"),
        fields.get("annonce"),
        alert.get("card_summary"),
        alert.get("card_text"),
        alert.get("detail_text"),
    ]

    for value in direct_candidates:
        clean = _normalize_legaltech_text(value)
        if (
            not _is_generic_legaltech_text(clean)
            and len(clean) >= 24
        ):
            return clean

    # Last fallback: assemble meaningful LegalTech source fields,
    # instead of ever displaying action labels such as "Télécharger".
    pieces: list[str] = []
    seen: set[str] = set()

    for field_name, clean in _iter_source_field_texts(fields):
        folded = clean.casefold()
        if folded in seen:
            continue
        seen.add(folded)

        company = _normalize_legaltech_text(_notification_company(alert)).casefold()
        if folded == company:
            continue

        if len(clean) < 10:
            continue

        pieces.append(clean)
        if len(pieces) >= 4:
            break

    if pieces:
        return " — ".join(pieces)

    return (
        "Aucun résumé textuel détaillé n'a été récupéré depuis LegalTech "
        "pour cette notification."
    )

def _clean(value: Any, limit: int | None = None) -> str:
    text = html.unescape(str(value or ""))
    text = __import__("re").sub(r"<[^>]+>", " ", text)
    text = " ".join(text.split()).strip()
    if limit and len(text) > limit:
        return text[: max(1, limit - 1)].rstrip() + "…"
    return text


def _date_obj(value: Any) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    raw = raw.split("T", 1)[0]
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    return None


def _flatten_metadata(value: Any, prefix: str = "", limit: int = 24) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []

    def walk(obj: Any, path: str) -> None:
        if len(rows) >= limit:
            return
        if isinstance(obj, dict):
            for k, v in obj.items():
                walk(v, f"{path}.{k}" if path else str(k))
        elif isinstance(obj, (list, tuple)):
            if obj and all(not isinstance(x, (dict, list, tuple)) for x in obj):
                text = ", ".join(str(x) for x in obj)
                if text.strip():
                    rows.append((path, _clean(text, 320)))
            else:
                for idx, child in enumerate(obj[:6]):
                    walk(child, f"{path}[{idx}]")
        else:
            text = _clean(obj, 320)
            if text:
                rows.append((path or "valeur", text))

    walk(value, prefix)
    return rows[:limit]
