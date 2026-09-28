"""Isolated regression coverage for the common correctness gates."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services import canonical_facts, correctness_gates, intelligence, document_scope
from modules import business_pipeline_registry as registry, llm_analyzer


CAPITAL_TEXT = (
    "AVIS DE RÉDUCTION DE CAPITAL ALPHA EXEMPLE Société Anonyme. "
    "Le capital est ramené de 100 000 dinars à 80 000 dinars. "
    "La réduction du capital est effectuée pour un montant de 20 000 dinars."
)


class CorrectnessGateTests(unittest.TestCase):
    def row(self, **overrides):
        row = {
            "uid": "legaltech:gate",
            "stable_uid": "gate",
            "kind": "legaltech",
            "title": "Annonce de test",
            "entity": "ALPHA EXEMPLE",
            "date": "2026-09-20",
            "services": ["investment"],
            "matches": [],
            "raw": {"detail_text": CAPITAL_TEXT},
        }
        row.update(overrides)
        return row

    def test_source_identity_blocks_record_mismatch(self):
        row = self.row(stable_uid="record-a")
        facts = canonical_facts.extract({**row, "stable_uid": "record-b"}, CAPITAL_TEXT)
        result = correctness_gates.source_identity(row, CAPITAL_TEXT, facts)
        self.assertEqual(result.outcome, "SOURCE_MISMATCH")

    def test_composite_document_requires_segmentation(self):
        row = self.row(kind="cmf", raw={"section": "bulletin", "pdf_url": "https://cmf.example/b.pdf"}, services=["compliance"])
        facts = canonical_facts.extract(row, CAPITAL_TEXT)
        result = correctness_gates.document_scope(row, facts)
        self.assertEqual(result.outcome, "SEGMENTATION_REQUIRED")

    def test_required_facts_are_event_specific(self):
        row = self.row()
        text = "Une réduction de capital est annoncée, mais les montants ne sont pas communiqués."
        facts = canonical_facts.extract(row, text)
        result = correctness_gates.event_and_facts(facts)
        self.assertEqual(result.outcome, "INSUFFICIENT_EVIDENCE")

    def test_public_warning_does_not_require_company(self):
        row = self.row(kind="cmf", services=["compliance"], raw={"section": "avis"})
        text = "Mise en garde du Conseil du Marché Financier. Le public et les investisseurs sont invités à la vigilance."
        facts = canonical_facts.extract(row, text)
        from services.event_profiles import enrich
        enrich(facts)
        facts["event_type"] = "PUBLIC_WARNING"
        result = correctness_gates.event_and_facts(facts)
        self.assertEqual(result.outcome, "SUCCESS")

    def test_portfolio_and_commerce_need_authoritative_context(self):
        row = self.row()
        facts = canonical_facts.extract(row, CAPITAL_TEXT)
        self.assertEqual(correctness_gates.service_relevance({**row, "services": ["portfolio"]}, "portfolio", facts).outcome, "INSUFFICIENT_EVIDENCE")
        self.assertEqual(correctness_gates.service_relevance({**row, "services": ["commercial"]}, "commercial", facts).outcome, "INSUFFICIENT_EVIDENCE")

    def test_evidence_cannot_cross_child_publications(self):
        facts = canonical_facts.extract(self.row(raw={"child_publication_id": "parent::1"}), CAPITAL_TEXT)
        facts["child_publication_id"] = "parent::1"
        result = {"grounding": {"evidence": [{"id": "S1", "child_publication_id": "parent::2"}]}}
        self.assertEqual(correctness_gates.evidence_boundaries(facts, result).outcome, "SOURCE_MISMATCH")

    def test_inconsistent_numbers_block_persistence_gate(self):
        row = self.row()
        facts = canonical_facts.extract(row, CAPITAL_TEXT.replace("80 000", "81 000"))
        self.assertEqual(correctness_gates.evaluate(row, "investment", CAPITAL_TEXT, facts).outcome, "INSUFFICIENT_EVIDENCE")

    def test_composite_attempt_is_failed_without_calling_model(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "business.sqlite3"
        row = self.row(kind="cmf", services=["compliance"], raw={"section": "bulletin", "raw_excerpt": CAPITAL_TEXT, "pdf_url": "https://cmf.example/b.pdf"})
        with patch.object(registry, "DATABASE", path), patch.object(llm_analyzer, "model_identity", return_value="gate-model"), patch.object(llm_analyzer, "request_structured") as request, patch("services.composite_documents.preprocess", return_value={'ok':True,'outcome':'SEGMENTATION_REQUIRED','operation':'segmentation'}):
            from services import business_analysis
            result = business_analysis.analyze(row)
        self.assertTrue(result["ok"])
        self.assertEqual(result["outcome"], "SEGMENTATION_REQUIRED")
        request.assert_not_called()
        self.assertFalse(path.exists())

    def test_segment_children_preserve_parent_and_page_boundaries(self):
        extraction = {"pages": [{"page_number": 1, "text": "Société Alpha. " + "A" * 110 + " 2026R01364SANB2"}, {"page_number": 2, "text": "Société Beta. " + "B" * 110 + " 2026S00603SODB1"}], "ocr_quality": 1, "method": "text"}
        children = document_scope.segment_children(extraction, parent_id="cmf:bulletin", parent_title="Bulletin officiel", pdf_url="https://cmf.example/b.pdf")
        self.assertEqual(len(children), 2)
        self.assertTrue(all(c["child_publication_id"].startswith("cmf:bulletin::") for c in children))
        self.assertEqual(children[0]["page_start"], 1)
        self.assertEqual(children[1]["page_start"], 2)


if __name__ == "__main__":
    unittest.main()
