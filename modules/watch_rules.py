from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sqlite3
import time
from typing import Any

from modules.alert_identity import stable_alert_uid

WATCH_RULES_VERSION = "watch_rules_v30_cached"
RULES_DB = Path("data/legaltech_watch_rules.sqlite3")
_INITIALIZED = False
_RULE_CACHE_AT = 0.0
_RULE_CACHE: list[dict[str, Any]] = []
_RULE_CACHE_TTL = 20.0


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    RULES_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(RULES_DB)
    con.row_factory = sqlite3.Row
    return con


def initialize() -> None:
    global _INITIALIZED
    if _INITIALIZED and RULES_DB.exists():
        return
    with _connect() as con:
        con.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS watch_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                conditions_json TEXT NOT NULL DEFAULT '{}',
                actions_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS watch_rule_hits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_id INTEGER NOT NULL,
                alert_uid TEXT NOT NULL,
                hit_at TEXT NOT NULL,
                actions_json TEXT NOT NULL DEFAULT '{}',
                UNIQUE(rule_id, alert_uid)
            );
            CREATE INDEX IF NOT EXISTS idx_watch_rule_hits_alert
              ON watch_rule_hits(alert_uid, hit_at DESC);
            """
        )
    _INITIALIZED = True


def _invalidate_rules() -> None:
    global _RULE_CACHE_AT, _RULE_CACHE
    _RULE_CACHE_AT = 0.0; _RULE_CACHE = []


def create_rule(name: str, conditions: dict[str, Any], actions: dict[str, Any], enabled: bool = True) -> int:
    initialize(); now = _now()
    with _connect() as con:
        cur = con.execute(
            """INSERT INTO watch_rules(name,enabled,conditions_json,actions_json,created_at,updated_at)
               VALUES (?,?,?,?,?,?)""",
            (name.strip() or "Règle de veille", int(enabled), json.dumps(conditions, ensure_ascii=False), json.dumps(actions, ensure_ascii=False), now, now),
        )
        rule_id = int(cur.lastrowid)
    _invalidate_rules(); return rule_id


def update_enabled(rule_id: int, enabled: bool) -> None:
    initialize()
    with _connect() as con:
        con.execute("UPDATE watch_rules SET enabled=?,updated_at=? WHERE id=?", (int(enabled), _now(), int(rule_id)))
    _invalidate_rules()


def delete_rule(rule_id: int) -> None:
    initialize()
    with _connect() as con:
        con.execute("DELETE FROM watch_rule_hits WHERE rule_id=?", (int(rule_id),))
        con.execute("DELETE FROM watch_rules WHERE id=?", (int(rule_id),))
    _invalidate_rules()


def list_rules(enabled_only: bool = False) -> list[dict[str, Any]]:
    global _RULE_CACHE_AT, _RULE_CACHE
    initialize(); now = time.monotonic()
    if not _RULE_CACHE or now - _RULE_CACHE_AT >= _RULE_CACHE_TTL:
        with _connect() as con:
            rows = con.execute("SELECT * FROM watch_rules ORDER BY id DESC").fetchall()
        parsed = []
        for row in rows:
            item = dict(row)
            for col, target in (("conditions_json","conditions"),("actions_json","actions")):
                try: item[target] = json.loads(item.get(col) or "{}")
                except Exception: item[target] = {}
            parsed.append(item)
        _RULE_CACHE, _RULE_CACHE_AT = parsed, now
    values = list(_RULE_CACHE)
    return [item for item in values if int(item.get("enabled") or 0) == 1] if enabled_only else values


def _norm(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold().strip()


def _field(alert: dict[str, Any], *names: str) -> str:
    fields = alert.get("source_fields") or {}
    if not isinstance(fields, dict): fields = {}
    for name in names:
        value = alert.get(name)
        if value not in (None, ""): return str(value)
        value = fields.get(name)
        if value not in (None, ""): return str(value)
    return ""


def _matches(alert: dict[str, Any], conditions: dict[str, Any], analysis: dict[str, Any] | None = None) -> bool:
    company = _norm(_field(alert,"company_or_query","notification_company","nom_entreprise","denomination"))
    raw_source = _norm(_field(alert,"source")); source_label = _norm(_field(alert,"source_label"))
    parts = [raw_source, source_label]
    if raw_source.startswith("jr") or source_label.startswith("journal"): parts.append("presse")
    if raw_source == "rne" or "registre national" in source_label: parts.append("rne")
    if raw_source == "jort" or "journal officiel" in source_label: parts.append("jort")
    source = " ".join(x for x in parts if x)
    category = _norm(_field(alert,"categories","categorie","personnalite_juridique"))
    ident = _norm(_field(alert,"identifiant_unique","article_id","doc_id"))
    blob = _norm(" ".join([company,source,category,ident,_field(alert,"card_title"),_field(alert,"card_summary"),_field(alert,"detail_text"),json.dumps(alert.get("source_fields") or {}, ensure_ascii=False)]))
    for name, corpus in (("company",company),("source",source),("category",category),("identifier",ident),("keyword",blob)):
        expected = _norm(conditions.get(name))
        if expected and expected not in corpus: return False
    min_risk = conditions.get("min_risk")
    if min_risk not in (None, ""):
        try:
            risk = float((analysis or {}).get("Score_Risque_IA", (analysis or {}).get("score_risque")))
            if risk < float(min_risk): return False
        except (TypeError, ValueError): return False
    return True


def evaluate_alert(alert: dict[str, Any], analysis: dict[str, Any] | None = None, *, record_hits: bool = True) -> dict[str, Any]:
    uid = stable_alert_uid(alert)
    effects: dict[str, Any] = {
        "matched_rule_ids": [],
        "tags": [],
        "priority": "",
        "notify": False,
        "send_review": False,
        "services": [],
        "digest": False,
    }
    hits_to_record: list[tuple[int, dict[str, Any]]] = []

    for rule in list_rules(enabled_only=True):
        if not _matches(alert, rule.get("conditions") or {}, analysis):
            continue

        actions = rule.get("actions") or {}
        rid = int(rule["id"])
        effects["matched_rule_ids"].append(rid)

        tag = str(actions.get("tag") or "").strip()
        if tag and tag not in effects["tags"]:
            effects["tags"].append(tag)

        if actions.get("priority"):
            effects["priority"] = str(actions["priority"])

        effects["notify"] = bool(effects["notify"] or actions.get("notify"))
        effects["send_review"] = bool(
            effects["send_review"] or actions.get("send_review")
        )
        effects["digest"] = bool(effects["digest"] or actions.get("digest"))

        raw_services = actions.get("services", actions.get("service", []))
        if isinstance(raw_services, str):
            raw_services = [raw_services]
        if isinstance(raw_services, (list, tuple, set)):
            for service_id in raw_services:
                clean = str(service_id or "").strip()
                if clean and clean not in effects["services"]:
                    effects["services"].append(clean)

        if record_hits:
            hits_to_record.append((rid, actions))

    if hits_to_record:
        with _connect() as con:
            for rid, actions in hits_to_record:
                con.execute(
                    """INSERT OR IGNORE INTO watch_rule_hits(
                           rule_id,alert_uid,hit_at,actions_json
                       ) VALUES (?,?,?,?)""",
                    (
                        rid,
                        uid,
                        _now(),
                        json.dumps(actions, ensure_ascii=False),
                    ),
                )
    return effects


def hits_for_alert(alert: dict[str, Any]) -> list[dict[str, Any]]:
    initialize(); uid = stable_alert_uid(alert)
    with _connect() as con:
        rows = con.execute("""SELECT h.*,r.name AS rule_name FROM watch_rule_hits h JOIN watch_rules r ON r.id=h.rule_id WHERE h.alert_uid=? ORDER BY h.id DESC""", (uid,)).fetchall()
    return [dict(row) for row in rows]
