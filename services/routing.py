"""Deterministic eligibility, entity matching and rule-based routing."""
import csv
import json
from pathlib import Path
import re
import unicodedata
from hashlib import sha256
from functools import lru_cache
from services import pipeline_config


def normalized(value):
    return _normalized(str(value or ""))


@lru_cache(maxsize=2048)
def _normalized(value):
    value = unicodedata.normalize("NFKD", value.casefold().replace("_", " "))
    return " ".join(re.sub(r"[^\w]+", " ", "".join(c for c in value if not unicodedata.combining(c))).split())


def source_text(row):
    raw = row.get("raw", {})
    return str(raw.get("detail_text") or raw.get("raw_excerpt") or raw.get("card_summary") or raw.get("card_text") or row.get("summary") or "")


def contains(text, term):
    return bool(normalized(term)) and " " + normalized(term) + " " in " " + normalized(text) + " "


def identify(row, config):
    from services.event_taxonomy import TAXONOMY
    classification = _classify_source(source_text(row), row.get("kind") == "cmf" and "bulletin" in str(row.get("raw", {}).get("section", "")))
    aliases = {"CAPITAL_REDUCTION":"capital_reduction", "CAPITAL_INCREASE":"capital_increase", "ACQUISITION":"transaction", "DISPOSAL":"transaction", "MERGER":"transaction", "GOVERNANCE":"governance", "DIRECTOR_APPOINTMENT":"governance", "LIQUIDATION":"liquidation", "FINANCING":"financing"}
    events = []
    # A multi-document/ambiguous source does not establish one main event.
    if classification["event_type"] != "UNKNOWN":
        for candidate in classification["candidates"]:
            code = candidate["code"]
            for key in dict.fromkeys([code, aliases.get(code, code)]):
                events.append({"code":key,"label":TAXONOMY[code][0],"trigger":"source_evidence", "evidence_ids":candidate["evidence_ids"],"source":"collected_text"})
    return {"entity":row.get("entity") or None,"events":events,"event_type":classification["event_type"]}


@lru_cache(maxsize=2048)
def _classify_source(text, multi):
    from services.event_taxonomy import classify
    # Browsing needs source-level triggers only. Detailed span extraction is
    # reserved for an explicit analysis, not every notification row render.
    return classify([] if multi else [{"id":"SOURCE","quote":text}], multi_document=multi)


def portfolio_matches(matches):
    return [m for m in matches if m.get("portfolio_verified") and not m.get("ambiguous")]


def referential(config, watchlists, items):
    result = []
    owners = {w["id"]: w for w in watchlists}
    for item in items:
        if item.get("active", 1) and item.get("company"):
            owner = owners.get(item["watchlist_id"], {})
            # A monitoring list is not evidence of a holding.
            result.append({"name": item["company"], "identifier": item.get("identifier", ""), "type": "watchlist", "service": owner.get("service_id"), "origin": owner.get("name", "Liste UGFS"), "record_id": str(item.get("id", ""))})
    errors = []
    for filename in config.get("referential_files", []):
        path = Path(filename)
        if not path.is_absolute():
            path = pipeline_config.ROOT / path
        try:
            if "template" in path.name.casefold():
                raise ValueError("Un modèle de fichier n’est pas un référentiel réel.")
            if path.suffix.lower() == ".csv":
                with path.open(encoding="utf-8-sig", newline="") as handle:
                    records = list(csv.DictReader(handle))
            elif path.suffix.lower() == ".json":
                records = json.loads(path.read_text(encoding="utf-8"))
            elif path.suffix.lower() == ".xlsx":
                from openpyxl import load_workbook
                book = load_workbook(path, read_only=True, data_only=True)
                try:
                    values = book.active.iter_rows(values_only=True)
                    columns = next(values)
                    records = [dict(zip(columns, values)) for values in values]
                finally:
                    book.close()
            else:
                raise ValueError("Format de référentiel non pris en charge (CSV, JSON, XLSX).")
            file_hash = sha256(path.read_bytes()).hexdigest()
            for position, entry in enumerate(records, 2):
                fields = {normalized(k): v for k, v in entry.items()}
                name = fields.get("name") or fields.get("nom") or fields.get("societe") or fields.get("company")
                if name:
                    kind = normalized(fields.get("type") or fields.get("role ugfs") or "entity")
                    kind = {"portefeuille": "portfolio", "participation": "portfolio", "participations": "portfolio", "portfolio company": "portfolio", "societe portefeuille": "portfolio", "dirigeant": "director", "actionnaire": "shareholder", "fonds": "fund"}.get(kind, kind)
                    result.append({"name": str(name), "identifier": fields.get("identifier") or fields.get("identifiant") or "", "type": kind, "service": fields.get("service") or "", "portfolio_company": fields.get("portfolio company") or fields.get("societe portefeuille") or "", "sector": fields.get("sector") or fields.get("gics l4") or fields.get("secteur") or "", "gics_l4": fields.get("gics l4") or "", "fund": fields.get("fund") or "", "as_of": fields.get("as of") or "", "source_reference": fields.get("source reference") or "", "origin": path.name, "record_id": fields.get("reference id") or f"{path.name}:{position}", "file_hash": file_hash})
        except Exception as exc:
            errors.append(f"Référentiel {path.name} : {exc}")
    return result, errors


def confirmed_holding(entity):
    if entity.get("type") != "portfolio":
        return False
    if normalized(entity.get("status")) in {"inactive", "inactif", "sortie", "cedee", "cede", "sold", "closed"}:
        return False
    if str(entity.get("ownership_pct", "")).strip():
        try:
            if float(str(entity["ownership_pct"]).replace("%", "").replace(",", ".")) <= 0:
                return False
        except ValueError:
            return False
    return True


def match(row, entities):
    blob = " ".join((str(row.get("entity") or ""), str(row.get("title") or ""), source_text(row)))
    found = []
    for entity in entities:
        names = [str(entity.get("identifier") or ""), str(entity.get("name") or "")]
        matched = next((name for name in names if len(normalized(name)) >= 3 and contains(blob, name)), None)
        if matched:
            duplicates = [e for e in entities if normalized(e["name"]) == normalized(entity["name"])]
            ambiguous = len({e.get("identifier") for e in duplicates if e.get("identifier")}) > 1 and matched != entity.get("identifier")
            linked_candidates = [e for e in entities if entity["type"] in {"director", "shareholder"} and confirmed_holding(e) and normalized(e["name"]) == normalized(entity.get("portfolio_company"))]
            linked = linked_candidates[0] if len(linked_candidates) == 1 else None
            verified = confirmed_holding(entity) or linked is not None
            found.append({**entity, "matched_text": matched, "match_reason": f"Correspondance exacte {matched} · {entity['origin']} · {entity.get('record_id', '')}", "ambiguous": ambiguous, "portfolio_verified": verified and not ambiguous, "affected_portfolio_entity": entity["name"] if entity["type"] == "portfolio" else linked["name"] if linked else None, "relationship_reason": f"{entity['type']} relié à {linked['name']} dans le référentiel" if linked else ""})
    return found


def suggest(row, matches, config):
    allowed = set(pipeline_config.eligible(row["kind"], config))
    services, reasons = [], []
    blob = normalized(" ".join((row.get("title", ""), source_text(row), row.get("entity", ""), row.get("type", ""))))
    events = identify(row, config)["events"]
    for rule in config.get("routing_rules", []):
        if not rule.get("active", True):
            continue
        if rule.get("source") and rule["source"] != row["kind"]:
            continue
        if rule.get("entity") and normalized(rule["entity"]) not in normalized(row["entity"]):
            continue
        if rule.get("document_type") and normalized(rule["document_type"]) not in normalized(row["type"]):
            continue
        if rule.get("referential_type") and not any((rule["referential_type"] == "portfolio" and m.get("portfolio_verified")) or (rule["referential_type"] != "portfolio" and m["type"] == rule["referential_type"]) for m in matches):
            continue
        if rule.get("event_types") and not set(rule["event_types"]).intersection(e["code"] for e in events):
            continue
        if rule.get("sectors") and not any(contains(m.get("sector"), sector) for m in matches for sector in rule["sectors"]):
            continue
        if rule.get("gics") and not any(normalized(m.get("gics_l4")) == normalized(code) for m in matches for code in rule["gics"]):
            continue
        if rule.get("entity_role") and not any(contains(m.get("role_ugfs"), rule["entity_role"]) for m in matches):
            continue
        keywords = rule.get("keywords", [])
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(",") if k.strip()]
        if keywords and not any(normalized(word) in blob for word in keywords):
            continue
        accepted = [service for service in rule.get("services", []) if service in allowed and (service != "portfolio" or portfolio_matches(matches))]
        services.extend(accepted)
        if accepted:
            reasons.append({"rule_id": rule.get("id"), "rule": rule.get("name", rule.get("id", "Règle")), "origin": "REFERENTIAL" if rule.get("referential_type") else "RULE", "priority": rule.get("priority"), "services": accepted, "events": events, "matches": [m["match_reason"] for m in matches if not m.get("ambiguous")]})
    services = list(dict.fromkeys(services))
    triage = config.get("sources", {}).get(row["kind"], {}).get("triage_service")
    if not services and not row.get("services") and triage in allowed and triage != "portfolio":
        services = [triage]
        reasons.append({"rule_id": "default_triage", "rule": "Triage initial — pertinence à confirmer", "origin": "TRIAGE", "services": [triage], "events": events, "matches": [], "priority": "Moyenne"})
    return services, reasons
