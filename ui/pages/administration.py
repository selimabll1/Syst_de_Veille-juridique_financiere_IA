"""Administration pages using the approved shell and the single UI adapter."""
from copy import deepcopy
import json
import streamlit as st
from services import ui_adapter as adapter
from services.lifecycle import successful_results
from ui import navigation as nav
from ui.components.presentation import _esc

DOMAINS = {'portfolio':'Participations','pipeline_dd':'Pipeline DD','fund':'Fonds','director':'Dirigeants','shareholder':'Actionnaires','sector':'GICS L4'}
SETTINGS_TABS = ['Vue d’ensemble','Configuration','Supervision']
CONFIG_TABS = ['Sources & règles de veille','Services & analyses','IA & restitution','Diffusion & accès']
REFERENCE_TABS = ['Vue d’ensemble',*DOMAINS.values(),'Imports']
LABELS = {'name':'Nom / société','identifier':'Identifiant','fund':'Fonds lié','status':'Statut','sector':'Secteur','gics_l4':'GICS L4','entry_date':'Date d’entrée','ownership_pct':'Participation (%)','source_reference':'Source / provenance','as_of':'Date de référence','imported_at':'Date d’import','portfolio_company':'Société liée','dd_status':'Statut DD','potential_fund':'Fonds potentiel','owner':'Responsable','notes':'Notes','function':'Fonction','fund_type':'Type de fonds','shareholder_type':'Type d’actionnaire','code':'Code','label':'Libellé','parent':'Classification parente','origin':'Fichier source','record_id':'Identifiant de référence','role_ugfs':'Rôle UGFS'}


def select(key,value):
    st.session_state[key] = value
    if key=='admin_settings_tab':st.session_state.pop('admin_link_consumed',None)


def route(page,tab=None):
    nav.navigate(page)
    if tab: st.session_state['admin_reference_tab' if page=='reference' else 'admin_settings_tab'] = tab


def header(reference=False):
    left,right = st.columns([3,2],vertical_alignment='center')
    with left:
        st.caption('ADMINISTRATION  /  '+('RÉFÉRENTIEL UGFS' if reference else 'ORGANISATION & PARAMÉTRAGE'))
        st.subheader('Référentiel UGFS' if reference else 'Organisation & Paramétrage')
        st.caption('Rapprochement des entités, participations et relations vérifiées' if reference else 'Configuration de la plateforme, sources, règles et IA locale')
    with right:
        a,b=st.columns(2)
        a.button('Référentiel UGFS',key='admin_reference_link',type='primary' if reference else 'secondary',on_click=route,args=('reference',),width='stretch')
        b.button('Organisation & Paramétrage',key='admin_settings_link',type='secondary' if reference else 'primary',on_click=route,args=('settings',),width='stretch')


def cards(values):
    st.markdown('<div class="ug-admin-kpis">'+''.join('<div class="ug-admin-kpi"><small>'+_esc(label)+'</small><strong>'+_esc(str(value))+'</strong><span>'+_esc(note)+'</span></div>' for label,value,note in values)+'</div>',unsafe_allow_html=True)


def table(rows, **kwargs):
    if rows: st.dataframe(rows,hide_index=True,width='stretch',**kwargs)
    else: st.caption('Non renseigné — aucun enregistrement disponible.')


def save(config,view,reason):
    result=nav.execute(adapter.command,'save_admin_config',config,view['fingerprint'],reason)
    st.rerun()


def reference(workspace):
    view=adapter.administration_view(workspace)
    header(True)
    selected=st.segmented_control('Domaines du référentiel',REFERENCE_TABS,default=None if 'admin_reference_tab' in st.session_state else REFERENCE_TABS[0],key='admin_reference_tab',label_visibility='collapsed') or REFERENCE_TABS[0]
    if selected=='Vue d’ensemble':
        if not any(view['counts'].values()):
            st.markdown('<div class="ug-admin-empty-reference"><div class="ug-admin-empty-icon">◎</div><h2>Référentiel UGFS à compléter</h2><p>Aucune donnée faisant autorité n’a encore été importée. Le référentiel permettra d’identifier les participations, fonds, dirigeants et actionnaires concernés par les informations collectées.</p></div>',unsafe_allow_html=True)
            a,b=st.columns(2)
            a.button('Importer des données',icon=':material/upload:',type='primary',on_click=select,args=('admin_reference_tab','Imports'),width='stretch')
            b.button('Voir les modèles d’import',key='reference_models_empty',on_click=select,args=('admin_reference_tab','Imports'),width='stretch')
            st.caption('Participations · Pipeline DD · Fonds · Dirigeants · Actionnaires · GICS L4')
            with st.expander('Détails des domaines disponibles'):
                table([{'Domaine':label,'État':'À compléter'} for key,label in DOMAINS.items()])
            return
        st.markdown('<div class="ug-admin-reference-intro"><strong>Référentiel UGFS renseigné</strong><span>Les correspondances confirmées restent liées à leur provenance.</span></div>',unsafe_allow_html=True)
        st.button('Importer des données',icon=':material/upload:',type='primary',on_click=select,args=('admin_reference_tab','Imports'))
        a,b=st.columns([1.3,1])
        with a,st.container(border=True):
            st.markdown('**Domaines du référentiel**')
            table([{'Domaine':label,'Enregistrements':view['counts'][key],'État':'Renseigné' if view['counts'][key] else 'Non renseigné'} for key,label in DOMAINS.items()])
        with b,st.container(border=True):
            st.markdown('**Rapprochement et provenance**')
            st.caption('Collecte → entité → référence vérifiée → services concernés. Un dossier DD ou une liste de surveillance ne prouve pas une détention.')
            matches=[{'Notification':r['title'],'Entité':m['name'],'Domaine':DOMAINS.get(m['type'],m['type']),'Provenance':m['match_reason'],'Relation':m.get('relationship_reason',''),'Participation confirmée':bool(m.get('portfolio_verified'))} for r in workspace['rows'] for m in r.get('matches',[])]
            table(matches)
        return
    if selected=='Imports':
        imports(view); return
    domain=next(k for k,v in DOMAINS.items() if v==selected)
    rows=[r for r in view['entities'] if r.get('type')==domain]
    search,filter_col=st.columns([3,1])
    term=search.text_input('Rechercher',key='reference_search_'+domain,placeholder='Nom, identifiant, société liée…')
    statuses=sorted({r.get('status') or r.get('dd_status') or 'Non renseigné' for r in rows})
    status=filter_col.selectbox('Statut',['Tous',*statuses],key='reference_status_'+domain)
    rows=[r for r in rows if (not term or term.casefold() in json.dumps(r,ensure_ascii=False).casefold()) and (status=='Tous' or (r.get('status') or r.get('dd_status') or 'Non renseigné')==status)]
    st.caption(f'{len(rows)} enregistrement(s) · provenance conservée lors de chaque import.')
    table([{LABELS.get(k,k):v for k,v in r.items() if k in LABELS} for r in rows])
    if domain in {'fund','sector'}:
        st.markdown('**Entités liées**')
        field='fund' if domain=='fund' else 'gics_l4'
        table([{'Entité':r['name'],'Lien':r[field],'Provenance':r.get('origin','Non disponible')} for r in view['entities'] if r.get(field)])
    st.button('Importer des données',key='import_'+domain,on_click=select,args=('admin_reference_tab','Imports'))


def imports(view):
    st.caption('Prévisualiser → examiner les erreurs et doublons → confirmer l’origine faisant autorité → importer. Aucun remplacement silencieux.')
    domain=st.selectbox('Domaine à importer',list(DOMAINS),format_func=DOMAINS.get,key='import_domain')
    filename,template=adapter.reference_template(domain)
    a,b=st.columns([1,2])
    a.download_button('Télécharger le modèle vide',template,file_name=filename,on_click='ignore',key='reference_template_download')
    if b.button('Prévisualiser le modèle vide',key='preview_template'):
        st.session_state['reference_preview']={'plan':adapter.reference_preview(filename,template,domain),'payload':template}
    upload=st.file_uploader('Fichier faisant autorité — CSV, XLSX ou JSON',type=['csv','xlsx','json'],key='reference_upload',help='Taille maximale acceptée : 10 Mo ; 10 000 lignes. Le fichier est contrôlé avant confirmation.')
    if st.button('Prévisualiser le fichier',disabled=upload is None,key='preview_reference'):
        try:
            payload=upload.getvalue()
            st.session_state['reference_preview']={'plan':adapter.reference_preview(upload.name,payload,domain),'payload':payload}
        except Exception as exc: st.error(str(exc)); st.session_state.pop('reference_preview',None)
    pending=st.session_state.get('reference_preview')
    if pending:
        plan=pending['plan']
        st.markdown('**Aperçu : '+_esc(plan['filename'])+'**')
        cards([('Domaine',DOMAINS[plan['domain']],'Détecté : '+(', '.join(plan['detected_domains']) or 'fichier vide')),('Lignes',plan['rows'],'Total'),('Valides',plan['valid_rows'],'Validation du schéma'),('Invalides',plan['invalid_rows'],'À corriger'),('Doublons',len(plan['duplicates']),'Revue requise')])
        st.caption('Colonnes reconnues : '+', '.join(plan['recognized_columns'])+' · Colonnes ignorées : '+(', '.join(plan['ignored_columns']) or 'aucune'))
        if plan['template']: st.info('Modèle vide / exemple : aperçu uniquement, import de production interdit.')
        table(plan['invalid']+plan['duplicates'])
        with st.expander('Examiner les lignes reconnues'): table([{LABELS.get(k,k):v for k,v in r.items() if k in LABELS} for r in plan['records']])
        confirmed=st.checkbox('Je confirme que ces données font autorité pour UGFS et que les lignes et doublons ont été examinés.',key='confirm_reference_'+plan['sha256'])
        if st.button('Confirmer l’import',type='primary',disabled=not (confirmed and plan['can_import']),key='commit_reference'):
            result=nav.execute(adapter.command,'import_reference',plan['filename'],pending['payload'],plan['domain'],plan['sha256'],confirmed)
            if result: st.session_state.pop('reference_preview',None)
            st.rerun()
    st.markdown('**Historique des imports**')
    table([{ 'Fichier':r['filename'],'Domaine':DOMAINS.get(r['domain'],r['domain']),'Lignes':r['row_count'],'Date':r['imported_at'],'Auteur':r['actor'],'Empreinte':r['sha256']} for r in view['imports']])


def settings(workspace):
    view=adapter.administration_view(workspace)
    header()
    links={'Sources':'Sources & règles de veille','Règles de veille':'Sources & règles de veille','Services & routage':'Services & analyses','Prompts IA':'IA & restitution','Utilisateurs':'Diffusion & accès','Paramètres généraux':'Diffusion & accès'}
    requested=st.session_state.get('admin_settings_tab')
    if requested==st.session_state.get('admin_link_consumed'):requested=None
    if requested:
        st.session_state['admin_link_consumed']=requested
        if requested in SETTINGS_TABS: st.session_state['admin_settings_section']=requested
        else:
            st.session_state['admin_settings_section']='Configuration'
            st.session_state['admin_configuration_section']=links.get(requested,requested if requested in CONFIG_TABS else CONFIG_TABS[0])
            if requested=='Règles de veille':st.session_state['admin_source_section']='Règles de veille'
    tab=st.segmented_control('Administration',SETTINGS_TABS,default=None if 'admin_settings_section' in st.session_state else SETTINGS_TABS[0],key='admin_settings_section',label_visibility='collapsed') or SETTINGS_TABS[0]
    if tab=='Vue d’ensemble': overview(workspace,view); return
    if tab=='Supervision': supervision(workspace,view); return
    group=st.segmented_control('Configuration',CONFIG_TABS,default=None if 'admin_configuration_section' in st.session_state else CONFIG_TABS[0],key='admin_configuration_section',label_visibility='collapsed') or CONFIG_TABS[0]
    if group==CONFIG_TABS[0]:
        section=st.radio('Configurer',['Sources','Règles de veille'],horizontal=True,key='admin_source_section')
        (sources if section=='Sources' else rules)(workspace,view)
    elif group==CONFIG_TABS[1]: services(workspace,view)
    elif group==CONFIG_TABS[2]: prompts(workspace,view)
    else:
        general(workspace,view)
        with st.expander('Accès et utilisateurs'):users(workspace,view)


def _health(label, status, detail, tone='ok'):
    return {'Élément':label,'État':status,'Détail':detail,'tone':tone}


def supervision(workspace,view):
    """Administrator-friendly operational health, backed by existing read models."""
    runtime=adapter.administration_runtime()
    sources=source_rows(workspace)
    failed_sources=sum(1 for row in sources if row.get('Erreur connue','') not in {'Non disponible',''})
    pending=sum(1 for result in successful_results(workspace) if result.get('review_status') in {'draft','pending','correction'})
    health=[
        _health('Collecte des sources','À surveiller' if failed_sources else 'Opérationnel',f"{len(sources)} sources suivies" if not failed_sources else f"{failed_sources} source(s) à contrôler",'warn' if failed_sources else 'ok'),
        _health('Notifications','Opérationnel',f"{len(workspace.get('rows',[]))} notifications disponibles"),
        _health('Traitements IA','À surveiller' if pending else 'Opérationnel',f"{pending} analyse(s) à valider" if pending else 'Aucune analyse en attente','warn' if pending else 'ok'),
        _health('Qualité / validation','À surveiller' if pending else 'Opérationnel','Validation humaine requise avant traitement final' if pending else 'Aucun blocage détecté','warn' if pending else 'ok'),
        _health('Diffusion email','Opérationnel' if runtime['smtp_configured'] else 'Non configuré','SMTP prêt' if runtime['smtp_configured'] else 'Configurer avant tout envoi','ok' if runtime['smtp_configured'] else 'neutral'),
        _health('Traçabilité','Opérationnel','Historique de configuration et des actions disponible'),
    ]
    st.markdown('<div class="ug-admin-health-grid">'+''.join(f'<div class="ug-admin-health {item["tone"]}"><div><strong>{_esc(item["Élément"])}</strong><span>{_esc(item["Détail"])}</span></div><b>{_esc(item["État"])}</b></div>' for item in health)+'</div>',unsafe_allow_html=True)
    with st.expander('Détails techniques'):
        table(source_rows(workspace))
        st.caption('Les détails techniques sont masqués par défaut pour garder la supervision lisible.')


def source_rows(workspace):
    result=[]
    for source in workspace['sources']:
        if source['key']=='legaltech':
            runs=workspace.get('legaltech_runs',[])
            successful=[r for r in runs if r.get('status')=='COLLECTED' and r.get('finished_at')]
            failed=any(r.get('status')=='FAILED' for r in runs)
            remote_error=workspace.get('remote',{}).get('status',{}).get('status')=='ERROR'
        elif source['key']=='cmf':
            runs=workspace.get('cmf_runs',[])
            successful=[r for r in runs if not json.loads(r.get('errors_json') or '[]') and r.get('finished_at')]
            failed=any(json.loads(r.get('errors_json') or '[]') for r in runs)
            remote_error=False
        else:
            successful=[];failed=False;remote_error=False
        result.append({'Source':source['label'],'Type':source['type'],'Statut':source['status'],'Services éligibles':' · '.join(adapter.service_label(k) for k in source['eligible_services']),'Dernière synchronisation réussie':max((r['finished_at'] for r in successful),default='Non disponible'),'Erreur connue':'Dernier contrôle LegalTech en erreur' if remote_error else 'Échec de collecte enregistré ; voir historique' if failed else 'Non disponible','Mode':'Collecteur manuel' if source['key'] in {'legaltech','cmf'} else 'Non connecté'})
    return result


def overview(workspace,view):
    config=view['config']; runtime=adapter.administration_runtime()
    pending=sum(1 for result in successful_results(workspace) if result.get('review_status') in {'draft','pending','correction'})
    cards([('Sources actives',sum(s.get('implemented',False) and s.get('active',True) for s in config['sources'].values()),'Collecte disponible'),('Services métiers',len(config['services']),'Routage configuré'),('Règles actives',sum(r.get('active',True) for r in view['rules']),'Règles de veille'),('Prompts IA',len(config['services']),'Prompts actifs'),('Analyses à valider',pending,'Validation humaine'),('Référentiel','Renseigné' if any(view['counts'].values()) else 'À compléter','Données faisant autorité')])
    st.markdown('<div class="ug-admin-question">Que souhaitez-vous vérifier ou configurer&nbsp;?</div>',unsafe_allow_html=True)
    cards_data=[('Sources','Collecte et disponibilité des sources',f"{sum(s.get('implemented',False) and s.get('active',True) for s in config['sources'].values())} active(s)",'Sources & règles de veille'),('Analyses IA','Prompts et résultats à valider',f'{pending} à valider','IA & restitution'),('Routage métier','Services et règles d’affectation',f"{sum(r.get('active',True) for r in view['rules'])} règle(s) active(s)",'Services & analyses'),('Diffusion','Exports et diffusion email','Configurée' if runtime['smtp_configured'] else 'Non configurée','Diffusion & accès')]
    with st.container(key='admin_simplified_cards'):
        cols=st.columns(4)
        for col,(title,subtitle,status,target) in zip(cols,cards_data):
            with col,st.container(border=True):
                st.markdown(f'<div class="ug-admin-simple-card"><strong>{_esc(title)}</strong><span>{_esc(subtitle)}</span><b>{_esc(status)}</b></div>',unsafe_allow_html=True)
                st.button('Configurer',key='admin_simple_'+title,on_click=select,args=('admin_settings_tab',target),width='stretch')
    with st.container(key='admin_overview_columns'):
        left,right=st.columns([1.35,1])
    with left:
        with st.container(border=True):
            st.markdown('**État des sources**')
            table([{'Source':row['Source'],'État':row['Statut'],'Dernière synchronisation':row['Dernière synchronisation réussie']} for row in source_rows(workspace)])
            st.button('Configurer les sources',key='overview_sources',on_click=select,args=('admin_settings_tab','Sources & règles de veille'))
        with st.container(border=True):
            st.markdown('**Services métiers**'); service_cards(view)
    with right:
        with st.container(border=True):
            st.markdown('**Référentiel UGFS**')
            if any(view['counts'].values()):
                st.success('Référentiel renseigné — correspondances disponibles.')
            else:
                st.info('Référentiel UGFS à compléter — aucune donnée faisant autorité importée.')
            st.button('Voir le référentiel',key='overview_reference',on_click=nav.navigate,args=('reference',),width='stretch')
        with st.container(border=True):
            st.markdown('**À surveiller**')
            st.markdown(f'**{pending}** analyse(s) à valider')
            st.caption('Les résultats restent soumis à la validation humaine avant traitement final.')
            st.button('Ouvrir la supervision',key='overview_supervision',on_click=select,args=('admin_settings_tab','Supervision'))


def service_cards(view):
    with st.container(key='admin_service_cards'):
        columns=st.columns(4)
    for column,service in zip(columns,view['services']):
        with column,st.container(border=True):
            st.markdown('**'+adapter.service_label(service['key'])+'**')
            st.caption(' · '.join(service['sources']) or 'Aucune source éligible')
            st.caption(f"{service['assigned']} notifications · {service['results']} résultats")
            st.caption(f"{service['rules']} règles · {service['backlog']} à revoir")
            st.caption(f"Prompt v{service['prompt_version']}")
            st.button('Configurer →',key='service_config_'+service['key'],on_click=select,args=('admin_settings_tab','Services & routage'))


def sources(workspace,view):
    table(source_rows(workspace))
    config=deepcopy(view['config'])
    key=st.selectbox('Source à configurer',list(config['sources']),format_func=lambda k:config['sources'][k]['label'])
    source=config['sources'][key]
    with st.form('admin_source_form_'+key):
        source['active']=st.checkbox('Collecte active',value=source['active'],disabled=not source['implemented'])
        source['eligible_services']=st.multiselect('Services éligibles',['compliance'] if key=='cmf' else list(adapter.SERVICES),default=source['eligible_services'],format_func=adapter.service_label,disabled=key=='cmf')
        if st.form_submit_button('Enregistrer la source'): save(config,view,'source_configuration')
    if not source['implemented']: st.info('À configurer — aucun collecteur connecté. Les critères d’éligibilité seuls ne créent pas de données.')
    st.button('Ouvrir les contrôles de collecte',on_click=nav.navigate,args=('sources',),key='admin_source_controls')
    if key=='cmf':
        st.markdown('**Pertinence CMF — avant collecte des documents**')
        st.caption('Les catégories, termes et rapprochements renseignés sont combinés par ET. Mots-clés/thèmes : au moins un terme ; exclusions prioritaires. Sans configuration, découverte uniquement.')
        policy=config.setdefault('cmf_relevance',{})
        with st.form('admin_cmf_relevance'):
            policy['configured']=st.checkbox('Activer le filtre de pertinence configuré',value=policy.get('configured',False))
            policy['categories']=split(st.text_input('Catégories / types (séparés par des virgules)',', '.join(policy.get('categories',[])),help='Exemples de sections réellement découvertes : avis, bulletin.'))
            policy['topics']=split(st.text_input('Thèmes réglementaires',', '.join(policy.get('topics',[]))))
            policy['keywords']=split(st.text_input('Mots-clés',', '.join(policy.get('keywords',[]))))
            policy['exclusions']=split(st.text_input('Exclusions',', '.join(policy.get('exclusions',[]))))
            policy['require_reference']=st.checkbox('Exiger une entité du référentiel reconnue',value=policy.get('require_reference',False))
            if st.form_submit_button('Enregistrer la pertinence CMF'): save(config,view,'cmf_relevance_configuration')
        table(view['discoveries'])


def split(value):
    return [v.strip() for v in value.split(',') if v.strip()]


def rules(workspace,view):
    st.caption('Règles explicites avant rapprochement, puis proposition IA si ambiguë. Les affectations humaines restent prioritaires. Désactiver conserve l’historique.')
    table([{'Nom':r['name'],'Source':r.get('source') or 'Toutes','Active':r.get('active',True),'Services':' · '.join(adapter.service_label(s) for s in r['services']),'Correspondances actuelles':r['matches'],'Dernier événement de routage':r['last_match'],'Créée':r.get('created_at','Non disponible'),'Modifiée':r.get('updated_at','Non disponible')} for r in view['rules']])
    choices={'new':'Créer une règle',**{r['id']:r['name'] for r in view['config']['routing_rules']}}
    chosen=st.selectbox('Règle',list(choices),format_func=choices.get)
    current=next((r for r in view['config']['routing_rules'] if r['id']==chosen),{'name':'','source':'legaltech','services':[],'active':True})
    if chosen!='new':
        a,b=st.columns(2)
        if a.button('Désactiver' if current.get('active',True) else 'Activer',key='rule_toggle'):
            nav.execute(adapter.command,'admin_rule','toggle',current,view['fingerprint']); st.rerun()
        if b.button('Dupliquer (copie inactive)',key='rule_duplicate'):
            nav.execute(adapter.command,'admin_rule','duplicate',current,view['fingerprint']); st.rerun()
    source=st.selectbox('Source de la règle',['',*view['config']['sources']],index=['',*view['config']['sources']].index(current.get('source','')),format_func=lambda k:view['config']['sources'][k]['label'] if k else 'Toutes les sources',key='rule_source_'+chosen)
    with st.form('admin_rule_form_'+chosen):
        value=deepcopy(current);value['source']=source
        value['name']=st.text_input('Nom de la règle',current['name'])
        a,b=st.columns(2)
        value['keywords']=split(a.text_input('Mots-clés / thèmes',', '.join(current.get('keywords',[]))))
        value['event_types']=b.multiselect('Événements',list(adapter.business_event_types(view['config'])),default=current.get('event_types',[]),format_func=lambda k:adapter.business_event_types(view['config'])[k]['label'])
        value['entity']=a.text_input('Entité',current.get('entity',''))
        value['referential_type']=b.selectbox('Critère référentiel',['',*DOMAINS,'watchlist'],index=['',*DOMAINS,'watchlist'].index(current.get('referential_type','')),format_func=lambda k:DOMAINS.get(k,k or 'Aucun'))
        value['sectors']=split(a.text_input('Secteurs',', '.join(current.get('sectors',[]))))
        value['gics']=split(b.text_input('Codes GICS',', '.join(current.get('gics',[]))))
        value['document_type']=a.text_input('Type de document',current.get('document_type',''))
        value['entity_role']=b.text_input('Rôle dans le référentiel',current.get('entity_role',''),help='Client, prospect, fournisseur ou concurrent uniquement si renseigné dans des données réelles.')
        eligible=['compliance'] if source=='cmf' else list(adapter.SERVICES) if not source else view['config']['sources'][source]['eligible_services']
        value['services']=st.multiselect('Services destinataires',eligible,default=[s for s in current.get('services',[]) if s in eligible],format_func=adapter.service_label)
        priorities=['','Critique','Haute','Moyenne','Basse']
        value['priority']=a.selectbox('Priorité attribuée',priorities,index=priorities.index(current.get('priority') or ''),format_func=lambda x:x or 'Conserver la priorité source')
        value['active']=b.checkbox('Règle active',current.get('active',True))
        if st.form_submit_button('Enregistrer la règle',type='primary'):
            result=nav.execute(adapter.command,'admin_rule','create' if chosen=='new' else 'edit',value,view['fingerprint'])
            st.rerun()
    if workspace.get('rules'):
        with st.expander('Règles historiques du collecteur — conservées'): table(workspace['rules'])


def services(workspace,view):
    service_cards(view)
    st.caption('Les affectations humaines priment sur les règles. Une proposition IA n’est jamais appliquée sans choix humain. CMF : Conformité uniquement. Portefeuille : preuve de participation ou personne liée obligatoire.')
    with st.expander('Détails techniques — affectations et provenance'):
        table([{'Notification':r['title'],'Services':' · '.join(adapter.service_label(s) for s in r['services']),'Origine':reason.get('origin','MANUAL' if r.get('manual_routing') else 'RULE'),'Justification':reason['rule']} for r in workspace['rows'] for reason in r.get('routing_reasons',[])])
    st.button('Modifier les règles',key='routing_to_rules',on_click=select,args=('admin_settings_tab','Règles de veille'))
    with st.expander('Familles d’événements et interprétations configurables'):
        config=deepcopy(view['config'])
        with st.form('admin_event_policies'):
            events=st.text_area('Événements (JSON)',json.dumps(config.get('event_types',{}),ensure_ascii=False,indent=2),height=240)
            actions=st.text_area('Actions métier (JSON)',json.dumps(config.get('business_actions',{}),ensure_ascii=False,indent=2),height=150)
            if st.form_submit_button('Enregistrer les politiques'):
                try: config['event_types']=json.loads(events); config['business_actions']=json.loads(actions); save(config,view,'routing_policy_update')
                except ValueError as exc: st.error(str(exc))


def prompts(workspace,view):
    config=deepcopy(view['config']);runtime=adapter.administration_runtime()
    st.caption('Moteur local commun : '+runtime['model']+' · aucun retraitement automatique des analyses historiques.')
    service=st.selectbox('Service métier',list(adapter.SERVICES),format_func=adapter.service_label,key='admin_prompt_service')
    value=config['services'][service]
    st.caption(f"Version active {value['prompt_version']} · Dernière modification : {value.get('updated_at','Non disponible')}")
    with st.expander('Détails techniques — schéma de sortie',expanded=False):
        contract=adapter.active_business_contract(service)
        st.json(contract['schema'])
        st.caption('Pipeline '+contract['pipeline_version']+' · champs métier persistés : '+', '.join(contract['schema']['required']))
    with st.form('admin_prompt_'+service):
        value['prompt']=st.text_area('Prompt actif',value['prompt'],height=220)
        schema=None
        st.caption('Les sélecteurs de preuves sont bornés automatiquement par la source. Le schéma du contrat métier est versionné avec le pipeline ; le prompt spécialisé reste modifiable.')
        if st.form_submit_button('Enregistrer une nouvelle version',type='primary'):
            try:
                if schema: value['output_schema']=json.loads(schema)
                save(config,view,'prompt_version_change')
            except ValueError as exc: st.error(str(exc))
    history=adapter.prompt_versions(service)
    st.markdown('**Versions conservées**')
    if history:
        record=st.selectbox('Version à consulter',history,format_func=lambda r:f"v{r['prompt']['prompt_version']} · {r['at']} · {r['id']}")
        with st.expander('Consulter le prompt historique'): st.code(record['prompt']['prompt'],language=None)
        st.caption('Activer un ancien contenu crée une nouvelle révision traçable ; les anciens résultats restent inchangés.')
        if st.button('Activer ce contenu',key='activate_prompt'):
            result=nav.execute(adapter.command,'activate_prompt',service,record['id'],view['fingerprint'])
            st.rerun()
    else: st.caption('Aucune version historique enregistrée pour ce service.')


def users(workspace,view):
    st.info('Gestion des utilisateurs non configurée')
    st.caption('Rôles préparés : Administrateur · Analyste · Validateur · Lecteur. Aucun compte ni contrôle d’accès fictif. L’application locale ne fournit pas encore une authentification multi-utilisateur.')
    st.button('Créer un utilisateur — indisponible',disabled=True)


def general(workspace,view):
    runtime=adapter.administration_runtime()
    left,right=st.columns(2)
    with left,st.container(border=True):
        st.markdown('**IA & extraction**')
        st.caption('Modèle local : '+runtime['model'])
        with st.expander('Détails techniques — moteur local'):
            st.caption('Délai : '+str(runtime['timeout'])+' s · Budget : '+str(runtime['input_budget'])+' caractères')
        st.markdown('**Synchronisation**');table(source_rows(workspace))
    with right,st.container(border=True):
        st.markdown('**Exports & diffusion**')
        st.markdown('**Diffusion email**')
        st.caption('Diffusion email — Configurée.' if runtime['smtp_configured'] else 'Diffusion email — Non configurée')
        if not runtime['smtp_configured']: st.button('Configurer',key='admin_configure_email',disabled=True)
        st.caption('Excel : export des résultats métier, preuves et traçabilité.')
        table([{'Service':adapter.service_label(s['service_id']),'Actif':bool(s.get('enabled')),'Cadence':s.get('cadence','Non disponible')} for s in workspace.get('digest_settings',[])])
        st.button('Configurer les digests',on_click=nav.navigate,args=('diffusion',),key='admin_digest')
        st.caption('Aucune action de purge ou de réinitialisation n’est proposée dans cette interface.')
        st.caption('Lecture des registres réussie.' if not workspace['errors'] else 'Des registres signalent une erreur ; consulter les messages en haut de page.')
    with st.expander('Journal de configuration complet'): table(view['events'])
    with st.expander('Avancé / Détails techniques'):
        st.caption(runtime['architecture'])
        table(runtime['databases'])
        st.caption('Modèle local configuré : '+runtime['model']+' · Timeout : '+str(runtime['timeout'])+' s')
