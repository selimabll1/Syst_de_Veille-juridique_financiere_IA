"""Executable financial golden cases. Synthetic, isolated, no production writes."""
from copy import deepcopy
from decimal import Decimal
import unittest
from unittest.mock import patch

from services import intelligence, financial_intelligence as fi, pipeline_config
from modules import llm_analyzer

CAPITAL = 'AVIS DE RÉDUCTION DE CAPITAL ALPHA Société Anonyme. Le capital est ramené de 100 000 dinars à 80 000 dinars. La réduction du capital pour un montant de 20 000 dinars résulte du rachat de 2 000 actions de valeur nominale de 10 dinars.'
ESG = 'Le Conseil du Marché Financier publie des précisions relatives aux informations ESG dans les notes aux états financiers des sociétés faisant appel public à l’épargne. Elles s’inscrivent dans une logique transitoire pour l’exercice clos au 31 décembre 2025 et ne créent pas, à ce titre, d’obligations nouvelles de nature normative.'
CASES = [
    ('capital_reduction', CAPITAL, 'CAPITAL_REDUCTION', 'investment', {'capital_before':'100000','capital_change':'-20000','capital_after':'80000'}, 'Variation du capital (%)', 'Recommandation UGFS'),
    ('capital_increase', CAPITAL.replace('RÉDUCTION','AUGMENTATION').replace('réduction','augmentation').replace('80 000','120 000').replace('rachat','émission'), 'CAPITAL_INCREASE', 'investment', {'capital_after':'120000'}, 'Variation du capital (%)', 'Recommandation UGFS'),
    ('bond', 'Émetteur : ALPHA\nÉmission d’un emprunt obligataire. Montant émis : 12 MDT. Coupon : 7 %. Maturité : 5 ans.', 'BOND_ISSUANCE','investment',{'issued_amount':'12000000','coupon':'7'},None,'coupon'),
    ('financial_results','Résultats financiers. Chiffre d’affaires exercice 2024 : 10 MDT; chiffre d’affaires exercice 2025 : 12 MDT; résultat net exercice 2025 : 2 MDT.', 'FINANCIAL_RESULTS','investment',{'revenue':'12000000','net_income':'2000000'},'Chiffre d’affaires — variation (%)','périodes comparables'),
    ('acquisition','Acquisition de titres de la société BETA. Acquéreur : ALPHA\nPrix d’acquisition : 3 millions de dinars.', 'ACQUISITION','investment',{'transaction_amount':'3000000'},None,'périmètre acquis'),
    ('disposal','Cession de parts sociales. Cédant : ALPHA\nPrix de cession : 500 milliers de dinars.', 'DISPOSAL','investment',{'transaction_amount':'500000'},None,'valeur comptable'),
    ('distress','La société ALPHA annonce sa liquidation. Les créanciers sont invités à consulter les modalités de la procédure.', 'LIQUIDATION','investment',{},None,'procédure'),
    ('governance','Renouvellement du conseil d’administration. Directeur : Karim Exemple', 'BOARD_CHANGE','investment',{},None,None),
    ('dividend','Distribution d’un dividende. Dividendes distribués exercice 2025 : 2 MDT; résultat net exercice 2025 : 4 MDT.', 'DIVIDEND','investment',{'dividends':'2000000'},'Distribution / résultat (%)','montant voté'),
    ('esg',ESG,'REGULATORY_GUIDANCE','compliance',{},None,'sociétés suivies'),
    ('warning','Le Conseil du Marché Financier publie une mise en garde contre les offres de services financiers sans agrément. Le public est invité à la vigilance.', 'PUBLIC_WARNING','compliance',{},None,'agréments'),
    ('composite_child',ESG,'REGULATORY_GUIDANCE','compliance',{},None,'sociétés suivies'),
    ('arabic','اعلان تخفيض رأس المال شركة مثال. تم تخفيض رأس مال الشركة من ١٠٠.٠٠٠ دينار إلى ٨٠.٠٠٠ دينار. تخفيض رأس المال بمبلغ قدره ٢٠.٠٠٠ دينار عن طريق شراء ٢.٠٠٠ سهما بقيمة اسمية قدرها ١٠ دنانير.', 'CAPITAL_REDUCTION','investment',{'capital_change':'-20000'},'Variation du capital (%)','Recommandation UGFS'),
    ('mixed',CAPITAL+' تفاصيل رسمية للمعاملة.', 'CAPITAL_REDUCTION','investment',{'share_counts':'2000'},'Actions × nominal','Recommandation UGFS'),
]


def prepare(text, source='legaltech', child=False):
    row={'uid':'fixture','stable_uid':'fixture','kind':source,'source':source,'title':'Fixture',
         'entity':'ALPHA','date':'2026-01-01','raw':{},'services':['investment','compliance'],'matches':[]}
    if child:
        row['raw']={'child_publication_id':'fixture-child'}
        row['child_publication']={'child_id':'fixture-child','parent_source_id':'fixture-parent','page_start':3,'page_end':8,
            'extraction_hash':'fixture-hash','document_hash':'fixture-document','parent_title':'Fixture bulletin',
            'page_spans':[{'page':3,'start':0,'end':len(text)}]}
    return row, intelligence.prepare(row,text,1,'fixture')


class FinancialGoldenTests(unittest.TestCase):
    def test_golden_cases(self):
        for name,text,event,service,expected,calculation,action in CASES:
            with self.subTest(case=name):
                row,p=prepare(text,'cmf' if service=='compliance' else 'legaltech',child=name=='composite_child')
                facts=p['facts'];self.assertEqual(facts['event_type'],event)
                data=facts['financial_enrichment']
                for key,value in expected.items():
                    self.assertTrue(any(n['concept']==key and Decimal(n['normalized_value'])==Decimal(value) for n in data['numbers']),key)
                if calculation:self.assertIn(calculation,[m['name'] for m in data['derived_metrics']])
                note=fi.note(facts,service)
                if action:self.assertIn(action,note['recommendation'])
                self.assertTrue(fi.validate_enrichment(facts))
                if name=='composite_child':
                    self.assertTrue(all(e['child_publication_id']=='fixture-child' and 3<=e['page_start']<=e['page_end']<=8 for e in facts['source_evidence']))
                self.assertTrue(set(note['evidence_ids'])<={e['id'] for e in facts['source_evidence']})
                # Forbidden positive conclusions must not leak into generated prose.
                generated=' '.join(s['text'] for s in note['sections'])
                for forbidden in ['rendement garanti','sous-évaluée','UGFS détient','croissance garantie']:
                    self.assertNotIn(forbidden,generated)

    def test_exact_financial_results(self):
        _,p=prepare(CASES[3][1]);metrics={m['name']:Decimal(m['result']) for m in p['facts']['financial_enrichment']['derived_metrics']}
        self.assertEqual(metrics['Chiffre d’affaires — variation (%)'],20)
        self.assertEqual(metrics['Chiffre d’affaires — variation'],2000000)
        self.assertAlmostEqual(float(metrics['Marge nette (%)']),100/6)

    def test_no_incompatible_period_currency_or_zero_denominator(self):
        for text in [
            'Chiffre d’affaires H1 2024 : 10 MDT; chiffre d’affaires exercice 2025 : 12 MDT.',
            'Chiffre d’affaires exercice 2024 : 10 EUR; chiffre d’affaires exercice 2025 : 12 TND.',
            'Chiffre d’affaires exercice 2025 : 0 MDT; résultat net exercice 2025 : 2 MDT.',
            'Chiffre d’affaires : 12 MDT; résultat net : 2 MDT.',
            'Chiffre d’affaires exercice 2025 : 12 MDT; chiffre d’affaires exercice 2025 : 15 MDT; résultat net exercice 2025 : 2 MDT.',
        ]:
            _,p=prepare(text);self.assertFalse(p['facts']['financial_enrichment']['derived_metrics'],text)

    def test_financial_table_not_dividend_event(self):
        _,p=prepare('États financiers de la société. Tableau : dividendes 200 000 dinars; réserves 50 000 dinars.')
        self.assertEqual(p['facts']['event_type'],'FINANCIAL_REPORTING_PUBLICATION')

    def test_lexical_candidates_need_nonhypothetical_context(self):
        for text in ['Émission obligataire','Exemple de réduction de capital dans un manuel.']:
            _,p=prepare(text)
            self.assertEqual(p['facts']['event_type'],'UNKNOWN')
            self.assertTrue(p['facts']['classification']['candidates'])

    def test_no_relative_materiality_without_reference(self):
        _,p=prepare(CASES[2][1]);self.assertEqual(p['facts']['financial_enrichment']['materiality']['status'],'NON_DETERMINEE')

    def test_role_labels_not_flattened(self):
        _,p=prepare('Émetteur : ALPHA\nAcquéreur : BETA\nVendeur : GAMMA\nCommissaire aux comptes : DELTA\nMontant émis : 12 MDT.')
        roles={r['role']:r['value'] for r in p['facts']['financial_enrichment']['entities_by_role']}
        self.assertEqual(roles['issuer'],'ALPHA');self.assertEqual(roles['acquirer'],'BETA')
        self.assertEqual(roles['seller'],'GAMMA');self.assertEqual(roles['auditor'],'DELTA')

    def test_issue_premium_and_no_ebitda_invention(self):
        _,p=prepare('Prix d’émission : 12 TND. Valeur nominale : 10 TND. Résultat net exercice 2025 : 2 MDT.')
        self.assertEqual(p['facts']['financial_enrichment']['derived_metrics'][0]['result'],'2')
        self.assertFalse(any(n['concept']=='ebitda' for n in p['facts']['financial_enrichment']['numbers']))

    def test_citations_and_arithmetic_tampering_fail_closed(self):
        _,p=prepare(CAPITAL);facts=p['facts'];bad=deepcopy(facts)
        bad['financial_enrichment']['numbers'][0]['evidence_ids']=['FOREIGN']
        with self.assertRaisesRegex(ValueError,'provenance'):fi.validate_enrichment(bad)
        bad=deepcopy(facts);bad['financial_enrichment']['derived_metrics'][0]['validation_status']='INCONSISTENT'
        with self.assertRaisesRegex(ValueError,'incohérent'):fi.validate_enrichment(bad)

    def test_esg_output_specific_no_new_obligation_and_no_false_deadline(self):
        row,p=prepare(ESG,'cmf')
        def select(prompt,system_prompt,schema):
            ids=schema['properties']['summary_evidence']['items']['enum']
            return {'summary_evidence':ids[:2],'focus_evidence':[],'action_ids':['monitor']}
        with patch.object(llm_analyzer,'request_structured',side_effect=select):
            result=intelligence.analyze_prepared(row,'compliance',p,pipeline_config.load())
        self.assertIn('ESG',result['summary']);self.assertIn('ne créent pas',result['summary'])
        self.assertIn('identifier les sociétés suivies',result['business_output']['action_required'])
        self.assertEqual(result['business_output']['echeances'],'Non déterminé')
        self.assertEqual(result['summary_derivation']['financial_note']['obligation_label'],'Précisions / attentes documentées')
        self.assertEqual(intelligence.validate_claims(result['claims'],result['grounding']['evidence']),[])


if __name__=='__main__':unittest.main()
