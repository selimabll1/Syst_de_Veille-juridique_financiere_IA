"""Read-only, service-scoped priority policy with explicit provenance."""
from services.lifecycle import PRIORITIES, priority

LABELS = {'HUMAN':'Choix humain', 'VALIDATED_RESULT':'Résultat validé', 'ANALYSIS_POLICY':'Politique métier de l’analyse', 'RULE':'Règle de veille', 'SOURCE_POLICY':'Politique explicite de la source', 'PROVISIONAL':'Priorité provisoire de triage', 'NONE':'Aucune règle applicable'}

def resolved(value=None, origin='NONE', detail=''):
    return {'value':priority(value), 'origin':origin, 'explanation':detail or LABELS[origin]}

def result_priority(record, service):
    if not record or not record.get('analysis'): return None
    metrics=record['analysis'].get('metrics', {})
    # Only documented service metrics with an unambiguous urgency mapping.
    field={'investment':'materiality','compliance':'regulatory_severity','portfolio':'monitoring_severity','commercial':'actionability'}[service]
    value={'Revue prioritaire':'Haute'}.get(metrics.get(field))
    if not value: return None
    origin='VALIDATED_RESULT' if record.get('review_status')=='validated' else 'ANALYSIS_POLICY'
    return resolved(value,origin,f"{LABELS[origin]} · {dict(investment='Investissement',compliance='Conformité',portfolio='Suivi portefeuille',commercial='Commerce')[service]} · revue prioritaire")

def resolve(row, service, config):
    overrides=row.get('priority_overrides', {})
    if service in overrides and overrides[service] is not None: return resolved(overrides[service],'HUMAN')
    result=result_priority(row.get('business_results',{}).get(service),service)
    if result: return result
    rules=[r for r in row.get('rule_matches',[]) if service in r.get('services',[]) and r.get('priority')]
    if rules:
        rule=min(rules,key=lambda r:PRIORITIES.index(priority(r['priority'])))
        return resolved(rule['priority'],'RULE','Règle « '+rule['rule']+' »')
    policy=config.get('sources',{}).get(row['kind'],{}).get('priority_policy',{}).get(service)
    if policy and policy.get('enabled'):
        return resolved(policy['value'],'SOURCE_POLICY',policy.get('name','Politique explicite de la source'))
    return resolved('Moyenne', 'PROVISIONAL')

def apply(row,config):
    row['service_priorities']={s:resolve(row,s,config) for s in row['services']}
    choices=[v for v in row['service_priorities'].values() if v['origin']!='NONE']
    row['global_priority']=min(choices,key=lambda v:PRIORITIES.index(v['value'])) if choices else resolved()
    row['priority']=row['global_priority']['value']
    row['priority_provenance']=row['global_priority']
    return row
