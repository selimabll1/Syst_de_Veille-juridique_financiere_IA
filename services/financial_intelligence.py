"""Shared, deterministic financial enrichment. No transport or persistence.

Amounts keep exact source provenance. Calculations require explicit compatible
inputs; generated interpretations and recommendations are separately labelled.
"""
from decimal import Decimal
import re

from services.canonical_facts import NUMBER, number
from services.event_taxonomy import normalize

VERSION = 'financial-1'
GROUPS = {
    'corporate_action': ['capital', 'actions nouvelles', 'annulation', 'راس المال'],
    'capital_structure': ['capital social', 'capital est', 'valeur nominale', 'راس المال'],
    'ownership_change': ['actionnariat', 'participation', 'controle', 'المساهم'],
    'transaction': ['acquisition', 'cession', 'fusion', 'apport', 'تفويت'],
    'financing': ['financement', 'emission', 'credit bancaire', 'تمويل'],
    'debt': ['emprunt', 'dette', 'coupon', 'قرض'],
    'performance': ['chiffre d', 'resultat', 'ebit', 'marge', 'نتيجة', 'رقم المعاملات'],
    'cash_liquidity': ['tresorerie', 'cash-flow', 'bfr', 'سيولة'],
    'distributions': ['dividende', 'distribution', 'توزيع الارباح'],
    'governance': ['dirigeant', 'conseil d', 'commissaire', 'assemblee', 'مجلس'],
    'distress': ['liquidation', 'cessation', 'continuite d', 'defaut', 'pertes', 'تصفية'],
    'regulatory_reporting': ['esg', 'reporting', 'obligation', 'information', 'declaration', 'افصاح'],
    'market_signal': ['marche', 'prospectus', 'cotation', 'visa', 'السوق'],
}
CONCEPTS = {
    'revenue': ['chiffre d’affaires', "chiffre d'affaires", 'revenus', 'رقم المعاملات'],
    'net_income': ['résultat net', 'النتيجة الصافية'],
    'operating_income': ['résultat d’exploitation', "résultat d'exploitation", 'EBIT'],
    'ebitda': ['EBITDA'], 'cash': ['trésorerie', 'النقدية'],
    'cashflow': ['cash-flow', 'flux de trésorerie'], 'working_capital': ['BFR', 'besoin en fonds de roulement'],
    'capex': ['CAPEX', 'dépenses d’investissement'], 'debt': ['dette financière', 'dette totale'],
    'equity': ['capitaux propres'], 'dividends': ['dividendes distribués', 'dividende total'],
    'issue_price': ['prix d’émission', "prix d'emission"],
    'nominal_value': ['valeur nominale', 'قيمة اسمية'],
    'issued_amount': ['montant émis', 'montant de l’emprunt', 'montant du financement'],
    'transaction_amount': ['prix de cession', 'prix d’acquisition'],
    'coupon': ['coupon', 'taux d’intérêt', "taux d'interet"],
    'ownership_percentage': ['participation de', 'pourcentage détenu'],
}
LABELS = {
    'capital_before': 'Capital avant', 'capital_change': 'Variation du capital',
    'capital_after': 'Capital après', 'share_counts': 'Actions concernées',
    'nominal_values': 'Valeur nominale', 'revenue': 'Chiffre d’affaires',
    'net_income': 'Résultat net', 'operating_income': 'Résultat d’exploitation',
    'ebitda': 'EBITDA', 'cash': 'Trésorerie', 'cashflow': 'Flux de trésorerie',
    'working_capital': 'BFR', 'capex': 'Investissements', 'debt': 'Dette',
    'equity': 'Capitaux propres', 'dividends': 'Dividendes distribués',
    'issue_price': 'Prix d’émission', 'nominal_value': 'Valeur nominale',
    'issued_amount': 'Montant émis', 'transaction_amount': 'Montant de transaction',
    'coupon': 'Coupon / taux', 'ownership_percentage': 'Participation mentionnée',
}
MONEY = re.compile(r'(?<!\w)(?P<value>[−-]?' + NUMBER + r')\s*(?P<scale>milliers?|millions?|milliards?|ألف|آلاف|مليون|ملايين)?\s*(?:de\s+)?(?P<unit>MDT|kTND|TND|DT|dinars?|دينار|دينارا|دنانير|EUR|euros?|USD|dollars?|%|٪)(?!\w)', re.I)
ROLES = {
    'issuer': r'émetteur', 'shareholder': r'actionnaire', 'acquirer': r'acquéreur',
    'seller': r'vendeur|cédant', 'fund': r'fonds', 'bond': r'emprunt obligataire',
    'instrument': r'instrument', 'auditor': r'commissaire aux comptes',
    'director': r'directeur|dirigeant', 'counterparty': r'contrepartie',
}


def period_of(text):
    """Do not treat a publication date as a financial period."""
    s = normalize(text)
    patterns = [
        ('H1', r'(?:h1|s1|premier semestre|1er semestre)\s*(?:de\s*)?(20\d{2})'),
        ('H2', r'(?:h2|s2|second semestre|deuxieme semestre)\s*(?:de\s*)?(20\d{2})'),
        ('FY', r'(?:exercice|annee|fy)\s*(?:clos(?:e)?\s*(?:au|le)?\s*(?:31[/-]12[/-])?|en\s*)?(20\d{2})'),
    ]
    found = [(kind, m[1]) for kind, pattern in patterns for m in re.finditer(pattern, s)]
    for m in re.finditer(r'(?:t|q)([1-4])\s*(20\d{2})', s):
        found.append(('Q' + m[1], m[2]))
    found = list(dict.fromkeys(found))
    return {'kind': found[0][0], 'year': int(found[0][1])} if len(found) == 1 else None


def cited(text, evidence_id, **extra):
    return {'value': text, 'evidence_ids': [evidence_id], **extra}


def normalized_amount(match, clause, evidence_id):
    raw = match.group('value').replace('−', '-')
    negative = raw.startswith('-')
    value = Decimal(number(raw.lstrip('-')))
    scale = normalize(match.group('scale') or '')
    multiplier = {'millier': 1000, 'milliers': 1000, 'million': 1000000,
                  'millions': 1000000, 'milliard': 1000000000, 'milliards': 1000000000,
                  'الف': 1000, 'الاف': 1000, 'مليون': 1000000, 'ملايين': 1000000}.get(scale, 1)
    unit = normalize(match.group('unit'))
    currency = None if unit in {'%', '٪'} else 'EUR' if unit in {'eur', 'euro', 'euros'} else 'USD' if unit in {'usd', 'dollar', 'dollars'} else 'TND'
    if unit == 'mdt': multiplier *= 1000000
    if unit == 'ktnd': multiplier *= 1000
    return {'raw_value': match[0], 'normalized_value': str(value * multiplier * (-1 if negative else 1)),
            'currency': currency, 'unit': 'percent' if currency is None else 'currency',
            'period': period_of(clause), 'evidence_id': evidence_id, 'evidence_ids': [evidence_id]}


def compatible(a, b, *, same_period=True):
    return (a['currency'] == b['currency'] and a['unit'] == b['unit']
            and a.get('period') is not None and b.get('period') is not None
            and (a['period'] == b['period'] if same_period else
                 a['period']['kind'] == b['period']['kind'] and a['period']['year'] != b['period']['year']))


def derive(name, formula, inputs, result, status='VERIFIED'):
    return {'name': name, 'formula': formula, 'inputs': inputs,
            'result': str(result), 'origin': 'PYTHON_DERIVED', 'validation_status': status,
            'evidence_ids': list(dict.fromkeys(i for v in inputs.values() for i in v['evidence_ids']))}


def calculations(numbers, facts):
    derived = []
    groups = {}
    for item in numbers:
        groups.setdefault(item['concept'], []).append(item)
    def unique(key):
        values = groups.get(key, [])
        return values[0] if len({(v['normalized_value'], v['currency'], str(v['period'])) for v in values}) == 1 else None
    a, b, c = [unique(k) for k in ('capital_before', 'capital_change', 'capital_after')]
    if a and b and c and a['currency'] and a['currency'] == b['currency'] == c['currency']:
        result = Decimal(a['normalized_value']) + Decimal(b['normalized_value'])
        ok = result == Decimal(c['normalized_value'])
        derived.append(derive('Capital après vérifié', 'capital_before + signed_change', {'capital_before': a, 'signed_change': b, 'capital_after': c}, result, 'VERIFIED' if ok else 'INCONSISTENT'))
        if ok and Decimal(a['normalized_value']) != 0:
            derived.append(derive('Variation du capital (%)', '100 * signed_change / abs(capital_before)', {'capital_before': a, 'signed_change': b}, 100 * Decimal(b['normalized_value']) / abs(Decimal(a['normalized_value']))))
    shares, nominal = unique('share_counts'), unique('nominal_values')
    if shares and nominal and b and nominal['currency'] and nominal['currency'] == b['currency']:
        result = Decimal(shares['normalized_value']) * Decimal(nominal['normalized_value'])
        derived.append(derive('Actions × nominal', 'shares * nominal', {'shares': shares, 'nominal': nominal, 'capital_change': b}, result, 'VERIFIED' if result == abs(Decimal(b['normalized_value'])) else 'INCONSISTENT'))
    issue, nominal = unique('issue_price'), unique('nominal_value') or nominal
    if issue and nominal and issue['currency'] == nominal['currency'] and issue['currency']:
        derived.append(derive('Prime par action', 'issue_price - nominal_value', {'issue_price': issue, 'nominal_value': nominal}, Decimal(issue['normalized_value']) - Decimal(nominal['normalized_value'])))
    for concept, values in groups.items():
        if concept in {'capital_before','capital_change','capital_after','share_counts','nominal_values'}: continue
        # Conflicting values for the same concept/period prevent a comparison.
        values = [v for v in values if v['period'] and len({x['normalized_value'] for x in values if x['period'] == v['period'] and x['currency'] == v['currency']}) == 1]
        unique_values = {(str(v['period']), v['currency']): v for v in values}
        ordered = sorted(unique_values.values(), key=lambda v: v['period']['year'])
        for previous, current in zip(ordered, ordered[1:]):
            if not compatible(previous, current, same_period=False): continue
            delta = Decimal(current['normalized_value']) - Decimal(previous['normalized_value'])
            inputs = {'current': current, 'previous': previous}
            derived.append(derive(LABELS.get(concept, concept) + ' — variation', 'current - previous', inputs, delta))
            if Decimal(previous['normalized_value']) != 0:
                derived.append(derive(LABELS.get(concept, concept) + ' — variation (%)', '100 * (current - previous) / abs(previous)', inputs, 100 * delta / abs(Decimal(previous['normalized_value']))))
    for name, numerator, denominator in [('Marge nette (%)','net_income','revenue'), ('Distribution / résultat (%)','dividends','net_income'), ('Dette / capitaux propres','debt','equity')]:
        for a in groups.get(numerator, []):
            matches = [b for b in groups.get(denominator, []) if compatible(a, b)]
            if len(matches) != 1 or Decimal(matches[0]['normalized_value']) <= 0: continue
            if sum(1 for x in groups[numerator] if compatible(a, x)) != 1: continue
            b = matches[0]; scale = 100 if '(%)' in name else 1
            derived.append(derive(name, f'{scale} * {numerator} / {denominator}', {numerator:a, denominator:b}, scale * Decimal(a['normalized_value']) / Decimal(b['normalized_value'])))
    return derived


def enrich(facts):
    evidence = facts['source_evidence']
    context = {group: [] for group in GROUPS}
    numbers, roles = [], []
    for e in evidence:
        s = normalize(e['quote'])
        for group, terms in GROUPS.items():
            if any(term in s for term in terms): context[group].append(cited(e['quote'], e['id']))
        # Explicit labelled roles only. A mention/search hit never establishes a role.
        for role, pattern in ROLES.items():
            for match in re.finditer(r'(?:' + pattern + r')\s*:\s*([^\n.;]{2,100})', e['quote'], re.I):
                roles.append(cited(match[1].strip(), e['id'], role=role))
        # Split clauses so separate periods do not leak between values.
        for clause in re.split(r'[;\n]|(?<=[.!?])\s', e['quote']):
            normalized = normalize(clause)
            for match in MONEY.finditer(clause):
                prefix = normalize(clause[:match.start()])
                candidates = []
                for concept, terms in CONCEPTS.items():
                    for term in terms:
                        found = list(re.finditer(r'(?<!\w)' + re.escape(normalize(term)) + r'(?!\w)', prefix))
                        if found and len(prefix) - found[-1].end() < 65:
                            candidates.append((found[-1].end(), concept))
                if not candidates: continue
                concept = max(candidates)[1]
                try: item = normalized_amount(match, clause, e['id'])
                except ValueError: continue
                if concept in {'coupon','ownership_percentage'} and item['unit'] != 'percent': continue
                if concept not in {'coupon','ownership_percentage'} and item['unit'] != 'currency': continue
                # A second amount without a repeated concept is ambiguous (e.g.
                # "10 MDT contre 8 MDT"). Preserve source, abstain from comparison.
                if len(list(MONEY.finditer(clause))) != 1: continue
                numbers.append({**item, 'concept':concept, 'label':LABELS[concept]})
    for key in ('capital_before','capital_change','capital_after','share_counts','nominal_values'):
        f = facts.get(key)
        if f:
            numbers.append({'concept':key, 'label':LABELS[key], 'raw_value':f.get('original',f['value']),
                            'normalized_value':f['value'], 'currency':f.get('currency'),
                            'unit':'shares' if key=='share_counts' else 'currency' if f.get('currency') else 'unspecified',
                            'period':None, 'evidence_id':f['evidence_ids'][0], 'evidence_ids':f['evidence_ids']})
    if facts.get('company'): roles.append({**facts['company'], 'role':'company'})
    if facts.get('issuing_authority'): roles.append({**facts['issuing_authority'], 'role':'regulator'})
    derived = calculations(numbers, facts)
    mechanisms = []
    for e in evidence:
        s = normalize(e['quote'])
        for label, terms in [('Rachat',['rachat','شراء']),('Annulation',['annulation','الغاء']),('Absorption de pertes',['absorber les pertes','absorption des pertes']),('Distribution de trésorerie',['remboursement aux actionnaires','distribution en numeraire'])]:
            if any(t in s for t in terms): mechanisms.append(cited(label, e['id']))
    regulatory = {}
    patterns = {
        'esg_reporting': r'\besg\b',
        'scope': r'societes faisant appel public a l.epargne',
        'no_new_obligation': r'ne creent pas.{0,55}obligations nouvelles|aucune nouvelle obligation normative',
        'transition': r'logique transitoire|periode transitoire',
        'reporting_notes': r'notes aux etats financiers',
        'period': r'exercice clos au 31 decembre 20\d{2}|(?:arretes au|au titre de l.exercice)\s*(?:31[/-]12[/-])?20\d{2}',
    }
    for key, pattern in patterns.items():
        regulatory[key] = [cited(e['quote'],e['id']) for e in evidence if re.search(pattern,normalize(e['quote']))]
    movement = next((d for d in derived if d['name']=='Variation du capital (%)' and d['validation_status']=='VERIFIED'), None)
    materiality = {'status':'NON_DETERMINEE','reason':'Aucun dénominateur ou contexte comparable ne permet de quantifier une matérialité relative.','evidence_ids':[]}
    if movement:
        materiality = {'status':'QUANTIFIED', 'reason':f"Variation du capital social : {Decimal(movement['result']):.2f} %. Cette mesure ne quantifie ni la valeur économique ni un rendement.", 'evidence_ids':movement['evidence_ids']}
    elif any('variation (%)' in d['name'] for d in derived):
        movements=[d for d in derived if 'variation (%)' in d['name']]
        materiality={'status':'QUANTIFIED','reason':' ; '.join(f"{d['name']} : {Decimal(d['result']):.2f} %" for d in movements)+'. Effet sur la valeur : non déterminé.', 'evidence_ids':list(dict.fromkeys(i for d in movements for i in d['evidence_ids']))}
    facts['financial_context'] = context
    attributes = {}
    for key, terms in {
        'maturity':['maturite','echeance de l.emprunt'],
        'repayment':['remboursement','amortissement'],
        'proceeds':['emploi des fonds','affectation des fonds','destine a financer'],
        'collateral':['garantie','surete'],
        'conditions':['condition suspensive','sous reserve de'],
    }.items():
        attributes[key]=[cited(e['quote'],e['id']) for e in evidence if any(re.search(t,normalize(e['quote'])) for t in terms)]
    facts['financial_enrichment'] = {'version':VERSION,'numbers':numbers,'derived_metrics':derived,
        'entities_by_role':roles,'mechanisms':mechanisms,'regulatory':regulatory,'materiality':materiality,'attributes':attributes}
    return facts


def format_number(item):
    value = Decimal(item['normalized_value'])
    return format(value, ',.2f').replace(',', ' ').rstrip('0').rstrip('.') + (' ' + item['currency'] if item.get('currency') else ' %' if item['unit']=='percent' else '')


def note(facts, service):
    """Evidence-derived presentation, separate from model selection and human edits."""
    data = facts.get('financial_enrichment') or {}
    reg = data.get('regulatory') or {}
    event = facts['event_type']
    key_facts, sections, ids = [], [], []
    order={'capital_before':0,'capital_change':1,'capital_after':2,'share_counts':3,'nominal_values':4}
    for n in sorted(data.get('numbers', []),key=lambda n:order.get(n['concept'],10)):
        if n['concept']=='nominal_value' and any(v['concept']=='nominal_values' for v in data.get('numbers',[])):continue
        key_facts.append({'label':n['label'], 'text':format_number(n), 'evidence_ids':n['evidence_ids']})
        ids.extend(n['evidence_ids'])
    def section(label, text, kind, evidence_ids):
        if not evidence_ids: return
        sections.append({'label':label, 'text':text, 'kind':kind, 'evidence_ids':list(dict.fromkeys(evidence_ids))})
        ids.extend(evidence_ids)
    event_ids = facts['classification']['evidence_ids']
    summary = None; recommendation = None
    if event in {'CAPITAL_REDUCTION','CAPITAL_INCREASE'}:
        mechanisms = data.get('mechanisms', [])
        section('Mécanisme documenté', ' · '.join(dict.fromkeys(m['value'] for m in mechanisms)) or 'Non déterminé', 'FACT', [i for m in mechanisms for i in m['evidence_ids']])
        section('Matérialité', data.get('materiality',{}).get('reason','Non déterminé'), 'INTERPRETATION', data.get('materiality',{}).get('evidence_ids',[]))
        section('Point de vigilance', 'La variation du capital social ne mesure pas une variation de valeur. Motivation économique, effet de trésorerie et droits des actionnaires : à vérifier dans les modalités publiées.', 'INTERPRETATION', event_ids)
        if service == 'investment':
            recommendation = 'Recommandation UGFS : rapprocher les montants avant/après et les actions concernées des résolutions ; vérifier le mécanisme, les flux de trésorerie et les effets sur les droits des actionnaires avant toute révision de la thèse d’investissement.'
    if service == 'investment' and event == 'FINANCIAL_STATEMENTS_FILING' and not facts.get('performance_facts'):
        summary = 'Dépôt d’états financiers : les comptes sont signalés comme déposés, mais leur contenu financier n’est pas disponible dans cette notification.'
        section('Signal financier', 'Contenu financier non disponible dans la notification.', 'INTERPRETATION', event_ids)
        section('Performance', 'Non déterminée.', 'INTERPRETATION', event_ids)
        section('Impact investissement', 'Non déterminé : le dépôt et les métadonnées comptables ne permettent pas d’inférer une performance.', 'INTERPRETATION', event_ids)
        recommendation = 'Recommandation UGFS : récupérer les états financiers déposés avant toute analyse de performance. Une fois les comptes disponibles, examiner rentabilité, structure financière, endettement, liquidité et génération de trésorerie sur périodes comparables.'
        if facts.get('accounting_year'):
            key_facts.append({'label':'Année comptable','text':facts['accounting_year']['value'],'evidence_ids':facts['accounting_year']['evidence_ids']})
        if facts.get('capital'):
            key_facts.append({'label':'Capital déclaré','text':facts['capital']['value'],'evidence_ids':facts['capital']['evidence_ids']})
    if service == 'compliance' and event == 'REGULATORY_GUIDANCE' and reg.get('esg_reporting'):
        authority = (facts.get('issuing_authority') or {}).get('value')
        if authority and reg.get('scope') and reg.get('reporting_notes'):
            summary = f"Le {authority} précise les informations ESG attendues dans les notes aux états financiers des sociétés faisant appel public à l’épargne."
            ids.extend(facts['issuing_authority']['evidence_ids'])
            for k in ('esg_reporting','scope','reporting_notes'): ids.extend(i for v in reg[k] for i in v['evidence_ids'])
            if reg.get('no_new_obligation'):
                summary += ' Le document précise que ces attentes ne créent pas de nouvelles obligations normatives.'
            if reg.get('transition'): summary += ' Il décrit une logique transitoire.'
            for fact in reg.get('period',[]):
                match=re.search(r'(?:exercice clos au 31 decembre|arretes au 31/12/)\s*(20\d{2})',normalize(fact['value']))
                if match:
                    summary += f" L’exercice concerné est clos au 31 décembre {match[1]}."
                    ids.extend(fact['evidence_ids']);break
            for k in ('no_new_obligation','transition'): ids.extend(i for v in reg.get(k,[]) for i in v['evidence_ids'])
            recommendation = 'Recommandation UGFS : identifier les sociétés suivies entrant dans le champ des sociétés faisant appel public à l’épargne et vérifier la prise en compte des précisions ESG dans leur reporting financier concerné. Applicabilité propre à UGFS : à confirmer.'
        for key, label in [('scope','Champ documenté'),('period','Exercice / période documenté'),('no_new_obligation','Absence de nouvelle obligation normative'),('transition','Précisions transitoires')]:
            if reg.get(key):
                fact = reg[key][0]
                section(label,fact['value'],'FACT',fact['evidence_ids'])
                if key in {'scope','no_new_obligation','period'}: key_facts.append({'label':label,'text':fact['value'],'evidence_ids':fact['evidence_ids']})
        section('Applicabilité UGFS', 'À confirmer ; le périmètre des sociétés visées ne prouve pas à lui seul une obligation applicable à UGFS.', 'INTERPRETATION', event_ids)
        key_facts=[]
        for key,label,text in [
            ('scope','Champ','Sociétés faisant appel public à l’épargne'),
            ('reporting_notes','Objet','Informations ESG — notes aux états financiers'),
            ('no_new_obligation','Obligation nouvelle','Non — explicitement indiqué par la source'),
            ('transition','Régime','Précisions transitoires'),
        ]:
            if reg.get(key):key_facts.append({'label':label,'text':text,'evidence_ids':reg[key][0]['evidence_ids']})
    if service == 'compliance' and event == 'PUBLIC_WARNING':
        recommendation = 'Recommandation UGFS : rapprocher les pratiques et acteurs cités de toute exposition effectivement documentée ; faire vérifier les agréments pertinents par la Conformité. Aucune exposition UGFS ni échéance ne sont déduites de la seule mise en garde.'
        for label,key in [('Objet de la mise en garde','warning_subject'),('Précautions documentées','recommended_precautions')]:
            for fact in facts.get(key,[])[:1]:
                section(label,fact['value'],'FACT',fact['evidence_ids'])
                key_facts.append({'label':label,'text':fact['value'],'evidence_ids':fact['evidence_ids']})
    if service == 'investment' and event not in {'CAPITAL_REDUCTION','CAPITAL_INCREASE'}:
        actions = {
            'BOND_ISSUANCE':'vérifier le coupon, la maturité, le remboursement, les sûretés et l’emploi des fonds publiés ; rapprocher la dette nouvelle des capacités financières documentées avant toute décision.',
            'FINANCIAL_RESULTS':'rapprocher les évolutions de périodes comparables de leur périmètre comptable ; contrôler les facteurs de résultat et la conversion en trésorerie avant de réviser la thèse d’investissement.',
            'FINANCIAL_STATEMENTS_FILING':'récupérer les états financiers déposés avant toute analyse de performance. Une fois les comptes disponibles, examiner rentabilité, structure financière, endettement, liquidité et génération de trésorerie sur périodes comparables.',
            'FINANCIAL_REPORTING_PUBLICATION':'examiner les états financiers publiés et vérifier les périodes, périmètres et chiffres comparables avant toute conclusion d’investissement.',
            'FINANCIAL_STATEMENTS_APPROVAL':'récupérer les états financiers approuvés et vérifier les chiffres, la période et les résolutions avant toute conclusion d’investissement.',
            'ACQUISITION':'vérifier le périmètre acquis, le prix, les conditions et le financement publiés ; distinguer le changement de contrôle documenté des synergies non démontrées.',
            'DISPOSAL':'vérifier les actifs cédés, le prix et les conditions publiés ; ne pas déduire une plus-value sans valeur comptable comparable.',
            'LIQUIDATION':'vérifier le stade de la procédure, les actifs et créances documentés ; ne pas estimer de récupération sans éléments chiffrés.',
            'DIVIDEND':'vérifier le montant voté, les droits et la date de mise en paiement explicite ; comparer la distribution au résultat et à la trésorerie uniquement sur données compatibles.',
            'BOARD_CHANGE':'identifier les mandats modifiés et leur date d’effet explicite ; vérifier les pouvoirs et continuités de gouvernance avant d’en déduire un effet sur la stratégie.',
            'DIRECTOR_APPOINTMENT':'vérifier le mandat, les pouvoirs et la prise de fonction documentés ; l’effet stratégique demeure à confirmer.',
        }
        if event in actions: recommendation = 'Recommandation UGFS : ' + actions[event]
    if event in {'BOND_ISSUANCE','DEBT_ISSUANCE','BANK_FINANCING','REFINANCING'}:
        for key,label in [('maturity','Maturité'),('repayment','Remboursement'),('proceeds','Emploi des fonds'),('collateral','Garanties documentées')]:
            for fact in data.get('attributes',{}).get(key,[])[:1]:section(label,fact['value'],'FACT',fact['evidence_ids'])
        section('Signal de financement','Un financement est documenté. Son coût global, sa soutenabilité et son incidence sur la valeur ne sont pas déduits du seul montant émis.','INTERPRETATION',event_ids)
    performance=[m for m in data.get('derived_metrics',[]) if 'variation (%)' in m['name']]
    for metric in performance:
        section('Comparaison financière',f"{metric['name']} : {Decimal(metric['result']):.2f} %. Comparaison des seules périodes et devises compatibles publiées.",'INTERPRETATION',metric['evidence_ids'])
    if service=='portfolio':
        # The orchestrator already enforces authoritative participation evidence.
        section('Suivi financier','Rapprocher les chiffres publiés de l’exposition autorisée du portefeuille. Ne pas quantifier une perte ou un gain sans données d’exposition compatibles.','INTERPRETATION',event_ids)
    if service=='commercial':
        from services.intelligence import commercial_matches
        if commercial_matches(facts['referential_matches']):
            section('Signal à qualifier','L’événement documenté peut être examiné dans le contexte de la relation UGFS confirmée ; il ne démontre pas à lui seul un besoin ou une opportunité commerciale.','INTERPRETATION',event_ids)
    if recommendation: section('Action recommandée',recommendation,'RECOMMENDATION',event_ids)
    return {'version':VERSION,'key_facts':key_facts,'sections':sections,'summary':summary,
            'recommendation':recommendation,'evidence_ids':list(dict.fromkeys(ids)),
            'metrics':data.get('derived_metrics',[]),'materiality':data.get('materiality',{}),
            'obligation_label':'Précisions / attentes documentées' if event=='REGULATORY_GUIDANCE' and reg.get('no_new_obligation') else 'Obligations documentées'}


def validate_enrichment(facts):
    """Fail closed if enrichment loses evidence or an arithmetic check fails."""
    data = facts.get('financial_enrichment', {})
    lookup = {e['id']:e for e in facts['source_evidence']}
    values = data.get('numbers',[]) + data.get('derived_metrics',[]) + data.get('entities_by_role',[]) + data.get('mechanisms',[])
    for items in facts.get('financial_context',{}).values(): values += items
    for items in data.get('regulatory',{}).values(): values += items
    for items in data.get('attributes',{}).values(): values += items
    for item in values:
        if not item.get('evidence_ids') or not set(item['evidence_ids']) <= lookup.keys():
            raise ValueError('UNSUPPORTED_CLAIM : provenance financière absente.')
        if item.get('validation_status') == 'INCONSISTENT':
            raise ValueError('INSUFFICIENT_EVIDENCE : contrôle financier incohérent.')
    if data and calculations(data.get('numbers',[]),facts)!=data.get('derived_metrics',[]):
        raise ValueError('INSUFFICIENT_EVIDENCE : calcul financier altéré.')
    return True
