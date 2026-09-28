"""Evidence-constrained business analysis using the shared local model.

The model selects source evidence, never supplies unconstrained financial facts.
Interpretations/actions come from visible configured policies and are labelled.
Unknown exposure, monetary effects, sector and deadlines stay unknown.
"""
from copy import deepcopy
from hashlib import sha256
import json
import re
from services import routing

UNKNOWN = "Non déterminé"


def evidence_catalog(text, config):
    """Exact source spans with topic/event tags; no paraphrased evidence."""
    evidence = []
    for chunk in re.finditer(r".+?(?:[.!?](?=\s|$)|\n|$)", text, re.DOTALL):
        quote = chunk.group().strip()
        if len(quote) < 12:
            continue
        # Keep complete sentences, including amounts after long legal preambles.
        # The caller already bounds the complete source to the model context.
        start = chunk.start() + len(chunk.group()) - len(chunk.group().lstrip())
        events = [code for code, rule in config.get("event_types", {}).items() if any(routing.contains(quote, phrase) for phrase in rule["keywords"])]
        topics = sorted({topic for code in events for topic in config["event_types"][code]["topics"]})
        evidence.append({"id": f"S{len(evidence)+1}", "quote": quote, "start": start, "end": start+len(quote), "events": events, "topics": topics, "origin": "source"})
    return evidence


def analyze(row, service, text, quality, method, config):
    from modules import llm_analyzer as engine
    from jsonschema import validate
    matches = routing.portfolio_matches(row.get("matches", []))
    if service == "portfolio" and not matches:
        raise ValueError("Aucune correspondance portefeuille confirmée. Renseignez le référentiel UGFS ; une affectation manuelle ne prouve pas une participation.")
    business = config["services"][service]
    source = text[:engine.MAX_INPUT_CHARS]
    catalog = evidence_catalog(source, config)
    if not catalog:
        raise ValueError("Aucune preuve source exploitable pour ce besoin métier.")
    by_id = {item["id"]: item for item in catalog}
    events = [code for code in config["event_types"] if any(code in e["events"] for e in catalog)]
    # Exclude weak governance hints when a more specific transaction is present.
    primary = next(iter(events), None)
    policy = config["event_types"].get(primary, {})
    allowed_actions = list(dict.fromkeys(policy.get("actions", []) + ["monitor"]))
    if service == "investment" and not matches:
        allowed_actions = [a for a in allowed_actions if a != "review_exposure"]
    schema = deepcopy(business["output_schema"])
    for field in ("summary_evidence", "focus_evidence"):
        schema["properties"][field]["items"]["enum"] = list(by_id)
    schema["properties"]["action_ids"]["items"]["enum"] = allowed_actions
    payload = {"service": service, "entity": row.get("entity"), "reference_matches": row.get("matches", []), "evidence": [{k:v for k,v in e.items() if k not in {"start", "end"}} for e in catalog], "allowed_actions": {a:config["business_actions"][a] for a in allowed_actions}}
    selected = engine.request_structured(json.dumps(payload, ensure_ascii=False), system_prompt=business["prompt"], schema=schema)
    validate(instance=selected, schema=schema)
    # A real model response is required. Invalid IDs fail; no fake fallback.
    summary_ids = selected["summary_evidence"]
    focus_ids = list(dict.fromkeys(selected["focus_evidence"] + summary_ids))
    event_ids = [e["id"] for e in catalog if primary in e["events"]] if primary else []
    if event_ids and not set(focus_ids).intersection(event_ids):
        raise ValueError("Le modèle n’a sélectionné aucune preuve de l’événement déterminant ; analyse à reprendre.")
    def quote(ids):
        return "\n".join(f"[{key}] {by_id[key]['quote']}" for key in ids) or UNKNOWN
    def topic(name):
        ids = [key for key in focus_ids if name in by_id[key]["topics"]]
        return quote(ids) if ids else UNKNOWN
    reference = [m for m in row.get("matches", []) if not m.get("ambiguous")]
    sector = " · ".join(sorted({str(m["sector"]) for m in reference if m.get("sector")})) or UNKNOWN
    uncertainty = "Effets chiffrés sur la valeur, performance future, croissance, opportunité économique et échéances contractuelles : non déterminés. Une date de publication n’est pas une échéance. Les citations sont des faits rapportés par la source, non une vérification indépendante."
    if not matches:
        uncertainty += " Aucune exposition UGFS confirmée par le référentiel."
    if len(text) > len(source):
        uncertainty += " Source tronquée à la taille du contexte : consulter le document complet."
    uncertainty += " Les classifications reposent sur des termes détectés : vérifier négations, contexte et pertinence avant validation."
    confidence = "Preuves textuelles exactes ; confiance limitée aux faits cités. Impacts économiques non établis."
    interpretation = policy.get("interpretation", "Interprétation : données insuffisantes pour établir une incidence métier.")
    output = {field: UNKNOWN for field in business["output_fields"]}
    common = {"summary": quote(summary_ids), "event_type": (policy.get("label", UNKNOWN) + (" — classification à vérifier " + ", ".join(f"[{i}]" for i in event_ids) if event_ids else "")), "recommended_actions": "\n".join("Recommandation : " + config["business_actions"][a] for a in selected["action_ids"]) or "Aucune action proposée par le modèle.", "confidence": confidence, "uncertainties": uncertainty, "validation_status": "Brouillon — revue humaine requise"}
    output.update(common)
    field_evidence = {"summary": summary_ids, "event_type": event_ids}
    if service == "investment":
        output.update(entities=str(row.get("entity") or UNKNOWN) + " — entité indiquée par la notification source", sector=sector, investment_relevance="Revue de l’événement documenté " + (policy.get("label") or "à déterminer") + ". Aucun portefeuille préalable requis.", investment_impact=interpretation, financial_signals=topic("financial"), strategic_signals=topic("strategic"), investment_signal=policy.get("investment_signal", "Preuves insuffisantes") + " — appréciation de règle, non fait confirmé", materiality=policy.get("materiality", "Non déterminée") + " — priorité de revue, non perte estimée")
        field_evidence.update(investment_impact=event_ids, investment_signal=event_ids, materiality=event_ids, financial_signals=[i for i in focus_ids if "financial" in by_id[i]["topics"]], strategic_signals=[i for i in focus_ids if "strategic" in by_id[i]["topics"]])
    else:
        output.update(matched_portfolio_entity=" · ".join(sorted({m["affected_portfolio_entity"] for m in matches})), referential_match_reason="\n".join(m["match_reason"] + (" · " + m["relationship_reason"] if m.get("relationship_reason") else "") for m in matches), portfolio_relevance="Entité ou personne rapprochée du référentiel. " + interpretation, financial_impact=topic("financial") + "\nIncidence économique : non déterminée.", operational_impact=topic("operational"), governance_impact=topic("governance"), legal_regulatory_impact=topic("legal"), monitoring_severity=policy.get("monitoring_severity", "Information") + " — priorité de suivi proposée, à vérifier")
        field_evidence.update(portfolio_relevance=event_ids, monitoring_severity=event_ids)
        for field, tag in (("financial_impact", "financial"), ("operational_impact", "operational"), ("governance_impact", "governance"), ("legal_regulatory_impact", "legal")):
            field_evidence[field] = [i for i in focus_ids if tag in by_id[i]["topics"]]
    used = list(dict.fromkeys(focus_ids + event_ids))
    output["evidence"] = quote(used)
    return {"business_output": output, "business_schema": "grounded_v1", "service": service, "source_kind": row["kind"], "llm_model": engine.OLLAMA_MODEL, "extraction_method": method, "source_excerpt": source[:1200], "source_truncated": len(text)>len(source), "grounding": {"method": "evidence_selection_and_configured_interpretation", "source_hash": sha256(text.encode()).hexdigest(), "evidence": [by_id[i] for i in used], "field_evidence": field_evidence, "reference_matches": reference, "selected_by_model": selected, "policy_snapshot": policy, "prompt_version": business["prompt_version"], "ocr_quality": quality, "limitations": uncertainty}, "summary": output["summary"], "confidence": confidence}
