"""Synthetic PDFs, temporary registries, no network or production mutations."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch

import fitz
from services import composite_documents as c, business_analysis, intelligence, correctness_gates, lifecycle
from modules import business_pipeline_registry as registry, llm_analyzer as engine


class CompositeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        for owner,key,value in [(registry,'DATABASE',self.root/'business.db'),(c,'CACHE',self.root/'pdf')]:
            p=patch.object(owner,key,value);p.start();self.addCleanup(p.stop)
        pdf=self.root/'source.pdf'
        with fitz.open() as d:
            for text in ['AVIS ET COMMUNIQUES DU CMF\nPRECISIONS SUR LES INFORMATIONS ESG 3\nAUTRE PUBLICATION DISTINCTE 4\nANNEXE I',
                         'ANNEXE I\nSommaire',
                         'Page -3-\nPRECISIONS RELATIVES AUX INFORMATIONS ESG\nLe Conseil du Marche Financier apporte des precisions. Les societes doivent examiner les informations ESG. Aucune nouvelle obligation normative. 2026 - AC - 001',
                         'Page -4-\nAUTRE PUBLICATION DISTINCTE\nSOCIETE EXEMPLE BETA : augmentation de capital. Montants et tableaux financiers sans rapport avec la publication precedente. 2026 - AS - 002']:
                d.new_page().insert_textbox(fitz.Rect(40,40,550,750),text,fontsize=10)
            d.save(pdf)
        self.row={'uid':'cmf:fixture','stable_uid':'fixture','kind':'cmf','title':'Bulletin officiel CMF', 'date':'2026-09-01','entity':'CMF','raw':{'section':'bulletin','pdf_url':'https://www.cmf.tn/fixture.pdf'},'pdf_path':str(pdf),'services':['compliance'],'matches':[]}

    def test_composite_bulletin_returns_segmentation_not_ai_failure(self):
        with patch.object(engine,'model_identity') as identity, patch.object(engine,'request_structured') as llm, patch.object(intelligence,'prepare') as facts:
            result=business_analysis.analyze(self.row)
        self.assertTrue(result['ok']);self.assertEqual(result['operation'],'segmentation')
        llm.assert_not_called();identity.assert_not_called();facts.assert_not_called()

    def test_segmentation_creates_stable_children(self):
        c.preprocess(self.row);children=c.children(self.row['uid'])
        self.assertEqual(len(children),2);self.assertNotEqual(children[0]['child_id'],children[1]['child_id'])
        self.assertEqual(children[0]['parent_source_id'],self.row['uid'])
        self.assertEqual(children[0]['pdf_path'],children[1]['pdf_path'])

    def test_resegmentation_is_idempotent(self):
        c.preprocess(self.row);before=c.children(self.row['uid'])
        with patch('fitz.open',side_effect=AssertionError('cache must avoid extraction')):result=c.preprocess(self.row)
        self.assertTrue(result['cached']);self.assertEqual(before,c.children(self.row['uid']))

    def test_child_page_ranges_are_valid(self):
        c.preprocess(self.row)
        for child in c.children(self.row['uid']):
            self.assertTrue(1<=child['page_start']<=child['page_end']<=4)
            self.assertEqual(child['segmentation_status'],'CONFIRMED')

    def test_child_analysis_uses_child_text_only(self):
        c.preprocess(self.row);child=c.children(self.row['uid'])[0];row=c.child_row(self.row,child)
        row['raw']['raw_excerpt']='INJECTED OTHER PUBLICATION'
        text,quality,method=business_analysis.extract_source(row)
        self.assertEqual(text,child['extracted_text']);self.assertNotIn('BETA',text)
        prepared=intelligence.prepare(row,text,quality,method)
        payload,_=intelligence.evidence_package(prepared['facts'],'compliance',__import__('services.pipeline_config',fromlist=['load']).load())
        self.assertNotIn('BETA',json.dumps(payload))
        for e in prepared['facts']['source_evidence']:self.assertEqual(e['page_start'],3);self.assertEqual(e['page_end'],3)

    def test_cross_child_evidence_is_rejected(self):
        c.preprocess(self.row);a,b=c.children(self.row['uid'])
        ra,rb=c.child_row(self.row,a),c.child_row(self.row,b)
        fa=intelligence.prepare(ra,a['extracted_text'],1,'fixture')['facts']
        fb=intelligence.prepare(rb,b['extracted_text'],1,'fixture')['facts']
        self.assertEqual(correctness_gates.evidence_boundaries(fa,{'grounding':{'evidence':fb['source_evidence']}}).outcome,'SOURCE_MISMATCH')
        bad=dict(fa['source_evidence'][0]);bad['page_end']=4
        self.assertEqual(correctness_gates.evidence_boundaries(fa,{'grounding':{'evidence':[bad]}}).outcome,'SOURCE_MISMATCH')

    def test_parent_not_marked_analysis_complete(self):
        business_analysis.analyze(self.row)
        with closing(sqlite3.connect(registry.DATABASE)) as con:
            self.assertEqual(con.execute('SELECT count(*) FROM business_results').fetchone()[0],0)
            self.assertEqual(con.execute('SELECT count(*) FROM business_analysis_attempts').fetchone()[0],0)

    def test_segmentation_required_uses_informational_ui(self):
        from streamlit.testing.v1 import AppTest
        from unittest.mock import patch
        job={'state':'failed','label':'Analyse Conformité','started':1,'finished':81,'error':'SEGMENTATION_REQUIRED','result':None}
        source="""import streamlit as st
from ui.components.action_status import _jobs_body
st.session_state['ugfs_jobs']=['one']
st.session_state['ugfs_jobs_seen']=['one']
st.session_state['ugfs_job_context']={'one':{'uid':'parent','title':'Bulletin','entity':'CMF'}}
_jobs_body()
"""
        with patch('services.ui_adapter.action_status',return_value=job):app=AppTest.from_string(source).run()
        self.assertFalse(app.exception);self.assertFalse(app.error);self.assertTrue(app.info)
        self.assertEqual(lifecycle.processing(attempt={'status':'failed','error':'SEGMENTATION_REQUIRED: composite'}),'Segmentation requise')

    def test_manual_page_range_fallback(self):
        c.preprocess(self.row)
        for start,end in [(0,1),(3,2),(1,5)]:
            with self.assertRaises(ValueError):c.manual(self.row,'Titre',start,end)
        result=c.manual(self.row,'Publication revue',3,3)
        child=next(x for x in c.children(self.row['uid']) if x['child_id']==result['child_id'])
        self.assertNotIn('BETA',child['extracted_text']);self.assertEqual(child['method'],'human_page_range')

    def test_unconfirmed_child_cannot_be_analyzed(self):
        c.preprocess(self.row);doc=c.snapshot(self.row['uid']);child=c.make_child(self.row,doc,'Incertain',3,4,status='REVIEW_REQUIRED');c._save(self.row,doc,[child])
        with self.assertRaises(ValueError):business_analysis.extract_source(c.child_row(self.row,child))

    def test_changed_document_creates_new_version_not_stale_cache(self):
        c.preprocess(self.row);old=c.children(self.row['uid'])[0]['child_id']
        with fitz.open(self.row['pdf_path']) as doc:
            doc[2].insert_text((50,200),'Source revision');doc.saveIncr()
        result=c.preprocess(self.row)
        self.assertFalse(result['cached']);self.assertNotEqual(old,c.children(self.row['uid'])[0]['child_id'])
