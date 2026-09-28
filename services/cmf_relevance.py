"""CMF discovery gating: rules before any document request or AI call."""
from pathlib import Path
from hashlib import sha256
import tempfile
from services import routing
from modules import admin_registry


def decision(item, policy, entities):
    if not policy.get('configured'):
        return False, 'À configurer : règles de pertinence CMF non renseignées.'
    text = ' '.join(str(item.get(k) or '') for k in ('title','category','raw_excerpt','section'))
    if any(routing.contains(text,k) for k in policy.get('exclusions',[])):
        return False, 'Exclusion explicite.'
    sections = policy.get('categories',[])
    if sections and item.get('section') not in sections and item.get('category') not in sections:
        return False, 'Catégorie hors périmètre.'
    terms = policy.get('keywords',[])+policy.get('topics',[])
    if terms and not any(routing.contains(text,k) for k in terms):
        return False, 'Aucun mot-clé ou thème pertinent dans l’index.'
    if policy.get('require_reference') and not routing.match({'entity':'','title':item.get('title',''),'raw':{'detail_text':text}},entities):
        return False, 'Aucune entité du référentiel reconnue dans l’index.'
    if not (sections or terms or policy.get('require_reference')):
        return False, 'Aucun critère positif ; revue requise.'
    return True, 'Critères déterministes de pertinence satisfaits.'


def collect_document(item):
    from modules.cmf_collector_v1 import fetch_detail_content, _safe_cmf_url
    result = dict(item)
    if item.get('detail_url') and not item.get('pdf_url'):
        content = fetch_detail_content(item['detail_url'])
        result['raw_excerpt'] = content['text']
        result['pdf_url'] = content['pdf_url']
    if result.get('pdf_url'):
        import requests
        from modules.ocr_engine import extract_pdf_text
        response = requests.get(_safe_cmf_url(result['pdf_url']),timeout=(10,60))
        response.raise_for_status()
        if not response.content.startswith(b'%PDF'): raise ValueError('Document CMF non PDF.')
        # No document request happens before the relevance decision.
        with tempfile.TemporaryDirectory(prefix='ugfs_cmf_relevant_') as temp:
            pdf = Path(temp)/'source.pdf'; pdf.write_bytes(response.content)
            extracted = extract_pdf_text(pdf,persist=False)
        if not extracted['text'].strip(): raise ValueError('Document CMF sans texte exploitable.')
        result['raw_excerpt'] = extracted['text']
        target = admin_registry.DATABASE.parent/'cmf_documents'/(sha256(response.content).hexdigest()+'.pdf')
        target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists(): target.write_bytes(response.content)
    if not str(result.get('raw_excerpt') or '').strip():
        raise ValueError('Aucun contenu pertinent collecté ; publication conservée dans la découverte uniquement.')
    return result


def relevant_items(items, policy, entities):
    selected, errors, decisions = [], [], []
    for item in items:
        accepted, reason = decision(item,policy,entities)
        state = 'relevant' if accepted else 'excluded' if policy.get('configured') else 'pending_configuration'
        if accepted:
            try: selected.append(collect_document(item))
            except Exception as exc:
                state, reason = 'collection_error', str(exc)
                errors.append(str(exc))
        decisions.append((item['uid'],item.get('title',''),item.get('section',''),state,reason,admin_registry.now()))
    with admin_registry.transaction() as con:
        con.executemany('INSERT INTO cmf_discovery VALUES(?,?,?,?,?,?) ON CONFLICT(uid) DO UPDATE SET title=excluded.title,section=excluded.section,decision=excluded.decision,reason=excluded.reason,checked_at=excluded.checked_at',decisions)
        admin_registry.event(con,'cmf_relevance_check',{'discovered':len(items),'selected':len(selected),'errors':len(errors)})
    return selected, errors
