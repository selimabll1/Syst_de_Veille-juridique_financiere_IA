"""Phase 6.1 contracts, using isolated fixtures and no production writes."""
from copy import deepcopy
from contextlib import closing
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from services import lifecycle, priority, intelligence, pipeline_config, result_presentation
from ui.pages.workspace import filter_rows
from modules import llm_analyzer as engine, business_pipeline_registry as registry
from tests.test_phase6_intelligence import TEXT

WARNING='Le Conseil du Marché Financier publie une mise en garde contre des tentatives d’escroquerie numérique. Le public et les investisseurs sont invités à la vigilance et à vérifier les coordonnées officielles.'

def row():
    return dict(uid='fixture61',stable_uid='fixture61',kind='cmf',services=['compliance'],business_results={},service_states={'compliance':'À analyser'},status='À analyser',treated=False,read=True,date='2026-09-21',priority='Non classée',raw={},entity='',title='Mise en garde',matches=[],tags=[],documents=[])

def prepared(text=WARNING):
    return intelligence.prepare(row(),text,1,'fixture')['facts']

class SemanticsTests(unittest.TestCase):
    def test_unanalysed_cmf_no_implicit_priority(self):
        r=row();r['raw']['priority']='Moyenne';priority.apply(r,{})
        self.assertEqual((r['priority'],r['status'],r['priority_provenance']['origin']),('Moyenne','À analyser','PROVISIONAL'))

    def test_explicit_rule_and_human_override(self):
        r=row();r['rule_matches']=[dict(priority='Haute',rule='Sanction réglementaire CMF',services=['compliance'])]
        priority.apply(r,{})
        self.assertEqual(r['priority_provenance']['origin'],'RULE');self.assertEqual(r['priority'],'Haute')
        r['priority_overrides']={'compliance':'Basse'};priority.apply(r,{})
        self.assertEqual((r['priority'],r['priority_provenance']['origin']),('Basse','HUMAN'))

    def test_validated_and_analysis_policy_precedence(self):
        r=row();r['business_results']={'compliance':{'review_status':'validated','analysis':{'metrics':{'regulatory_severity':'Revue prioritaire'}}}}
        r['rule_matches']=[dict(priority='Critique',rule='Rule',services=['compliance'])]
        priority.apply(r,{});self.assertEqual((r['priority'],r['priority_provenance']['origin']),('Haute','VALIDATED_RESULT'))
        r['business_results']['compliance']['review_status']='draft';priority.apply(r,{})
        self.assertEqual(r['priority_provenance']['origin'],'ANALYSIS_POLICY')

    def test_source_policy_requires_configuration(self):
        r=row();priority.apply(r,{'sources':{'cmf':{'priority_policy':{'compliance':{'enabled':True,'value':'Basse'}}}}})
        self.assertEqual((r['priority'],r['priority_provenance']['origin']),('Basse','SOURCE_POLICY'))

    def test_partial_treatment_exact_filter_contract(self):
        r=row();r.update(services=['investment','commercial'],service_states={'investment':'Traité','commercial':'Analyse terminée'})
        r['status']=lifecycle.aggregate(r['service_states']);self.assertEqual(r['status'],'Partiellement traité')
        for service,yes in [(None,False),('investment',True),('commercial',False)]:
            for label,expected in [('Traitées',yes),('Non traitées',not yes)]:
                self.assertEqual(bool(filter_rows([r],{'treatment':label},{},service=service)),expected)

    def test_read_state_never_changes_treatment(self):
        r=row();r.update(treated=True,status='Traité',service_states={'compliance':'Traité'})
        for read in (False,True):
            r['read']=read
            self.assertTrue(filter_rows([r],{'treatment':'Traitées'},{}))
            self.assertFalse(filter_rows([r],{'treatment':'Non traitées'},{}))
            self.assertEqual(lifecycle.scoped(r,'compliance')['status'],'Traité')

    def test_service_priorities_independent(self):
        r=row();r['services']=['investment','commercial'];r['priority_overrides']={'investment':'Haute'}
        priority.apply(r,{})
        self.assertEqual(r['priority'],'Haute');self.assertEqual(lifecycle.scoped(r,'commercial')['priority'],'Moyenne')
        self.assertEqual(lifecycle.scoped(r,'investment')['priority'],'Haute')

    def test_no_company_warning_not_capped(self):
        f=prepared();self.assertIsNone(f['company'])
        r=intelligence.reliability(f,'compliance')
        self.assertGreater(r['score'],80);self.assertEqual(r['caps'],[])
        self.assertIsNone(r['components']['financial_consistency']);self.assertIsNone(r['components']['entity_resolution'])

    def test_missing_required_company_cap(self):
        f=prepared(TEXT);f['company']=None
        r=intelligence.reliability(f,'investment');self.assertLessEqual(r['score'],60)
        self.assertTrue(any('Société' in c['reason'] for c in r['caps']))

    def test_general_regulation_and_reporting_no_company_gate(self):
        for event in ('REGULATION','REPORTING_OBLIGATION'):
            f=prepared();f['event_type']=event;f['obligations_identified']=f['warning_content']
            r=intelligence.reliability(f,'compliance')
            self.assertFalse(any('Société' in c['reason'] for c in r['caps']))
            self.assertIsNone(r['components']['financial_consistency'])

    def test_missing_authority_penalized(self):
        f=prepared();f['issuing_authority']=None
        self.assertLessEqual(intelligence.reliability(f,'compliance')['score'],55)

    def test_factual_reliability_distinct_from_commerce(self):
        f=prepared(TEXT);r=intelligence.reliability(f,'commercial')
        self.assertGreater(r['factual_score'],80);self.assertLessEqual(r['score'],35)

    def test_invented_warning_claim_rejected(self):
        f=prepared();e=f['source_evidence'][0]
        for text in ['Société inventée visée','Échéance 31 décembre 2026','UGFS doit déposer une déclaration']:
            self.assertEqual(intelligence.validate_claims([{'kind':'FACT','text':text,'evidence_ids':[e['id']]}],[e]),['UNSUPPORTED_CLAIM'])

    def test_summary_separate_and_whole_source_message(self):
        f=prepared(TEXT);s=result_presentation.synthesis(f)
        self.assertNotIn('[S',s['text']);self.assertIn('20 000',s['text']);self.assertTrue(s['evidence_ids'])
        msg=result_presentation.selection_message({'evidence_selection_status':'FULL_SOURCE_SCANNED','source_truncated':True})
        self.assertNotIn('début',msg);self.assertIn('extraits pertinents',msg)

    def test_priority_override_persisted_in_isolation(self):
        from services import ui_adapter as adapter
        import sqlite3
        with tempfile.TemporaryDirectory() as tmp,patch.object(registry,'DATABASE',Path(tmp)/'test.sqlite3'):
            adapter.command('set_priority',row(),'compliance','Haute')
            with closing(sqlite3.connect(registry.DATABASE)) as c:
                self.assertEqual(c.execute("select event_type from business_pipeline_events where event_type='priority_override'").fetchone()[0],'priority_override')

    def test_all_four_visible_result_fields(self):
        from services import ui_adapter as adapter
        from tests.test_final_ui import workspace_fixture
        from ui.pages.workspace import detail
        config=pipeline_config.load()
        for service in intelligence.FIELDS:
            r=row();r['kind']='legaltech';r['services']=[service]
            prep=intelligence.prepare(r,TEXT,1,'fixture')
            if service=='portfolio':
                prep['facts']['referential_matches']=[{'name':'ALPHA EXEMPLE','type':'portfolio','portfolio_verified':True,'affected_portfolio_entity':'ALPHA EXEMPLE','match_reason':'Fixture only'}]
            def select(prompt,*,system_prompt,schema):
                ids=schema['properties']['summary_evidence']['items']['enum']
                return {'summary_evidence':ids[:2],'focus_evidence':ids[2:5],'action_ids':['monitor']}
            with patch.object(engine,'request_structured',side_effect=select):
                result=intelligence.analyze_prepared(r,service,prep,config)
            w=workspace_fixture();display=w['rows'][0];display.update(services=[service],business_results={service:{'analysis':result,'review_status':'draft'}},service_states={service:'Analyse terminée'},analysis=result)
            def app(display,w,service):
                from ui.pages.workspace import detail
                detail(display,w,preferred_service=service)
            with patch.object(adapter,'command',side_effect=AssertionError('No writes')):
                app_test=AppTest.from_function(app,args=(display,w,service)).run(timeout=30)
            self.assertFalse(app_test.exception)
            visible=' '.join(e.value for e in app_test.markdown)
            self.assertIn(result['business_output'][result_presentation.RECOMMENDATIONS[service]],visible)
            self.assertIn('Résumé métier',visible);self.assertIn('Incertitudes',visible);self.assertIn('Preuves source',visible)
            self.assertTrue(any(e.label=='Données techniques de l’analyse' and not e.proto.expanded for e in app_test.expander))


    def test_task_card_states_without_fake_progress(self):
        from services import ui_adapter as adapter
        import time
        for state in ('running','complete','failed'):
            job={'label':'Analyse Commerce','state':state,'started':time.time()-14,'stage':'inference','completed_stages':['extraction','facts','evidence'],'service':'commercial','error':'Timeout réel de test' if state=='failed' else '', 'result':None}
            def app():
                import streamlit as st
                from ui.components.action_status import _body
                st.session_state['ugfs_jobs']=['test']
                st.session_state['ugfs_jobs_seen']=['test']
                st.session_state['ugfs_job_context']={'test':{'uid':'fixture','entity':'Entité de test','title':'Événement de test','retry':('Analyse','ollama','run_analysis',(),{})}}
                _body()
            with patch.object(adapter,'action_status',return_value=job):at=AppTest.from_function(app).run()
            self.assertFalse(at.exception)
            self.assertTrue(at.expander or at.status)
            text=' '.join(e.value for e in list(at.caption)+list(at.markdown))
            self.assertNotIn('%',text)
            self.assertIn('○ Contrôle de cohérence',text)
            if state=='complete':self.assertTrue(any(b.label=='Voir le résultat' for b in at.button))
            if state=='failed':self.assertTrue(any(b.label=='Réessayer' for b in at.button))
