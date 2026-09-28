"""Business eligibility/prompts/rules; the referential is enrichment, not a source."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
from modules.service_model import SERVICES

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "business_pipeline.json"


def load():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def validate(config):
    if not {"cmf", "legaltech"}.issubset(config.get("sources", {})):
        raise ValueError("LegalTech et CMF doivent rester configurés.")
    if not isinstance(config.get("routing_rules", []), list):
        raise ValueError("Les règles de routage doivent former une liste JSON.")
    if set(config.get("services", {})) != set(SERVICES):
        raise ValueError("Les quatre services UGFS doivent rester configurés.")
    if "referential" in config.get("sources", {}) or "ugfs" in config.get("sources", {}):
        raise ValueError("Le référentiel UGFS est une couche de rapprochement, pas une source externe.")
    for name, source in config.get("sources", {}).items():
        if source.get("implemented") and name not in {"legaltech", "cmf"}:
            raise ValueError("Aucun collecteur réel n’est implémenté pour cette source.")
        if set(source.get("eligible_services", [])) - SERVICES.keys():
            raise ValueError(f"Service inconnu pour {name}.")
        triage = source.get("triage_service")
        if triage and (triage not in source.get("eligible_services", []) or triage == "portfolio"):
            raise ValueError("Le service de triage doit être éligible et ne peut présumer une participation UGFS.")
        if name == "cmf" and source.get("eligible_services") != ["compliance"]:
            raise ValueError("CMF doit rester exclusivement éligible à la Conformité.")
        if not source.get("implemented") and source.get("active"):
            raise ValueError(f"Le collecteur {name} n’est pas connecté.")
    for rule in config.get("routing_rules", []):
        if not isinstance(rule, dict):
            raise ValueError("Chaque règle doit être un objet JSON.")
        if not rule.get("id") or not str(rule.get("name", "")).strip():
            raise ValueError("Identifiant et nom de règle requis.")
        if rule.get("priority") and rule["priority"] not in {"Critique", "Haute", "Moyenne", "Basse"}:
            raise ValueError("Priorité de règle inconnue.")
        if not isinstance(rule, dict):
            raise ValueError("Chaque règle doit être un objet JSON.")
        if rule.get("source") and rule["source"] not in config["sources"]:
            raise ValueError("Une règle référence une source inconnue.")
        if set(rule.get("services", [])) - SERVICES.keys():
            raise ValueError("Une règle contient un service inconnu.")
        if rule.get("source") == "cmf" and set(rule.get("services", [])) - {"compliance"}:
            raise ValueError("Une règle CMF ne peut cibler que la Conformité.")
        if rule.get("source") and set(rule.get("services", [])) - set(config["sources"][rule["source"]]["eligible_services"]):
            raise ValueError("Une règle cible un service non éligible pour sa source.")
    for service in config["services"].values():
        if not service.get("prompt", "").strip() or not service.get("output_fields"):
            raise ValueError("Chaque service doit disposer d’un prompt et d’un schéma de sortie.")
        if service.get("grounded"):
            from jsonschema import Draft202012Validator
            schema = service.get("output_schema", {})
            Draft202012Validator.check_schema(schema)
            expected = {"summary_evidence", "focus_evidence", "action_ids"}
            if set(schema.get("properties", {})) != expected or set(schema.get("required", [])) != expected or schema.get("additionalProperties") is not False:
                raise ValueError("Le schéma métier doit conserver les trois sélecteurs de preuves/actions, sans champ libre.")
            for field in expected:
                if schema["properties"][field].get("type") != "array" or schema["properties"][field].get("items", {}).get("type") != "string":
                    raise ValueError("Chaque sélecteur doit être une liste d’identifiants de preuve/action.")
    for code, event in config.get("event_types", {}).items():
        if not event.get("keywords") or not event.get("label") or not event.get("interpretation"):
            raise ValueError(f"Événement {code} : libellé, déclencheurs et interprétation explicite requis.")
        if set(event.get("actions", [])) - set(config.get("business_actions", {})):
            raise ValueError(f"Événement {code} : action métier inconnue.")
    for rule in config.get("routing_rules", []):
        if set(rule.get("event_types", [])) - set(available_events(config)):
            raise ValueError("Une règle référence un type d’événement inconnu.")
    ids = [r["id"] for r in config.get("routing_rules", [])]
    if len(ids) != len(set(ids)):
        raise ValueError("Identifiants de règles dupliqués.")
    policy = config.get("cmf_relevance", {})
    for field in ("categories", "topics", "keywords", "exclusions"):
        if not isinstance(policy.get(field, []), list) or any(not isinstance(v, str) for v in policy.get(field, [])):
            raise ValueError("Les critères CMF doivent être des listes de textes.")
    if policy.get("configured") and not any(policy.get(k) for k in ("categories", "topics", "keywords", "require_reference")):
        raise ValueError("Au moins un critère positif CMF est nécessaire.")
    return config


def save(config, *, reason="configuration_update", expected_hash=None):
    from modules import admin_registry
    value = validate(deepcopy(config))
    old = load()
    for key, service in value["services"].items():
        before = old["services"][key]
        changed = any(before.get(field) != service.get(field) for field in ("prompt", "output_fields", "output_schema", "activated_from")) or (service.get("grounded") and any(old.get(field) != value.get(field) for field in ("event_types", "business_actions")))
        service["prompt_version"] = int(before.get("prompt_version", 1)) + int(bool(changed))
        if changed:
            service["updated_at"] = admin_registry.now()
    # Atomic config replacement; the previous version is preserved for recovery.
    archive = ROOT / "backups" / "pipeline_configuration"
    archive.mkdir(parents=True, exist_ok=True)
    from datetime import datetime
    backup = archive / (datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".json")
    backup.write_text(json.dumps(old, ensure_ascii=False, indent=2), encoding="utf-8")
    fd, path = tempfile.mkstemp(prefix="pipeline_", suffix=".json", dir=CONFIG_PATH.parent)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
    replaced = False
    try:
        with admin_registry.transaction() as con:
            if expected_hash is not None:
                from services.administration import fingerprint
                if fingerprint(load()) != expected_hash:
                    raise ValueError("Configuration modifiée ; rechargez avant d’enregistrer.")
            # Preserve both sides; historical analysis provenance is never rewritten.
            for snapshot, label in ((old, "before"), (value, reason)):
                con.execute("INSERT INTO configuration_versions(snapshot_json,recorded_at,reason) VALUES(?,?,?)", (json.dumps(snapshot, ensure_ascii=False), admin_registry.now(), label))
            admin_registry.event(con, reason, {"sources_changed": old["sources"] != value["sources"], "rules_changed": old["routing_rules"] != value["routing_rules"], "prompts_changed": [s for s in value["services"] if old["services"][s] != value["services"][s]]})
            os.replace(path, CONFIG_PATH)
            replaced = True
    except BaseException:
        if replaced:
            CONFIG_PATH.write_text(json.dumps(old, ensure_ascii=False, indent=2), encoding="utf-8")
        raise
    return "Configuration enregistrée ; la version précédente est conservée."


def eligible(source, config=None):
    value = (config or load())["sources"].get(source, {})
    return list(value.get("eligible_services", []))


def require_source(source):
    value = load()["sources"].get(source, {})
    if not value.get("implemented"):
        raise ValueError("Cette source n’a pas de collecteur connecté.")
    if not value.get("active"):
        raise ValueError("Cette source est désactivée dans Organisation & Paramétrage.")


def available_events(config):
    from services.event_taxonomy import TAXONOMY
    return {**config.get("event_types", {}), **{key:{"label":value[0]} for key,value in TAXONOMY.items()}}
