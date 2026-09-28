"""Executive dashboard: inexpensive projection of the cached workspace only."""
from datetime import datetime, timezone
from html import escape
import streamlit as st
from services import ui_adapter as adapter
from ui import navigation as nav
from ui.components.icons import icon
from ui.components import presentation as p
from ui.components.shell import kpis

SERVICE_ICONS={'investment':'chart','compliance':'shield','portfolio':'monitor','commercial':'person'}
SERVICE_COLORS={'investment':'cyan','compliance':'purple','portfolio':'blue','commercial':'amber'}
DESCRIPTIONS={'investment':'Due diligence, screening et veille','compliance':'Veille juridique, gouvernance et réglementation','portfolio':'Suivi des participations et événements','commercial':'Signaux commerciaux et opportunités'}

def short_date(value, now=None):
    if not value or value=='Jamais':return 'Jamais synchronisée'
    try:
        stamp=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if stamp.tzinfo:stamp=stamp.astimezone()
        now=now or datetime.now().astimezone()
        day=(now.date()-stamp.date()).days
        label='Aujourd’hui' if day==0 else 'Hier' if day==1 else f"{stamp.day} {['janv.','févr.','mars','avr.','mai','juin','juil.','août','sept.','oct.','nov.','déc.'][stamp.month-1]} {stamp.year if stamp.year!=now.year else ''}".strip()
        return label+(' · '+stamp.strftime('%H:%M') if 'T' in str(value) or ':' in str(value) else '')
    except (ValueError,TypeError):return str(value)[:16]

def dashboard_data(workspace):
    rows=workspace['rows']
    services={s:{'count':sum(s in r['services'] for r in rows),'analysed':sum(bool((r.get('business_results',{}).get(s) or {}).get('analysis')) for r in rows if s in r['services']),'pending':sum((r.get('business_results',{}).get(s) or {}).get('review_status') in {'draft','pending','correction'} for r in rows if s in r['services'])} for s in adapter.SERVICES}
    backlog=[]
    for r in rows+workspace.get('child_rows',[]):
        for service,record in r.get('business_results',{}).items():
            if record and record.get('analysis') and record.get('review_status') in {'draft','pending','correction'}:
                backlog.append({'row':r,'service':service,'state':record['review_status']})
        legacy=r.get('legacy_result')
        if legacy and legacy.get('analysis') and legacy.get('review_status') in {'draft','pending','correction'}:
            backlog.append({'row':r,'service':'legacy','state':legacy['review_status']})
    for r in workspace.get('child_rows',[]):
        for s,record in r.get('business_results',{}).items():
            if record and record.get('analysis'):
                services[s]['analysed']+=1
                services[s]['pending']+=record.get('review_status') in {'draft','pending','correction'}
    recent=sorted(rows,key=lambda r:adapter.date_obj(r.get('date')) or datetime.min.date(),reverse=True)[:5]
    return {'services':services,'backlog':backlog,'recent':recent,'references':len(workspace.get('referential_entities',[]))}

def sources_page():
    st.session_state['admin_settings_tab']='Sources';nav.navigate('settings')

def review_page(uid=None):
    # Drafts as well as pending/correction results belong in this dashboard queue.
    st.session_state['validation_scope']='Toutes'
    if uid:nav.navigate_with_selection('validation',uid)
    else:nav.navigate('validation')

def panel_header(title,subtitle,symbol,action=None):
    left,right=st.columns([3,1.55],vertical_alignment='center') if action else (st.container(),None)
    left.markdown(f'<div class="ug-home-panelhead"><span class="ug-home-icon">{icon(symbol)}</span><div><h2>{escape(title)}</h2><p>{escape(subtitle)}</p></div></div>',unsafe_allow_html=True)
    if action:
        label,key,callback,args=action
        right.button(label,key=key,on_click=callback,args=args,width='stretch')

def render(workspace):
    view=dashboard_data(workspace)
    with st.container(key='home_dashboard'):
        globe='<svg viewBox="0 0 500 180" aria-hidden="true"><defs><pattern id="ug-grid" width="12" height="12" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1" fill="#35B7E6"/></pattern><clipPath id="ug-globe"><ellipse cx="260" cy="188" rx="230" ry="170"/></clipPath></defs><g clip-path="url(#ug-globe)"><rect width="500" height="180" fill="url(#ug-grid)"/><g fill="none" stroke="#1B78A8"><ellipse cx="260" cy="188" rx="230" ry="170"/><ellipse cx="260" cy="188" rx="160" ry="170"/><ellipse cx="260" cy="188" rx="80" ry="170"/><ellipse cx="260" cy="188" rx="230" ry="110"/><ellipse cx="260" cy="188" rx="230" ry="50"/></g></g></svg>'
        st.markdown('<div class="ug-home-hero"><div><h1>Vue d’ensemble</h1><p>Synthèse de la veille juridique, financière et réglementaire</p></div>'+globe+'<aside>Des informations fiables<br>pour de meilleures décisions</aside></div>',unsafe_allow_html=True)
        kpis(workspace)
        with st.container(key='home_columns'):
            left,right=st.columns([1.85,1],gap='small')
            with left:
                with st.container(key='home_activity',border=True):
                    panel_header('Activité des services','Suivi des activités par service','bars')
                    for group in [('investment','compliance'),('portfolio','commercial')]:
                        columns=st.columns(2,gap='small')
                        for column,service in zip(columns,group):
                            stats=view['services'][service]
                            with column,st.container(key='home_service_'+service):
                                st.markdown(f'<div class="ug-home-service"><span class="ug-home-orb {SERVICE_COLORS[service]}">{icon(SERVICE_ICONS[service])}</span><div><h3>{escape(adapter.service_label(service))}</h3><div class="ug-home-count"><strong>{stats["count"]}</strong> notifications</div><small>{stats["analysed"]} analyses enregistrées · {stats["pending"]} à examiner</small><p>{DESCRIPTIONS[service]}</p></div><span class="ug-home-chevron">{icon("chevron")}</span></div>',unsafe_allow_html=True)
                                st.button('Ouvrir '+adapter.service_label(service),key='home_'+service,on_click=nav.navigate,args=(service,),width='stretch')
                with st.container(key='home_feed',border=True):
                    panel_header('Flux récent','Dernières notifications publiées','clock',('Toutes les notifications','home_all',nav.navigate,('notifications',)))
                    for row in view['recent']:
                        with st.container(key='home_feedrow_'+row['uid']):
                            title=p._clean(row.get('title'),115) or 'Notification sans titre'
                            context=p._clean(row.get('entity') or row.get('summary'),90)
                            st.markdown(f'<div class="ug-home-feedrow"><span class="ug-home-icon">{icon("document")}</span><div class="ug-home-feedtext"><strong>{escape(title)}</strong><small>{escape(context)}</small><div>{p._services_badges(row["services"], row.get("triage_services", [])) if row["services"] else ""}</div></div><div class="ug-home-feedmeta">{p._priority_badge(row["priority"])}<small>{escape(row.get("source", ""))}</small><time>{escape(short_date(row.get("date")))}</time></div><span class="ug-home-chevron">{icon("chevron")}</span></div>',unsafe_allow_html=True)
                            st.button('Ouvrir '+title,key='home_row_'+row['uid'],on_click=nav.navigate_with_selection,args=('notifications',row['uid']),width='stretch')
                    if not view['recent']:st.markdown('<div class="ug-home-empty">Aucune activité récente</div>',unsafe_allow_html=True)
            with right:
                with st.container(key='home_attention',border=True):
                    panel_header('À examiner','Analyses nécessitant une revue','search',('Ouvrir la validation','home_validation',review_page,()))
                    st.markdown(f'<div class="ug-home-attention-count"><strong>{len(view["backlog"])}</strong> analyses à examiner</div>',unsafe_allow_html=True)
                    for index,item in enumerate(view['backlog'][:2]):
                        row=item['row'];label='Analyse historique' if item['service']=='legacy' else adapter.service_label(item['service'])
                        with st.container(key='home_reviewrow_'+str(index)):
                            st.markdown(f'<div class="ug-home-review"><span class="ug-home-icon">{icon("document")}</span><div><strong>{escape(p._clean(row["title"],70))}</strong><small>{escape(label)} · {escape({"draft":"Analyse terminée","pending":"À valider","correction":"À corriger"}[item["state"]])}</small></div>{icon("chevron")}</div>',unsafe_allow_html=True)
                            st.button('Examiner '+row['title'],key='home_review_'+str(index),on_click=review_page,args=(row['uid'],),width='stretch')
                    if not view['backlog']:st.markdown('<div class="ug-home-empty">Aucune analyse en attente de revue</div>',unsafe_allow_html=True)
                with st.container(key='home_sources',border=True):
                    panel_header('État des sources','Collecte et disponibilité constatée','database',('Toutes les sources','home_sources_link',sources_page,()))
                    for source in [s for s in workspace['sources'] if s['status']!='À configurer']:
                        status=source['status'];tone='amber' if any(t in status.lower() for t in ['erreur','incompl','non connecté']) else 'cyan'
                        st.markdown(f'<div class="ug-home-source"><div><strong>{escape(source["label"])}</strong><span class="ug-home-source-state {tone}">{escape(status)}</span></div><small>Dernière collecte : {escape(short_date(source.get("last_check_at")))}</small></div>',unsafe_allow_html=True)
                    future=[s for s in workspace['sources'] if s['status']=='À configurer']
                    if future:
                        with st.expander(f'{len(future)} sources à configurer',expanded=False):
                            for source in future:st.caption(source['label']+' · À configurer')
                    if not workspace['sources']:st.caption('Aucune source configurée.')
                with st.container(key='home_reference',border=True):
                    panel_header('Référentiel UGFS','Correspondance et enrichissement des données','book')
                    title='Référentiel non renseigné' if not view['references'] else f'{view["references"]} enregistrements de référence disponibles'
                    message='Le rapprochement automatique avec les participations UGFS nécessite l’import du référentiel faisant autorité.' if not view['references'] else 'Les rapprochements confirmés restent consultables dans les notifications concernées.'
                    st.markdown(f'<div class="ug-home-reference"><strong>{escape(title)}</strong><p>{escape(message)}</p></div>',unsafe_allow_html=True)
                    st.button('Compléter le référentiel' if not view['references'] else 'Consulter le référentiel',key='home_reference_link',on_click=nav.navigate,args=('reference',),width='stretch')
