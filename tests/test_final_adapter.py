"""Offline adapter contracts. All test records live in temporary directories."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from modules.alert_identity import stable_alert_uid
from modules.service_model import SERVICES
from services import ui_adapter as adapter


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.patch = patch.object(adapter, "DATA_DIR", self.directory)
        self.patch.start()
        adapter.invalidate_cache()

    def tearDown(self):
        adapter.invalidate_cache()
        self.patch.stop()
        self.temp.cleanup()

    def write_table(self, database, sql, values=()):
        connection = sqlite3.connect(self.directory / adapter.DATABASES[database])
        try:
            connection.executescript(sql)
            for statement, params in values:
                connection.execute(statement, params)
            connection.commit()
        finally:
            connection.close()

    def test_queries_do_not_create_missing_databases(self):
        workspace = adapter.load_workspace()
        self.assertEqual(workspace["rows"], [])
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_stable_service_and_saved_review_contract(self):
        raw = {"alert_key": "legacy-key", "article_id": "article-123456", "source": "rne"}
        uid = stable_alert_uid(raw)
        self.write_table("legaltech", "CREATE TABLE notification_alerts(alert_key TEXT, article_id TEXT, source TEXT, card_title TEXT, card_date TEXT, source_fields_json TEXT);", [("INSERT INTO notification_alerts VALUES (?,?,?,?,?,?)", ("legacy-key", "article-123456", "rne", "Une publication réelle de test", "2026-09-01", "{}"))])
        self.write_table("business", "CREATE TABLE alert_service_routes(alert_uid TEXT,service_id TEXT,active INTEGER); CREATE TABLE alert_assignments(alert_uid TEXT,assignee TEXT);", [("INSERT INTO alert_service_routes VALUES (?,?,1)", (uid, "investment")), ("INSERT INTO alert_assignments VALUES (?,?)", (uid, "Analyste test"))])
        self.write_table("workflow", "CREATE TABLE alert_workflow(alert_key TEXT,is_read INTEGER,ai_status TEXT,updated_at TEXT);", [("INSERT INTO alert_workflow VALUES (?,1,'done','2026-09-01')", ("legacy-key",))])
        self.write_table("results", "CREATE TABLE ai_results(alert_uid TEXT,alert_key TEXT,result_json TEXT,review_status TEXT,updated_at TEXT);", [("INSERT INTO ai_results VALUES (?,?,?,'validated','2026-09-01')", (uid, "legacy-key", json.dumps({"Score_Risque_IA": 65, "Résumé_IA": "Résultat test"})))])
        before = {p.name: p.read_bytes() for p in self.directory.iterdir()}
        row = adapter.load_workspace()["rows"][0]
        self.assertEqual(row["services"], ["investment"])
        self.assertEqual(row["assignment"]["assignee"], "Analyste test")
        self.assertFalse(row["treated"])
        self.assertEqual(row["legacy_result"]["review_status"], "validated")
        self.assertEqual(row["priority"], "Moyenne")
        self.assertEqual(row["stable_uid"], uid)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.directory.iterdir()})

    def test_remote_bell_counts_cards_and_increased_results_not_unread(self):
        from modules.alert_identity import stable_notification_uid
        from modules.legaltech_remote_watcher import _pending_comparison
        notifications = [{"company_or_query": "A", "notification_date": "2026-09-01", "announced_result_count": 2}, {"company_or_query": "B", "notification_date": "2026-09-01", "announced_result_count": 7}]
        remote = []
        for company, count in (("A", 5), ("B", 6), ("C", 10)):
            item = {"company_or_query": company, "notification_date": "2026-09-01", "announced_result_count": count, "is_missing_local": 1}
            item["remote_uid"] = stable_notification_uid(item)
            remote.append(item)
        alerts = []
        for notification, count in zip(notifications, (2, 7)):
            notification['notification_key'] = notification['company_or_query']
            notification['collected_result_count'] = count
            alerts.extend({'notification_key': notification['notification_key'], 'source': 'rne',
                           'article_id': f"{notification['notification_key']}-{i}"} for i in range(count))
        snapshot = adapter._remote_snapshot(notifications, remote, [], alerts)
        self.assertEqual(snapshot["status"]["missing_count"], 2)
        self.assertEqual({r["pending_reason"] for r in snapshot["pending"]}, {"NEW_NOTIFICATION", "NEW_RESULTS"})
        self.assertEqual(_pending_comparison(remote[0], notifications[0]), (True, "NEW_RESULTS", 2, 3))

    def test_source_links_use_nested_actual_files_only(self):
        pdf = self.directory / "source.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        raw = {"metadata": {"document": {"download_path": str(pdf), "source_url": "https://example.org/source"}}, "pdf_path": str(self.directory / "missing.pdf")}
        docs = adapter.source_links(raw)
        self.assertEqual(len(docs), 2)
        self.assertEqual({d["kind"] for d in docs}, {"pdf", "url"})
        self.assertEqual(adapter.source_links({"article_id": "123"}), [])

    def test_cached_result_is_not_shared_mutable_state(self):
        first = adapter.load_workspace()
        first["rows"].append({"uid": "not-persisted"})
        self.assertEqual(adapter.load_workspace()["rows"], [])

    def test_all_four_services_are_canonical(self):
        from modules import service_registry
        self.assertIs(service_registry.SERVICES, SERVICES)
        self.assertEqual(set(SERVICES), {"investment", "compliance", "portfolio", "commercial"})

    def test_duplicate_captures_have_one_display_identity_and_keep_legacy_state(self):
        self.write_table("legaltech", "CREATE TABLE notification_alerts(alert_key TEXT,article_id TEXT,source TEXT,card_title TEXT,source_fields_json TEXT);", [("INSERT INTO notification_alerts VALUES (?,?,?,?,?)", (key, "same-article", "rne", "Annonce", "{}")) for key in ("old-capture", "new-capture")])
        self.write_table("workflow", "CREATE TABLE alert_workflow(alert_key TEXT,is_read INTEGER,ai_status TEXT,updated_at TEXT);", [("INSERT INTO alert_workflow VALUES (?,1,'pending','2026-09-01')", ("old-capture",))])
        before = {p.name: p.read_bytes() for p in self.directory.iterdir()}
        rows = adapter.load_workspace()["rows"]
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["read"])
        self.assertEqual(set(rows[0]["legacy_keys"]), {"old-capture", "new-capture"})
        self.assertEqual(len(rows[0]["raw"]["source_variants"]), 2)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.directory.iterdir()})

    def test_explicit_canonical_routing_overrides_legacy_inference(self):
        raw = {"article_id": "article-route", "source": "rne"}
        uid = stable_alert_uid(raw)
        self.write_table("legaltech", "CREATE TABLE notification_alerts(alert_key TEXT,article_id TEXT,source TEXT,source_fields_json TEXT);", [("INSERT INTO notification_alerts VALUES (?,?,?,?)", ("legacy", "article-route", "rne", '{"service":"commercial"}'))])
        self.write_table("business", "CREATE TABLE alert_service_routes(alert_uid TEXT,service_id TEXT,active INTEGER);", [("INSERT INTO alert_service_routes VALUES (?,?,?)", (uid, "commercial", 0)), ("INSERT INTO alert_service_routes VALUES (?,?,?)", (uid, "investment", 1)), ("INSERT INTO alert_service_routes VALUES (?,?,?)", ("legacy", "portfolio", 1))])
        self.assertEqual(adapter.load_workspace()["rows"][0]["services"], ["investment"])

    def test_network_capture_alias_is_read_only_and_preserves_read_state(self):
        common = dict(source='rne', doc_id='document', card_title='Publication', card_date='2026-01-01')
        real = dict(common, article_id='article', alert_key='real')
        duplicate = dict(common, article_id='network-duplicate', alert_key='capture')
        capture_uid = stable_alert_uid(duplicate)
        self.write_table('legaltech', 'CREATE TABLE notification_alerts(alert_key TEXT, article_id TEXT, source TEXT, doc_id TEXT, card_title TEXT, card_date TEXT);',
                         [('INSERT INTO notification_alerts VALUES (?,?,?,?,?,?)', tuple(r[k] for k in ('alert_key','article_id','source','doc_id','card_title','card_date'))) for r in (real, duplicate)])
        self.write_table('workflow', 'CREATE TABLE alert_workflow(alert_key TEXT,is_read INTEGER,ai_status TEXT,updated_at TEXT);',
                         [("INSERT INTO alert_workflow VALUES (?,1,'pending','2026-01-01')", (capture_uid,))])
        before = {p.name:p.read_bytes() for p in self.directory.iterdir()}
        rows = adapter.load_workspace()['rows']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['stable_uid'], stable_alert_uid(real))
        self.assertTrue(rows[0]['read'])
        self.assertEqual(rows[0]['capture_aliases'], [capture_uid])
        self.assertEqual(len(rows[0]['raw']['source_variants']), 2)
        self.assertEqual(before, {p.name:p.read_bytes() for p in self.directory.iterdir()})
        self.write_table('business', 'CREATE TABLE alert_service_routes(alert_uid TEXT,service_id TEXT,active INTEGER,origin TEXT);',
                         [("INSERT INTO alert_service_routes VALUES (?,'commercial',1,'manual')", (capture_uid,))])
        adapter.invalidate_cache()
        self.assertEqual(len(adapter.load_workspace()['rows']), 2)


if __name__ == "__main__":
    unittest.main()
