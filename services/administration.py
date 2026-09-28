"""Read-only administration view models and explicit configuration commands."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import uuid
from modules import admin_registry
from services import pipeline_config, reference_import, routing, lifecycle

ROLES = ('Administrateur','Analyste','Validateur','Lecteur')


def fingerprint(config):
    return sha256(json.dumps(config,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def overview(workspace):
    config = workspace.get('pipeline_config') or pipeline_config.load()
    entities = [e for e in workspace.get('referential_entities',[]) if e.get('type') in reference_import.DOMAINS]
    counts = {key:sum(e.get('type')==key for e in entities) for key in reference_import.DOMAINS}
    rules = []
    for rule in config.get('routing_rules',[]):
        hits = [row for row in workspace['rows'] if any(reason.get('rule_id') == rule['id'] for reason in row.get('rule_matches',row.get('routing_reasons',[])))]
        rules.append({**rule,'matches':len(hits),'last_match':max((e.get('event_at','') for e in workspace.get('pipeline_events',[]) if e.get('event_type')=='routing_inferred' and rule['id'] in str(e.get('details_json',''))),default='Non disponible')})
    services = []
    for key,value in config['services'].items():
        from services.lifecycle import successful_results
        records = [r for r in successful_results(workspace) if r.get('service_id')==key]
        services.append({'key':key,'sources':[s['label'] for s in config['sources'].values() if key in s['eligible_services']], 'rules':sum(key in r.get('services',[]) and r.get('active',True) for r in rules),'assigned':sum(key in r['services'] for r in workspace['rows']),'results':len(records),'backlog':sum(r.get('review_status') in {'draft','pending','correction'} for r in records),'prompt_version':value['prompt_version']})
    return {'config':config,'fingerprint':fingerprint(config),'counts':counts,'entities':entities,'rules':rules,'services':services,'imports':admin_registry.read('reference_imports'),'events':sorted(admin_registry.read('admin_events'),key=lambda e:e['id'],reverse=True),'versions':admin_registry.read('configuration_versions'),'discoveries':admin_registry.read('cmf_discovery')}


def save(config, expected_hash, reason):
    if fingerprint(pipeline_config.load()) != expected_hash:
        raise ValueError('La configuration a changé ; rechargez la page avant d’enregistrer.')
    return pipeline_config.save(config, reason=reason, expected_hash=expected_hash)


def rule_action(action, rule, expected_hash):
    config = pipeline_config.load()
    if fingerprint(config) != expected_hash:
        raise ValueError('Configuration modifiée depuis l’ouverture du formulaire.')
    rules = config['routing_rules']
    current = next((r for r in rules if r['id']==rule.get('id')),None)
    value = deepcopy(rule)
    stamp = admin_registry.now()
    if action in {'create','duplicate'}:
        value['id'] = uuid.uuid4().hex
        value['created_at'] = stamp
        if action == 'duplicate':
            value['name'] += ' — copie'
            value['active'] = False
    elif current is None:
        raise ValueError('Règle introuvable.')
    value['updated_at'] = stamp
    if action == 'toggle': value['active'] = not current.get('active',True)
    if action not in {'create','duplicate','edit','toggle'}: raise ValueError('Action inconnue.')
    if action in {'create','duplicate'}: rules.append(value)
    else: rules[rules.index(current)] = value
    return save(config,expected_hash,'rule_'+action)


def prompt_history(service):
    versions = []
    for record in admin_registry.read('configuration_versions'):
        snapshot = json.loads(record['snapshot_json'])
        if service in snapshot.get('services',{}):
            versions.append({'id':str(record['id']),'at':record['recorded_at'],'prompt':snapshot['services'][service]})
    archive = pipeline_config.ROOT/'backups/pipeline_configuration'
    for path in sorted(archive.glob('*.json')) if archive.exists() else []:
        try:
            snapshot = json.loads(path.read_text(encoding='utf-8'))
            if service in snapshot.get('services',{}): versions.append({'id':path.name,'at':'Archive '+path.stem,'prompt':snapshot['services'][service]})
        except (ValueError,OSError): continue
    return versions


def activate_prompt(service, version_id, expected_hash):
    record = next((v for v in prompt_history(service) if v['id']==version_id),None)
    if not record: raise ValueError('Version historique introuvable.')
    config = pipeline_config.load()
    config['services'][service] = deepcopy(record['prompt'])
    config['services'][service]['activated_from'] = version_id
    return save(config,expected_hash,'prompt_activation')


def runtime_status():
    from modules import llm_analyzer
    from modules.email_digest_service import smtp_status
    from config import OUTPUT_EXCEL_DIR
    return {'model':llm_analyzer.OLLAMA_MODEL,'timeout':llm_analyzer.REQUEST_TIMEOUT_SECONDS,'input_budget':llm_analyzer.MAX_INPUT_CHARS,'smtp_configured':smtp_status()['configured'],'excel':str(OUTPUT_EXCEL_DIR),'architecture':'app.py → ui.app_ui → services.ui_adapter → backend','roles':ROLES}
