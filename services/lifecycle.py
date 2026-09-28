"""Canonical, independent priority / processing / reading dimensions."""
PRIORITIES = ("Critique", "Haute", "Moyenne", "Basse")
LIFECYCLE = ("Nouveau", "À analyser", "Analyse terminée", "À valider", "Traité", "Erreur d’analyse")


def priority(value):
    return {"critique": "Critique", "haute": "Haute", "élevée": "Haute", "moyenne": "Moyenne", "faible": "Basse", "basse": "Basse"}.get(str(value or "").casefold(), "Moyenne")


def result_validated(result):
    return bool(result and result.get("analysis")) and result.get("review_status") == "validated"


def successful_results(workspace):
    """Current métier results for business views, excluding composite parents.

    Historical results remain accessible with their original provenance; failed
    correctness outcomes never become successful business rows or backlog KPIs.
    """
    parents = {r['uid'] for r in workspace.get('rows', []) if r.get('document_status')}
    return [r for r in workspace.get('business_results', []) if r.get('analysis')
            and r['notification_uid'] not in parents
            and (r['analysis'].get('correctness') or {}).get('outcome') in {None, 'SUCCESS', 'SUCCESS_REVIEW_REQUIRED'}]


def treated(results):
    """All required business results must exist and be human validated.

    Neither read state nor priority participates in this definition.
    """
    return bool(results) and all(result_validated(result) for result in results)


def processing(result=None, attempt=None, *, is_new=False):
    if attempt and str(attempt.get('error','')).startswith('SEGMENTATION_REQUIRED') and not result:
        return 'Segmentation requise'
    if result_validated(result):
        return "Traité"
    if result and result.get("analysis"):
        return "Analyse terminée" if result.get("review_status") == "draft" else "À valider"
    if attempt and attempt.get("status") == "failed":
        return "Erreur d’analyse"
    return "Nouveau" if is_new and not attempt else "À analyser"


def aggregate(states):
    values=list(states.values())
    if values and all(s=='Traité' for s in values): return 'Traité'
    if 'Traité' in values: return 'Partiellement traité'
    return next((s for s in ('Segmentation requise','Publications détectées','Erreur d’analyse','À valider','Analyse terminée','À analyser','Nouveau') if s in values),'À analyser')


def scoped(row, service=None):
    view=dict(row)
    if service and service in row.get('services',[]):
        view['status']=row.get('service_states',{}).get(service,'À analyser')
        view['treated']=view['status']=='Traité'
        provenance=row.get('service_priorities',{}).get(service,{'value':'Moyenne','origin':'PROVISIONAL','explanation':'Priorité provisoire de triage'})
        view['priority']=provenance['value'];view['priority_provenance']=provenance
        view['analysis']=(row.get('business_results',{}).get(service) or {}).get('analysis')
        view['ai_state']={'Non analysée':'pending','Segmentation requise':'pending','Publications détectées':'pending','Analyse en cours':'running','Analysée':'done','Erreur d’analyse':'failed'}[ai_status(row,service)]
        view['business_results']={service:row.get('business_results',{}).get(service)}
    return view


def ai_status(row, service=None):
    """AI progress is independent of reading, priority and human validation."""
    if row.get('document_status'):return row['document_status']
    if service:
        attempt = (row.get('analysis_attempts', {}).get(service) or {})
        if str(attempt.get('error','')).startswith('SEGMENTATION_REQUIRED'):return 'Segmentation requise'
        result = row.get('business_results', {}).get(service)
        if attempt.get('status') == 'running': return 'Analyse en cours'
        if attempt.get('status') == 'failed': return 'Erreur d’analyse'
        if result and result.get('analysis'): return 'Analysée'
        return 'Non analysée'
    if row.get('ai_state') == 'running': return 'Analyse en cours'
    if row.get('ai_state') == 'failed': return 'Erreur d’analyse'
    if row.get('analysis') or any(r and r.get('analysis') for r in row.get('business_results', {}).values()): return 'Analysée'
    return 'Non analysée'
