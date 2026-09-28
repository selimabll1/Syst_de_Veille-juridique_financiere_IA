"""Generic Phase 6 regression: isolated storage and non-production fixtures."""
from copy import deepcopy
from contextlib import closing
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from services import canonical_facts as facts, intelligence, business_analysis, pipeline_config, routing
from modules import business_pipeline_registry as registry, llm_analyzer as engine

TEXT='AVIS DE RÉDUCTION DE CAPITAL ALPHA EXEMPLE Société Anonyme. Le capital est ramené de 100 000 dinars à 80 000 dinars. La réduction du capital est effectuée pour un montant de 20 000 dinars par rachat de 2 000 actions de valeur nominale de 10 dinars. Réunion du 14 septembre 2026.'


class IntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.config=pipeline_config.load()
        self.row={'uid':'legaltech:fixture6','stable_uid':'fixture6','kind':'legaltech','source':'LegalTech','entity':'ALPHA EXEMPLE','title':'Annonce de test','date':'2026-09-20','type':'Annonce','services':['investment'],'matches':[],'raw':{'detail_text':TEXT}}
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        p=patch.object(registry,'DATABASE',Path(self.temp.name)/'business.sqlite3');p.start();self.addCleanup(p.stop)
        p=patch.object(engine,'model_identity',return_value='test-model-digest');p.start();self.addCleanup(p.stop)

    def select(self,prompt,*,system_prompt,schema):
        ids=schema['properties']['summary_evidence']['items']['enum']
        return {'summary_evidence':ids[:2],'focus_evidence':ids[2:5],'action_ids':['monitor']}

    def test_financial_equations_and_signed_change(self):
        f=facts.extract(self.row,TEXT)
        self.assertEqual(f['event_type'],'CAPITAL_REDUCTION')
        self.assertEqual(f['capital_change']['value'],'-20000')
        self.assertEqual(f['validation']['status'],'VERIFIED')
        self.assertEqual(float(f['validation']['percentage_variation']['value']),-20)
        for e in f['source_evidence']:self.assertEqual(TEXT[e['start']:e['end']],e['quote'])

    def test_company_and_amount_metamorphism(self):
        for company in ['BETA EXEMPLE','GAMMA EXEMPLE','DELTA EXEMPLE']:
            t=TEXT.replace('ALPHA EXEMPLE',company).replace('100 000','200 000').replace('80 000','180 000')
            f=facts.extract({**self.row,'entity':company},t)
            self.assertEqual(f['company']['value'],company);self.assertEqual(f['validation']['status'],'VERIFIED')

    def test_arabic_numbers_and_equations(self):
        text='اعلان تخفيض رأس المال شركة مثال. تم تخفيض رأس مال الشركة من ١٠٠.٠٠٠ دينار إلى ٨٠.٠٠٠ دينار. تخفيض رأس المال بمبلغ قدره ٢٠.٠٠٠ دينار عن طريق شراء ٢.٠٠٠ سهما بقيمة اسمية قدرها ١٠ دنانير. الجلسة بتاريخ ١٤ جويلية ٢٠٢٦.'
        f=facts.extract(self.row,text)
        self.assertEqual(f['language'],'ar');self.assertEqual(f['validation']['status'],'VERIFIED')
        self.assertIn('2026-07-14',[d['value'] for d in f['dates']])

    def test_number_formats(self):
        for raw,value in [('41.367,200','41367.200'),('١٢٣٬٤٥٦٫٧٨','123456.78'),('47.990','47990'),('1 234,50','1234.50')]:self.assertEqual(facts.number(raw),value)

    def test_inconsistent_and_missing_financials(self):
        self.assertEqual(facts.extract(self.row,TEXT.replace('80 000','81 000'))['validation']['status'],'INCONSISTENT')
        self.assertIsNone(facts.extract(self.row,'Une réduction de capital est annoncée ; montants non communiqués.')['capital_change'])

    def test_dates_publication_not_deadline(self):
        f=facts.extract(self.row,TEXT+' Dépôt au plus tard le 30/09/2026. Effet à compter du 01/10/2026.')
        self.assertEqual([d['value'] for d in f['deadlines']],['2026-09-30'])
        self.assertEqual([d['value'] for d in f['effective_dates']],['2026-10-01'])
        self.assertNotIn('2026-09-20',[d['value'] for d in f['deadlines']])

    def test_unknown_and_negated_event(self):
        for text in ['Aucune réduction de capital décidée.','Document source de nature inconnue.']:
            self.assertEqual(facts.extract(self.row,text)['event_type'],'UNKNOWN')

    def test_all_event_types_have_source_trigger(self):
        from services.event_taxonomy import TAXONOMY,classify
        for code,(_,_,terms) in TAXONOMY.items():
            if not terms:continue
            result=classify([{'id':'S1','quote':terms[0]}])
            self.assertIn(code,[c['code'] for c in result['candidates']])

    def test_evidence_selector_finds_late_event_with_budget(self):
        text=('Texte administratif sans fait nouveau. '*1000)+TEXT
        f=facts.extract(self.row,text);payload,selected=intelligence.evidence_package(f,'investment',self.config)
        self.assertLessEqual(len(json.dumps(payload,ensure_ascii=False)),8000)
        self.assertTrue(any('80 000' in e['quote'] for e in selected))

    def test_multi_document_never_combines_capital(self):
        row={**self.row,'kind':'cmf','raw':{'section':'bulletins'}}
        f=facts.extract(row,TEXT)
        self.assertEqual(f['event_type'],'UNKNOWN');self.assertIsNone(f['capital_change'])

    def test_claims_reject_invented_text_and_citations(self):
        evidence=[{'id':'S1','quote':'Un fait source.'}]
        for claim in [{'kind':'FACT','text':'Croissance de 20 %.','evidence_ids':['S1']},{'kind':'FACT','text':'Un fait source.','evidence_ids':['BAD']}]:self.assertEqual(intelligence.validate_claims([claim],evidence),['UNSUPPORTED_CLAIM'])

    def test_invalid_model_claim_not_persisted(self):
        with patch.object(engine,'request_structured',return_value={'summary_evidence':['S1'],'focus_evidence':[],'action_ids':[],'person':'Invented'}):
            result=business_analysis.analyze(self.row)
        self.assertFalse(result['ok'])
        with closing(sqlite3.connect(registry.DATABASE)) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM business_results').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT status FROM business_analysis_attempts').fetchone()[0],'failed')

    def test_commerce_without_reference_has_no_opportunity(self):
        r={**self.row,'services':['commercial']}
        with patch.object(engine,'request_structured',side_effect=self.select):result=intelligence.analyze_prepared(r,'commercial',intelligence.prepare(r,TEXT,1,'fixture'),self.config)
        self.assertEqual(result['business_output']['commercial_relevance'],'Non déterminée')
        self.assertEqual(result['business_output']['supported_opportunity'],'Non')
        self.assertLessEqual(result['reliability']['score'],35)

    def test_portfolio_requires_authoritative_match(self):
        with patch.object(engine,'request_structured') as call,self.assertRaisesRegex(ValueError,'Aucune correspondance'):
            intelligence.analyze_prepared({**self.row,'services':['portfolio']},'portfolio',intelligence.prepare(self.row,TEXT,1,'fixture'),self.config)
        call.assert_not_called()

    def test_reliability_is_deterministic_and_capped(self):
        f=facts.extract(self.row,TEXT.replace('80 000','81 000'))
        r=intelligence.reliability(f,'investment');self.assertLessEqual(r['score'],30)
        self.assertEqual(sum(r['weights'].values()),1)
        self.assertLessEqual(intelligence.reliability(f,'investment',unsupported=1)['score'],20)

    def test_cache_preserves_human_validation_and_force_creates_version(self):
        with patch.object(engine,'request_structured',side_effect=self.select) as call:
            self.assertTrue(business_analysis.analyze(self.row)['ok'])
            registry.review(self.row,'investment','validated')
            self.assertEqual(business_analysis.analyze(self.row)['cached'],['investment'])
            self.assertEqual(call.call_count,1)
            with closing(sqlite3.connect(registry.DATABASE)) as c:self.assertEqual(c.execute('SELECT review_status FROM business_results').fetchone()[0],'validated')
            self.assertTrue(business_analysis.analyze(self.row,force=True)['ok']);self.assertEqual(call.call_count,2)
        with closing(sqlite3.connect(registry.DATABASE)) as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM business_result_versions').fetchone()[0],2)

    def test_cache_relevant_changes(self):
        p=intelligence.prepare(self.row,TEXT,1,'fixture');key=intelligence.cache_key(p,'investment',self.config,'digest')
        self.assertNotEqual(key,intelligence.cache_key(p,'investment',self.config,'new-digest'))
        config=deepcopy(self.config);config['services']['investment']['prompt']+=' changed'
        self.assertNotEqual(key,intelligence.cache_key(p,'investment',config,'digest'))
        p['facts']['referential_matches']=[{'name':'fixture','role_ugfs':'client'}]
        self.assertNotEqual(key,intelligence.cache_key(p,'investment',self.config,'digest'))

    def test_timeout_no_fake_success(self):
        with patch.object(engine,'request_structured',side_effect=TimeoutError('Local timeout')):
            self.assertFalse(business_analysis.analyze(self.row)['ok'])

    def test_cmf_stays_compliance_only(self):
        with self.assertRaises(ValueError):business_analysis.analyze({**self.row,'kind':'cmf'})

    def test_empty_explicit_service_list_is_not_all_services(self):
        with self.assertRaises(ValueError):business_analysis.analyze(self.row,[])

    def test_conflicting_figures_abstain_and_flag(self):
        f=facts.extract(self.row,TEXT+' Une réduction du capital pour un montant de 25 000 dinars est aussi indiquée.')
        self.assertIsNone(f['capital_change'])
        self.assertEqual(f['validation']['status'],'INCONSISTENT')

    def test_money_scale_and_no_invented_commercial_relation(self):
        f=facts.extract(self.row,'Une opération de 1,5 million de dinars est évoquée dans cette annonce source.')
        self.assertEqual(f['amounts'][0]['value'],'1500000.0')
        self.assertFalse(f['relationships']['commercial'])

    def test_query_label_does_not_establish_portfolio_subject(self):
        row={**self.row,'entity':'UNRELATED','matches':[{'name':'UNRELATED','type':'portfolio','portfolio_verified':True,'origin':'isolated','record_id':'fixture'}]}
        f=facts.extract(row,TEXT)
        self.assertFalse(f['relationships']['portfolio'])

    def test_invented_recommendation_and_interpretation_rejected(self):
        for kind in ['RECOMMENDATION','INTERPRETATION']:
            self.assertEqual(intelligence.validate_claims([{'kind':kind,'text':'Investir : croissance garantie de 20 %.','evidence_ids':['S1'],'policy_id':'monitor'}],[{'id':'S1','quote':'Une assemblée se réunit.'}]),['UNSUPPORTED_CLAIM'])
