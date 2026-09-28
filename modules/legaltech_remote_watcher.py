from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3
import time
from typing import Any

from modules.alert_identity import stable_notification_uid, stable_alert_uid, confirmed_capture_aliases
from modules.legaltech_notifications_collector import DEFAULT_NOTIFICATIONS_URL
from modules.legaltech_notifications_network_collector import DEFAULT_V5_DB, NetworkFirstNotificationsCollector

REMOTE_WATCHER_VERSION = "legaltech_remote_watcher_v29_2_remote_delta"
WATCH_DB = Path("data/legaltech_remote_watch.sqlite3")


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    WATCH_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(WATCH_DB)
    con.row_factory = sqlite3.Row
    return con


def _ensure_column(con: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    cols = {str(r["name"]) for r in con.execute(f'PRAGMA table_info("{table}")')}
    if column not in cols:
        con.execute(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {definition}')


def initialize() -> None:
    with _connect() as con:
        con.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS watcher_runs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              checked_at TEXT NOT NULL,
              remote_count INTEGER NOT NULL,
              missing_count INTEGER NOT NULL,
              status TEXT NOT NULL,
              message TEXT
            );
            CREATE TABLE IF NOT EXISTS remote_notifications (
              remote_uid TEXT PRIMARY KEY,
              company_or_query TEXT,
              notification_date TEXT,
              announced_result_count INTEGER,
              raw_text TEXT,
              first_detected_at TEXT NOT NULL,
              last_detected_at TEXT NOT NULL,
              is_missing_local INTEGER NOT NULL DEFAULT 1
            );
            """
        )
        _ensure_column(con, "remote_notifications", "local_result_count", "INTEGER")
        _ensure_column(con, "remote_notifications", "result_delta", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(con, "remote_notifications", "pending_reason", "TEXT NOT NULL DEFAULT 'NEW_NOTIFICATION'")


def collected_notification_map(notifications, alerts):
    """Compare remote cards with persisted unique articles, never discovery counts."""
    aliases = confirmed_capture_aliases(alerts)
    cards = {row.get("notification_key"): stable_notification_uid(row) for row in notifications}
    collected = {}
    for alert in alerts:
        card = cards.get(alert.get("notification_key"))
        if card is not None:
            uid = stable_alert_uid(alert)
            collected.setdefault(card, set()).add(aliases.get(uid, uid))
    out = {}
    for row in notifications:
        uid = stable_notification_uid(row)
        out[uid] = {**row, "collected_result_count": len(collected.get(uid, set()))}
    return out


def _local_map(db_path: Path = DEFAULT_V5_DB) -> dict[str, dict[str, Any]]:
    if not db_path.exists():
        return {}
    con = sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in con.execute("SELECT * FROM notifications")]
        alerts = [dict(r) for r in con.execute("SELECT * FROM notification_alerts")]
        return collected_notification_map(rows, alerts)
    finally:
        con.close()


def _click_next_left(collector: NetworkFirstNotificationsCollector) -> bool:
    page = collector._page()
    before = collector._fingerprint_notifications() if hasattr(collector, "_fingerprint_notifications") else ""
    clicked = page.locator("body").evaluate(
        r"""root => {
          const vw = window.innerWidth || 1500;
          const items = [];
          for (const el of root.querySelectorAll('button,a,[role="button"]')) {
            const txt = ((el.innerText||'')+' '+(el.getAttribute('aria-label')||'')+' '+(el.getAttribute('title')||'')).trim();
            if (!/(suivant|suivante|next|^[>›»]$)/i.test(txt)) continue;
            const r = el.getBoundingClientRect();
            if (!r.width || !r.height) continue;
            const center = r.left + r.width/2;
            if (center >= vw*0.50) continue;
            if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
            items.push({el,y:r.top});
          }
          items.sort((a,b)=>b.y-a.y);
          if (!items.length) return false;
          items[0].el.scrollIntoView({block:'center'});
          items[0].el.click();
          return true;
        }"""
    )
    if not clicked:
        return False
    deadline = time.time() + 7
    while time.time() < deadline:
        page.wait_for_timeout(300)
        now = collector._fingerprint_notifications() if hasattr(collector, "_fingerprint_notifications") else ""
        if now and now != before:
            return True
    return False


def _pending_comparison(remote: dict[str, Any], local: dict[str, Any] | None) -> tuple[bool, str, int, int]:
    remote_count = int(remote.get("announced_result_count") or 0)
    if local is None:
        return True, "NEW_NOTIFICATION", 0, max(1, remote_count)
    local_count = int(local.get("collected_result_count") or 0)
    delta = max(0, remote_count - local_count)
    if delta > 0:
        return True, "NEW_RESULTS", local_count, delta
    return False, "SYNCED", local_count, 0


def _check_remote(browser, *, max_pages: int = 100) -> dict[str, Any]:
    """Read only the left LegalTech notification list and compare it locally.

    Pending means either:
      * a brand-new LegalTech notification card is absent locally; or
      * an existing remote card now announces more results than the local copy.
    """
    initialize()
    collector = NetworkFirstNotificationsCollector(browser)
    browser.goto(DEFAULT_NOTIFICATIONS_URL)
    if not browser.is_authenticated():
        from modules.legaltech_browser_collector import AuthenticationRequired
        raise AuthenticationRequired("Connexion LegalTech requise.")

    remote: dict[str, dict[str, Any]] = {}
    page_no = 1
    while page_no <= max_pages:
        candidates = collector._notification_candidates()
        if not candidates:
            break
        for idx, row in enumerate(candidates):
            item = collector._parse_notification(
                row.get("text") or "",
                page_no,
                notification_index=idx,
            )
            d = {
                "company_or_query": item.company_or_query,
                "notification_date": item.notification_date,
                "announced_result_count": item.announced_result_count,
                "raw_text": item.raw_text,
            }
            remote[stable_notification_uid(d)] = d
        if not _click_next_left(collector):
            break
        page_no += 1

    local_map = _local_map()
    if page_no > max_pages:
        from modules.legaltech_browser_collector import BrowserCollectorError
        raise BrowserCollectorError("Vérification distante incomplète : limite de pages atteinte. Dernier état conservé.")
    if not remote:
        from modules.legaltech_browser_collector import AuthenticationRequired, BrowserCollectorError
        if not browser.is_authenticated():
            raise AuthenticationRequired("Connexion LegalTech requise ; dernier état distant conservé.")
        raise BrowserCollectorError("Aucune carte LegalTech lisible. La session ou le chargement de la page doit être vérifié ; le dernier état distant est conservé.")
    now = _now()
    missing_count = 0
    with _connect() as con:
        con.execute("UPDATE remote_notifications SET is_missing_local=0, result_delta=0, pending_reason='SYNCED'")
        for uid, item in remote.items():
            pending, reason, local_count, delta = _pending_comparison(item, local_map.get(uid))
            if pending:
                missing_count += 1
            old = con.execute(
                "SELECT first_detected_at FROM remote_notifications WHERE remote_uid=?",
                (uid,),
            ).fetchone()
            first = old["first_detected_at"] if old else now
            con.execute(
                """INSERT INTO remote_notifications(
                     remote_uid,company_or_query,notification_date,announced_result_count,
                     raw_text,first_detected_at,last_detected_at,is_missing_local,
                     local_result_count,result_delta,pending_reason
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(remote_uid) DO UPDATE SET
                     company_or_query=excluded.company_or_query,
                     notification_date=excluded.notification_date,
                     announced_result_count=excluded.announced_result_count,
                     raw_text=excluded.raw_text,
                     last_detected_at=excluded.last_detected_at,
                     is_missing_local=excluded.is_missing_local,
                     local_result_count=excluded.local_result_count,
                     result_delta=excluded.result_delta,
                     pending_reason=excluded.pending_reason""",
                (
                    uid, item["company_or_query"], item["notification_date"],
                    item["announced_result_count"], item["raw_text"], first, now,
                    int(pending), local_count, delta, reason,
                ),
            )
        con.execute(
            "INSERT INTO watcher_runs(checked_at,remote_count,missing_count,status,message) VALUES (?,?,?,?,?)",
            (now, len(remote), missing_count, "OK", f"{missing_count} notification(s) distante(s) à synchroniser"),
        )
    return {"checked_at": now, "remote_count": len(remote), "missing_count": missing_count, "pages": page_no}


def check_remote(browser, *, max_pages: int = 100) -> dict[str, Any]:
    try:
        return _check_remote(browser, max_pages=max_pages)
    except Exception as exc:
        with _connect() as con:
            pending = con.execute("SELECT COUNT(*) FROM remote_notifications WHERE is_missing_local=1").fetchone()[0]
            con.execute("INSERT INTO watcher_runs(checked_at,remote_count,missing_count,status,message) VALUES(?,?,?,?,?)", (_now(), 0, pending, "ERROR", str(exc)))
        raise


def reconcile_local() -> int:
    initialize()
    local_map = _local_map()
    cleared = 0
    with _connect() as con:
        rows = con.execute("SELECT * FROM remote_notifications WHERE last_detected_at=(SELECT MAX(last_detected_at) FROM remote_notifications)").fetchall()
        for row in rows:
            item = dict(row)
            pending, reason, local_count, delta = _pending_comparison(item, local_map.get(item["remote_uid"]))
            if not pending:
                cleared += 1
            con.execute(
                """UPDATE remote_notifications
                   SET is_missing_local=?,local_result_count=?,result_delta=?,pending_reason=?
                   WHERE remote_uid=?""",
                (int(pending), local_count, delta, reason, item["remote_uid"]),
            )
    return cleared


def pending_remote(limit: int = 20) -> list[dict[str, Any]]:
    initialize()
    reconcile_local()
    with _connect() as con:
        rows = con.execute(
            """SELECT * FROM remote_notifications WHERE is_missing_local=1
               ORDER BY last_detected_at DESC LIMIT ?""",
            (int(limit),),
        ).fetchall()
    return [dict(r) for r in rows]


def watcher_status() -> dict[str, Any]:
    initialize()
    reconcile_local()
    with _connect() as con:
        run = con.execute("SELECT * FROM watcher_runs ORDER BY id DESC LIMIT 1").fetchone()
        count = con.execute("SELECT COUNT(*) n FROM remote_notifications WHERE is_missing_local=1").fetchone()["n"]
    out = dict(run) if run else {"checked_at": "", "remote_count": 0, "missing_count": 0, "status": "NEVER"}
    out["missing_count"] = int(count)
    return out
