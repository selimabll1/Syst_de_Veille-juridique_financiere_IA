"""Phase 3 persistence and business invariants; exclusively temporary storage."""
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from modules import business_pipeline_registry as registry
from services import lifecycle, pipeline_config, business_analysis


class PipelineTests(unittest.TestCase):
    def setUp(self):
        from modules import llm_analyzer
        model_patch=patch.object(llm_analyzer,"model_identity",return_value="isolated-digest")
        model_patch.start();self.addCleanup(model_patch.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "business.sqlite3"
        replacement = patch.object(registry, "DATABASE", self.path)
        replacement.start()
        self.addCleanup(replacement.stop)
        self.row = dict(uid="legaltech:isolated", stable_uid="isolated", kind="legaltech", title="Isolated test", entity="Test", date="2026-01-01", services=["investment", "portfolio"], raw={})

    def records(self):
        with closing(sqlite3.connect(self.path)) as con:
            con.row_factory = sqlite3.Row
            rows = [dict(r) for r in con.execute("SELECT * FROM business_results")]
        return [{**r, "analysis": json.loads(r["result_json"])} for r in rows]

    def save(self, service):
        token = registry.start_attempt(self.row, service)
        registry.save_result(self.row, service, {"business_output": {"recommendation": "Temporary"}}, model="isolated-model", prompt_version=1, source_hash="isolated", attempt=token)

    def test_one_notification_independent_results_and_human_validation(self):
        for service in self.row["services"]:
            self.save(service)
        self.assertFalse(lifecycle.treated(self.records()))
        registry.review(self.row, "investment", "validated")
        self.assertFalse(lifecycle.treated(self.records()))
        registry.review(self.row, "portfolio", "validated")
        self.assertTrue(lifecycle.treated(self.records()))
        with closing(sqlite3.connect(self.path)) as con:
            self.assertEqual(con.execute("SELECT count(*) FROM central_notifications").fetchone()[0], 1)
            self.assertEqual(con.execute("SELECT count(*) FROM business_results").fetchone()[0], 2)
            self.assertEqual(con.execute("SELECT count(*) FROM business_result_versions").fetchone()[0], 2)
        self.save("investment")
        self.assertFalse(lifecycle.treated(self.records()))

    def test_failed_reanalysis_retains_result_and_validation(self):
        self.save("investment")
        registry.review(self.row, "investment", "validated")
        token = registry.start_attempt(self.row, "investment")
        registry.fail_attempt(token, "Offline")
        self.assertTrue(lifecycle.result_validated(self.records()[0]))

    def test_cmf_cannot_be_routed_to_other_services(self):
        config = pipeline_config.load()
        config["sources"]["cmf"]["eligible_services"].append("investment")
        with self.assertRaises(ValueError):
            pipeline_config.validate(config)
        row = {**self.row, "kind": "cmf", "services": ["investment"]}
        with self.assertRaises(ValueError):
            business_analysis.analyze(row)
        self.assertFalse(self.path.exists())

    def test_missing_bulletin_document_never_analyzes_a_listing(self):
        row = {**self.row, "kind": "cmf", "raw": {"section": "bulletins", "detail_url": "https://www.cmf.tn/bulletin-officiel"}}
        with self.assertRaisesRegex(ValueError, "document collecté"):
            business_analysis.extract_source(row)

    def test_lifecycle_is_independent_of_priority_and_reading(self):
        result = {"analysis": {"resume": "Isolated"}, "review_status": "validated"}
        for read in (False, True):
            for priority in lifecycle.PRIORITIES:
                self.assertEqual(lifecycle.processing({**result, "read": read, "priority": priority}), "Traité")
        self.assertFalse(lifecycle.treated([result, None]))
        self.assertEqual(lifecycle.priority("Faible"), "Basse")
        self.assertEqual(lifecycle.priority("À classer"), "Moyenne")

    def test_cmf_history_supports_the_installed_compact_schema(self):
        from modules.cmf_registry_v1 import record_sync
        with closing(sqlite3.connect(self.path)) as con:
            con.execute("CREATE TABLE cmf_sync_runs(id INTEGER PRIMARY KEY,started_at TEXT,finished_at TEXT,mode TEXT,found_count INTEGER,new_count INTEGER,errors_json TEXT)")
            con.commit()
        record_sync({"items": [{"uid": "isolated"}], "errors": []}, stats={"new": 1}, database_path=self.path)
        with closing(sqlite3.connect(self.path)) as con:
            self.assertEqual(con.execute("SELECT found_count,new_count FROM cmf_sync_runs").fetchone(), (1, 1))

    def test_cmf_pdf_is_matched_inside_its_own_listing_row(self):
        from modules.cmf_collector_v1 import _extract_bulletins, _ReadableParser
        html = '<div class="views-row views-row-1"><h2>Bulletin officiel du CMF N°100</h2><div>11 Septembre 2026</div><a href="/bo11092026.pdf"><img/></a></div><div class="views-row views-row-2"><h2>Bulletin officiel du CMF N°99</h2><div>10 Septembre 2026</div><a href="/bo10092026.pdf"><img/></a></div>'
        rows = _extract_bulletins(html, "https://www.cmf.tn/bulletin-officiel")
        self.assertEqual([r["pdf_url"].rsplit("/", 1)[-1] for r in rows], ["bo11092026.pdf", "bo10092026.pdf"])
        parser = _ReadableParser()
        parser.feed('<nav>Unrelated</nav><div id="block-system-main"><div>Publication</div><object data="https://www.cmf.tn/source.pdf#view=Fit"></object></div><footer>Unrelated</footer>')
        self.assertEqual(parser.text(), "Publication")
        self.assertEqual(parser.document_pdf, "https://www.cmf.tn/source.pdf")

    def test_old_revision_cannot_be_silently_validated(self):
        self.save("investment")
        self.save("investment")
        with self.assertRaisesRegex(ValueError, "changé"):
            registry.review(self.row, "investment", "validated", expected_revision=1)
        self.assertFalse(lifecycle.result_validated(self.records()[0]))

    def test_cmf_and_legaltech_use_the_same_engine_with_distinct_business_schema(self):
        from modules import llm_analyzer as engine
        self.row["matches"] = [{"portfolio_verified": True, "affected_portfolio_entity": "Test", "match_reason": "Isolated fixture", "origin": "isolated", "type": "portfolio", "name": "Test"}]
        def response(prompt, *, system_prompt, schema):
            if "summary_evidence" in schema["properties"]:
                return {"summary_evidence": ["S1"], "focus_evidence": ["S1"], "action_ids": ["monitor"]}
            return {"societe": "Test", "categorie": "Autre", "type_evenement": "Autre", "type_evenement_code": "AUTRE", "resume": "Publication isolée", "faits_extraits": {"montants_originaux": [], "dates_importantes": [], "delais": [], "parties_citees": [], "decision_ou_action": "Non indiquée"}, "risques_detectes": [], "opportunites_detectees": [], "action_recommandee": "Vérifier", "niveau_confiance_llm": 0.5, "business_output": {k: "Information absente de la source." for k in schema["properties"]["business_output"]["required"]}}
        with patch.object(business_analysis, "extract_source", return_value=("Test : publication isolée pour les tests de pipeline.", 1.0, "isolated")), patch.object(engine, "request_structured", side_effect=response) as request:
            self.assertTrue(business_analysis.analyze(self.row)["ok"])
            cmf = {**self.row, "uid": "cmf:isolated", "kind": "cmf", "services": ["compliance"]}
            self.assertTrue(business_analysis.analyze(cmf)["ok"])
        self.assertEqual(request.call_count, 3)
        outputs = {r["service_id"]: r["analysis"]["business_output"] for r in self.records()}
        self.assertIn("echeances", outputs["compliance"])
        self.assertIn("financial_impact", outputs["portfolio"])
        self.assertIn("investment_impact", outputs["investment"])

    def test_empty_remote_check_preserves_last_known_bell_count(self):
        from modules import legaltech_remote_watcher as watcher
        from modules.legaltech_browser_collector import BrowserCollectorError
        from unittest.mock import Mock
        class ClosingConnection(sqlite3.Connection):
            def __exit__(self, *args):
                try:
                    return super().__exit__(*args)
                finally:
                    self.close()
        def connect():
            con = sqlite3.connect(self.path, factory=ClosingConnection)
            con.row_factory = sqlite3.Row
            return con
        browser = Mock()
        browser.is_authenticated.return_value = True
        collector = Mock()
        collector._notification_candidates.return_value = []
        with patch.object(watcher, "_connect", side_effect=connect), patch.object(watcher, "NetworkFirstNotificationsCollector", return_value=collector), patch.object(watcher, "_local_map", return_value={}):
            watcher.initialize()
            with connect() as con:
                columns = {r["name"] for r in con.execute("PRAGMA table_info(remote_notifications)")}
                values = {"remote_uid": "isolated", "company_or_query": "Isolated", "notification_date": "2026-01-01", "announced_result_count": 2, "raw_text": "Isolated", "first_detected_at": "2026-01-01", "last_detected_at": "2026-01-01", "is_missing_local": 1, "local_result_count": 0, "result_delta": 2, "pending_reason": "NEW_NOTIFICATION"}
                values = {k:v for k,v in values.items() if k in columns}
                con.execute("INSERT INTO remote_notifications(" + ",".join(values) + ") VALUES(" + ",".join("?" for _ in values) + ")", list(values.values()))
            with self.assertRaises(BrowserCollectorError):
                watcher.check_remote(browser)
            with connect() as con:
                self.assertEqual(con.execute("SELECT is_missing_local FROM remote_notifications").fetchone()[0], 1)
                self.assertEqual(con.execute("SELECT status FROM watcher_runs ORDER BY id DESC LIMIT 1").fetchone()[0], "ERROR")


if __name__ == "__main__":
    unittest.main()
