"""Explicit, cached CMF preprocessing. No model calls and no source DB writes."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import re
import time

from modules import business_pipeline_registry as registry
from services.jobs import report, stage
from services.event_taxonomy import normalize

VERSION = 'cmf-segments-1'
CACHE = Path(__file__).resolve().parents[1] / 'data' / 'composite_documents'


def is_parent(row):
    return row.get('kind') == 'cmf' and 'bulletin' in str(row.get('raw', {}).get('section', '')).lower() and not row.get('child_id')


def _read(table, parent_id):
    import sqlite3
    if not registry.DATABASE.exists(): return []
    con = sqlite3.connect(registry.DATABASE.resolve().as_uri() + '?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    try:
        if not con.execute('SELECT 1 FROM sqlite_master WHERE name=?', (table,)).fetchone(): return []
        return [json.loads(r[0]) for r in con.execute(f'SELECT metadata_json FROM {table} WHERE parent_source_id=?', (parent_id,))]
    finally: con.close()


def snapshot(parent_id):
    records = _read('composite_documents', parent_id)
    return records[0] if records else None


def children(parent_id):
    current = snapshot(parent_id)
    if not current: return []
    return sorted([c for c in _read('composite_publications', parent_id) if c['document_hash'] == current['document_hash']], key=lambda c:(c['page_start'], c['title']))


def _save(row, document, publications):
    with registry.transaction() as con:
        con.execute('CREATE TABLE IF NOT EXISTS composite_documents(parent_source_id TEXT PRIMARY KEY, metadata_json TEXT NOT NULL)')
        con.execute('CREATE TABLE IF NOT EXISTS composite_publications(child_id TEXT PRIMARY KEY, parent_source_id TEXT NOT NULL, metadata_json TEXT NOT NULL)')
        con.execute('INSERT INTO composite_documents VALUES(?,?) ON CONFLICT(parent_source_id) DO UPDATE SET metadata_json=excluded.metadata_json', (row['uid'], json.dumps(document, ensure_ascii=False)))
        for child in publications:
            con.execute('INSERT INTO composite_publications VALUES(?,?,?) ON CONFLICT(child_id) DO UPDATE SET metadata_json=excluded.metadata_json', (child['child_id'],row['uid'],json.dumps(child,ensure_ascii=False)))
        registry._register(con,row)
        registry._event(con,row['uid'],None,'document_segmented',{'children':len(publications),'status':document['status'],'timings':document['timings'],'document_hash':document['document_hash']})


def _page_text(pages, start, end):
    selected = [p for p in pages if start <= p['page_number'] <= end]
    text=''; spans=[]
    for p in selected:
        if text: text+='\n\n'
        a=len(text); text+=p['text']; spans.append({'page':p['page_number'],'start':a,'end':len(text)})
    return text, spans


def make_child(row, document, title, start, end, *, category='', status='CONFIRMED', method='toc', confidence=1.0):
    if not title.strip() or not 1 <= start <= end <= document['total_pages']:
        raise ValueError('Indiquez un titre et une plage comprise entre 1 et le nombre total de pages.')
    text,spans=_page_text(document['pages'], start, end)
    identity='|'.join([row['uid'],normalize(title),str(start),str(end),document['document_hash']])
    return {'child_id':'cmf-child:'+sha256(identity.encode()).hexdigest(), 'parent_source_id':row['uid'],
            'parent_bulletin_number':document['bulletin_number'],'title':title.strip(),'category':category,
            'page_start':start,'page_end':end,'extracted_text':text,'page_spans':spans,
            'extraction_hash':sha256(text.encode()).hexdigest(),'document_hash':document['document_hash'],
            'publication_date':row['date'],'source_url':document['source_url'],'pdf_path':document['pdf_path'],
            'segmentation_status':status,'segmentation_confidence':confidence,'method':method,
            'pipeline_version':VERSION,'parent_title':row['title']}


def toc_entries(pages):
    """Only explicit TOC title + page numbers, never generated titles."""
    entries=[]; pending=[]; section=''; prefix=''
    for page in pages[:3]:
        # Stop at the first numbered content page, not a fixed cover count.
        if page['page_number'] > 1 and not re.search(r'ANNEXE|SOMMAIRE',page['text']): break
        for line in page['text'].splitlines():
            line=' '.join(line.split())
            if not line: continue
            if line.startswith(('ANNEXE','VALEURS LIQUIDATIVES')): return entries
            if line.startswith(('AVIS ET COMMUNI','AVIS DES SOCI')):
                section=line; pending=[]; prefix='';continue
            if not section:continue
            if line.startswith('INSTAURATION '):prefix=line;continue
            match=re.match(r'^(.*?)\s+(\d{1,3})$',line)
            if match:
                title=' '.join(pending+[match[1]]).strip(' .');pending=[]
                if prefix:title=prefix+' — '+title
                if len(title)>10:entries.append({'title':title,'start':int(match[2]),'category':section})
            else:pending.append(line)
    return entries


def segment(row, document):
    pages=document['pages']; entries=toc_entries(pages); result=[]
    # Printed page numbering must agree with physical PDF pages for TOC use.
    for i,entry in enumerate(entries):
        start=entry['start']; end=entries[i+1]['start']-1 if i+1<len(entries) else start
        if not 1<=start<=end<=len(pages):continue
        numbered=all(re.search(r'Page\s*-?\s*'+str(n)+r'\s*-',pages[n-1]['text'],re.I) for n in range(start,end+1))
        # Last TOC notice ends only at an explicit publication footer; otherwise
        # leave its boundary unconfirmed rather than swallow the annexes.
        terminal=bool(re.search(r'20\d{2}\s*[–-]\s*(?:AS|AC)\s*[–-]\s*\d+',pages[end-1]['text']))
        confirmed=numbered and (i+1<len(entries) or terminal)
        result.append(make_child(row,document,entry['title'],start,end,category=entry['category'],status='CONFIRMED' if confirmed else 'REVIEW_REQUIRED',confidence=.95 if confirmed else .4))
    if not result:
        # Major repeated heading markers are suggestions for manual confirmation.
        for page in pages:
            lines=[s.strip() for s in page['text'].splitlines() if s.strip()]
            title=next((s for s in lines[:18] if len(s)>15 and s.isupper() and not s.startswith(('PAGE','N°','BULLETIN'))),None)
            if title:result.append(make_child(row,document,title,page['page_number'],page['page_number'],status='REVIEW_REQUIRED',method='heading_candidates',confidence=.3))
    return result


def preprocess(row):
    if not is_parent(row):raise ValueError('La segmentation concerne un bulletin parent.')
    started=time.perf_counter();stage('scope'); detect=time.perf_counter()-started
    report('Document composite détecté : préparation des publications, sans analyse IA du bulletin.')
    url=row['raw'].get('pdf_url') or ''; old=snapshot(row['uid'])
    local=Path(row['pdf_path']) if row.get('pdf_path') else None
    if old and old['pipeline_version']==VERSION and old['source_url']==url and Path(old['pdf_path']).is_file():
        path=local or Path(old['pdf_path'])
        if sha256(path.read_bytes()).hexdigest()==old['document_hash']:
            return response(old,children(row['uid']),cached=True,timings={'composite_detection':detect,'total_preprocessing':time.perf_counter()-started})
    stage('extraction');t=time.perf_counter()
    if local and local.is_file():data=local.read_bytes()
    else:
        if not url:raise ValueError('PDF officiel absent : collectez le document du bulletin.')
        import requests
        from modules.cmf_collector_v1 import _safe_cmf_url
        fetched=requests.get(_safe_cmf_url(url),timeout=(10,60));fetched.raise_for_status();data=fetched.content
    download=time.perf_counter()-t
    if not data.startswith(b'%PDF'):raise ValueError('La source ne contient pas un PDF.')
    digest=sha256(data).hexdigest();CACHE.mkdir(parents=True,exist_ok=True);path=CACHE/(digest+'.pdf')
    if not path.exists():path.write_bytes(data)
    import fitz
    t=time.perf_counter()
    with fitz.open(stream=data,filetype='pdf') as pdf:
        pages=[{'page_number':i+1,'text':page.get_text('text').strip()} for i,page in enumerate(pdf)]
    extraction=time.perf_counter()-t
    number=re.search(r'N[°º]\s*(\d+)',row['title']); number=number[1] if number else ''
    observed=re.search(r'N[°º]\s*(\d+)',pages[0]['text']) if pages else None
    if number and observed and number!=observed[1]:raise ValueError('SOURCE_MISMATCH : le numéro du PDF diffère du bulletin sélectionné.')
    document={'parent_source_id':row['uid'],'document_hash':digest,'pdf_path':str(path.resolve()),'source_url':url,
              'bulletin_number':number,'pages':pages,'total_pages':len(pages),'pipeline_version':VERSION}
    stage('segmentation');t=time.perf_counter();publications=segment(row,document);segmentation=time.perf_counter()-t
    confirmed=[c for c in publications if c['segmentation_status']=='CONFIRMED']
    covered={n for c in confirmed for n in range(c['page_start'],c['page_end']+1)}
    document['uncovered_pages']=[n for n in range(3,len(pages)+1) if n not in covered]
    document['status']='REVIEW_REQUIRED' if document['uncovered_pages'] or not confirmed else 'COMPLETE'
    document['timings']={'download':download,'extraction':extraction,'composite_detection':detect,'segmentation':segmentation,'total_preprocessing':time.perf_counter()-started}
    stage('sections');_save(row,document,publications)
    return response(document,publications)


def response(document, publications, *, cached=False, timings=None):
    count=len(publications)
    return {'ok':True,'outcome':'SEGMENTATION_REQUIRED' if document['status']=='REVIEW_REQUIRED' else 'PUBLICATIONS_DETECTED',
            'operation':'segmentation','parent_source_id':document['parent_source_id'],'children_count':count,'cached':cached,
            'message':f'{count} publications détectées.'+(' Certaines pages nécessitent une sélection manuelle.' if document['status']=='REVIEW_REQUIRED' else ''),
            'timings':timings or document['timings'],'services':[],'errors':[]}


def manual(row,title,start,end):
    document=snapshot(row['uid'])
    if not document:raise ValueError('Préparez le bulletin avant de sélectionner les pages.')
    child=make_child(row,document,title,int(start),int(end),method='human_page_range')
    if len(child['extracted_text'].strip())<80:
        # OCR is restricted to the explicitly selected pages, never the bulletin.
        import fitz
        from modules.ocr_engine import _select_page_text
        with fitz.open(document['pdf_path']) as pdf:
            for n in range(int(start),int(end)+1):document['pages'][n-1]['text']=_select_page_text(pdf[n-1],n)['text']
        child=make_child(row,document,title,int(start),int(end),method='human_page_range_ocr')
    if len(child['extracted_text'].strip())<80:raise ValueError('Texte insuffisant sur les pages sélectionnées ; OCR à vérifier.')
    _save(row,document,[child]);return {'ok':True,'message':'Publication sélectionnée et bornée aux pages indiquées.','child_id':child['child_id']}


def child_row(parent,child):
    row=deepcopy(parent)
    row.update(uid=child['child_id'],stable_uid=child['child_id'],child_id=child['child_id'],parent_source_id=parent['uid'],
               title=child['title'],entity='',services=['compliance'],matches=[],analysis=None,business_results={},analysis_attempts={},
               legacy_result=None,record={},review_status='',status='À analyser',ai_state='pending',treated=False,
               pdf_path=child['pdf_path'],source_url=child['source_url'],summary='',read=True)
    row['raw']={'section':'child_publication','child_publication_id':child['child_id'],'pdf_url':child['source_url'],'raw_excerpt':child['extracted_text']}
    row['child_publication']=child
    return row


def verified_child(row):
    """Reload trusted child content; ignore any caller-supplied parent text."""
    matches=[c for c in children(row.get('parent_source_id','')) if c['child_id']==row.get('child_id')]
    if len(matches)!=1 or matches[0]['segmentation_status']!='CONFIRMED':raise ValueError('Segmentation requise : confirmez le titre et la plage de cette publication.')
    child=matches[0]
    if sha256(child['extracted_text'].encode()).hexdigest()!=child['extraction_hash']:raise ValueError('SOURCE_MISMATCH : texte enfant altéré.')
    if sha256(Path(child['pdf_path']).read_bytes()).hexdigest()!=child['document_hash']:raise ValueError('SOURCE_MISMATCH : PDF modifié ; préparez de nouveau le bulletin.')
    return child
