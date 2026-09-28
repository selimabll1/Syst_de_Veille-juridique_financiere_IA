"""Poll only the progress fragment; refresh workspace once on completion."""
import streamlit as st
import time
from services import ui_adapter as adapter


def _dismiss(token):
    st.session_state.setdefault('ugfs_jobs_dismissed',[]).append(token)


def _jobs_body():
    st.empty()  # Emit an empty tree when every task has been dismissed.
    acknowledged = st.session_state.setdefault("ugfs_jobs_seen", [])
    refresh = False
    for token in list(dict.fromkeys(st.session_state.get("ugfs_jobs", [])))[-5:]:
        if token in st.session_state.get("ugfs_jobs_dismissed",[]):continue
        job = adapter.action_status(token)
        if not job:
            continue
        running = job["state"] == "running"
        context=st.session_state.get('ugfs_job_context',{}).get(token)
        result=job.get('result') or {}
        segmentation=(context or {}).get('operation')=='segmentation' or (isinstance(result,dict) and (result.get('operation')=='segmentation' or result.get('outcome')=='SEGMENTATION_REQUIRED')) or 'SEGMENTATION_REQUIRED' in str(job.get('error') or (result.get('message') if isinstance(result,dict) else ''))
        if segmentation and context:
            from ui import navigation as nav
            with st.container(border=True):
                st.markdown('**'+('Analyse du bulletin CMF' if running else 'Publications du bulletin' if job['state']=='complete' else 'Segmentation requise')+'**')
                st.caption(context['title'])
                if running:
                    for code,label in [('extraction','Extraction'),('segmentation','Identification des publications'),('sections','Création des sections')]:
                        st.write(('✓ ' if code in job.get('completed_stages',[]) else '● ' if job.get('stage')==code else '○ ')+label)
                    st.caption('Vous pouvez continuer à naviguer.')
                else:
                    st.info(result.get('message','Segmentation requise : sélectionnez une publication avant l’analyse.') if isinstance(result,dict) else 'Segmentation requise')
                    if job.get('error') and 'SEGMENTATION_REQUIRED' not in job['error']:st.warning(job['error'])
                    if st.button('Voir les publications',key='view_publications_'+token):nav.navigate_with_selection('notifications',context['uid']);st.rerun()
                    st.button('Masquer',key='dismiss_'+token,on_click=_dismiss,args=(token,))
            if not running and token not in acknowledged:acknowledged.append(token);refresh=True
            continue
        if context:
            from ui import navigation as nav
            service=adapter.service_label(job.get('service','')) if job.get('service') else job['label'].replace('Analyse ','')
            elapsed=int(job.get('finished',time.time())-job['started'])
            suffix='en cours' if running else 'échouée' if job['state']=='failed' else 'terminée'
            line,action,close=st.columns([7,1.6,.55],vertical_alignment='top')
            with line.expander(f"Analyse {service} · {suffix} · {elapsed} s",expanded=running,icon=':material/auto_awesome:' if running else ':material/error_outline:' if job['state']=='failed' else ':material/check_circle:'):
                st.caption(context['entity']+' · '+context['title'])
                stages=[('extraction','Extraction du document'),('facts','Faits et classification'),('evidence','Sélection des preuves'),('inference','Analyse métier'),('validation','Contrôle de cohérence'),('persistence','Enregistrement')]
                current=next((i for i,(key,_) in enumerate(stages) if key==job.get('stage')), -1)
                for i,(_,label) in enumerate(stages):
                    symbol='✓' if stages[i][0] in job.get('completed_stages',[]) or (job['state']=='complete' and i==current) else '●' if running and i==current else '○'
                    st.markdown(f'<div class="ug-action-stage {"active" if symbol=="●" else ""}">{symbol} {label}</div>',unsafe_allow_html=True)
                if running:st.caption('Vous pouvez continuer à naviguer pendant l’analyse.')
                if job['state']=='failed':
                    result=job.get('result') or {}
                    st.error(job.get('error') or (result.get('message') if isinstance(result,dict) else str(result)) or 'Analyse interrompue.')
                    if action.button('Réessayer',key='retry_'+token):
                        label,resource,name,args,kwargs=context['retry'];nav.start_action(label,resource,name,*args,**kwargs);st.rerun()
            if not running:
                close.button('Masquer',icon=':material/close:',key='dismiss_'+token,help='Masquer cette tâche',on_click=_dismiss,args=(token,))
            if job['state']=='complete' and action.button('Voir le résultat',key='view_'+token):
                service = job.get('service') or next(iter(job.get('services') or []), None)
                nav.navigate_to_result(context['uid'], service);st.rerun()
        else:
            state='running' if running else 'error' if job['state']=='failed' else 'complete'
            with st.status(job['label'],state=state,expanded=running):
                for message in job.get('messages',[])[-8:]:st.text(message)
                if job.get('error'):st.error(job['error'])
                result=job.get('result')
                if isinstance(result,dict):st.write(result.get('message',''))
                elif isinstance(result,tuple):st.text(str(result[1])[-5000:])
            if not running:st.button('Masquer',key='dismiss_'+token,on_click=_dismiss,args=(token,))
        if not running and token not in acknowledged:
            acknowledged.append(token)
            refresh = True
    if refresh:
        adapter.invalidate_cache()
        st.rerun()


def _body():
    from pathlib import Path
    import re
    active=[t for t in st.session_state.get('ugfs_jobs',[]) if t not in st.session_state.get('ugfs_jobs_dismissed',[]) and adapter.action_status(t)]
    notice=st.session_state.get('ugfs_notice')
    if not active and not notice:st.empty();return
    with st.container(key='action_center'):
        st.caption('CENTRE D’ACTIONS')
        _jobs_body()
        if notice:
            level,message=notice
            safe=re.sub(r'[A-Za-z]:[\\/][^\n]+','Consultez les détails techniques.',str(message))[:240]
            st.markdown(('**Opération réussie** · ' if level=='success' else '**Déjà en cours** · ' if level=='warning' else '**Opération interrompue** · ')+safe)
            if level=='warning':st.caption('Une opération est actuellement active. Vous pouvez continuer à naviguer.')
            path=st.session_state.get('ugfs_notice_download')
            if path and Path(path).is_file():st.download_button('Télécharger',Path(path).read_bytes(),file_name=Path(path).name,key='notice_download',on_click='ignore')
            if safe!=message:
                with st.expander('Détails de l’opération',expanded=False):st.text(message)
            if st.button('Fermer',key='notice_close'):
                st.session_state.pop('ugfs_notice',None);st.session_state.pop('ugfs_notice_download',None);st.rerun()


def render():
    running = any((adapter.action_status(token) or {}).get("state") == "running" for token in st.session_state.get("ugfs_jobs", []))
    st.fragment(run_every="2s" if running else None)(_body)()
