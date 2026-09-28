from pathlib import Path
import sqlite3

DB = Path("data/legaltech_notifications_v5.sqlite3")

def main():
    if not DB.exists():
        raise SystemExit(f"DB introuvable: {DB}")

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    tables = {
        row["name"]
        for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }

    required = {"runs", "notifications", "notification_alerts"}
    missing = sorted(required - tables)
    assert not missing, f"Tables manquantes: {missing}"

    run = con.execute(
        "SELECT * FROM runs ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    assert run is not None, "Aucun run disponible."

    notifications = con.execute(
        "SELECT COUNT(*) AS n FROM notifications WHERE run_id=?",
        (run["run_id"],),
    ).fetchone()["n"]

    alerts = con.execute(
        "SELECT COUNT(*) AS n FROM notification_alerts WHERE run_id=?",
        (run["run_id"],),
    ).fetchone()["n"]

    collected_pdfs = con.execute(
        """SELECT COUNT(*) AS n
           FROM notification_alerts
           WHERE run_id=? AND download_status='COLLECTED'""",
        (run["run_id"],),
    ).fetchone()["n"]

    con.close()

    print("NOTIFICATIONS DASHBOARD DB TEST OK")
    print("run_id:", run["run_id"])
    print("notifications:", notifications)
    print("alerts:", alerts)
    print("pdfs_collected:", collected_pdfs)

if __name__ == "__main__":
    main()
