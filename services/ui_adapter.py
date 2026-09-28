"""Read-only workspace queries and explicit commands for the final UI.

Queries batch registry reads, never call initialize/migrate/reconcile, and cache by
database/WAL signatures. Display IDs and persistence IDs are deliberately distinct.
Existing registries are used only by explicitly requested commands in operations.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime
from functools import lru_cache
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Any

from modules.alert_identity import stable_alert_uid, stable_notification_uid, confirmed_capture_aliases
from modules.service_model import SERVICES, service_key, service_label
from services import normalization as n
from services import lifecycle, pipeline_config, routing, priority as priority_policy

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DATABASES = {
    "legaltech": "legaltech_notifications_v5.sqlite3",
    "workflow": "legaltech_workflow.sqlite3",
    "results": "legaltech_ai_results.sqlite3",
    "business": "legaltech_business_workflow.sqlite3",
    "rules": "legaltech_watch_rules.sqlite3",
    "links": "legaltech_alert_links.sqlite3",
    "registry": "legaltech_registry.sqlite3",
    "cmf": "cmf_compliance_v1.sqlite3",
    "remote": "legaltech_remote_watch.sqlite3",
    "library": "pdf_library.sqlite3",
}
analysis_value = n._analysis_value
date_obj = n._date_obj
flatten_metadata = n._flatten_metadata


def _json(value, default=None):
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or "null") or ({} if default is None else default)
    except (TypeError, ValueError):
        return {} if default is None else default


def _read(database: str, table: str, errors: list | None = None) -> list[dict]:
    """Only identifiers defined by this module are passed here; never UI input."""
    path = DATA_DIR / DATABASES[database]
    if not path.exists():
        return []
    # Immutable reads avoid even sidecar creation for a closed, checkpointed DB.
    # An active WAL must be respected, so use ordinary read-only mode in that case.
    flags = "mode=ro" if Path(str(path) + "-wal").exists() else "mode=ro&immutable=1"
    connection = None
    try:
        connection = sqlite3.connect(path.resolve().as_uri() + "?" + flags, uri=True, timeout=2)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        if not exists:
            return []
        return [dict(row) for row in connection.execute('SELECT * FROM "' + table + '"')]
    except sqlite3.Error as exc:
        if errors is not None:
            errors.append(f"{path.name} / {table} : {exc}")
        return []
    finally:
        if connection is not None:
            connection.close()


def workspace_signature() -> tuple:
    from modules import admin_registry
    signature = [str(DATA_DIR.resolve())]
    for suffix in ("", "-wal"):
        path = Path(str(admin_registry.DATABASE) + suffix)
        signature.append((str(path), path.stat().st_mtime_ns if path.exists() else 0))
    for filename in DATABASES.values():
        for suffix in ("", "-wal"):
            path = DATA_DIR / (filename + suffix)
            try:
                stat = path.stat()
                signature.append((filename + suffix, stat.st_mtime_ns, stat.st_size))
            except OSError:
                signature.append((filename + suffix, 0, 0))
    # Poll document metadata periodically, but do not throw away the whole
    # workspace every 30 seconds when the actual files have not changed.
    signature.append(_document_signature(str(DATA_DIR), int(time.monotonic() // 30)))
    signature.append(pipeline_config.CONFIG_PATH.stat().st_mtime_ns)
    for filename in pipeline_config.load().get("referential_files", []):
        path = Path(filename)
        if not path.is_absolute():
            path = ROOT / path
        signature.append((str(path), path.stat().st_mtime_ns if path.exists() else 0))
    return tuple(signature)


@lru_cache(maxsize=4)
def _document_signature(directory, interval):
    del directory, interval
    values = []
    for item in _pdf_catalog():
        try:
            info = Path(item["path"]).stat()
            values.append((item["path"], info.st_mtime_ns, info.st_size))
        except OSError:
            pass
    return tuple(values)


@lru_cache(maxsize=1024)
def _parsed_fields(text, fields_json):
    from modules.legaltech_detail_parser import parse_detail_text
    return parse_detail_text(text, json.loads(fields_json))


@lru_cache(maxsize=1024)
def _normalized_row(raw_json):
    raw = json.loads(raw_json)
    return dict(source=n._source_short(raw), entity=n._notification_company(raw), title=n._alert_subject(raw), type=n._document_type(raw), date=n._date(raw), summary=n._legaltech_summary(raw))


def invalidate_cache():
    _workspace_cached.cache_clear()


def _existing_pdf(value) -> Path | None:
    if not isinstance(value, (str, Path)) or not str(value).strip():
        return None
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    try:
        return path.resolve() if path.suffix.casefold() == ".pdf" and path.is_file() else None
    except (OSError, ValueError):
        return None


def _source_candidates(obj, depth=0):
    if depth > 7:
        return
    if isinstance(obj, dict):
        for key, value in obj.items():
            normalized = str(key).casefold().replace("-", "_")
            if isinstance(value, str):
                if normalized.endswith("_json"):
                    yield from _source_candidates(_json(value), depth + 1)
                if normalized in {"pdf_path", "download_path", "local_path", "file_path", "path", "document_path", "last_known_path"}:
                    yield "pdf", value
                if normalized in {"url", "href", "article_url", "source_url", "detail_url", "pdf_url", "document_url", "download_url"}:
                    yield "url", value.strip()
            elif isinstance(value, (dict, list, tuple)):
                yield from _source_candidates(value, depth + 1)
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            yield from _source_candidates(value, depth + 1)


def source_links(raw: dict, linked: list[dict] | None = None) -> list[dict]:
    """Return only actual URLs and existing PDFs; never infer a URL from an ID."""
    documents, seen = [], set()
    for kind, value in _source_candidates([raw, *(linked or [])]):
        if kind == "pdf":
            path = _existing_pdf(value)
            if path is None or str(path) in seen:
                continue
            seen.add(str(path))
            documents.append({"kind": "pdf", "path": str(path), "label": path.name, "size": path.stat().st_size})
        elif value.startswith(("https://", "http://")) and value not in seen:
            seen.add(value)
            documents.append({"kind": "url", "url": value, "label": "Document source" if ".pdf" in value.lower() else "Lien source"})
    return documents


def _pdf_catalog():
    from modules.alert_pdf_linker import _norm
    items = []
    folders = [DATA_DIR / x for x in ("pdf_raw", "pdf_archive", "legaltech_pdfs", "pdfs", "pdf", "legaltech_browser_downloads")]
    folders.append(ROOT / "pdfs")
    seen = set()
    for folder in folders:
        if folder.exists():
            for path in folder.rglob("*.pdf"):
                if str(path) not in seen:
                    seen.add(str(path))
                    items.append({"path": str(path.resolve()), "search": _norm(path.name)})
    return items


def _priority(analysis, alert, rules):
    # Compatibility field only; canonical service priority is resolved below.
    return "Moyenne"


def _merge_workflow(states):
    """Read legacy/stable states together without migrating production rows."""
    if not states:
        return {"is_read": False, "ai_status": "pending"}
    latest = dict(max(states, key=lambda x: str(x.get("updated_at") or "")))
    latest["is_read"] = any(bool(s.get("is_read")) for s in states)
    return latest


def treated_state(state, review_status):
    # Compatibility helper; reading and priority are deliberately independent.
    return state.get("ai_status") == "done" and review_status == "validated"


def _status(state, review, analysis):
    ai = str(state.get("ai_status") or "pending")
    if ai == "running":
        return "Analyse en cours"
    if ai == "failed" or n._analysis_failed(analysis):
        return "Échec IA"
    if ai == "done" or analysis:
        return {"validated": "Validée", "correction": "À corriger"}.get(review, "À valider")
    return "Nouveau" if not state.get("is_read") else "À analyser"


def _remote_snapshot(notifications, remote_rows, runs, alerts=()):
    # Reuse the watcher's exact comparison function. Importing it performs no I/O.
    from modules.legaltech_remote_watcher import _pending_comparison, collected_notification_map
    local = collected_notification_map(notifications, alerts)
    pending = []
    latest_check = max((str(item.get("last_detected_at") or "") for item in remote_rows), default="")
    for item in remote_rows:
        if str(item.get("last_detected_at") or "") != latest_check:
            continue
        missing, reason, count, delta = _pending_comparison(item, local.get(item["remote_uid"]))
        if missing:
            pending.append({**item, "pending_reason": reason, "local_result_count": count, "result_delta": delta})
    pending.sort(key=lambda x: str(x.get("last_detected_at") or ""), reverse=True)
    status = dict(max(runs, key=lambda x: int(x.get("id") or 0))) if runs else {"checked_at": "", "remote_count": 0, "status": "NEVER"}
    status["missing_count"] = len(pending)
    return {"status": status, "pending": pending}


@lru_cache(maxsize=4)
def _workspace_cached(signature):
    del signature
    errors = []
    def read(db, table):
        return _read(db, table, errors)
    runs = read("legaltech", "runs")
    notifications = read("legaltech", "notifications")
    notification_map = {x["notification_key"]: x for x in notifications}
    alerts = read("legaltech", "notification_alerts")
    workflow = {x["alert_key"]: x for x in read("workflow", "alert_workflow")}
    records = read("results", "ai_results")
    results, results_by_key = {}, {}
    for record in records:
        record["analysis"] = _json(record.get("result_json"))
        results[record["alert_uid"]] = record
        results_by_key[str(record.get("alert_key") or "")] = record
    routes, tags, assignments, links = defaultdict(list), defaultdict(list), {}, defaultdict(list)
    route_owners = set()
    for item in read("business", "alert_service_routes"):
        route_owners.add(item["alert_uid"])
        key = service_key(item.get("service_id"))
        if item.get("active") and key:
            routes[item["alert_uid"]].append(key)
    for item in read("business", "alert_tags"):
        tags[item["alert_uid"]].append(item["tag"])
    for item in read("business", "alert_assignments"):
        assignments[item["alert_uid"]] = item
    for item in read("links", "alert_documents"):
        links[item["alert_uid"]].append(item)
    registry = read("registry", "documents") + read("registry", "announcements")
    registry_index = defaultdict(list)
    for item in registry:
        for field in ("article_id", "doc_id", "document_id", "alert_key", "source_id", "reference"):
            if item.get(field):
                registry_index[str(item[field])].append(item)
    rules = read("rules", "watch_rules")
    catalog = _pdf_catalog()
    from modules.alert_pdf_linker import _score, _norm
    catalog_by_path = {item["path"]: item for item in catalog}
    registry_documents = []
    for item in registry + read("library", "pdf_activity"):
        docs = source_links(item)
        registry_documents.extend(docs)
        for doc in docs:
            if doc["kind"] == "pdf":
                existing = catalog_by_path.get(doc["path"], {"path": doc["path"], "search": _norm(doc["label"])})
                corpus = " ".join(str(item.get(key) or "") for key in ("filename", "reference", "source_id", "metadata_json"))
                catalog_by_path[doc["path"]] = {**existing, "search": existing["search"] + " " + _norm(corpus)}
    catalog = list(catalog_by_path.values())
    legaltech_rows = []
    grouped_alerts = defaultdict(list)
    protected = set(results) | set(results_by_key) | set(assignments) | set(tags)
    protected.update(r['notification_uid'] for r in read('business', 'business_results'))
    protected.update(r['notification_uid'] for r in read('business', 'business_analysis_attempts'))
    protected.update(r['notification_uid'] for r in read('business', 'business_pipeline_events')
                     if r.get('event_type') != 'notification_registered')
    protected.update(r['alert_uid'] for r in read('business', 'alert_service_routes')
                     if r.get('origin') in {None, 'manual'})
    aliases = confirmed_capture_aliases(alerts, protected)
    for raw in alerts:
        parent = notification_map.get(raw.get("notification_key"), {})
        for key in ("company_or_query", "notification_date", "announced_result_count", "panel_total"):
            raw[key] = parent.get(key, raw.get(key))
        raw["notification_raw_text"] = parent.get("raw_text", "")
        raw["source_fields"] = _json(raw.get("source_fields_json"))
        if not isinstance(raw["source_fields"], dict):
            raw["source_fields"] = {"collected_metadata": raw["source_fields"]}
        if raw.get("detail_text"):
            raw["source_fields"] = deepcopy(_parsed_fields(raw["detail_text"], json.dumps(raw["source_fields"], ensure_ascii=False, sort_keys=True)))
        capture_uid = stable_alert_uid(raw)
        grouped_alerts[aliases.get(capture_uid, capture_uid)].append(raw)
    # Repeated captures share the backend's stable identity. Consolidate the
    # display only; preserve every source variant and legacy persistence key.
    for uid, variants in grouped_alerts.items():
        variants.sort(key=lambda a: (stable_alert_uid(a) == uid, str(a.get("last_seen_at") or ""), len(str(a.get("detail_text") or ""))), reverse=True)
        raw = dict(variants[0])
        for variant in variants[1:]:
            for field, value in variant.items():
                if not raw.get(field) and value:
                    raw[field] = value
        raw["source_variants"] = variants
        legacy_keys = list(dict.fromkeys(str(v.get("alert_key") or "") for v in variants))
        capture_aliases = list(dict.fromkeys(stable_alert_uid(v) for v in variants if stable_alert_uid(v) != uid))
        legacy_keys.extend(k for k in capture_aliases if k not in legacy_keys)
        key = str(raw.get("alert_key") or "")
        raw["stable_alert_uid"] = uid
        record = results.get(uid) or max((results_by_key[k] for k in legacy_keys if k in results_by_key), key=lambda r: str(r.get("updated_at") or ""), default={})
        analysis = record.get("analysis") or None
        state = _merge_workflow([workflow[k] for k in dict.fromkeys([uid, *legacy_keys]) if k in workflow])
        # Reflect persisted successful/failed results without per-row reconcile writes.
        if analysis and state.get("ai_status") != "running":
            state["ai_status"] = "failed" if n._analysis_failed(analysis) else "done"
        linked = links.get(uid, [])[:]
        for alias in capture_aliases:
            linked.extend(links.get(alias, []))
        for field in ("article_id", "doc_id", "alert_key", "reference"):
            linked.extend(registry_index.get(str(raw.get(field) or ""), []))
        documents = source_links(raw, linked)
        if not any(d["kind"] == "pdf" for d in documents):
            match = max(catalog, key=lambda item: _score(raw, item), default=None)
            if match and _score(raw, match) >= 60:
                documents.extend(source_links({"pdf_path": match["path"]}))
        services = list(dict.fromkeys(routes.get(uid, []))) if uid in route_owners else list(dict.fromkeys(s for k in legacy_keys for s in routes.get(k, [])))
        services = list(dict.fromkeys(services + [s for alias in capture_aliases for s in routes.get(alias, [])]))
        if uid not in route_owners and not any(k in route_owners for k in legacy_keys):
            for value in (raw.get("service"), raw.get("service_key"), raw["source_fields"].get("service")):
                sk = service_key(value)
                if sk and sk not in services:
                    services.append(sk)
        review = str(record.get("review_status") or "pending")
        treated = treated_state(state, review)
        normalized = _normalized_row(json.dumps({k: v for k, v in raw.items() if k != "source_variants"}, ensure_ascii=False, sort_keys=True))
        legaltech_rows.append({
            "uid": "legaltech:" + uid, "stable_uid": uid, "source_key": key,
            "legacy_keys": legacy_keys,
            "capture_aliases": capture_aliases,
            "kind": "legaltech", "raw": raw, **normalized,
            "priority": _priority(analysis, raw, rules), "read": bool(state.get("is_read")),
            "treated": treated, "status": "Traité" if treated else _status(state, review, analysis),
            "services": services,
            "analysis": analysis, "record": record, "review_status": review,
            "ai_state": state.get("ai_status", "pending"), "metadata": raw["source_fields"],
            "documents": documents, "pdf_path": next((d["path"] for d in documents if d["kind"] == "pdf"), ""),
            "source_url": next((d["url"] for d in documents if d["kind"] == "url"), ""),
            "tags": list(dict.fromkeys(tags.get(uid, []) + [t for k in legacy_keys for t in tags.get(k, [])])),
            "assignment": assignments.get(uid) or next((assignments[k] for k in legacy_keys if k in assignments), {}),
        })
    cmf_rows = []
    cmf_items = sorted(read("cmf", "cmf_items"), key=lambda x: (str(x.get("published_at") or ""), str(x.get("first_seen_at") or "")), reverse=True)
    for raw in [x for x in cmf_items if x.get("source_mode") != "demo"]:
        uid = str(raw.get("uid") or "")
        if not uid:
            continue
        documents = source_links(raw)
        cmf_rows.append({
            "uid": "cmf:" + uid, "stable_uid": uid, "source_key": uid, "kind": "cmf", "raw": raw,
            "source": "CMF", "entity": "CMF", "title": n._clean(raw.get("title"), 180),
            "type": "Avis / Communiqué CMF" if raw.get("section") == "avis" else "Bulletin officiel CMF",
            "date": str(raw.get("published_at") or ""), "priority": raw.get("priority") or "À classer",
            "read": bool(raw.get("is_read")), "treated": False,
            "status": "Nouveau" if raw.get("is_new") and not raw.get("is_read") else "À analyser",
            "services": ["compliance"], "summary": n._clean(raw.get("raw_excerpt"), 700),
            "analysis": None, "record": {}, "review_status": "", "ai_state": "pending",
            "metadata": raw, "documents": documents, "tags": [], "assignment": {},
            "pdf_path": next((d["path"] for d in documents if d["kind"] == "pdf"), ""),
            "source_url": next((d["url"] for d in documents if d["kind"] == "url"), ""),
        })
    rows = legaltech_rows + cmf_rows
    from services.composite_documents import child_row, is_parent
    documents={r['parent_source_id']:_json(r['metadata_json']) for r in read('business','composite_documents')}
    parents={r['uid']:r for r in rows}
    for record in read('business','composite_publications'):
        child=_json(record['metadata_json']);parent=parents.get(child['parent_source_id'])
        if parent and documents.get(parent['uid'],{}).get('document_hash')==child['document_hash']:
            rows.append(child_row(parent,child))
    config = pipeline_config.load()
    business_results = read("business", "business_results")
    for result in business_results:
        result["analysis"] = _json(result["result_json"])
    result_map = {(r["notification_uid"], r["service_id"]): r for r in business_results}
    attempts = sorted(read("business", "business_analysis_attempts"), key=lambda r: r["started_at"])
    attempt_map = {(r["notification_uid"], r["service_id"]): r for r in attempts}
    watchlists = read("business", "watchlists")
    watchlist_items = read("business", "watchlist_items")
    entities, reference_errors = routing.referential(config, watchlists, watchlist_items)
    from modules import admin_registry
    entities.extend(admin_registry.entities())
    errors.extend(reference_errors)
    route_records = read("business", "alert_service_routes")
    manual_owners = {r["alert_uid"] for r in route_records if r.get("origin") in {None, "manual"}}
    pipeline_events = read("business", "business_pipeline_events")
    evaluated_uids = {e['notification_uid'] for e in pipeline_events if e.get('event_type') in {'routing_evaluated', 'routing_inferred', 'service_assignment'}}
    manual_selections = {e["notification_uid"]: _json(e["details_json"]).get("services", []) for e in sorted(pipeline_events, key=lambda e: e["id"]) if e["event_type"] == "service_assignment"}
    for row in rows:
        row["priority"] = lifecycle.priority(row["priority"])
        row["eligible_services"] = pipeline_config.eligible(row["kind"], config)
        row["matches"] = routing.match(row, entities)
        row["identification"] = routing.identify(row, config)
        row["portfolio_confirmed"] = bool(routing.portfolio_matches(row["matches"]))
        row["referential_status"] = "Correspondance portefeuille confirmée" if row["portfolio_confirmed"] else "Aucune correspondance confirmée" if entities else "Référentiel UGFS non renseigné / Aucune correspondance confirmée"
        suggested, reasons = routing.suggest(row, row["matches"], config)
        row["routing_reasons"] = reasons
        row["rule_matches"] = list(reasons)
        from modules.watch_rules import _matches
        for rule in rules:
            action=_json(rule.get('actions_json'))
            if rule.get('enabled') and action.get('priority') and _matches(row['raw'],_json(rule.get('conditions_json')),row.get('analysis')):
                row['rule_matches'].append({'rule':rule.get('name','Règle de veille'),'priority':action['priority'],'services':action.get('services') or row['services']})
        row["routing_suggestions"] = suggested
        row["manual_routing"] = row["stable_uid"] in manual_owners or row["uid"] in manual_owners
        if row["uid"] in manual_selections:
            row["manual_routing"] = True
            row["services"] = manual_selections[row["uid"]]
            row["routing_reasons"] = [{"origin": "MANUAL", "rule": "Affectation corrigée manuellement — prioritaire sur les règles", "services": row["services"]}]
        if not row["manual_routing"]:
            row["services"] = list(dict.fromkeys([s for s in row["services"] if s not in {"investment", "portfolio"}] + suggested))
            priorities = [r.get("priority") for r in reasons if r.get("priority") in lifecycle.PRIORITIES]
            if priorities:
                row["priority"] = min(priorities, key=lifecycle.PRIORITIES.index)
        row["services"] = [s for s in row["services"] if s in row["eligible_services"]]
        triage = config.get("sources", {}).get(row["kind"], {}).get("triage_service")
        if not row["services"] and triage in row["eligible_services"] and triage != "portfolio":
            row["services"] = [triage]
            row["routing_reasons"] = list(row.get("routing_reasons") or []) + [{"origin":"TRIAGE", "rule":"Triage initial — pertinence à confirmer", "services":[triage], "priority":"Moyenne"}]
        row["triage_services"] = list(dict.fromkeys(s for reason in row["routing_reasons"] if reason.get("origin") == "TRIAGE" for s in reason.get("services", []) if s in row["services"]))
        if row["kind"] == "cmf":
            row["services"] = ["compliance"]
            row["assignment"] = assignments.get(row["uid"], {})
        row['routing_status'] = (
            'Triage initial — pertinence métier à confirmer' if row['triage_services'] else
            'Affectation manuelle enregistrée' if row['manual_routing'] else
            'Routage évalué et enregistré' if row['uid'] in evaluated_uids and row['services'] else
            'Routage évalué — aucune correspondance enregistrée' if row['uid'] in evaluated_uids else
            'Règles vérifiées à l’affichage — décision de routage non enregistrée')
        row["legacy_result"] = row.get("record") if row.get("analysis") else None
        row["business_results"] = {s: result_map.get((row["uid"], s)) for s in row["services"]}
        row["analysis_attempts"] = {s: attempt_map.get((row["uid"], s)) for s in row["services"]}
        row["service_states"] = {s: lifecycle.processing(row["business_results"][s], row["analysis_attempts"][s]) for s in row["services"]}
        assigned_results = list(row["business_results"].values())
        row["treated"] = lifecycle.treated(assigned_results) if row["services"] else lifecycle.result_validated(row["legacy_result"])
        present = [r for r in assigned_results if r]
        if present:
            row["analysis"] = present[0]["analysis"]
        row["ai_state"] = "running" if any((a or {}).get("status") == "running" for a in row["analysis_attempts"].values()) else "failed" if any((a or {}).get("status") == "failed" for a in row["analysis_attempts"].values()) else "done" if present else row["ai_state"]
        states = list(row["service_states"].values())
        row["status"] = "Traité" if row["treated"] else next((s for s in ("Erreur d’analyse", "À valider", "Analyse terminée", "À analyser", "Nouveau") if s in states), lifecycle.processing(row["legacy_result"], is_new=True))
        row["status"] = lifecycle.aggregate(row["service_states"]) if row["services"] else row["status"]
        row["priority_overrides"] = {e["service_id"]: _json(e["details_json"]).get("value") for e in sorted(pipeline_events,key=lambda e:e["id"]) if e["notification_uid"]==row["uid"] and e["event_type"]=="priority_override"}
        priority_policy.apply(row, config)
        row["has_business_analysis"] = bool(present)
        if is_parent(row):
            row['document_status']='Publications détectées' if row['uid'] in documents else 'Segmentation requise'
            row['status']=row['document_status'];row['treated']=False;row['ai_state']='pending'
            row['analysis']=None;row['business_results']={};row['legacy_result']=None
            row['service_states']={s:row['document_status'] for s in row['services']}
            row['has_business_analysis']=False
    child_rows=[r for r in rows if r.get('child_id')]
    rows=[r for r in rows if not r.get('child_id')]
    rows.sort(key=lambda r: date_obj(r["date"]) or date.min, reverse=True)
    latest_run = max(runs, key=lambda x: str(x.get("started_at") or ""), default=None)
    return {
        "run": latest_run, "legaltech_runs": runs, "notifications": notifications, "alerts": alerts, "rows": rows,
        "child_rows":child_rows,
        "results": sorted(records, key=lambda x: str(x.get("updated_at") or ""), reverse=True),
        "sources": source_overview(config, latest_run, read("cmf", "cmf_sync_runs"), read("remote", "watcher_runs")), "rules": rules,
        "watchlists": watchlists, "watchlist_items": watchlist_items,
        "pipeline_config": config, "business_results": business_results, "pipeline_events": pipeline_events, "referential_entities": entities,
        "assignments": list(assignments.values()), "notes": read("business", "alert_notes"),
        "digest_settings": read("business", "service_digest_settings"), "digest_queue": read("business", "digest_queue"),
        "cmf_runs": read("cmf", "cmf_sync_runs"), "catalog": catalog, "registry_documents": registry_documents,
        "history": read("workflow", "workflow_events"), "errors": errors,
        "admin_events":admin_registry.read('admin_events'),
        "central_records":read('business','central_notifications'),
        "remote": _remote_snapshot(notifications, read("remote", "remote_notifications"), read("remote", "watcher_runs"), alerts),
    }


def load_workspace():
    return deepcopy(_workspace_cached(workspace_signature()))


def bulletin_publications(parent_id):
    from services.composite_documents import snapshot, children
    document=snapshot(parent_id)
    return document, children(parent_id)


def source_overview(config, legaltech_run, cmf_runs, watcher_runs=()):
    sources = []
    for key, source in config["sources"].items():
        run = max(cmf_runs, key=lambda r: r.get("id", 0), default={}) if key == "cmf" else (legaltech_run or {}) if key == "legaltech" else {}
        status = "À configurer" if not source.get("implemented") else "Inactive" if not source.get("active") else "Collecte enregistrée" if run else "Non connecté"
        watcher = max(watcher_runs, key=lambda r: r.get("id", 0), default={})
        if key == "legaltech" and watcher.get("status") == "ERROR":
            status = "Non connecté / dernier contrôle en erreur"
        if key == "cmf" and run:
            status = "Collecte incomplète" if _json(run.get("errors_json"), []) else "Connecté lors de la dernière collecte"
        sources.append({"key": key, "label": source["label"], "type": source["type"], "active": source["active"], "status": status, "last_check_at": run.get("finished_at") or run.get("started_at") or "Jamais", "eligible_services": source["eligible_services"], "note": "Session à vérifier lors de la prochaine collecte." if key == "legaltech" else "Conformité uniquement." if key == "cmf" else "Collecteur non implémenté."})
    return sources


def load_legaltech_rows():
    return [r for r in load_workspace()["rows"] if r["kind"] == "legaltech"]


def load_cmf_rows():
    return [r for r in load_workspace()["rows"] if r["kind"] == "cmf"]


def remote_bell_status(workspace=None):
    return (workspace or load_workspace())["remote"]


def workflow_history(row, workspace=None):
    workspace = workspace or load_workspace()
    business_events = [e for e in workspace.get("pipeline_events", []) if e.get("notification_uid") == row["uid"]]
    if row["kind"] == "cmf":
        return sorted(business_events + [{"event_at": row["raw"].get(key), "event_type": label} for key, label in (("first_seen_at", "Première détection"), ("last_seen_at", "Dernière détection"), ("updated_at", "Mise à jour")) if row["raw"].get(key)], key=lambda e: e.get("event_at") or "", reverse=True)
    keys = {row["stable_uid"], row["source_key"], *row.get("legacy_keys", [])}
    return sorted(business_events + [e for e in workspace["history"] if e.get("alert_key") in keys], key=lambda e: str(e.get("event_at") or ""), reverse=True)[:50]


def selected_result_rows(workspace):
    """Include saved results whose original notification is no longer in a run."""
    rows = [r for r in workspace["rows"] if r.get("analysis")]
    seen = {r["stable_uid"] for r in rows}
    for record in workspace["results"]:
        if record["alert_uid"] not in seen:
            rows.append({"uid": "legaltech:" + record["alert_uid"], "stable_uid": record["alert_uid"], "source_key": record.get("alert_key", ""), "kind": "legaltech", "raw": {"alert_key": record.get("alert_key", ""), "stable_alert_uid": record["alert_uid"]}, "entity": record.get("company", ""), "title": record.get("subject", ""), "source": record.get("source", ""), "date": record.get("alert_date", ""), "type": "Résultat enregistré", "analysis": record["analysis"], "record": record, "review_status": record.get("review_status"), "status": lifecycle.processing(record), "services": [], "priority": "Moyenne", "read": True, "treated": record.get("review_status") == "validated", "metadata": {}, "documents": [], "summary": analysis_value(record["analysis"], "Résumé_IA", "resume", default=""), "tags": [], "assignment": {}, "pdf_path": "", "source_url": "", "ai_state": "done"})
    return rows


def command(name, *args, **kwargs):
    """Explicit action gateway; never called by a workspace query."""
    from services import operations
    allowed = {"mark_read", "set_review", "save_assignment", "run_analysis", "export_excel", "sync_legaltech", "check_remote", "sync_pdfs", "sync_cmf", "fetch_cmf_excerpt", "save_digest", "queue_digest", "send_digest", "save_note", "create_watchlist", "add_watchlist_item", "create_rule", "toggle_rule", "save_pipeline_config", "register_workspace", "suggest_routing"}
    allowed.update({"set_priority", "import_reference", "save_admin_config", "admin_rule", "activate_prompt", "segment_bulletin", "select_publication"})
    if name not in allowed:
        raise ValueError("Unknown workspace command")
    try:
        return getattr(operations, name)(*args, **kwargs)
    finally:
        invalidate_cache()


def mark_read(row, is_read=True):
    return command("mark_read", row, is_read)


def assign_services(row, services, **assignment):
    return command("save_assignment", row, services, **assignment)


def run_analysis(row, services=None):
    return command("run_analysis", row, services)


def export_excel(row, service=None):
    return command("export_excel", row, service)


def sync_legaltech(alerts):
    return command("sync_legaltech", alerts)


def check_remote():
    return command("check_remote")


def sync_pdfs():
    return command("sync_pdfs")


def sync_cmf(max_pages=1):
    return command("sync_cmf", max_pages)


def set_review_status(row, status, service=None, **kwargs):
    return command("set_review", row, status, service, **kwargs)


def start_action(label, resource, name, *args, **kwargs):
    from services.jobs import start
    return start(label, resource, command, name, *args, **kwargs)


def action_status(token):
    from services.jobs import status
    return status(token)


def active_actions():
    from services.jobs import active
    return active()


def model_configuration():
    from config import OLLAMA_MODEL, OLLAMA_URL
    return {"model": OLLAMA_MODEL, "endpoint": OLLAMA_URL}


def pdf_preview(path, page=1):
    from modules.pdf_preview import page_preview
    return page_preview(path, page)


def business_view(row, service):
    view = lifecycle.scoped(row, service)
    record = row.get("business_results", {}).get(service) if service != "legacy" else row.get("legacy_result")
    view["analysis"] = record.get("analysis") if record else None
    view["record"] = record or {}
    view["review_status"] = record.get("review_status") if record else ""
    view["treated"] = lifecycle.result_validated(record)
    return view


def digest_preview(service, rows):
    from services.operations import build_digest
    return build_digest(service, rows)


def smtp_status():
    from modules.email_digest_service import smtp_status as status
    return status()

# Administration stays behind the same service adapter as the notification UI.
def administration_view(workspace):
    from services.administration import overview
    return overview(workspace)


def reference_preview(filename, payload, domain):
    from services.reference_import import preview
    return preview(filename,payload,domain)


def reference_template(domain):
    from services.reference_import import template
    return template(domain)


def administration_runtime():
    from services.administration import runtime_status
    from modules import admin_registry
    value = runtime_status()
    paths = [DATA_DIR / filename for filename in DATABASES.values()] + [admin_registry.DATABASE]
    databases = []
    for path in paths:
        status = 'Non initialisée'
        if path.exists():
            connection = None
            try:
                flags = 'mode=ro' if Path(str(path)+'-wal').exists() else 'mode=ro&immutable=1'
                connection = sqlite3.connect(path.resolve().as_uri()+'?'+flags, uri=True, timeout=2)
                connection.execute('SELECT name FROM sqlite_master LIMIT 1').fetchall()
                status = 'Accessible en lecture seule'
            except sqlite3.Error:
                status = 'Erreur de lecture'
            finally:
                if connection is not None: connection.close()
        databases.append({'Base':path.name,'État':status})
    value['databases'] = databases
    return value


def prompt_versions(service):
    from services.administration import prompt_history
    return prompt_history(service)


def business_event_types(config):
    return pipeline_config.available_events(config)


def active_business_contract(service):
    from services.intelligence import result_schema, PIPELINE_VERSION
    return {"pipeline_version":PIPELINE_VERSION,"schema":result_schema(service)}


def service_view(row, service=None):
    return lifecycle.scoped(row, service)


def result_presentation(analysis):
    from services.result_presentation import output_view, selection_message, RECOMMENDATIONS
    output=output_view(analysis)
    return {'output':output,'recommendation':output.get(RECOMMENDATIONS.get(analysis.get('service'),'recommended_actions'),'Non déterminé'),'selection_message':selection_message(analysis)}
