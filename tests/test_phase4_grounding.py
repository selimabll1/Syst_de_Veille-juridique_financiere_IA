"""Isolated evidence, reference, routing and business lifecycle checks."""
import json
import sqlite3
import tempfile
from contextlib import closing
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
from services import routing, grounded_analysis, pipeline_config, business_analysis, operations, lifecycle
from modules import business_pipeline_registry as registry, service_registry, llm_analyzer

TEXT = "ALPHA TEST annonce une réduction de capital de 100 à 80 unités. Le procès-verbal est disponible auprès de la société."


class GroundingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        model_patch=patch.object(llm_analyzer,"model_identity",return_value="isolated-digest")
        model_patch.start();self.addCleanup(model_patch.stop)
        self.config = pipeline_config.load()
        self.row = dict(uid="legaltech:isolated-phase4", stable_uid="isolated-phase4", source_key="isolated", kind="legaltech", source="LegalTech", title="Réduction de capital", entity="ALPHA TEST", date="2026-01-01", services=["investment", "portfolio"], raw={"detail_text": TEXT}, summary=TEXT, type="Annonce", read=False, business_results={})
        self.references = [{"name":"ALPHA TEST", "identifier":"TEST-001", "type":"portfolio", "sector":"Secteur de test", "origin":"fixture isolée", "record_id":"isolated:1"}]
        self.row["matches"] = routing.match(self.row, self.references)
        for owner, name, value in [(registry,"DATABASE",self.folder/"business.db"), (service_registry,"BUSINESS_DB",self.folder/"business.db"), (service_registry,"_INITIALIZED",False), (service_registry,"_CACHE_AT",0), (service_registry,"_ROUTE_CACHE",{}), (service_registry,"_TAG_CACHE",{})]:
            replacement = patch.object(owner,name,value)
            replacement.start()
            self.addCleanup(replacement.stop)

    def response(self, prompt, *, system_prompt, schema):
        return {"summary_evidence":["S1"], "focus_evidence":["S1"], "action_ids":["review_capital" if "review_capital" in schema["properties"]["action_ids"]["items"].get("enum",[]) else "monitor"]}

    def analyze(self, service="investment"):
        with patch.object(llm_analyzer,"request_structured",side_effect=self.response):
            return grounded_analysis.analyze(self.row,service,TEXT,1.0,"fixture",self.config)

    def records(self):
        with closing(sqlite3.connect(registry.DATABASE)) as con:
            con.row_factory=sqlite3.Row
            return {r["service_id"]:{**dict(r),"analysis":json.loads(r["result_json"])} for r in con.execute("SELECT * FROM business_results")}

    def test_exact_source_spans_no_generated_growth_deadline_or_score(self):
        result=self.analyze()
        self.assertNotIn("Score_Risque_IA",result)
        for evidence in result["grounding"]["evidence"]:
            self.assertEqual(TEXT[evidence["start"]:evidence["end"]],evidence["quote"])
        self.assertIn("non déterminés",result["business_output"]["uncertainties"])
        self.assertIn("Interprétation",result["business_output"]["investment_impact"])

    def test_unknown_or_fabricated_model_content_is_rejected(self):
        from jsonschema import ValidationError
        for value in ({"summary_evidence":["invented"],"focus_evidence":[],"action_ids":[]}, {"summary_evidence":["S1"],"focus_evidence":[],"action_ids":[],"growth":"50%"}):
            with patch.object(llm_analyzer,"request_structured",return_value=value), self.assertRaises(ValidationError):
                grounded_analysis.analyze(self.row,"investment",TEXT,1,"fixture",self.config)

    def test_decimal_amount_is_not_detached_from_its_sentence(self):
        text = "ALPHA TEST annonce une réduction de capital de 100.500 dinars à 80.250 dinars."
        evidence = grounded_analysis.evidence_catalog(text, self.config)
        self.assertEqual(evidence[0]["quote"], text)

    def test_long_preamble_does_not_discard_financial_amount(self):
        text = "Réduction de capital " + "contexte juridique " * 70 + "de 100 à 80 unités."
        evidence = grounded_analysis.evidence_catalog(text, self.config)
        self.assertEqual(evidence[0]["quote"], text)

    def test_director_link_to_homonymous_holdings_is_not_confirmed(self):
        person = {"name": "PERSON TEST", "type": "director", "portfolio_company": "ALPHA TEST", "origin": "fixture"}
        row = {**self.row, "entity": "PERSON TEST", "title": "Nomination", "raw": {"detail_text": "PERSON TEST est nommé directeur."}}
        references = self.references + [{**self.references[0], "identifier": "OTHER"}, person]
        self.assertFalse(routing.portfolio_matches(routing.match(row, references)))

    def test_no_referential_means_no_portfolio_route_or_analysis(self):
        self.row["matches"]=[]
        suggested,_=routing.suggest(self.row,[],self.config)
        self.assertIn("investment",suggested)
        self.assertNotIn("portfolio",suggested)
        with patch.object(llm_analyzer,"request_structured") as model, self.assertRaisesRegex(ValueError,"Aucune correspondance"):
            grounded_analysis.analyze(self.row,"portfolio",TEXT,1,"fixture",self.config)
        model.assert_not_called()

    def test_monitoring_list_and_unverified_relationship_do_not_prove_holding(self):
        for entity in ({"name":"ALPHA TEST","type":"watchlist","origin":"test"}, {"name":"ALPHA TEST","type":"director","portfolio_company":"UNKNOWN","origin":"test"}):
            self.assertFalse(routing.portfolio_matches(routing.match(self.row,[entity])))

    def test_director_relationship_requires_existing_portfolio_record(self):
        person={"name":"PERSON TEST","type":"director","portfolio_company":"ALPHA TEST","origin":"fixture"}
        row={**self.row,"entity":"PERSON TEST","raw":{"detail_text":"PERSON TEST est nommé directeur."}}
        matches=routing.match(row,self.references+[person])
        self.assertEqual(routing.portfolio_matches(matches)[0]["affected_portfolio_entity"],"ALPHA TEST")

    def test_same_name_different_identifiers_is_ambiguous(self):
        matches=routing.match(self.row,self.references+[{**self.references[0],"identifier":"OTHER"}])
        self.assertFalse(routing.portfolio_matches(matches))

    def test_import_schema_and_gics_are_loaded_without_ui_change(self):
        path=self.folder/"real_reference.csv"
        path.write_text("name,identifier,type,portfolio_company,gics_l4\nALPHA TEST,TEST-001,portfolio,,TEST-GICS\n",encoding="utf-8")
        refs,errors=routing.referential({"referential_files":[str(path)]},[],[])
        self.assertFalse(errors)
        self.assertEqual(refs[0]["gics_l4"],"TEST-GICS")
        self.assertTrue(routing.portfolio_matches(routing.match(self.row,refs)))

    def test_manual_removal_survives_inferred_route_persistence(self):
        operations.save_assignment(self.row,["investment"])
        operations.persist_routing([{**self.row,"manual_routing":True}])
        self.assertEqual(service_registry.routes_for_alert(self.row["stable_uid"]),["investment"])

    def test_two_results_corrections_validation_export_and_queue_are_independent(self):
        from modules import business_export
        operations.save_assignment(self.row,["investment","portfolio"])
        with patch.object(llm_analyzer,"request_structured",side_effect=self.response):
            self.assertTrue(business_analysis.analyze(self.row)["ok"])
        before=self.records()
        changed=dict(before["investment"]["analysis"]["business_output"])
        changed["recommended_actions"]="Correction humaine isolée : examiner le procès-verbal [S1]."
        registry.review(self.row,"investment","pending",corrected=changed,note="Vérification isolée de S1",expected_revision=1)
        after=self.records()
        self.assertEqual(before["portfolio"],after["portfolio"])
        registry.review(self.row,"investment","validated",expected_revision=2)
        self.assertFalse(lifecycle.treated(list(self.records().values())))
        registry.review(self.row,"portfolio","validated",expected_revision=1)
        saved=self.records()
        self.assertTrue(lifecycle.treated(list(saved.values())))
        self.assertFalse(self.row["read"])
        self.row["business_results"]=saved
        with patch.object(business_export,"OUTPUT_EXCEL_DIR",self.folder):
            path=operations.export_excel(self.row,"investment")
        from openpyxl import load_workbook
        with closing(load_workbook(path,read_only=True)) as book:
            self.assertIn("Preuves source",book.sheetnames)
            self.assertNotIn("Méthodologie_Scoring",book.sheetnames)
        operations.queue_digest(self.row,"portfolio")
        with closing(sqlite3.connect(registry.DATABASE)) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM central_notifications").fetchone()[0],1)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM business_results").fetchone()[0],2)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM alert_service_routes WHERE active=1").fetchone()[0],2)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM digest_queue").fetchone()[0],1)

    def test_cmf_cannot_enter_investment_or_portfolio(self):
        row={**self.row,"kind":"cmf"}
        self.assertEqual(routing.suggest(row,self.row["matches"],self.config)[0],["compliance"])
