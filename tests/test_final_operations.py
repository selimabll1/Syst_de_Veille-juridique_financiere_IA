"""Explicit actions tested with temporary registries or mocked integrations."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from services import operations
from tests.test_final_ui import workspace_fixture


class OperationTests(unittest.TestCase):
    def setUp(self):
        self.row = workspace_fixture()["rows"][0]
        from modules import business_pipeline_registry
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.registry_patch = patch.object(business_pipeline_registry, "DATABASE", Path(self.temp.name) / "pipeline.sqlite3")
        self.registry_patch.start()
        self.addCleanup(self.registry_patch.stop)
        from modules import admin_registry
        admin_patch = patch.object(admin_registry, "DATABASE", Path(self.temp.name) / "admin.sqlite3")
        admin_patch.start()
        self.addCleanup(admin_patch.stop)
        from modules import service_registry
        for name, value in {"BUSINESS_DB": Path(self.temp.name) / "pipeline.sqlite3", "_INITIALIZED": False, "_CACHE_AT": 0, "_ROUTE_CACHE": {}, "_TAG_CACHE": {}}.items():
            isolated = patch.object(service_registry, name, value)
            isolated.start()
            self.addCleanup(isolated.stop)

    def test_sync_commands_preserve_existing_scripts_and_have_no_reset_flags(self):
        with patch.object(operations, "_run_command", return_value=(True, "checked")) as run:
            operations.check_remote()
            run.assert_called_with(["-m", "scripts.check_legaltech_remote_v29", "--headless"], 90)
            operations.sync_pdfs()
            run.assert_called_with(["-m", "scripts.download_pdfs_v5_network_capture_v3", "--notification", "", "--limit", "0", "--headless"], 300)
            run.return_value = (False, "offline")
            with patch('services.ui_adapter.load_workspace', return_value={'alerts': [], 'rows': []}), \
                 patch('modules.alert_workflow.ensure_alerts'), \
                 patch('modules.alert_workflow.mark_new_alerts'), \
                 patch('modules.legaltech_remote_watcher.reconcile_local'), \
                 patch('modules.business_pipeline_registry.register_notifications'), \
                 patch.object(operations, 'persist_routing'):
                self.assertFalse(operations.sync_legaltech([])[0])
            run.assert_called_with(["-m", "scripts.sync_legaltech_notifications_v5", "--max-notifications", "0", "--headless"], 1800)

    def test_assignment_uses_stable_uid_and_persists_investment_in_temp_registry(self):
        from modules import service_registry as registry
        with tempfile.TemporaryDirectory() as directory, patch.object(registry, "BUSINESS_DB", Path(directory) / "business.sqlite3"), patch.object(registry, "_INITIALIZED", False), patch.object(registry, "_CACHE_AT", 0), patch.object(registry, "_ROUTE_CACHE", {}), patch.object(registry, "_TAG_CACHE", {}):
            operations.save_assignment(self.row, list(registry.SERVICES), assignee="Temporary analyst")
            self.assertEqual(set(registry.routes_for_alert("test-0")), set(registry.SERVICES))

    def test_cmf_keeps_first_live_baseline_and_does_not_seed_or_purge(self):
        result = {"items": [{"uid": "temporary-cmf"}]}
        collector = SimpleNamespace(collect_cmf=Mock(return_value=deepcopy(result)))
        registry = SimpleNamespace(upsert_items=Mock(return_value={"new": 0, "inserted": 0, "updated": 0, "unchanged": 1}), record_sync=Mock(), seed_demo=Mock(), purge_demo_items=Mock())
        with patch.dict(sys.modules, {"modules.cmf_collector_v1": collector, "modules.cmf_registry_v1": registry}):
            with patch("services.cmf_relevance.relevant_items", return_value=(result["items"], [])):
                operations.sync_cmf(2)
        collector.collect_cmf.assert_called_once_with(max_pages=2)
        registry.upsert_items.assert_called_once_with(result["items"], source_mode="live", first_live_sync_as_baseline=True)
        registry.seed_demo.assert_not_called()
        registry.purge_demo_items.assert_not_called()

    def test_review_and_export_use_saved_record_identity(self):
        row = workspace_fixture()["rows"][2]
        row["record"]["alert_uid"] = "persisted-legacy-identity"
        registry = SimpleNamespace(set_review_status=Mock(), mark_exported=Mock())
        excel = SimpleNamespace(export_results=Mock(return_value="temporary.xlsx"))
        with patch.dict(sys.modules, {"modules.analysis_results_registry": registry, "modules.excel_manager": excel}):
            operations.set_review(row, "correction")
            operations.export_excel(row)
        registry.set_review_status.assert_called_once_with("persisted-legacy-identity", "correction")
        registry.mark_exported.assert_called_once_with("persisted-legacy-identity")
        excel.export_results.assert_called_once_with([row["analysis"]])

    def test_cmf_sync_routes_only_new_cmf_records(self):
        old = {'uid': 'cmf:old', 'kind': 'cmf'}
        unrelated = {'uid': 'legaltech:old', 'kind': 'legaltech'}
        new = {'uid': 'cmf:new', 'kind': 'cmf'}
        snapshots = [{'rows': [old, unrelated], 'referential_entities': []},
                     {'rows': [old, unrelated, new]}]
        result = {'items': [{'uid': 'new'}]}
        registry = SimpleNamespace(upsert_items=Mock(return_value={'new': 1, 'inserted': 1, 'updated': 0, 'unchanged': 0}), record_sync=Mock())
        collector = SimpleNamespace(collect_cmf=Mock(return_value=result))
        with patch.dict(sys.modules, {'modules.cmf_collector_v1': collector, 'modules.cmf_registry_v1': registry}), \
             patch('services.ui_adapter.load_workspace', side_effect=snapshots), \
             patch('services.ui_adapter.invalidate_cache'), \
             patch('services.cmf_relevance.relevant_items', return_value=(result['items'], [])), \
             patch('modules.business_pipeline_registry.register_notifications') as register, \
             patch.object(operations, 'persist_routing') as route, \
             patch.object(operations, 'register_workspace', side_effect=AssertionError('Unrelated routing')):
            operations.sync_cmf()
        register.assert_called_once_with([new])
        route.assert_called_once_with([new])

    def test_failed_excel_export_is_not_marked_exported(self):
        registry = SimpleNamespace(mark_exported=Mock())
        excel = SimpleNamespace(export_results=Mock(side_effect=OSError("temporary test failure")))
        with patch.dict(sys.modules, {"modules.analysis_results_registry": registry, "modules.excel_manager": excel}):
            with self.assertRaises(OSError):
                operations.export_excel(workspace_fixture()["rows"][2])
        registry.mark_exported.assert_not_called()

    def test_analysis_orchestration_uses_stored_text_scoring_and_result_registry(self):
        from services import business_analysis
        with patch.object(business_analysis, "analyze", return_value={"ok": True}) as analyze:
            self.assertTrue(operations.run_analysis(self.row, ["investment"])["ok"])
        analyze.assert_called_once_with(self.row, ["investment"], force=False)

    def test_digest_preview_preserves_collected_content_without_sending(self):
        subject, text, markup = operations.build_digest("investment", [self.row])
        self.assertIn("Investissement", subject)
        self.assertIn(self.row["entity"], text)
        self.assertIn(self.row["title"], markup)
        self.assertIn(self.row["summary"], text)


if __name__ == "__main__":
    unittest.main()
