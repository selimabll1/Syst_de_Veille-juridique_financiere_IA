"""Behavioral freeze regression checks, using isolated in-memory fixtures."""
from copy import deepcopy
from unittest.mock import patch
import unittest
from streamlit.testing.v1 import AppTest
from tests.test_final_ui import workspace_fixture, ROOT
from services import ui_adapter as adapter, lifecycle
from ui.pages.business_workspace import result_index, needs, value_text, reliability
from ui.pages.workspace import filter_rows
from ui.pages.activity import event_rows


def fixture():
    w=workspace_fixture();w['business_results']=[]
    for row in w['rows']:
        row.update(services=['investment','commercial'],business_results={},analysis_attempts={},service_states={'investment':'À analyser','commercial':'À analyser'},service_priorities={})
    row=w['rows'][0]
    for service,review in [('investment','validated'),('commercial','draft')]:
        record={'notification_uid':row['uid'],'service_id':service,'need_id':'primary','revision':1,'review_status':review,'updated_at':'2026-09-01','analysis':{'service':service,'business_output':{'summary':'Résumé isolé '+service,'recommended_actions':'Action isolée','commercial_relationship':'Aucune relation confirmée'},'reliability':{'score':35}}}
        w['business_results'].append(record);row['business_results'][service]=record
    row['service_states']={'investment':'Traité','commercial':'Analyse terminée'}
    row['status']=lifecycle.aggregate(row['service_states']);row['analysis']=row['business_results']['investment']['analysis']
    return w


class FreezeTests(unittest.TestCase):
    def test_failed_reanalysis_preserves_result_and_exposes_retry(self):
        w = fixture()
        row = w['rows'][0]
        original = deepcopy(row['business_results']['investment'])
        row['analysis_attempts']['investment'] = {'status': 'failed', 'error': 'Délai dépassé'}
        row['ai_state'] = 'failed'
        self.assertEqual(lifecycle.ai_status(row, 'investment'), 'Erreur d’analyse')
        self.assertEqual(lifecycle.ai_status(row), 'Erreur d’analyse')
        self.assertEqual(lifecycle.processing(original, row['analysis_attempts']['investment']), 'Traité')
        self.assertEqual(len(result_index(w)), 2)
        self.assertEqual(row['business_results']['investment'], original)

    def test_result_navigation_replaces_stale_service_selection(self):
        from ui import navigation
        state = {'result_selected': 'another:commercial:primary'}
        with patch.object(navigation.st, 'session_state', state):
            navigation.navigate_to_result('current', 'investment')
            self.assertEqual(state['result_selected'], 'current:investment:primary')
            self.assertEqual(state[navigation.SELECTED], 'current')
            navigation.navigate_with_selection('validation', 'next')
            self.assertNotIn('result_selected', state)

    def test_service_filter_scope_survives_every_row(self):
        w=fixture();second=deepcopy(w['rows'][0]);second['uid']='second'
        self.assertEqual(len(filter_rows([w['rows'][0],second],{'treatment':'Traitées'}, {},service='investment')),2)
        self.assertFalse(filter_rows([w['rows'][0],second],{'treatment':'Traitées'}, {},service='commercial'))
        self.assertFalse(filter_rows([w['rows'][0]],{'treatment':'Traitées'}, {}))

    def test_ai_status_independent_of_read_priority_validation(self):
        r=fixture()['rows'][0]
        self.assertEqual(lifecycle.ai_status(r,'investment'),'Analysée')
        self.assertEqual(lifecycle.ai_status(r,'commercial'),'Analysée')
        r['read']=True;r['priority']='Critique'
        self.assertEqual(lifecycle.aggregate(r['service_states']),'Partiellement traité')
        r['analysis_attempts']['commercial']={'status':'running'}
        self.assertEqual(lifecycle.ai_status(r,'commercial'),'Analyse en cours')

    def test_ai_filters(self):
        w=fixture();rows=w['rows'][:2]
        self.assertEqual(len(filter_rows(rows,{'ai':'Analysée'},{})),1)
        self.assertEqual(len(filter_rows(rows,{'ai':'Non analysée'},{})),1)

    def test_index_excludes_zero_result_keeps_independent_services(self):
        items=result_index(fixture())
        self.assertEqual(len(items),2);self.assertEqual(len({i['key'] for i in items}),2)
        self.assertEqual({i['service'] for i in items},{'investment','commercial'})

    def test_needs_are_per_service(self):
        items=needs(fixture())
        self.assertEqual(sum(i['state']=='Analysée' for i in items),2)
        self.assertEqual(sum(i['state']=='Non analysée' for i in items),48)

    def test_history_sorted_and_no_identifiers_in_business_text(self):
        w=fixture();w['history']=[];w['pipeline_events']=[{'notification_uid':w['rows'][0]['uid'],'service_id':'commercial','event_type':'review_validated','event_at':stamp,'details_json':'{}'} for stamp in ['2026-09-01','2026-09-03']]
        events=event_rows(w);self.assertEqual(events[0]['at'],'2026-09-03')
        self.assertNotIn('legaltech:test',events[0]['text']);self.assertEqual(events[0]['title'],'Résultat validé')

    def test_reliability_does_not_present_prose_as_score(self):
        self.assertIsNone(reliability({'confidence':'Preuves limitées'}))
        self.assertEqual(reliability({'reliability':{'score':0}}),0)
        self.assertNotIn('{',value_text({'obligations':['Lire la source']}))

    def test_result_opens_directly_and_validation_excludes_validated(self):
        w=fixture()
        with patch.object(adapter,'load_workspace',return_value=w),patch.object(adapter,'command',side_effect=AssertionError('Read only')):
            app=AppTest.from_file(str(ROOT/'app.py')).run()
            self.assertEqual(app.session_state['ugfs_page'],'home')
            app.button(key='nav_results').click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any('Résultat métier' in e.value for e in app.markdown))
            self.assertTrue(any(b.label=='✓ Validé' and b.disabled for b in app.button))
            app.button(key='nav_validation').click().run()
            self.assertFalse(app.exception)
            picks=[b for b in app.button if str(b.key).startswith('result_pick_')]
            self.assertEqual(len(picks),1);self.assertIn('commercial',picks[0].key)

    def test_portfolio_empty_state_has_clear_reason(self):
        w=fixture()
        with patch.object(adapter,'load_workspace',return_value=w):
            app=AppTest.from_file(str(ROOT/'app.py')).run();app.button(key='nav_portfolio').click().run()
            self.assertFalse(app.exception);self.assertTrue(app.button(key='portfolio_reference'))

    def test_warning_is_not_error_and_deduplicates_job_cards(self):
        def screen():
            import streamlit as st
            from ui.components.action_status import _body
            st.session_state['ugfs_jobs']=['x','x'];st.session_state['ugfs_jobs_seen']=['x']
            st.session_state['ugfs_notice']=('warning','Vérification LegalTech déjà en cours')
            _body()
        with patch.object(adapter,'action_status',return_value={'label':'Vérification LegalTech','state':'complete','messages':[]}):
            app=AppTest.from_function(screen).run()
            self.assertFalse(app.exception);self.assertEqual(len([b for b in app.button if b.key=='dismiss_x']),1)
            self.assertFalse(app.error)


if __name__=='__main__':unittest.main()
