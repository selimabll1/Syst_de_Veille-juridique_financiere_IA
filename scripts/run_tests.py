"""Maintained isolated suite; excludes historical/live diagnostic scripts."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
SUITE = ('final_adapter','final_ui','final_operations','phase3_pipeline',
         'phase4_grounding','phase5_administration','phase61_semantics',
         'phase6_intelligence','product_freeze','correctness_gates','golden_events',
         'composite_workflow','home_dashboard','financial_intelligence',
         'pdf_preview','rehearsal_hardening')

if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromNames(['tests.test_'+name for name in SUITE])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
