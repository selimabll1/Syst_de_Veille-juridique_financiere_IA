"""Preview and confirmed, append-only authoritative referential imports."""
import csv
import io
import json
import uuid
from pathlib import Path
from hashlib import sha256
from modules import admin_registry
from services import routing, pipeline_config

DOMAINS = {'portfolio':'Participations','pipeline_dd':'Pipeline DD','fund':'Fonds','director':'Dirigeants','shareholder':'Actionnaires','sector':'GICS L4'}
TEMPLATES = {'portfolio':'participations','pipeline_dd':'pipeline_dd','fund':'fonds','director':'dirigeants','shareholder':'actionnaires','sector':'gics_l4'}
FIELDS = ('name','identifier','type','portfolio_company','fund','gics_l4','sector','role_ugfs','reference_id','source_reference','as_of','status','entry_date','ownership_pct','dd_status','potential_fund','owner','notes','function','fund_type','shareholder_type','parent','code','label')
ALIASES = {'societe':'name','nom':'name','nom du fonds':'name','actionnaire':'name','identifiant':'identifier','fonds lie':'fund','fonds potentiel':'potential_fund','societe liee':'portfolio_company','fonction':'function','statut':'status','statut dd':'dd_status','responsable':'owner','secteur':'sector','date entree':'entry_date','date d entree':'entry_date','date':'as_of','derniere mise a jour':'as_of','source':'source_reference','provenance':'source_reference','participation':'ownership_pct','libelle':'label','parent classification':'parent'}
KINDS = {'participation':'portfolio','participations':'portfolio','portefeuille':'portfolio','pipeline dd':'pipeline_dd','fonds':'fund','dirigeant':'director','dirigeants':'director','actionnaire':'shareholder','actionnaires':'shareholder','gics l4':'sector'}


def parse(filename, payload):
    if len(payload) > 10 * 1024 * 1024:
        raise ValueError('Fichier limité à 10 Mo.')
    suffix = Path(filename).suffix.lower()
    if suffix == '.csv':
        text = payload.decode('utf-8-sig')
        try:
            dialect = csv.Sniffer().sniff(text[:8192], delimiters=',;\t')
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        columns = list(reader.fieldnames or [])
        rows = list(reader)
    elif suffix == '.json':
        rows = json.loads(payload.decode('utf-8-sig'))
        if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
            raise ValueError('JSON attendu : liste d’objets.')
        columns = list(dict.fromkeys(k for row in rows for k in row))
    elif suffix == '.xlsx':
        from openpyxl import load_workbook
        book = load_workbook(io.BytesIO(payload), read_only=True, data_only=True)
        try:
            values = book.active.iter_rows(values_only=True)
            columns = [str(c or '') for c in next(values, [])]
            rows = [dict(zip(columns, values)) for values in values if any(v is not None for v in values)]
        finally:
            book.close()
    else:
        raise ValueError('Formats acceptés : CSV UTF-8, XLSX ou JSON.')
    if len(rows) > 10000:
        raise ValueError('Un import est limité à 10 000 lignes.')
    if len(set(routing.normalized(c) for c in columns)) != len(columns):
        raise ValueError('En-têtes dupliqués ou vides : corrigez les colonnes.')
    known = {routing.normalized(k):k for k in FIELDS}
    mapped = {c:known.get(routing.normalized(c), ALIASES.get(routing.normalized(c))) for c in columns}
    targets = [v for v in mapped.values() if v]
    if len(targets) != len(set(targets)):
        raise ValueError('Plusieurs colonnes correspondent au même champ ; fusionnez-les explicitement.')
    clean = [{mapped[k]:str(v).strip() for k,v in row.items() if mapped.get(k) and v is not None and str(v).strip()} for row in rows]
    return clean, mapped


def preview(filename, payload, domain):
    if domain not in DOMAINS:
        raise ValueError('Domaine de référentiel inconnu.')
    filename = Path(filename).name
    rows, mapped = parse(filename, payload)
    configured, errors = routing.referential(pipeline_config.load(), [], [])
    if errors:
        raise ValueError('Résolvez les erreurs des référentiels existants avant import : '+' ; '.join(errors))
    existing = configured + admin_registry.entities()
    valid, invalid, duplicates = [], [], []
    detected = set()
    for number, row in enumerate(rows, 2):
        kind = KINDS.get(routing.normalized(row.get('type')), row.get('type') or domain)
        detected.add(kind)
        name = row.get('name') or (row.get('label') if domain == 'sector' else '')
        issue = ''
        if not name:
            issue = 'Nom / société / libellé requis.'
        elif kind != domain:
            issue = 'Type de ligne incompatible avec le domaine choisi.'
        elif domain == 'sector' and not (row.get('code') or row.get('gics_l4') or row.get('identifier')):
            issue = 'Code GICS requis.'
        elif row.get('ownership_pct'):
            try:
                percent = float(row['ownership_pct'].replace('%','').replace(',','.'))
                if not 0 <= percent <= 100: raise ValueError()
            except ValueError:
                issue = 'Participation attendue entre 0 et 100 %.'
        if issue:
            invalid.append({'ligne':number,'erreur':issue}); continue
        item = {**row,'name':name,'type':domain,'origin':filename,'source_reference':row.get('source_reference') or filename,'record_id':'','file_hash':sha256(payload).hexdigest()}
        same = [e for e in existing+valid if e.get('type') == domain and (routing.normalized(e.get('name')) == routing.normalized(name) or (item.get('identifier') and routing.normalized(e.get('identifier')) == routing.normalized(item['identifier'])))]
        if same:
            duplicates.append({'ligne':number,'nom':name,'motif':'Nom ou identifiant déjà présent : revue requise, aucun rapprochement automatique.'})
        valid.append(item)
    blocked_template = 'template' in filename.casefold() or 'exemple' in filename.casefold()
    return {'filename':filename,'domain':domain,'detected_domains':sorted(detected),'rows':len(rows),'valid_rows':len(valid),'invalid_rows':len(invalid),'invalid':invalid,'duplicates':duplicates,'recognized_columns':{k:v for k,v in mapped.items() if v},'ignored_columns':[k for k,v in mapped.items() if not v],'records':valid,'sha256':sha256(payload).hexdigest(),'can_import':bool(valid) and not invalid and not duplicates and not blocked_template,'template':blocked_template}


def commit(filename, payload, domain, expected_hash, confirmed=False):
    if not confirmed:
        raise ValueError('Confirmation explicite de l’origine faisant autorité requise.')
    with admin_registry.transaction() as con:
        plan = preview(filename, payload, domain)
        if plan['sha256'] != expected_hash or not plan['can_import']:
            raise ValueError('Import refusé : aperçu modifié, lignes invalides, modèle ou doublons à revoir.')
        token, stamp = uuid.uuid4().hex, admin_registry.now()
        con.execute('INSERT INTO reference_imports VALUES(?,?,?,?,?,?,?,?)',(token,plan['filename'],domain,plan['sha256'],plan['valid_rows'],stamp,'Utilisateur local — non authentifié',payload))
        for item in plan['records']:
            key = uuid.uuid4().hex
            item.update(record_id=key, import_id=token, imported_at=stamp)
            con.execute('INSERT INTO reference_records VALUES(?,?,?,?,?,?,?)',(key,token,domain,routing.normalized(item['name']),routing.normalized(item.get('identifier')),json.dumps(item,ensure_ascii=False),stamp))
        admin_registry.event(con,'referential_import',{'import_id':token,'filename':plan['filename'],'domain':domain,'rows':plan['valid_rows'],'sha256':plan['sha256']})
    return f"{plan['valid_rows']} enregistrement(s) importé(s), provenance conservée."


def template(domain):
    path = pipeline_config.ROOT/'data/reference/import_templates'/(TEMPLATES[domain]+'_template.csv')
    return path.name, path.read_bytes()
