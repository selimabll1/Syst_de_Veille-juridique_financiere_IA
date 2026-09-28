"""Chronological business activity; identifiers stay in collapsed diagnostics."""
import json
from datetime import date,timedelta
import streamlit as st
from services import ui_adapter as adapter
from ui.components.presentation import _esc

EVENTS={'analysis_completed':('Analyse IA','Analyse IA terminée'),'analysis_failed':('Erreur IA','Analyse IA interrompue'),'analysis_started':('Analyse IA','Analyse IA lancée'),'service_assignment':('Affectation','Affectation métier modifiée'),'routing_inferred':('Affectation','Routage métier évalué'),'human_correction':('Correction','Résultat corrigé'),'review_validated':('Validation','Résultat validé'),'review_pending':('Validation','Résultat soumis à validation'),'review_correction':('Correction','Correction demandée'),'priority_override':('Priorité','Priorité modifiée'),'excel_export':('Export','Export Excel généré'),'digest_queued':('Diffusion','Ajout à la file de diffusion')}
EVENTS.update({'excel_exported':('Export','Export Excel généré'),'digest_sent':('Diffusion','Digest envoyé'),'note_added':('Suivi','Note ajoutée'),'notification_registered':('Collecte','Notification enregistrée'),'routing_evaluated':('Affectation','Routage métier évalué'),'analysis_cache_hit':('Analyse IA','Résultat existant réutilisé'),'AI_PROPOSAL':('Affectation','Proposition de routage IA'),'read':('Lecture','Notification lue'),'unread':('Lecture','Notification marquée non lue'),'reference_import':('Référentiel','Référentiel importé'),'referential_import':('Référentiel','Référentiel importé')})


def event_rows(workspace):
    lookup={key:r for r in workspace['rows']+workspace.get('child_rows',[]) for key in {r['uid'],r.get('stable_uid',''),r.get('source_key','')}}
    result=[]
    for event in workspace.get('pipeline_events',[])+workspace.get('history',[])+workspace.get('admin_events',[]):
        raw=event.get('event_type') or event.get('action') or 'Événement'
        family,title=EVENTS.get(raw,('Activité','Mise à jour du suivi'))
        if raw=='document_segmented':family,title='Préparation documentaire','Publications du bulletin préparées'
        if raw=='analysis_failed' and 'SEGMENTATION_REQUIRED' in str(event.get('details_json','')):family,title='Préparation documentaire','Segmentation requise'
        if any(term in raw for term in ('configuration','prompt','rule_','policy')):family,title='Configuration','Configuration mise à jour'
        row=lookup.get(event.get('notification_uid') or event.get('alert_key'),{})
        result.append({'at':str(event.get('event_at') or event.get('created_at') or ''),'title':title,'family':family,'service':event.get('service_id') or '', 'source':row.get('source',''),'text':row.get('title',''),'uid':row.get('uid',''),'raw':event})
    for key,source in [('legaltech_runs','LegalTech'),('cmf_runs','CMF')]:
        for run in workspace.get(key,[]):
            failed=run.get('status')=='FAILED' or bool(json.loads(run.get('errors_json') or '[]'))
            completed=bool(run.get('finished_at'))
            result.append({'at':str(run.get('finished_at') or run.get('started_at') or ''),'title':f'Synchronisation {source} '+('interrompue' if failed else 'terminée' if completed else 'lancée'),'family':'Synchronisation','service':'','source':source,'text':'Consultez le compte rendu de collecte.' if failed else 'Collecte enregistrée.','uid':'','raw':run})
    return sorted(result,key=lambda e:e['at'],reverse=True)


def timeline(events):
    if not events:st.info('Aucun événement enregistré pour cette sélection.');return
    day=None
    for event in events[:100]:
        if event['at'][:10]!=day:
            day=event['at'][:10];st.markdown('**'+('Aujourd’hui' if day==date.today().isoformat() else day or 'Date non renseignée')+'**')
        st.markdown(f'<div class="ug-timeline-event"><time>{_esc(event["at"][11:16])}</time><div><strong>{_esc(event["title"])}</strong><p>{_esc(event["text"])}</p><small>{_esc(adapter.service_label(event["service"]) if event["service"] else event["source"])}</small></div></div>',unsafe_allow_html=True)
    with st.expander('Détails techniques',expanded=False):st.json([e['raw'] for e in events[:100]])


def render(workspace):
    st.title('Historique');st.caption('Toutes les actions et événements du système')
    events=event_rows(workspace)
    a,b,c,d=st.columns(4)
    period=a.selectbox('Période',['Toutes','7 derniers jours','30 derniers jours'],key='history_period')
    service=b.selectbox('Service',['Tous',*adapter.SERVICES],format_func=lambda s:adapter.service_label(s) if s!='Tous' else s,key='history_service')
    family=c.selectbox('Action',['Toutes',*sorted({e['family'] for e in events})],key='history_family')
    source=d.selectbox('Source',['Toutes',*sorted({e['source'] for e in events if e['source']})],key='history_source')
    days={'7 derniers jours':7,'30 derniers jours':30}.get(period)
    timeline([e for e in events if (service=='Tous' or e['service']==service) and (family=='Toutes' or e['family']==family) and (source=='Toutes' or e['source']==source) and (not days or e['at'][:10]>=(date.today()-timedelta(days=days)).isoformat())])
