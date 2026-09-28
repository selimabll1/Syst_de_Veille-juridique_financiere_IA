"""Deterministic facts with exact source offsets. Absent/ambiguous values stay null."""
from decimal import Decimal, InvalidOperation
from datetime import date
from hashlib import sha256
import re
import json
from services.event_taxonomy import classify, normalize

NUMBER = r'[0-9٠-٩۰-۹]+(?:[ .٬٫,\u00a0\u202f][0-9٠-٩۰-۹]+)*'
CURRENCY = r'(?:dinars?|dinar|MDT|kTND|DT|TND|دنانير|دينار|دينارا|euros?|EUR|USD|dollars?)'
DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹','01234567890123456789')
MONTHS = {'janvier':1,'février':2,'mars':3,'avril':4,'mai':5,'juin':6,'juillet':7,'août':8,'septembre':9,'octobre':10,'novembre':11,'décembre':12,'جانفي':1,'فيفري':2,'مارس':3,'أفريل':4,'ماي':5,'جوان':6,'جويلية':7,'أوت':8,'سبتمبر':9,'أكتوبر':10,'نوفمبر':11,'ديسمبر':12}


def number(value):
    value=str(value).translate(DIGITS).replace('\u00a0','').replace('\u202f','').replace(' ','').replace('٬','')
    if '٫' in value:value=value.replace('٫','.')
    elif ',' in value:
        if value.count(',')>1:raise ValueError('Séparateurs numériques ambigus')
        value=value.replace('.','').replace(',','.')
    elif '.' in value:
        parts=value.split('.')
        if all(len(p)==3 for p in parts[1:]):value=''.join(parts)
        elif len(parts)!=2:raise ValueError('Séparateurs numériques ambigus')
    try:return format(Decimal(value),'f')
    except InvalidOperation:raise ValueError('Nombre invalide')


def evidence_catalog(text):
    # Sentence boundaries exclude decimal/thousand separators. Long paragraphs
    # are split into exact bounded spans, never truncated to the document prefix.
    result=[]
    for part in re.finditer(r'.+?(?:[.!?](?=\s|$)|\n\s*\n|$)',text,re.DOTALL):
        start,end=part.span()
        while start<end:
            stop=min(end,start+900)
            if stop<end:
                boundary=text.rfind(' ',start+450,stop)
                if boundary>start:stop=boundary
            a=start
            while a<stop and text[a].isspace():a+=1
            b=stop
            while b>a and text[b-1].isspace():b-=1
            if b-a>=8:result.append({'id':f'S{len(result)+1}','quote':text[a:b],'start':a,'end':b,'origin':'source'})
            start=stop
    return result


def extract(row,text,quality=1.0,method='collected_text'):
    evidence=evidence_catalog(text)
    if not evidence:raise ValueError('Aucune preuve source exploitable.')
    raw=row.get('raw') or {}
    source_raw = raw
    child_id=raw.get('child_publication_id') or raw.get('child_event_id') or raw.get('segment_id')
    child=row.get('child_publication') or {}
    for item in evidence:
        item.setdefault('source_record_id', row.get('stable_uid'))
        if child_id:
            item['child_publication_id']=child_id
            item['parent_source_id']=child.get('parent_source_id')
            spans=[s for s in child.get('page_spans',[]) if s['start']<item['end'] and s['end']>item['start']]
            if spans:
                item['page_start']=min(s['page'] for s in spans)
                item['page_end']=max(s['page'] for s in spans)
    def ids(start,end):return [e['id'] for e in evidence if e['start']<end and e['end']>start]
    def fact(value,start,end,**extra):return {'value':value,'original':text[start:end],'evidence_ids':ids(start,end),'start':start,'end':end,**extra}
    arabic=sum('\u0600'<=c<='\u06ff' for c in text);latin=sum(c.isascii() and c.isalpha() for c in text)
    language='ar' if arabic>latin*2 else 'mixed' if arabic>=10 else 'fr'
    multi=row.get('kind')=='cmf' and 'bulletin' in str(row.get('raw',{}).get('section','')).lower() and not child_id
    event=classify(evidence,multi_document=multi)
    facts={k:None for k in ['company','publication_date','capital_before','capital_change','capital_after','nominal_values','share_counts','event_subtype','performance_facts','accounting_year','capital','registered_capital','start_date','trade_name','responsible_person']}
    facts.update(document_scope='multiple' if multi else 'single',source=row.get('kind'),source_record_id=row.get('stable_uid'),source_title=raw.get('source_title') or row.get('title'),document_url=raw.get('pdf_url') or raw.get('document_url') or row.get('source_url'),child_publication_id=child_id,source_hash=sha256(text.encode()).hexdigest(),language=language,entities=[],people=[],effective_dates=[],deadlines=[],amounts=[],currencies=[],percentages=[],legal_actions=[],governance_actions=[],transaction_information=[],source_evidence=evidence,unknown_fields=[],event_type=event['event_type'],classification=event,extraction={'quality':max(0,min(1,float(quality))),'method':method,'characters':len(text)},entity_query=row.get('entity'),referential_matches=row.get('matches',[]))
    if child:
        facts['child_scope']={k:child[k] for k in ('child_id','parent_source_id','page_start','page_end','extraction_hash','document_hash','parent_title')}
    for m in re.finditer(r'(?<!\w)('+NUMBER+r')\s*(milliers?|millions?|milliards?|آلاف|ألف|مليون|ملايين)?\s*(?:de\s+)?('+CURRENCY+r')(?!\w)',text,re.I):
        try:value=number(m[1])
        except ValueError:continue
        multiplier={'millier':1000,'milliers':1000,'million':1000000,'millions':1000000,'milliard':1000000000,'milliards':1000000000,'آلاف':1000,'ألف':1000,'مليون':1000000,'ملايين':1000000}.get((m[2] or '').lower(),1)
        multiplier*=1000000 if m[3].lower()=='mdt' else 1000 if m[3].lower()=='ktnd' else 1
        value=format(Decimal(value)*multiplier,'f')
        cur=normalize(m[3]);cur='TND' if cur in {'mdt','ktnd','dt','tnd','dinar','dinars','دينار','دينارا','دنانير'} else 'EUR' if cur in {'euro','euros','eur'} else 'USD'
        facts['amounts'].append(fact(value,*m.span(),currency=cur))
    facts['currencies']=sorted({f['currency'] for f in facts['amounts']})
    for m in re.finditer('('+NUMBER+r')\s*[%٪]',text):
        try:facts['percentages'].append(fact(number(m[1]),*m.span()))
        except ValueError:continue
    # Roles are assigned only from local explicit clauses, never amount magnitude.
    def unique(values):
        keys={(v['value'],v.get('currency')) for v in values}
        return values[0] if len(keys)==1 else None
    changes=[];nominals=[];shares=[];pairs=[]
    for f in facts['amounts']:
        before=normalize(text[max(0,f['start']-125):f['start']])
        if re.search(r'(?:reduction|augmentation|تخفيض|ترفيع|زيادة).{0,85}(?:montant|مبلغ)(?:.{0,18})$',before):changes.append(f)
        if re.search(r'(?:valeur nominale|valeur unitaire|قيمة اسمية)(?:.{0,30})$',before):nominals.append(f)
    for m in re.finditer('('+NUMBER+r')\s*(?:de ses propres actions|actions|parts sociales|سهما|سهم|أسهم)(?!\w)',text,re.I):
        try:shares.append(fact(number(m[1]),*m.span()))
        except ValueError:continue
    for a,b in zip(facts['amounts'],facts['amounts'][1:]):
        prefix=normalize(text[max(0,a['start']-115):a['start']]);between=normalize(text[a['end']:b['start']])
        if ('capital' in prefix or ('راس' in prefix and 'مال' in prefix)) and re.search(r'(?:de|من)\s*$',prefix) and between in {'a','الي'} and a['currency']==b['currency']:pairs.append((a,b))
    if len(pairs)==1:facts['capital_before'],facts['capital_after']=pairs[0]
    facts['capital_change']=unique(changes)
    # Some official notices state capital figures with a unit word rather
    # than a currency (for example ``de 100 à 80 unités``).  The figures are
    # still deterministic capital facts and must be checked arithmetically.
    if event['event_type'] in {'CAPITAL_REDUCTION','CAPITAL_INCREASE'} and not facts['capital_before']:
        capital_range = re.search(r'(?:capital|راس\s+المال).{0,80}?\bde\s+(' + NUMBER + r').{0,25}?\b[aà]\s+(' + NUMBER + r')', text, re.I)
        if capital_range:
            try:
                before_value, after_value = number(capital_range.group(1)), number(capital_range.group(2))
                facts['capital_before'] = fact(before_value, *capital_range.span(1))
                facts['capital_after'] = fact(after_value, *capital_range.span(2))
                delta = Decimal(after_value) - Decimal(before_value)
                facts['capital_change'] = {**fact(format(delta, 'f'), *capital_range.span()), 'normalization': 'Variation calculée à partir des deux montants explicitement publiés'}
            except (ValueError, InvalidOperation):
                pass
    if facts['capital_change'] and event['event_type']=='CAPITAL_REDUCTION':
        facts['capital_change']={**facts['capital_change'],'value':format(-abs(Decimal(facts['capital_change']['value'])),'f'),'normalization':'Réduction explicitement indiquée : variation négative'}
    facts['nominal_values']=unique(nominals);facts['share_counts']=unique(shares)
    date_pattern=r'(?<!\d)(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4}|\d{1,2}\s+(?:'+ '|'.join(MONTHS)+r')\s+\d{4})(?!\d)'
    translated=text.translate(DIGITS);facts['dates']=[]
    for m in re.finditer(date_pattern,translated,re.I):
        date_raw=m[1];parts=re.split(r'[-/\s]+',date_raw)
        try:
            if len(parts[0])==4:y,mo,d=map(int,parts)
            else:d=int(parts[0]);mo=int(parts[1]) if parts[1].isdigit() else MONTHS[parts[1].lower()];y=int(parts[2])
            value=date(y,mo,d).isoformat()
        except (ValueError,KeyError):continue
        item=fact(value,*m.span());facts['dates'].append(item)
        context=normalize(text[max(0,m.start()-70):m.start()])
        if re.search(r'(?:au plus tard(?: le)?|date limite|avant le|echeance|delai de reservation|اخر اجل|قبل يوم)\s*[:：]?\s*$',context):facts['deadlines'].append(item)
        elif re.search(r'(?:effet (?:au|du)|a compter du|entre en vigueur le|ابتداء من|بداية من)\s*$',context):facts['effective_dates'].append(item)
    if row.get('date'):
        facts['publication_date']={'value':row['date'],'original':row['date'],'evidence_ids':['M1'],'origin':'source_metadata','role':'publication uniquement, jamais échéance'}
    patterns=[r'(?:Dénomination latin|Dénomination\s*:)\s*\n?([^\n:]{3,110})',r'(?:AVIS DE RÉDUCTION DE CAPITAL|AVIS D.AUGMENTATION DE CAPITAL)\s+(.{3,120}?)(?=\s+Société)',r'(?:اعلان تخفيض رأس المال)\s+(.{3,120}?)(?=\s+شركة)',r'(?:Société)\s+([A-Z][A-Z \-]{3,70})(?=\s+Société|\s+société)']
    for pattern in patterns:
        for m in re.finditer(pattern,text):
            name=m[1].strip();facts['entities'].append(fact(name,*m.span(1),normalized=normalize(name),role='mentioned'))
    primary_names={normalize(f['value']) for f in facts['entities']}
    if len(primary_names)==1:facts['company']=facts['entities'][0]
    elif not primary_names and row.get('entity') and str(row['entity']).casefold() not in {'cmf','unknown','non determine'}:
        m=re.search(re.escape(str(row['entity'])),text,re.I)
        if m:facts['entities'].append(fact(m[0],*m.span(),normalized=normalize(m[0]),role='query_mentioned_only'))
    if not facts['company'] and len({normalize(f['value']) for f in facts['entities']}) == 1:
        facts['company'] = facts['entities'][0]
    # Explicit RNE fields outrank a free-text company guess. Values must still
    # occur in this document, so metadata cannot import evidence from elsewhere.
    if row.get('kind') == 'legaltech':
        from modules.legaltech_detail_parser import parse_detail_text
        fields = parse_detail_text(text)
        stored = source_raw.get('source_fields_json') or {}
        if isinstance(stored, str):
            try: stored = json.loads(stored)
            except (ValueError, TypeError): stored = {}
        fields.update({k:v for k,v in stored.items() if isinstance(v,str) and v in text})
        def field_fact(value):
            if not isinstance(value,str) or not value.strip(): return None
            # Reject contaminated legacy structured values as well.
            from modules.legaltech_detail_parser import KNOWN_LABELS
            boundary = re.search(r'\s*,\s*(?:'+'|'.join(re.escape(k) for k in KNOWN_LABELS)+r')\s*[:：]', value, re.I)
            if boundary: value = value[:boundary.start()].strip()
            start = text.find(value)
            return fact(value,start,start+len(value),normalized=normalize(value),role='source_field') if start >= 0 else None
        names = [fields.get(k) for k in ('denomination_latin','raison_sociale','nom_entreprise','denomination_alternative','denomination_reservee','denomination')]
        latin = next((field_fact(v) for v in names if isinstance(v,str) and re.search('[A-Za-z]',v) and field_fact(v)),None)
        arabic_name = next((field_fact(v) for v in names if isinstance(v,str) and re.search('[\u0600-\u06ff]',v) and field_fact(v)),None)
        if latin or arabic_name:
            facts['company'] = latin or arabic_name
            facts['company']['canonical_name'] = facts['company']['value']
            if arabic_name: facts['company']['arabic_name'] = arabic_name['value']
            facts['entities'] = [v for v in (latin,arabic_name) if v]
        for key, field in [('trade_name','enseigne'),('accounting_year','annee_comptable'),('registered_capital','capital'),('start_date','date_debut_activite')]:
            facts[key] = field_fact(fields.get(field))
        facts['capital'] = facts.get('registered_capital')
        person = field_fact(fields.get('responsable'))
        role = field_fact(fields.get('qualite'))
        facts['responsible_person'] = {'name':person['value'],'role':role['value'] if role else None,'evidence_ids':person['evidence_ids'] + (role['evidence_ids'] if role else [])} if person else None
    for m in re.finditer(r'(?:Mr\.?|Mme\.?|Monsieur|Madame|Représentant légal\s*:)\s+([A-ZÀ-Ÿ][\wÀ-ÿ-]+(?:\s+[A-ZÀ-Ÿ][\wÀ-ÿ-]+){1,3})',text):facts['people'].append(fact(m[1],*m.span(1)))
    # A search/watchlist label is not proof that the referenced company is
    # the subject. Keep the original match separately from source grounding.
    resolved=[]
    for reference in facts['referential_matches']:
        value=dict(reference)
        named=bool(value.get('name') and re.search(r'(?<!\w)'+re.escape(normalize(value['name']))+r'(?!\w)',normalize(text)))
        identified=bool(value.get('identifier') and re.search(r'(?<!\w)'+re.escape(normalize(value['identifier']))+r'(?!\w)',normalize(text)))
        value['source_supported']=named or identified
        if not value['source_supported']:
            value['portfolio_verified']=False
            value['ambiguous']=True
        if facts['company'] and value.get('type')=='portfolio' and normalize(value.get('name','')) not in facts['company']['normalized'] and not identified:
            value['portfolio_verified']=False
            value['relationship_limitation']='Entité mentionnée, mais société principale différente.'
        resolved.append(value)
    facts['referential_matches']=resolved
    facts['relationships']={'portfolio':[m for m in resolved if m.get('portfolio_verified') and not m.get('ambiguous')], 'commercial':[m for m in resolved if m.get('source_supported') and m.get('role_ugfs') and not m.get('ambiguous')]}
    for m in re.finditer(r'(?:الرئيس المدير العام|الممثل القانوني|السيد|السيدة)\s*[:：]?\s*([\u0600-\u06ff]+(?:[ \t]+[\u0600-\u06ff]+){1,3})',text):
        facts['people'].append(fact(m[1],*m.span(1)))
    for m in re.finditer(r'([A-ZÀ-Ÿ][a-zà-ÿ]+ [A-ZÀ-Ÿ]{2,}(?: [A-ZÀ-Ÿ]{2,})?)\s+Président[- ]Directeur',text):
        facts['people'].append(fact(m[1],*m.span(1)))
    facts['identifiers']=[]
    for m in re.finditer(r'(?:Identifiant [Uu]nique|MF)\s*:?\s*([0-9]{5,10}\s*[A-Z](?:[/A-Z0-9]*)?)',text):
        facts['identifiers'].append(fact(m[1].replace(' ',''),*m.span(1)))
    for e in evidence:
        s=normalize(e['quote'])
        for key,terms in [('legal_actions',['statut','plainte','قرار','حكم']),('governance_actions',['assemblee','nomination','dirigeant','مجلس','جلسة']),('transaction_information',['rachat','cession','acquisition','شراء','تفويت'])]:
            if any(t in s for t in terms):facts[key].append({'value':e['quote'],'evidence_ids':[e['id']]})
    if multi:
        for key in ['company','capital_before','capital_change','capital_after','share_counts','nominal_values']:facts[key]=None
    facts['unknown_fields']=[k for k,v in facts.items() if v is None or v==[]]
    facts['validation']=validate_financial(facts)
    if not multi:
        conflicts=[k for k,values in [('capital_change',changes),('nominal_values',nominals),('share_counts',shares)] if len({(v['value'],v.get('currency')) for v in values})>1]
        if conflicts:
            facts['validation']['checks'].append({'check':'Conflicting explicit figures','status':'INCONSISTENT','fields':conflicts,'evidence_ids':list(dict.fromkeys(i for v in changes+nominals+shares for i in v['evidence_ids']))})
            facts['validation']['status']='INCONSISTENT'
    return facts


def validate_financial(facts):
    checks=[]
    def check(name,keys,fn):
        values=[facts.get(k) for k in keys]
        if not all(values):checks.append({'check':name,'status':'INSUFFICIENT_DATA','evidence_ids':[]});return
        currencies={v.get('currency') for v in values if v.get('currency')}
        if len(currencies)>1:checks.append({'check':name,'status':'INSUFFICIENT_DATA','reason':'Devises différentes','evidence_ids':[]});return
        nums=[Decimal(v['value']) for v in values];delta=fn(*nums)
        checks.append({'check':name,'status':'VERIFIED' if abs(delta)<=Decimal('0.001') else 'INCONSISTENT','difference':str(delta),'evidence_ids':list(dict.fromkeys(i for v in values for i in v['evidence_ids']))})
    check('capital_before + capital_change = capital_after',['capital_before','capital_change','capital_after'],lambda a,b,c:a+b-c)
    check('shares × nominal = absolute capital_change',['share_counts','nominal_values','capital_change'],lambda a,b,c:a*b-abs(c))
    before,change=facts.get('capital_before'),facts.get('capital_change')
    variation=None
    if before and change and Decimal(before['value'])!=0:variation={'value':str(100*Decimal(change['value'])/Decimal(before['value'])),'origin':'PYTHON_DERIVED','evidence_ids':before['evidence_ids']+change['evidence_ids']}
    return {'checks':checks,'percentage_variation':variation,'status':'INCONSISTENT' if any(c['status']=='INCONSISTENT' for c in checks) else 'VERIFIED' if all(c['status']=='VERIFIED' for c in checks) else 'INSUFFICIENT_DATA','duplicate_amount_mentions':len(facts['amounts'])-len({(f['value'],f['currency']) for f in facts['amounts']})}


CANONICAL_SCHEMA = {
    "type":"object",
    "required":["source","source_record_id","language","company","entities","people","event_type","event_subtype","publication_date","effective_dates","deadlines","amounts","currencies","percentages","share_counts","nominal_values","capital_before","capital_change","capital_after","legal_actions","governance_actions","transaction_information","source_evidence","unknown_fields","validation"],
    "properties":{"event_type":{"type":"string"}, "source_evidence":{"type":"array","minItems":1},"unknown_fields":{"type":"array"}},
    "additionalProperties":True,
}
