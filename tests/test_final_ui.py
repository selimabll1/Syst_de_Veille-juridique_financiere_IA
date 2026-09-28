"""Streamlit behavior with synthetic in-memory rows, never collected data."""
import ast
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from services import ui_adapter as adapter
from ui.pages.workspace import filter_rows

ROOT = Path(__file__).resolve().parents[1]


def workspace_fixture():
    rows = []
    for i in range(25):
        rows.append(dict(uid=f"legaltech:test-{i}", stable_uid=f"test-{i}", source_key=f"legacy-{i}", kind="legaltech", raw={"article_id": str(i)}, source="LegalTech", entity=f"Société test {i}", title=f"Publication temporaire {i}", type="Annonce", date="2026-09-01", priority="Haute" if i == 0 else "Faible", read=False, treated=False, status="Nouveau", services=list(adapter.SERVICES), summary="Contenu de test uniquement", analysis=None, record={}, review_status="pending", ai_state="pending", metadata={}, documents=[], pdf_path="", source_url="", tags=[], assignment={}))
    rows[2]["analysis"] = {"Résumé_IA": "Résultat temporaire", "Score_Risque_IA": 20}
    rows[2]["record"] = {"alert_uid": "test-2", "review_status": "pending", "analysis": rows[2]["analysis"]}
    return dict(rows=rows, run={}, notifications=[], alerts=[], results=[rows[2]["record"]], sources=[], rules=[], watchlists=[], watchlist_items=[], assignments=[], notes=[], digest_settings=[], digest_queue=[], cmf_runs=[], catalog=[], history=[], errors=[], remote={"status": {"checked_at": "2026-09-01", "missing_count": 1}, "pending": [{"company_or_query": "Remote test", "pending_reason": "NEW_RESULTS", "result_delta": 3}]})


class UITests(unittest.TestCase):
    def setUp(self):
        self.workspace = workspace_fixture()
        self.loader = patch.object(adapter, "load_workspace", side_effect=lambda: deepcopy(self.workspace))
        self.loader.start()
        self.commands = patch.object(adapter, "command", side_effect=AssertionError("Unexpected persistent action during render"))
        self.commands.start()
        self.app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)

    def tearDown(self):
        self.commands.stop()
        self.loader.stop()

    def assert_clean(self):
        self.assertFalse(self.app.exception, [e.message for e in self.app.exception])

    def test_all_pages_render_without_persistent_commands(self):
        self.app.run(timeout=45)
        self.assert_clean()
        for page in ("home", "investment", "compliance", "portfolio", "commercial", "notifications", "sources", "ai", "results", "validation", "history", "diffusion", "reference", "settings"):
            with self.subTest(page=page):
                self.app.button(key="nav_" + page).click().run(timeout=30)
                self.assert_clean()
                self.assertEqual(self.app.session_state["ugfs_page"], page)

    def test_twenty_rows_and_explicit_read_callback(self):
        self.app.run(timeout=45)
        self.assertEqual(self.app.session_state['ugfs_page'],'home')
        self.app.button(key='nav_notifications').click().run()
        self.assert_clean()
        buttons = [b for b in self.app.button if str(b.key).startswith("select_")]
        self.assertEqual(len(buttons), 20)
        with patch.object(adapter, "mark_read") as mark:
            self.app.button(key="select_legaltech:test-1").click().run()
            mark.assert_called_once()
            self.assertEqual(mark.call_args.args[0]["stable_uid"], "test-1")
        self.assertEqual(self.app.session_state["ugfs_selected_uid"], "legaltech:test-1")
        self.assertEqual(self.app.session_state["ugfs_page"], "notifications")
        self.app.button(key="nav_ai").click().run()
        self.assertEqual(self.app.session_state["ugfs_selected_uid"], "legaltech:test-1")
        self.assert_clean()
        self.app.button(key='nav_notifications').click().run()
        self.app.button(key="page_next").click().run()
        self.assertEqual(len([b for b in self.app.button if str(b.key).startswith("select_")]), 5)

    def test_modal_opens_and_filters_without_writes(self):
        self.app.run(timeout=45)
        self.app.button(key='nav_notifications').click().run()
        self.app.button(key="advanced_filters").click().run()
        self.assert_clean()
        self.assertTrue(any(x.label == "État IA" for x in self.app.selectbox))
        apply = next(b for b in self.app.button if b.label == "Appliquer les filtres")
        apply.click().run()
        self.assert_clean()

    def test_source_and_settings_subpages(self):
        self.app.run(timeout=45)
        self.app.button(key="nav_sources").click().run()
        # segmented_control is exposed as button_group by Streamlit AppTest.
        for view in ("Supervision des sources", "Historique CMF", "Documents collectés"):
            self.app.session_state["sources_view"] = view
            self.app.run()
            self.assert_clean()
        self.app.button(key="nav_settings").click().run()
        for view in ("Environnement", "Synchronisation", "Règles de veille"):
            self.app.session_state["settings_view"] = view
            self.app.run()
            self.assert_clean()

    def test_filters_preserve_service_and_treatment_contract(self):
        self.assertEqual(len(filter_rows(self.workspace["rows"], {"service": "investment"}, {})), 25)
        self.assertEqual(filter_rows(self.workspace["rows"], {"treatment": "Traitées"}, {}), [])
        self.assertEqual(len(filter_rows(self.workspace["rows"], {}, {"ai": "Analysé"})), 1)
        self.assertEqual(filter_rows(self.workspace["rows"], {}, {"docs": "PDF local"}), [])

    def test_import_and_theme_boundaries(self):
        legacy = ("ugfs_ui_master", "ugfs_desktop_ui", "notifications_dashboard", "cmf_compliance_ui")
        for folder in ("ui", "services"):
            for path in (ROOT / folder).rglob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    names = [n.name for n in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
                    for name in names:
                        self.assertFalse(any(old in name for old in legacy), (path, name))
                        if folder == "services":
                            self.assertFalse(name.startswith("streamlit"), path)
                if path.name != "theme.py":
                    self.assertNotIn("<style", path.read_text(encoding="utf-8"))
        self.assertNotIn("!important", (ROOT / "ui/theme.py").read_text(encoding="utf-8").split('CSS = """', 1)[1])


if __name__ == "__main__":
    unittest.main()
