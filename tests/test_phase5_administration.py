"""Phase 5 writes are isolated from production configuration and registries."""
from copy import deepcopy
from contextlib import closing
from pathlib import Path
import io
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from services import administration, reference_import, pipeline_config, cmf_relevance, routing
from modules import admin_registry


class AdministrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.config=deepcopy(pipeline_config.load())
        self.path=self.root/'pipeline.json';self.path.write_text(json.dumps(self.config),encoding='utf-8')
        for owner,name,value in [(pipeline_config,'ROOT',self.root),(pipeline_config,'CONFIG_PATH',self.path),(admin_registry,'DATABASE',self.root/'admin.sqlite3')]:
            p=patch.object(owner,name,value);p.start();self.addCleanup(p.stop)
        self.csv=b'name,identifier,type,ownership_pct\nISOLATED COMPANY,TEST-001,portfolio,20\n'

    def test_read_queries_create_nothing(self):
        self.assertEqual(admin_registry.entities(),[])
        self.assertEqual(admin_registry.read('admin_events'),[])
        self.assertFalse(admin_registry.DATABASE.exists())

    def test_preview_does_not_write_and_confirmation_is_required(self):
        p=reference_import.preview('authoritative.csv',self.csv,'portfolio')
        self.assertTrue(p['can_import']);self.assertEqual(p['valid_rows'],1)
        self.assertFalse(admin_registry.DATABASE.exists())
        with self.assertRaises(ValueError): reference_import.commit('authoritative.csv',self.csv,'portfolio',p['sha256'])
        self.assertFalse(admin_registry.DATABASE.exists())

    def test_confirmed_import_provenance_and_duplicate_rejection(self):
        p=reference_import.preview('authoritative.csv',self.csv,'portfolio')
        reference_import.commit('authoritative.csv',self.csv,'portfolio',p['sha256'],True)
        rows=admin_registry.entities();self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['origin'],'authoritative.csv');self.assertEqual(rows[0]['ownership_pct'],'20')
        again=reference_import.preview('newname.csv',self.csv,'portfolio')
        self.assertEqual(len(again['duplicates']),1);self.assertFalse(again['can_import'])
        with self.assertRaises(ValueError): reference_import.commit('newname.csv',self.csv,'portfolio',again['sha256'],True)
        self.assertEqual(len(admin_registry.entities()),1)
        self.assertEqual(len(admin_registry.read('reference_imports')),1)

    def test_template_empty_invalid_rows_and_ambiguous_duplicates(self):
        p=reference_import.preview('participations_template.csv',b'name,identifier,type\n','portfolio')
        self.assertEqual(p['rows'],0);self.assertFalse(p['can_import'])
        invalid=b'name,type,ownership_pct\n,portfolio,10\nCompany,portfolio,101\nDD,pipeline_dd,10\n'
        p=reference_import.preview('invalid.csv',invalid,'portfolio');self.assertEqual(p['invalid_rows'],3)
        p=reference_import.preview('duplicate.csv',b'name,identifier,type\nSAME,ONE,portfolio\nSAME,TWO,portfolio\n','portfolio')
        self.assertFalse(p['can_import']);self.assertEqual(len(p['duplicates']),1)

    def test_json_and_xlsx_preview(self):
        from openpyxl import Workbook
        data=json.dumps([{'name':'FIXTURE FUND','type':'fund','fund_type':'Fixture'}]).encode()
        self.assertTrue(reference_import.preview('funds.json',data,'fund')['can_import'])
        book=Workbook();book.active.append(['code','label','type']);book.active.append(['TEST','Fixture sector','sector'])
        stream=io.BytesIO();book.save(stream);book.close()
        plan=reference_import.preview('gics.xlsx',stream.getvalue(),'sector')
        self.assertTrue(plan['can_import']);self.assertEqual(plan['records'][0]['name'],'Fixture sector')

    def test_dd_or_fund_link_does_not_prove_holding(self):
        refs=[{'name':'PORTFOLIO FIXTURE','type':'portfolio','origin':'test'},{'name':'DD FIXTURE','type':'pipeline_dd','portfolio_company':'PORTFOLIO FIXTURE','origin':'test'}]
        row={'title':'DD FIXTURE','entity':'DD FIXTURE','raw':{}}
        self.assertFalse(routing.portfolio_matches(routing.match(row,refs)))

    def test_exited_or_zero_ownership_does_not_prove_current_holding(self):
        for fields in ({'status':'Sortie'},{'ownership_pct':'0'}):
            record={'name':'FIXTURE','type':'portfolio','origin':'test',**fields}
            self.assertFalse(routing.portfolio_matches(routing.match({'entity':'FIXTURE','title':'FIXTURE','raw':{}},[record])))

    def test_source_eligibility_and_fake_collector_rejected(self):
        for mutate in ('cmf','fake'):
            config=deepcopy(self.config)
            if mutate=='cmf': config['sources']['cmf']['eligible_services']=['investment']
            else: config['sources']['social']['implemented']=True
            with self.assertRaises(ValueError): pipeline_config.validate(config)
        self.assertEqual(set(pipeline_config.eligible('legaltech')),{'investment','portfolio','commercial','compliance'})

    def test_prompt_version_history_activation_and_stale_edit(self):
        old=deepcopy(self.config['services']['investment'])
        changed=deepcopy(self.config);changed['services']['investment']['prompt']+=' Révision isolée.'
        administration.save(changed,administration.fingerprint(self.config),'prompt_version_change')
        current=pipeline_config.load()
        self.assertEqual(current['services']['investment']['prompt_version'],old['prompt_version']+1)
        with self.assertRaises(ValueError): administration.save(changed,administration.fingerprint(self.config),'stale')
        version=next(v for v in administration.prompt_history('investment') if v['prompt']['prompt']==old['prompt'])
        administration.activate_prompt('investment',version['id'],administration.fingerprint(current))
        active=pipeline_config.load()['services']['investment']
        self.assertEqual(active['prompt'],old['prompt']);self.assertEqual(active['prompt_version'],old['prompt_version']+2)
        self.assertGreaterEqual(len(admin_registry.read('configuration_versions')),4)

    def test_create_edit_duplicate_toggle_rule_and_preserve_history(self):
        rule={'name':'Isolated investment','source':'legaltech','services':['investment'],'keywords':['fixture'],'active':True,'priority':'Haute'}
        administration.rule_action('create',rule,administration.fingerprint(pipeline_config.load()))
        rule=pipeline_config.load()['routing_rules'][-1];rule['name']='Edited fixture'
        administration.rule_action('edit',rule,administration.fingerprint(pipeline_config.load()))
        administration.rule_action('duplicate',rule,administration.fingerprint(pipeline_config.load()))
        administration.rule_action('toggle',rule,administration.fingerprint(pipeline_config.load()))
        config=pipeline_config.load();self.assertFalse(next(r for r in config['routing_rules'] if r['id']==rule['id'])['active'])
        self.assertFalse(config['routing_rules'][-1]['active'])
        self.assertEqual(len(admin_registry.read('admin_events')),4)

    def test_cmf_relevance_filters_before_collection_and_without_ai(self):
        items=[{'uid':'yes','title':'Règle obligation fixture','section':'avis'},{'uid':'no','title':'Sport fixture','section':'avis'},{'uid':'excluded','title':'Obligation exclusion','section':'avis'}]
        policy={'configured':True,'categories':['avis'],'keywords':['obligation'],'exclusions':['exclusion']}
        with patch.object(cmf_relevance,'collect_document',side_effect=lambda r:{**r,'raw_excerpt':'texte de fixture'}) as fetch:
            selected,errors=cmf_relevance.relevant_items(items,policy,[])
        self.assertEqual([r['uid'] for r in selected],['yes']);fetch.assert_called_once();self.assertFalse(errors)
        self.assertEqual(len(admin_registry.read('cmf_discovery')),3)

    def test_cmf_unconfigured_and_failed_document_never_promote(self):
        item={'uid':'pending','title':'Fixture','section':'avis'}
        with patch.object(cmf_relevance,'collect_document') as fetch:
            self.assertFalse(cmf_relevance.relevant_items([item],{},[])[0]);fetch.assert_not_called()
        with patch.object(cmf_relevance,'collect_document',side_effect=ValueError('Document indisponible')):
            selected,errors=cmf_relevance.relevant_items([item],{'configured':True,'categories':['avis']},[])
        self.assertFalse(selected);self.assertTrue(errors)

    def test_reference_role_and_gics_rules_use_real_matches(self):
        config=deepcopy(self.config);config['routing_rules']=[{'id':'fixture','name':'Fixture','source':'legaltech','services':['commercial'],'gics':['TEST'],'entity_role':'client'}]
        row={'kind':'legaltech','title':'Fixture','entity':'Fixture','type':'Notice','raw':{}}
        match={'name':'Fixture','type':'pipeline_dd','gics_l4':'TEST','role_ugfs':'client','match_reason':'Fixture'}
        self.assertEqual(routing.suggest(row,[match],config)[0],['commercial'])
        self.assertEqual(routing.suggest(row,[],config)[0], ['compliance'])


class AdministrationUITests(unittest.TestCase):
    def test_every_admin_tab_and_empty_template_preview(self):
        from streamlit.testing.v1 import AppTest
        from tests.test_final_ui import workspace_fixture
        from services import ui_adapter as adapter
        root=Path(__file__).resolve().parents[1]
        fixture=workspace_fixture()
        fixture['rows']=[];fixture['results']=[];fixture['pipeline_config']=pipeline_config.load()
        fixture['referential_entities']=[];fixture['business_results']=[]
        with tempfile.TemporaryDirectory() as folder, patch.object(admin_registry,'DATABASE',Path(folder)/'admin.sqlite3'), patch.object(adapter,'load_workspace',side_effect=lambda:deepcopy(fixture)), patch.object(adapter,'command',side_effect=AssertionError('No write on navigation')):
            app=AppTest.from_file(str(root/'app.py')).run(timeout=45)
            app.button(key='nav_reference').click().run()
            for tab in ['Vue d’ensemble','Participations','Pipeline DD','Fonds','Dirigeants','Actionnaires','GICS L4','Imports']:
                app.session_state['admin_reference_tab']=tab;app.run()
                self.assertFalse(app.exception,[e.message for e in app.exception])
            app.button(key='preview_template').click().run()
            self.assertFalse(app.exception)
            self.assertTrue(app.button(key='commit_reference').disabled)
            app.button(key='nav_settings').click().run()
            for tab in ['Vue d’ensemble','Sources','Règles de veille','Services & routage','Prompts IA','Utilisateurs','Paramètres généraux']:
                app.session_state['admin_settings_tab']=tab;app.run()
                self.assertFalse(app.exception,[e.message for e in app.exception])
            self.assertFalse(admin_registry.DATABASE.exists())
