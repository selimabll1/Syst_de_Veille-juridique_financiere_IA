"""Additive central notification/result history in the existing business registry.

No source database is replaced, copied per service, reset or migrated. Tables
are created only on an explicit command. The adapter performs read-only queries.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid

DATABASE = Path(__file__).resolve().parents[1] / "data" / "legaltech_business_workflow.sqlite3"


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def transaction():
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DATABASE, timeout=15)
    con.row_factory = sqlite3.Row
    try:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS central_notifications(
            notification_uid TEXT PRIMARY KEY, source_kind TEXT NOT NULL,
            source_key TEXT NOT NULL, title TEXT NOT NULL, entity TEXT,
            source_date TEXT, metadata_json TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS business_results(
            notification_uid TEXT NOT NULL, service_id TEXT NOT NULL, need_id TEXT NOT NULL,
            result_json TEXT NOT NULL, model TEXT NOT NULL, prompt_version INTEGER NOT NULL,
            source_hash TEXT NOT NULL, review_status TEXT NOT NULL, revision INTEGER NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, validated_at TEXT,
            PRIMARY KEY(notification_uid,service_id,need_id));
        CREATE TABLE IF NOT EXISTS business_result_versions(
            id INTEGER PRIMARY KEY AUTOINCREMENT, notification_uid TEXT NOT NULL,
            service_id TEXT NOT NULL, need_id TEXT NOT NULL, revision INTEGER NOT NULL,
            snapshot_json TEXT NOT NULL, recorded_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS business_analysis_attempts(
            id TEXT PRIMARY KEY, notification_uid TEXT NOT NULL, service_id TEXT NOT NULL,
            need_id TEXT NOT NULL, status TEXT NOT NULL, error TEXT,
            started_at TEXT NOT NULL, finished_at TEXT);
        CREATE TABLE IF NOT EXISTS business_pipeline_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT, notification_uid TEXT NOT NULL,
            service_id TEXT, event_type TEXT NOT NULL, details_json TEXT NOT NULL,
            event_at TEXT NOT NULL);
        """)
        with con:
            yield con
    finally:
        con.close()


def _event(con, uid, service, kind, details):
    con.execute("INSERT INTO business_pipeline_events(notification_uid,service_id,event_type,details_json,event_at) VALUES(?,?,?,?,?)", (uid, service, kind, json.dumps(details, ensure_ascii=False), now()))


def _register(con, row):
    con.execute("""INSERT INTO central_notifications VALUES(?,?,?,?,?,?,?,?)
        ON CONFLICT(notification_uid) DO UPDATE SET title=excluded.title,entity=excluded.entity,
        source_date=excluded.source_date,metadata_json=excluded.metadata_json,updated_at=excluded.updated_at""",
        (row["uid"], row["kind"], row["stable_uid"], row["title"], row["entity"], row["date"], json.dumps({"legacy_keys": row.get("legacy_keys", []), "matches": row.get("matches", []), "identification": row.get("identification", {}), "routing_reasons": row.get("routing_reasons", [])}, ensure_ascii=False), now()))


def register_notifications(rows):
    with transaction() as con:
        for row in rows:
            exists = con.execute("SELECT 1 FROM central_notifications WHERE notification_uid=?", (row["uid"],)).fetchone()
            _register(con, row)
            if not exists:
                _event(con, row["uid"], None, "notification_registered", {"source": row["kind"]})


def event(row, service, kind, details):
    with transaction() as con:
        _register(con, row)
        _event(con, row["uid"], service, kind, details)


def start_attempt(row, service, need="primary"):
    token = uuid.uuid4().hex
    with transaction() as con:
        _register(con, row)
        con.execute("INSERT INTO business_analysis_attempts VALUES(?,?,?,?,?,'',?,NULL)", (token, row["uid"], service, need, "running", now()))
        _event(con, row["uid"], service, "analysis_started", {"attempt": token, "need": need})
    return token


def fail_attempt(token, message):
    with transaction() as con:
        attempt = con.execute("SELECT * FROM business_analysis_attempts WHERE id=?", (token,)).fetchone()
        if attempt:
            con.execute("UPDATE business_analysis_attempts SET status='failed',error=?,finished_at=? WHERE id=?", (str(message), now(), token))
            _event(con, attempt["notification_uid"], attempt["service_id"], "analysis_failed", {"error": str(message)})


def _preserve_version(con, current):
    if current:
        con.execute("INSERT INTO business_result_versions(notification_uid,service_id,need_id,revision,snapshot_json,recorded_at) VALUES(?,?,?,?,?,?)", (current["notification_uid"], current["service_id"], current["need_id"], current["revision"], json.dumps(dict(current), ensure_ascii=False), now()))


def save_result(row, service, analysis, *, model, prompt_version, source_hash, attempt, need="primary"):
    with transaction() as con:
        _register(con, row)
        current = con.execute("SELECT * FROM business_results WHERE notification_uid=? AND service_id=? AND need_id=?", (row["uid"], service, need)).fetchone()
        _preserve_version(con, current)
        revision = int(current["revision"]) + 1 if current else 1
        con.execute("""INSERT INTO business_results VALUES(?,?,?,?,?,?,?,'draft',?,?,?,NULL)
            ON CONFLICT(notification_uid,service_id,need_id) DO UPDATE SET
            result_json=excluded.result_json,model=excluded.model,prompt_version=excluded.prompt_version,
            source_hash=excluded.source_hash,review_status='draft',revision=excluded.revision,
            updated_at=excluded.updated_at,validated_at=NULL""",
            (row["uid"], service, need, json.dumps(analysis, ensure_ascii=False), model, prompt_version, source_hash, revision, now(), now()))
        con.execute("UPDATE business_analysis_attempts SET status='succeeded',finished_at=? WHERE id=?", (now(), attempt))
        _event(con, row["uid"], service, "analysis_completed", {"revision": revision, "model": model, "need": need})


def review(row, service, status, *, corrected=None, note="", need="primary", expected_revision=None):
    if status not in {"pending", "correction", "validated"}:
        raise ValueError("État de validation non reconnu.")
    with transaction() as con:
        current = con.execute("SELECT * FROM business_results WHERE notification_uid=? AND service_id=? AND need_id=?", (row["uid"], service, need)).fetchone()
        if not current:
            raise ValueError("Aucun résultat persistant pour ce service.")
        if expected_revision is not None and current["revision"] != expected_revision:
            raise ValueError("Ce résultat a changé. Actualisez la page avant de le valider ou de le corriger.")
        _preserve_version(con, current)
        analysis = json.loads(current["result_json"])
        if corrected is not None:
            if set(corrected) != set(analysis.get("business_output", {})) or any(not isinstance(v, str) or not v.strip() for v in corrected.values()):
                raise ValueError("La correction doit conserver tous les champs métier renseignés.")
            if analysis.get("business_schema") in {"grounded_v1", "intelligence_v6"}:
                if not note.strip():
                    raise ValueError("Indiquez le motif et la preuve de votre correction métier.")
                changes = {key: {"before": analysis["business_output"][key], "after": value} for key, value in corrected.items() if value != analysis["business_output"][key]}
                analysis["grounding"].setdefault("human_changes", []).append({"changes": changes, "note": note, "at": now()})
                for key in changes:
                    analysis["grounding"]["field_evidence"].pop(key, None)
            analysis["business_output"] = corrected
        if analysis.get("business_schema") in {"grounded_v1", "intelligence_v6"}:
            analysis["business_output"]["validation_status"] = {"pending":"À valider", "correction":"À corriger", "validated":"Validé humainement"}[status]
            analysis["summary"] = analysis["business_output"]["summary"]
        con.execute("UPDATE business_results SET result_json=?,review_status=?,revision=revision+1,updated_at=?,validated_at=? WHERE notification_uid=? AND service_id=? AND need_id=?", (json.dumps(analysis, ensure_ascii=False), status, now(), now() if status == "validated" else None, row["uid"], service, need))
        _event(con, row["uid"], service, "human_correction" if corrected is not None else "review_" + status, {"note": note, "revision": int(current["revision"]) + 1})


def reuse_current(row, service, cache_key, attempt):
    """Only reuse a matching current revision; never restore an obsolete review."""
    with transaction() as con:
        record = con.execute("SELECT result_json FROM business_results WHERE notification_uid=? AND service_id=? AND need_id='primary'", (row["uid"], service)).fetchone()
        if not record or json.loads(record["result_json"]).get("cache_key") != cache_key:
            return False
        con.execute("UPDATE business_analysis_attempts SET status='cached',finished_at=? WHERE id=?", (now(), attempt))
        _event(con, row["uid"], service, "analysis_cache_hit", {"cache_key":cache_key,"attempt":attempt})
        return True
