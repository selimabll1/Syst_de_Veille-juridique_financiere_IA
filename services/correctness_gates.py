"""Deterministic correctness gates for every métier analysis.

The gates are deliberately independent of Streamlit and of the LLM transport.
They classify an analysis attempt before a result can be persisted as a normal
business result.  A failed gate is recorded on the attempt by the caller; no
production source data is changed here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from services.event_profiles import profile
from services import routing


OUTCOMES = {
    "SUCCESS",
    "SUCCESS_REVIEW_REQUIRED",
    "INSUFFICIENT_EVIDENCE",
    "EVENT_AMBIGUOUS",
    "SEGMENTATION_REQUIRED",
    "SOURCE_MISMATCH",
    "ANALYSIS_ERROR",
}


@dataclass(frozen=True)
class GateResult:
    outcome: str
    reasons: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.outcome in {"SUCCESS", "SUCCESS_REVIEW_REQUIRED"}

    @property
    def normal_result(self) -> bool:
        return self.outcome == "SUCCESS_REVIEW_REQUIRED"

    def error_message(self) -> str:
        suffix = "; ".join(self.reasons) or "Contrôle de cohérence non satisfait."
        return f"{self.outcome}: {suffix}"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _url(value: Any) -> str:
    raw = _text(value)
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
        return (parsed.scheme.casefold(), parsed.netloc.casefold(), parsed.path.rstrip("/")).__repr__()
    except ValueError:
        return raw.casefold().rstrip("/")


def source_identity(row: dict[str, Any], text: str, facts: dict[str, Any]) -> GateResult:
    """Ensure metadata and extracted text still describe one source record.

    Missing optional metadata is tolerated for legacy fixtures.  If two
    independently populated values disagree, the attempt is blocked.
    """
    raw = row.get("raw") or {}
    reasons: list[str] = []
    if not _text(text):
        reasons.append("Texte extrait absent")
    row_id = _text(row.get("stable_uid") or row.get("uid"))
    fact_id = _text(facts.get("source_record_id"))
    if row_id and fact_id and row_id != fact_id:
        reasons.append("source_record_id différent du registre")
    row_title = _text(row.get("title"))
    fact_title = _text(facts.get("source_title") or raw.get("source_title"))
    if row_title and fact_title and row_title.casefold() != fact_title.casefold():
        reasons.append("titre source différent")
    row_date = _text(row.get("date"))
    fact_date = _text(facts.get("publication_date", {}).get("value") if isinstance(facts.get("publication_date"), dict) else facts.get("publication_date"))
    if row_date and fact_date and row_date != fact_date:
        reasons.append("date de publication différente")
    row_pdf = _url(raw.get("pdf_url") or row.get("pdf_url"))
    fact_pdf = _url(facts.get("document_url") or raw.get("document_url") or raw.get("pdf_url"))
    if row_pdf and fact_pdf and row_pdf != fact_pdf:
        reasons.append("URL du document différente")
    if reasons:
        return GateResult("SOURCE_MISMATCH", tuple(reasons), {"source_record_id": row_id or fact_id})
    return GateResult("SUCCESS", details={"source_record_id": row_id or fact_id})


def document_scope(row: dict[str, Any], facts: dict[str, Any]) -> GateResult:
    scope = str(facts.get("document_scope") or "unknown").casefold()
    raw = row.get("raw") or {}
    child = raw.get("child_publication_id") or raw.get("child_event_id") or raw.get("segment_id")
    if scope in {"multiple", "multiple_events", "multiple_documents"} and not child:
        return GateResult("SEGMENTATION_REQUIRED", ("Le document contient plusieurs publications ou événements indépendants.",), {"scope": "MULTIPLE_EVENTS"})
    if scope in {"unknown", "unknown_scope", ""}:
        return GateResult("INSUFFICIENT_EVIDENCE", ("Périmètre documentaire non déterminé.",), {"scope": "UNKNOWN_SCOPE"})
    return GateResult("SUCCESS", details={"scope": "SINGLE_EVENT" if not child else "SEGMENTED_EVENT", "child_publication_id": child})


def event_and_facts(facts: dict[str, Any]) -> GateResult:
    event = str(facts.get("event_type") or "UNKNOWN")
    classification = facts.get("classification") or {}
    candidates = classification.get("candidates") or []
    if event == "UNKNOWN":
        if len(candidates) > 1:
            return GateResult("EVENT_AMBIGUOUS", ("Plusieurs familles d’événement restent concurrentes.",), {"candidates": candidates})
        spec = profile(event)
        if spec.get("allows_unknown") and facts.get("source_evidence"):
            return GateResult("SUCCESS", ("Famille d’événement non déterminée; résultat limité.",), {"event_type": event, "limited": True})
        return GateResult("INSUFFICIENT_EVIDENCE", ("Aucune famille d’événement suffisamment étayée.",), {"event_type": event})
    spec = profile(event)
    missing = []
    for key in spec.get("required", []):
        value = facts.get(key)
        if key == "event_type":
            present = event != "UNKNOWN"
        else:
            present = bool(value)
        if not present:
            missing.append(key)
    if missing:
        return GateResult("INSUFFICIENT_EVIDENCE", ("Faits obligatoires absents: " + ", ".join(missing),), {"event_type": event, "missing_required": missing})
    return GateResult("SUCCESS", details={"event_type": event, "missing_required": []})


def service_relevance(row: dict[str, Any], service: str, facts: dict[str, Any]) -> GateResult:
    matches = facts.get("referential_matches") or []
    if service == "portfolio" and not routing.portfolio_matches(matches):
        return GateResult("INSUFFICIENT_EVIDENCE", ("Aucune participation UGFS confirmée dans le référentiel.",), {"pertinence": "NON_DETERMINEE"})
    if service == "commercial":
        commercial = [m for m in matches if m.get("source_supported") and m.get("role_ugfs") and not m.get("ambiguous")]
        if not commercial:
            return GateResult("INSUFFICIENT_EVIDENCE", ("Aucun contexte commercial confirmé.",), {"pertinence": "NON_DETERMINEE"})
    return GateResult("SUCCESS")


def evidence_boundaries(facts: dict[str, Any], result: dict[str, Any] | None = None) -> GateResult:
    child = facts.get("child_publication_id") or facts.get("child_event_id")
    evidence = (result or {}).get("grounding", {}).get("evidence") or facts.get("source_evidence") or []
    if not child:
        return GateResult("SUCCESS")
    scope=facts.get('child_scope') or {}
    canonical={e['id']:e for e in facts.get('source_evidence',[])}
    bad = [e.get("id") for e in evidence if e.get("child_publication_id") != child
           or e.get('source_record_id')!=facts.get('source_record_id')
           or (scope and (not isinstance(e.get('page_start'),int) or not isinstance(e.get('page_end'),int)
                          or not scope['page_start']<=e['page_start']<=e['page_end']<=scope['page_end']))
           or e.get('id') not in canonical or e!=canonical.get(e.get('id'))]
    if bad:
        return GateResult("SOURCE_MISMATCH", ("Une preuve appartient à une autre publication enfant.",), {"foreign_evidence_ids": bad, "child_publication_id": child})
    return GateResult("SUCCESS")


def evaluate(row: dict[str, Any], service: str, text: str, facts: dict[str, Any], result: dict[str, Any] | None = None) -> GateResult:
    checks = [source_identity(row, text, facts), document_scope(row, facts), event_and_facts(facts), service_relevance(row, service, facts), evidence_boundaries(facts, result)]
    for check in checks:
        if check.outcome != "SUCCESS":
            return check
    validation = facts.get("validation") or {}
    if validation.get("status") == "INCONSISTENT":
        return GateResult("INSUFFICIENT_EVIDENCE", ("Les contrôles numériques sont incohérents.",), {"validation": validation})
    if result is not None:
        reliability = result.get("reliability") or {}
        score = reliability.get("score")
        if isinstance(score, (int, float)) and score < 60:
            if str(facts.get("event_type")) == "UNKNOWN" and profile("UNKNOWN").get("allows_unknown"):
                return GateResult("SUCCESS_REVIEW_REQUIRED", (f"Événement non déterminé; revue humaine obligatoire ({score}/100).",), {"score": score, "limited": True})
            return GateResult("INSUFFICIENT_EVIDENCE", (f"Fiabilité insuffisante ({score}/100).",), {"score": score})
        if isinstance(score, (int, float)) and score < 80:
            return GateResult("SUCCESS_REVIEW_REQUIRED", (f"Revue humaine renforcée ({score}/100).",), {"score": score})
    return GateResult("SUCCESS_REVIEW_REQUIRED", ("Résultat sourcé, validation humaine obligatoire.",))
