from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sqlite3
from typing import Any

from modules.alert_identity import stable_alert_uid

RESULTS_DB = Path("data/legaltech_ai_results.sqlite3")


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    RESULTS_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(RESULTS_DB)
    con.row_factory = sqlite3.Row
    return con


def initialize() -> None:
    con = _connect()
    try:
        con.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS ai_results (
                alert_uid TEXT PRIMARY KEY,
                alert_key TEXT,
                company TEXT,
                subject TEXT,
                source TEXT,
                alert_date TEXT,
                result_json TEXT NOT NULL,
                review_status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                validated_at TEXT,
                correction_requested_at TEXT,
                exported_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_ai_results_updated
              ON ai_results(updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_ai_results_review
              ON ai_results(review_status, updated_at DESC);
            """
        )
        con.commit()
    finally:
        con.close()


def _uid(alert_or_uid: dict[str, Any] | str) -> str:
    if isinstance(alert_or_uid, dict):
        return stable_alert_uid(alert_or_uid)
    return str(alert_or_uid or "").strip()


def save_analysis_result(alert: dict[str, Any], analysis: dict[str, Any]) -> str:
    initialize()
    uid = _uid(alert)
    now = _now()
    fields = alert.get("source_fields") or {}
    if not isinstance(fields, dict):
        fields = {}
    company = str(
        fields.get("nom_entreprise")
        or alert.get("company_or_query")
        or alert.get("notification_company")
        or "—"
    )
    subject = str(
        fields.get("objet_fr")
        or fields.get("objet")
        or fields.get("titre_alerte")
        or alert.get("card_title")
        or "Alerte LegalTech"
    )
    source = str(alert.get("source") or alert.get("source_label") or "")
    alert_date = str(alert.get("card_date") or alert.get("notification_date") or "")
    payload = json.dumps(analysis, ensure_ascii=False, sort_keys=True, default=str)
    con = _connect()
    try:
        con.execute(
            """
            INSERT INTO ai_results(
                alert_uid, alert_key, company, subject, source, alert_date,
                result_json, review_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            ON CONFLICT(alert_uid) DO UPDATE SET
                alert_key=excluded.alert_key,
                company=excluded.company,
                subject=excluded.subject,
                source=excluded.source,
                alert_date=excluded.alert_date,
                result_json=excluded.result_json,
                updated_at=excluded.updated_at
            """,
            (
                uid,
                str(alert.get("alert_key") or ""),
                company,
                subject,
                source,
                alert_date,
                payload,
                now,
                now,
            ),
        )
        con.commit()
    finally:
        con.close()
    return uid


def load_results_map() -> dict[str, dict[str, Any]]:
    initialize()
    con = _connect()
    try:
        rows = con.execute("SELECT * FROM ai_results").fetchall()
    finally:
        con.close()
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = dict(row)
        try:
            analysis = json.loads(item.get("result_json") or "{}")
            if not isinstance(analysis, dict):
                analysis = {}
        except Exception:
            analysis = {}
        item["analysis"] = analysis
        out[str(item["alert_uid"])] = item
    return out


def get_analysis_result(alert_or_uid: dict[str, Any] | str) -> dict[str, Any] | None:
    uid = _uid(alert_or_uid)
    item = load_results_map().get(uid)
    if not item:
        return None
    analysis = item.get("analysis")
    return analysis if isinstance(analysis, dict) else None


def list_analysis_results() -> list[dict[str, Any]]:
    values = list(load_results_map().values())
    values.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return values


def set_review_status(alert_or_uid: dict[str, Any] | str, status: str) -> None:
    initialize()
    uid = _uid(alert_or_uid)
    status = status if status in {"pending", "correction", "validated"} else "pending"
    now = _now()
    validated_at = now if status == "validated" else None
    correction_at = now if status == "correction" else None
    con = _connect()
    try:
        con.execute(
            """
            UPDATE ai_results
            SET review_status=?, updated_at=?,
                validated_at=CASE WHEN ?='validated' THEN ? ELSE validated_at END,
                correction_requested_at=CASE WHEN ?='correction' THEN ? ELSE correction_requested_at END
            WHERE alert_uid=?
            """,
            (status, now, status, validated_at, status, correction_at, uid),
        )
        con.commit()
    finally:
        con.close()


def mark_exported(alert_or_uid: dict[str, Any] | str) -> None:
    initialize()
    uid = _uid(alert_or_uid)
    con = _connect()
    try:
        con.execute(
            "UPDATE ai_results SET exported_at=?, updated_at=? WHERE alert_uid=?",
            (_now(), _now(), uid),
        )
        con.commit()
    finally:
        con.close()
