"""Read-only dashboard projections and native navigation contracts."""
from copy import deepcopy
from unittest.mock import patch
import unittest
from streamlit.testing.v1 import AppTest
from tests.test_final_ui import workspace_fixture,ROOT
from services import ui_adapter as adapter
from ui.pages.home import dashboard_data,short_date

class HomeTests(unittest.TestCase):
    def test_counts_and_no_mutation(self):
        w=workspace_fixture();before=deepcopy(w);v=dashboard_data(w)
        self.assertEqual(v['services']['investment']['count'],25)
        self.assertEqual(len(v['recent']),5);self.assertEqual(w,before)
        self.assertEqual(v['references'],0)

    def test_empty_dashboard(self):
        w=workspace_fixture();w.update(rows=[],results=[],sources=[],business_results=[])
        with patch.object(adapter,'load_workspace',return_value=w),patch.object(adapter,'command',side_effect=AssertionError('No writes')):
            at=AppTest.from_file(str(ROOT/'app.py'));at.session_state['ugfs_page']='home';at.run()
            self.assertFalse(at.exception)
            text=' '.join(m.value for m in at.markdown)
            self.assertIn('Aucune activité récente',text);self.assertIn('Référentiel non renseigné',text)

    def test_all_navigation_and_no_commands(self):
        w=workspace_fixture()
        with patch.object(adapter,'load_workspace',return_value=w),patch.object(adapter,'command',side_effect=AssertionError('No writes')):
            at=AppTest.from_file(str(ROOT/'app.py'));at.session_state['ugfs_page']='home';at.run()
            for key,page in [('home_investment','investment'),('home_compliance','compliance'),('home_portfolio','portfolio'),('home_commercial','commercial'),('home_all','notifications'),('home_validation','validation'),('home_sources_link','settings'),('home_reference_link','reference'),('home_row_legaltech:test-0','notifications')]:
                at.button(key=key).click().run(timeout=30)
                self.assertFalse(at.exception)
                self.assertEqual(at.session_state['ugfs_page'],page)
                if key=='home_sources_link':self.assertEqual(at.session_state['admin_settings_tab'],'Sources')
                if key.startswith('home_row'):self.assertEqual(at.session_state['ugfs_selected_uid'],'legaltech:test-0')
                at.button(key='nav_home').click().run()

    def test_job_dismissal(self):
        def app():
            import streamlit as st
            from ui.components.action_status import _body
            st.session_state['ugfs_jobs']=['home-test'];st.session_state['ugfs_jobs_seen']=['home-test']
            st.session_state['ugfs_job_context']={'home-test':{'uid':'fixture','entity':'Test','title':'Test','retry':()}}
            _body()
        job={'label':'Analyse Commerce','state':'complete','started':0,'finished':42,'stage':'persistence','service':'commercial'}
        with patch.object(adapter,'action_status',return_value=job):
            at=AppTest.from_function(app).run();at.button(key='dismiss_home-test').click().run()
            self.assertFalse(at.exception);self.assertFalse(at.button)

    def test_path_feedback_is_compact(self):
        w=workspace_fixture()
        with patch.object(adapter,'load_workspace',return_value=w):
            at=AppTest.from_file(str(ROOT/'app.py'));at.session_state['ugfs_page']='home'
            at.session_state['ugfs_notice']=('success',r'C:\Users\Example\report.xlsx');at.run()
            visible=' '.join(x.value for x in at.markdown)
            self.assertNotIn('C:\\Users',visible)
            self.assertTrue(any(e.label=='Détails de l’opération' and not e.proto.expanded for e in at.expander))
            at.button(key='notice_close').click().run();self.assertFalse(at.exception)
