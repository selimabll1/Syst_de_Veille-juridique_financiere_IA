"""Result and AI workspaces: one row per persisted result or assigned need."""
import json
from datetime import date, timedelta
import streamlit as st
from services import ui_adapter as adapter
from services.lifecycle import ai_status, result_validated, successful_results
from ui import navigation as nav
from ui.components import presentation as p
from ui.pages.workspace import BUSINESS_LABELS

REVIEW = {'draft':'Analyse terminée','pending':'À valider','correction':'À corriger','validated':'Validé'}


def result_index(workspace):
    """Index saved métier records, never synthesize a result from a notification."""
    rows = {r['uid']:r for r in workspace['rows']+workspace.get('child_rows',[])}
    archived={r['notification_uid']:r for r in workspace.get('central_records',[])}
    items = []
    for record in successful_results(workspace):
        if not record.get('analysis'): continue
        row = rows.get(record['notification_uid'])
        if row and row.get('document_status'):continue
        if not row:
            saved=archived.get(record['notification_uid'],{})
            row={'uid':record['notification_uid'],'stable_uid':saved.get('source_key',record['notification_uid']),'source_key':saved.get('source_key',''),'title':saved.get('title') or 'Résultat conservé — source historique','entity':saved.get('entity',''),'kind':saved.get('source_kind','legaltech'),'source':saved.get('source_kind','Source historique'),'date':saved.get('source_date',''),'services':[record['service_id']],'business_results':{},'raw':{},'metadata':{},'documents':[],'read':True,'treated':False,'priority':'Moyenne','status':'Analyse terminée','summary':'','pdf_path':'','source_url':''}
        row={**row,'business_results':{**row.get('business_results',{}),record['service_id']:record}}
        items.append({'row':row,'record':record,'service':record['service_id'],
                      'key':f"{record['notification_uid']}:{record['service_id']}:{record.get('need_id','primary')}"})
    return sorted(items,key=lambda i:str(i['record'].get('updated_at','')),reverse=True)


def needs(workspace):
    return [{'row':r,'service':s,'state':ai_status(r,s),'record':r.get('business_results',{}).get(s),
             'attempt':r.get('analysis_attempts',{}).get(s) or {},'key':r['uid']+':'+s}
            for r in workspace['rows']+workspace.get('child_rows',[]) for s in r['services']]


def choose_result(key, uid):
    st.session_state['result_selected']=key
    nav.navigate_with_selection('results',uid)


def value_text(value):
    if isinstance(value,dict): return '\n'.join(f"{BUSINESS_LABELS.get(k,k.replace('_',' ').capitalize())} : {value_text(v)}" for k,v in value.items())
    if isinstance(value,list): return '\n'.join('• '+value_text(v) for v in value)
    return str(value) if value not in (None,'') else 'Non renseigné dans cette version'


def reliability(analysis):
    rel=analysis.get('reliability') or {}
    value=rel.get('score',analysis.get('confidence'))
    return value if isinstance(value,(int,float)) and not isinstance(value,bool) else None


def detail(item,workspace,context):
    original=item['row']; service=item['service']; record=item['record']; analysis=record['analysis']
    row=adapter.business_view(original,service)
    presentation=adapter.result_presentation({**analysis,'service':service})
    output=presentation['output']
    key=context+'_'+item['key']
    st.markdown('### Résultat métier')
    st.markdown('**'+p._esc(original['title'])+'**')
    st.caption(f"{adapter.service_label(service)} · Version {record.get('revision',1)} · {REVIEW.get(record.get('review_status'),'À valider')} · {record.get('updated_at','')}")
    scope=analysis.get('canonical_facts',{}).get('child_scope')
    if scope:st.caption(f"{scope['parent_title']} · Pages {scope['page_start']}–{scope['page_end']} · Publication indépendante")
    st.caption(f"Événement : {output.get('event_type','Non déterminé')} · Priorité : {row.get('priority','Moyenne')} · Fiabilité : {reliability(analysis) if reliability(analysis) is not None else 'Non disponible'}/100")
    correctness = analysis.get('correctness') or {}
    score = reliability(analysis)
    if not correctness:
        st.warning('Résultat historique : les contrôles de conformité actuels de l’analyse ne sont pas enregistrés dans cette version. Réexaminer les preuves avant utilisation.')
    elif correctness.get('details', {}).get('limited') or (score is not None and score < 80):
        st.warning('Résultat limité — revue humaine renforcée. ' + ' '.join(correctness.get('reasons', [])))
    financial_note=analysis.get('summary_derivation',{}).get('financial_note',{})
    # Corrections are authoritative; do not overlay a previous generated note.
    if analysis.get('grounding',{}).get('human_changes'):financial_note={}
    peers=[i for i in result_index(workspace) if i['row']['uid']==original['uid']]
    if len(peers)>1:
        for col,peer in zip(st.columns(len(peers)),peers):
            col.button(adapter.service_label(peer['service']),key=key+'_peer_'+peer['service'],on_click=choose_result,args=(peer['key'],original['uid']),width='stretch')
    tabs=st.tabs(['Résumé','Analyse détaillée','Preuves','Source','Historique'])
    with tabs[0]:
        st.markdown('**Synthèse métier**')
        st.write(value_text(output.get('summary') or analysis.get('summary') or 'Résumé non disponible dans cette version.'))
        key_facts=financial_note.get('key_facts',[])
        if key_facts:
            st.markdown('**Faits clés documentés**')
            numeric=[f for f in key_facts if f['text'].lstrip('-')[:1].isdigit()][:5]
            if numeric:
                for col,fact in zip(st.columns(min(3,len(numeric))),numeric[:3]):
                    col.metric(fact['label'],fact['text'])
                for fact in numeric[3:]:st.caption(fact['label']+' · '+fact['text'])
            else:
                for fact in key_facts[:4]:
                    if len(fact['text'])<=160:
                        st.markdown('**'+fact['label']+'**');st.write(fact['text'])
                    else:
                        with st.expander(fact['label']):st.write(fact['text'])
            for metric in financial_note.get('metrics',[]):
                if metric['name']=='Variation du capital (%)' and metric['validation_status']=='VERIFIED':
                    st.caption(f"Variation du capital : {float(metric['result']):.2f} % · Calcul Python vérifié")
            for section in financial_note.get('sections',[]):
                if section['label']=='Mécanisme documenté':st.write('Mécanisme documenté : '+section['text'])
        for field in ('event_type','regulatory_legal_event','investment_signal','commercial_signal','portfolio_relevance'):
            if output.get(field): st.caption(BUSINESS_LABELS.get(field,field)+' · '+value_text(output[field]))
        st.markdown('**Action recommandée**')
        st.write(value_text(presentation['recommendation']))
        if output.get('uncertainties'):
            st.markdown('**Incertitudes**');st.write(value_text(output['uncertainties']))
        rel=analysis.get('reliability') or {}
        cols=st.columns(3)
        cols[0].metric('Fiabilité factuelle',str(rel.get('factual_score','Non disponible')))
        relevance=rel.get('service_relevance',{})
        cols[1].metric('Pertinence métier',relevance.get('label','Non disponible') if isinstance(relevance,dict) else str(relevance))
        cols[2].metric('Indice global',str(reliability(analysis) if reliability(analysis) is not None else 'Non disponible'))
        st.caption('Mesure de complétude, cohérence et ancrage des preuves. Ce score n’est pas une probabilité statistique de vérité.')
    with tabs[1]:
        for section in financial_note.get('sections',[]):
            st.markdown('**'+section['label']+'**')
            st.caption({'FACT':'Fait source','INTERPRETATION':'Interprétation — à valider','RECOMMENDATION':'Recommandation UGFS'}[section['kind']])
            st.write(section['text'])
            st.caption('Preuves : '+', '.join(section['evidence_ids']))
        if financial_note.get('metrics'):
            with st.expander('Chiffres clés et calculs vérifiés'):
                for metric in financial_note['metrics']:
                    st.write(f"{metric['name']} : {float(metric['result']):,.2f} · {metric['validation_status']}")
                    st.caption(metric['formula']+' · Preuves : '+', '.join(metric['evidence_ids']))
        for field,value in output.items():
            if field in {'evidence','confidence','validation_status'}: continue
            label=financial_note.get('obligation_label') if field=='obligations' else None
            st.markdown('**'+(label or BUSINESS_LABELS.get(field,field.replace('_',' ').capitalize()))+'**');st.write(value_text(value))
        with st.expander('Données techniques de l’analyse',expanded=False):st.json(analysis)
    with tabs[2]:
        evidence=analysis.get('grounding',{}).get('evidence',[])
        if not evidence: st.info('Aucune citation structurée disponible dans cette version historique.')
        for e in evidence:
            if isinstance(e,dict):
                st.caption(str(e.get('id') or e.get('evidence_id') or 'Preuve source'))
                if e.get('page_start'):st.caption(f"Pages {e['page_start']}–{e['page_end']}")
                st.write(e.get('quote') or e.get('text') or e.get('citation') or value_text(e))
            else:st.write(str(e))
    with tabs[3]: p._source_tab(row)
    with tabs[4]:
        from ui.pages.activity import timeline, event_rows
        events=[e for e in event_rows(workspace) if e.get('uid')==original['uid'] and e.get('service') in {'',service}]
        timeline(events)
    a,b,c,d=st.columns(4)
    if a.button('Corriger',key=key+'_correct',disabled=service not in original['services'],width='stretch'):st.session_state[key+'_editing']=True
    validated=result_validated(record)
    if b.button('✓ Validé' if validated else 'Valider',key=key+'_validate',disabled=validated or service not in original['services'],width='stretch',type='primary'):
        nav.execute(adapter.set_review_status,original,'validated',service);st.rerun()
    if c.button('Exporter Excel',key=key+'_export',width='stretch'):
        nav.execute(adapter.export_excel,original,service);st.rerun()
    d.button('Diffuser',key=key+'_diffuse',disabled=not validated or service not in original['services'],on_click=nav.navigate_to_diffusion,args=(original['uid'],service),width='stretch')
    if service not in original['services']:st.caption('Résultat conservé : ce service n’est plus affecté. La validation et la diffusion sont indisponibles.')
    if st.session_state.get(key+'_editing'):
        with st.form(key+'_correction'):
            raw_output=analysis.get('business_output',{})
            changed={field:st.text_area(BUSINESS_LABELS.get(field,field.replace('_',' ').capitalize()),value_text(value)) for field,value in raw_output.items() if isinstance(value,str) and field not in {'validation_status','evidence','matched_portfolio_entity','referential_match_reason'}}
            note=st.text_input('Motif de correction')
            if st.form_submit_button('Enregistrer la correction'):
                nav.execute(adapter.set_review_status,original,'pending',service,corrected={**raw_output,**changed},note=note)
                st.session_state.pop(key+'_editing',None);st.rerun()


def results(workspace,validation=False):
    st.title('Validation' if validation else 'Résultats')
    st.caption('Résultats en attente de validation humaine' if validation else 'Tous les résultats métier enregistrés de l’analyse IA')
    items=result_index(workspace)
    if validation:items=[i for i in items if i['record'].get('review_status') in {'draft','pending','correction'}]
    mode=st.segmented_control('Validation des résultats',['Tous','À valider','Validés'] if not validation else ['À valider','À corriger'],default='À valider' if validation else 'Tous',key='result_mode_'+str(validation))
    a,b,c=st.columns([2,1,1])
    query=a.text_input('Rechercher un résultat',key='result_query_'+str(validation))
    service=b.selectbox('Service',['Tous',*adapter.SERVICES],format_func=lambda s:adapter.service_label(s) if s!='Tous' else s,key='result_service_'+str(validation))
    min_score=c.slider('Indice global minimum',0,100,0,key='result_score_'+str(validation))
    with st.expander('Filtres avancés'):
        a,b,c=st.columns(3)
        event=a.selectbox('Événement',['Tous',*sorted({str(i['record']['analysis'].get('canonical_facts',{}).get('event_type') or i['record']['analysis'].get('business_output',{}).get('event_type') or 'Non déterminé') for i in items})],key='result_event_'+str(validation))
        priority=b.selectbox('Priorité',['Toutes','Critique','Haute','Moyenne','Basse'],key='result_priority_'+str(validation))
        since=c.date_input('Analysé depuis',value=None,key='result_date_'+str(validation))
    filtered=[]
    for item in items:
        r=item['record'];row=adapter.service_view(item['row'],item['service']);analysis=r['analysis'];review=r.get('review_status')
        if service!='Tous' and item['service']!=service:continue
        if mode=='Validés' and review!='validated':continue
        if mode=='À valider' and review not in {'draft','pending','correction'}:continue
        if mode=='À corriger' and review!='correction':continue
        if query.casefold() not in (row['title']+' '+row['entity']).casefold():continue
        score=reliability(analysis)
        if min_score and (not isinstance(score,(int,float)) or score<min_score):continue
        if priority!='Toutes' and row['priority']!=priority:continue
        if since and str(r.get('created_at',''))[:10]<since.isoformat():continue
        ev=str(analysis.get('canonical_facts',{}).get('event_type') or analysis.get('business_output',{}).get('event_type') or 'Non déterminé')
        if event!='Tous' and event!=ev:continue
        filtered.append(item)
    left,right=st.columns([1,1.6],gap='small')
    selected=next((i for i in filtered if i['key']==st.session_state.get('result_selected')),next((i for i in filtered if i['row']['uid']==st.session_state.get(nav.SELECTED)),filtered[0] if filtered else None))
    with left:
        st.caption(f'{len(filtered)} résultat(s) métier')
        with st.container(height=580,border=False):
            for item in filtered:
                with st.container(border=True):
                    if st.button(p._clean(item['row']['title'],110),key='result_pick_'+str(validation)+item['key'],width='stretch'):
                        st.session_state['result_selected']=item['key'];st.rerun()
                    st.markdown(p._services_badges([item['service']])+' '+p._status_badge(REVIEW.get(item['record'].get('review_status'),'À valider')),unsafe_allow_html=True)
                    st.caption(f"Indice global : {reliability(item['record']['analysis']) or 'Non disponible'} · {str(item['record'].get('updated_at',''))[:16]}")
    with right,st.container(border=True):
        if selected:detail(selected,workspace,'validation' if validation else 'results')
        else:st.info('Aucun résultat en attente de validation.' if validation else 'Aucun résultat enregistré ne correspond à ces filtres.')


def analysis(workspace):
    st.title('Analyses IA');st.caption('Lancer, suivre et consulter les traitements IA')
    items=needs(workspace)
    active={(j.get('notification_uid'),s):j for j in adapter.active_actions() for s in j.get('services',[])}
    for item in items:
        item['job']=active.get((item['row']['uid'],item['service']))
        if item['job']:item['state']='Analyse en cours'
        elif item['state']=='Analyse en cours':item['state']='Erreur d’analyse';item['attempt']={**item['attempt'],'error':'Traitement interrompu : aucune tâche active dans cette session serveur. Vous pouvez réessayer.'}
    labels={'À analyser':'Non analysée','En cours':'Analyse en cours','Terminées':'Analysée','Erreurs':'Erreur d’analyse','Bulletins':'composite'}
    for col,(label,state) in zip(st.columns(5),labels.items()):col.metric(label,sum((bool(i['row'].get('document_status')) if state=='composite' else i['state']==state) for i in items))
    tab=st.segmented_control('Traitements IA',list(labels),default='À analyser',key='ai_workspace_tab') or 'À analyser'
    a,b=st.columns([3,1]);query=a.text_input('Rechercher une notification',key='ai_query');service=b.selectbox('Service',['Tous',*adapter.SERVICES],format_func=lambda s:adapter.service_label(s) if s!='Tous' else s,key='ai_service')
    selected=[i for i in items if (bool(i['row'].get('document_status')) if tab=='Bulletins' else i['state']==labels[tab]) and (service=='Tous' or service==i['service']) and query.casefold() in (i['row']['title']+' '+i['row']['entity']).casefold()]
    if not selected:st.info('Aucun traitement dans cette catégorie.')
    st.caption('Chaque analyse concerne un seul service. Les notifications sans affectation restent disponibles dans Notifications.')
    page=st.number_input('Page des analyses',1,max(1,(len(selected)+11)//12),key='ai_page')
    for item in selected[(page-1)*12:page*12]:
        row=item['row'];s=item['service']
        with st.container(border=True):
            a,b=st.columns([4,1.3])
            a.markdown('**'+p._esc(row['title'])+'**');a.caption(f"{row['source']} · {row['date']} · {adapter.service_label(s)}")
            if tab=='Bulletins':
                a.info(row['document_status'])
                b.button('Voir les publications',key='publications_'+row['uid'],on_click=nav.navigate_with_selection,args=('notifications',row['uid']))
                continue
            a.caption(f"Priorité : {adapter.service_view(row,s)['priority']} · Source : {'disponible' if row['documents'] else 'à vérifier'}")
            if tab=='Terminées':
                a.caption(f"{REVIEW.get(item['record'].get('review_status'),'À valider')} · Indice global : {reliability(item['record']['analysis']) or 'Non disponible'}")
                b.button('Voir le résultat',key='ai_result_'+item['key'],on_click=choose_result,args=(item['key']+':primary',row['uid']))
            if tab=='En cours':
                import time
                job=item['job']
                a.caption(f"{int(time.time()-job['started'])} s · Étape : "+{'extraction':'Extraction','facts':'Classification','evidence':'Préparation des preuves','inference':'Analyse IA','validation':'Contrôle de cohérence','persistence':'Enregistrement'}.get(job.get('stage'),'Démarrage'))
                a.caption('Vous pouvez continuer à naviguer.');continue
            if tab=='Erreurs':a.warning(str(item['attempt'].get('error') or item['attempt'].get('error_message') or 'Le dernier traitement a échoué. Consultez les détails avant de réessayer.'))
            if b.button('Réanalyser' if tab=='Terminées' else 'Réessayer' if tab=='Erreurs' else 'Analyser avec l’IA',icon=':material/auto_awesome:',key='ai_run_'+item['key'],disabled=s=='portfolio' and not row.get('portfolio_confirmed'),type='primary'):
                nav.start_action('Analyse '+adapter.service_label(s),'ollama','run_analysis',row,[s],force=tab=='Terminées');st.rerun()
