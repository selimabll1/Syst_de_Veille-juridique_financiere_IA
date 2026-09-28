"""Production rehearsal regressions. Synthetic fixtures and temporary exports only."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import tempfile
import unittest


class RehearsalTests(unittest.TestCase):
    def test_performance_requires_a_metric_value_not_nearby_metadata(self):
        from services.event_taxonomy import classify, performance_evidence
        negatives = [
            "Dépôt des états financiers. Résultat net : non fourni. Capital : 1931191. Année comptable : 2025.",
            "Chiffre d’affaires exercice 2025 : non disponible. Capital : 1931191.",
            "إيداع القوائم المالية. النتيجة الصافية غير متوفرة. رأس المال 1931191. سنة 2025.",
        ]
        for text in negatives:
            evidence = [{'id':'e1', 'quote':text}]
            with self.subTest(text=text):
                self.assertFalse(performance_evidence(evidence))
                result = classify(evidence)
                self.assertNotEqual(result['event_type'], 'FINANCIAL_RESULTS')
                self.assertFalse(any(c['confirmed_evidence_ids'] for c in result['candidates'] if c['code']=='FINANCIAL_RESULTS'))
        for text in ("Chiffre d’affaires exercice 2025 : 12 millions de dinars.", "النتيجة الصافية سنة ٢٠٢٥ : ٣ مليون دينار."):
            with self.subTest(text=text):
                self.assertTrue(performance_evidence([{'id':'e1','quote':text}]))

    def test_triage_configuration_and_badges_do_not_invent_assignment(self):
        from services import pipeline_config, routing
        from ui.components.presentation import _services_badges
        config = pipeline_config.load()
        config['sources']['legaltech']['triage_service'] = 'commercial'
        row = {'kind':'legaltech','title':'Notice','entity':'Example','type':'Modification','raw':{}}
        self.assertEqual(routing.suggest(row, [], config)[0], ['commercial'])
        self.assertNotIn('Conformité', _services_badges([]))
        self.assertIn('triage à confirmer', _services_badges(['compliance'], ['compliance']))
        config['sources']['legaltech']['triage_service'] = 'portfolio'
        with self.assertRaises(ValueError):
            pipeline_config.validate(config)

    def test_rne_filing_is_not_financial_results_and_keeps_structured_boundaries(self):
        from services.canonical_facts import extract
        text = ('Bulletin N°: 236 , Date Publication: 2026-09-18 , Type publication: MODIFICATION , '
                'Identifiant Unique: 0760635K , Dénomination réservée: شركــة إقزابايـــــت , '
                'التسمية المحجوزة: SOCIETE HEXABYTE , Enseigne: HEXABYTE , '
                'Type modification: Dépôt des états financiers , Capital: 1931191 , '
                '1er responsable: وديع الطرابلسي , Qualité: مراقب حسابات , Annonce N°: 2026147091 , '
                "Date de début d’activité: 2001-05-09 , Année comptable: 2025")
        row = {'kind':'legaltech','stable_uid':'rne:2026147091','title':'RNE Publication N°2026147091',
               'entity':'HEXABYTE','date':'2026-09-18','raw':{'card_summary':text}}
        facts = extract(row, text)
        self.assertEqual(facts['event_type'], 'FINANCIAL_STATEMENTS_FILING')
        self.assertEqual(facts['company']['canonical_name'], 'SOCIETE HEXABYTE')
        self.assertEqual(facts['company']['arabic_name'], 'شركــة إقزابايـــــت')
        self.assertEqual(facts['capital']['value'], '1931191')
        self.assertEqual(facts['accounting_year']['value'], '2025')
        self.assertEqual(facts['start_date']['value'], '2001-05-09')
        self.assertEqual(facts['responsible_person']['name'], 'وديع الطرابلسي')
        self.assertEqual(facts['responsible_person']['role'], 'مراقب حسابات')
        self.assertIsNone(facts['performance_facts'])
        from services.event_profiles import enrich
        from services.financial_intelligence import enrich as enrich_financial, note
        enrich(facts); enrich_financial(facts)
        presentation = note(facts, 'investment')
        self.assertIn('Dépôt d’états financiers', presentation['summary'])
        self.assertIn('récupérer les états financiers déposés', presentation['recommendation'])
        self.assertNotIn('conversion en trésorerie avant de réviser', presentation['recommendation'])

    def test_unmatched_legaltech_gets_explicit_triage_service(self):
        from services import pipeline_config, routing
        row = {'kind':'legaltech','title':'Notice','entity':'HEXABYTE','type':'Modification','raw':{'card_text':'Mise à jour administrative'}}
        services, reasons = routing.suggest(row, [], pipeline_config.load())
        self.assertEqual(services, ['compliance'])
        self.assertEqual(reasons[-1]['origin'], 'TRIAGE')
    def test_notification_pagination_detects_a_changed_page_and_end(self):
        from unittest.mock import Mock
        from modules.legaltech_notifications_network_collector import NetworkFirstNotificationsCollector
        collector = object.__new__(NetworkFirstNotificationsCollector)
        page = Mock()
        with patch.object(collector, '_page', return_value=page), \
             patch.object(collector, '_notification_candidates', side_effect=[[{'text':'A'}],[{'text':'B'}]]):
            page.locator.return_value.evaluate.return_value = True
            self.assertTrue(collector._click_next_notification_page())
        with patch.object(collector, '_page', return_value=page), \
             patch.object(collector, '_notification_candidates', return_value=[{'text':'B'}]):
            page.locator.return_value.evaluate.return_value = False
            self.assertFalse(collector._click_next_notification_page())

    def test_financial_events_route_to_investment_without_inventing_holdings(self):
        from services import routing, pipeline_config
        config = pipeline_config.validate(pipeline_config.load())
        for code in ('FINANCIAL_RESULTS', 'SHARE_CANCELLATION', 'INSOLVENCY'):
            row = {'kind':'legaltech', 'title':'Fixture', 'entity':'Fixture', 'type':'Annonce', 'raw':{}}
            with patch.object(routing, 'identify', return_value={'events':[{'code':code}]}):
                services, reasons = routing.suggest(row, [], config)
            self.assertIn('investment', services)
            self.assertNotIn('portfolio', services)
            self.assertTrue(reasons)

    def test_partial_collection_cannot_clear_remote_bell(self):
        from modules.alert_identity import stable_notification_uid
        from modules.legaltech_remote_watcher import collected_notification_map, _pending_comparison
        from services.ui_adapter import _remote_snapshot
        card = {'notification_key':'card', 'company_or_query':'Fixture',
                'notification_date':'2026-01-01', 'announced_result_count':3}
        article = {'notification_key':'card', 'source':'rne', 'article_id':'real',
                   'doc_id':'doc', 'card_title':'Titre', 'card_date':'2026-01-01'}
        alerts = [article, {**article, 'article_id':'network-copy'}, dict(article)]
        uid = stable_notification_uid(card)
        local = collected_notification_map([card], alerts)[uid]
        self.assertEqual(_pending_comparison(card, local), (True, 'NEW_RESULTS', 1, 2))
        remote = {**card, 'remote_uid':uid, 'is_missing_local':0}
        self.assertEqual(_remote_snapshot([card], [remote], [], alerts)['status']['missing_count'], 1)
        alerts += [{**article, 'article_id':str(i), 'doc_id':str(i)} for i in (2,3)]
        self.assertEqual(_remote_snapshot([card], [remote], [], alerts)['status']['missing_count'], 0)

    def test_failed_sync_routes_only_records_actually_collected(self):
        from modules.alert_identity import stable_alert_uid
        from services import operations
        old = {'source':'rne', 'article_id':'old'}
        new = {'source':'rne', 'article_id':'new'}
        uid = stable_alert_uid(new)
        row = {'uid':'legaltech:'+uid, 'stable_uid':uid, 'kind':'legaltech'}
        with patch.object(operations, '_run_command', return_value=(False,'Délai dépassé')), \
             patch('services.ui_adapter.load_workspace', return_value={'alerts':[old,new], 'rows':[row]}), \
             patch('services.ui_adapter.invalidate_cache'), \
             patch('modules.alert_workflow.ensure_alerts') as ensure, \
             patch('modules.alert_workflow.mark_new_alerts') as mark, \
             patch('modules.legaltech_remote_watcher.reconcile_local'), \
             patch('modules.watch_rules.evaluate_alert', return_value={}) as evaluate, \
             patch('modules.business_pipeline_registry.register_notifications') as register, \
             patch.object(operations, 'persist_routing') as route:
            ok, message = operations.sync_legaltech([old])
        self.assertFalse(ok)
        self.assertIn('incomplète', message)
        ensure.assert_called_once_with({uid})
        mark.assert_called_once_with([uid])
        evaluate.assert_called_once_with(new, None, record_hits=True)
        register.assert_called_once_with([row])
        route.assert_called_once_with([row])

    def test_business_counts_exclude_composite_parents_and_failed_outcomes(self):
        from services.lifecycle import successful_results
        records = [
            {'notification_uid':'parent','analysis':{'summary':'Historical bulletin'},'review_status':'draft'},
            {'notification_uid':'child','analysis':{'summary':'Publication','correctness':{'outcome':'SUCCESS_REVIEW_REQUIRED'}},'review_status':'draft'},
            {'notification_uid':'failed','analysis':{'correctness':{'outcome':'SOURCE_MISMATCH'}},'review_status':'draft'},
            {'notification_uid':'historical','analysis':{'summary':'Earlier review'},'review_status':'validated'},
        ]
        workspace = {'rows':[{'uid':'parent','document_status':'Publications détectées'}], 'business_results':records}
        self.assertEqual([r['notification_uid'] for r in successful_results(workspace)], ['child','historical'])

    def test_diffusion_includes_validated_child_and_keeps_service_boundary(self):
        from ui.pages.secondary import diffusion_candidates
        child = {'uid':'cmf-child:fixture', 'services':['compliance'], 'business_results':{'compliance':{'analysis':{'summary':'Fixture'},'review_status':'validated'}}}
        workspace = {'rows':[], 'child_rows':[child]}
        self.assertEqual(diffusion_candidates(workspace,'compliance'), [child])
        self.assertEqual(diffusion_candidates(workspace,'investment'), [])
        child['business_results']['compliance']['review_status']='draft'
        self.assertEqual(diffusion_candidates(workspace,'compliance'), [])

    def test_digest_preview_uses_readable_business_fields_without_transport(self):
        from services.operations import build_digest
        from tests.test_product_freeze import fixture
        row = fixture()['rows'][0]
        subject, text, markup = build_digest('investment', [row])
        self.assertIn('Résumé métier : Résumé isolé investment',text)
        self.assertIn('Actions recommandées : Action isolée',text)
        self.assertNotIn('"business_output"',text)
        self.assertNotIn('"summary"',text)

    def test_capture_aliases_require_unambiguous_full_source_identity(self):
        from modules.alert_identity import confirmed_capture_aliases, stable_alert_uid
        real = dict(source='rne', article_id='article-1', doc_id='document', card_title='Publication', card_date='2026-01-01')
        fallback = dict(real, article_id='network-capture')
        uid = stable_alert_uid(fallback)
        self.assertEqual(confirmed_capture_aliases([real, fallback]), {uid:stable_alert_uid(real)})
        self.assertEqual(confirmed_capture_aliases([real, fallback], ['legaltech:'+uid]), {})
        self.assertEqual(confirmed_capture_aliases([real, fallback, dict(real, article_id='article-2')]), {})
        for field in ('source','doc_id','card_title','card_date'):
            self.assertEqual(confirmed_capture_aliases([real, dict(fallback, **{field:''})]), {})

    def test_es_hit_does_not_create_network_duplicate(self):
        from modules.legaltech_notifications_network_collector import NetworkFirstNotificationsCollector as Collector
        from modules.legaltech_notifications_collector import NotificationItem
        collector = object.__new__(Collector)
        collector.browser = SimpleNamespace(base_url='https://example.invalid')
        notification = NotificationItem('fixture', 'Example', '2026-01-01', 1, 1, '')
        source = {'source': 'rne', 'docId': 'document-1', 'title': 'Publication', 'publishedAt': '2026-01-01'}
        payload = {'hits': {'hits': [{'_id': 'article-1', '_source': source}]}}
        results = collector._alerts_from_payloads(notification, [payload, payload])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].article_id, 'article-1')
        different = {'hits': {'hits': [{'_id': 'article-2', '_source': source}]}}
        self.assertEqual(len(collector._alerts_from_payloads(notification, [payload, different])), 2)

    def test_excel_has_business_labels_and_child_evidence_boundaries(self):
        from modules import business_export
        from openpyxl import load_workbook
        from tests.test_financial_intelligence import prepare, ESG
        row, prepared = prepare(ESG, 'cmf', child=True)
        row.update(source='CMF', source_url='https://example.invalid/source.pdf')
        facts = prepared['facts']
        analysis = {'canonical_facts': facts, 'business_output': {'summary': 'Résumé fixture', 'action_required': '=A1', 'event_type': facts['event_type']},
                    'grounding': {'evidence': facts['source_evidence']}, 'reliability': {'factual_score': 90, 'score': 85}}
        record = {'analysis': analysis, 'service_id': 'compliance', 'model': 'fixture', 'revision': 1, 'review_status': 'draft'}
        with tempfile.TemporaryDirectory() as directory, patch.object(business_export, 'OUTPUT_EXCEL_DIR', Path(directory)):
            path = business_export.export_grounded(row, record)
            book = load_workbook(path)
            self.assertIn('Faits et calculs', book.sheetnames)
            cells = dict(book['Résultat métier'].values)
            self.assertEqual(cells['Service'], 'Conformité')
            self.assertEqual(cells['Action de conformité'], '=A1')
            self.assertIn('Guidance réglementaire', cells['Résumé métier'])
            self.assertEqual(cells['Validation humaine'], 'À valider')
            self.assertNotIn('action_required', cells)
            self.assertTrue(all(c.data_type != 'f' for sheet in book for line in sheet for c in line))
            evidence = list(book['Preuves source'].values)
            self.assertEqual(evidence[0][2:5], ('Page début', 'Page fin', 'Publication enfant'))
            self.assertTrue(all(e[2:5] == ('3', '3', 'fixture-child') for e in evidence[1:]))
            book.close()


if __name__ == '__main__':
    unittest.main()
