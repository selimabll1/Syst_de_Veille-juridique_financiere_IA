"""Parent bulletin and scoped publication selection; no backend writes on render."""
import streamlit as st
from services import ui_adapter as adapter
from ui import navigation as nav


def render(row,workspace,context):
    key=context+'_'+row['uid'];document,children=adapter.bulletin_publications(row['uid'])
    st.info('Document composite détecté. Ce bulletin contient plusieurs publications distinctes. Elles doivent être analysées séparément afin d’éviter de mélanger des événements sans rapport.')
    if not document:
        if st.button('Voir les publications',key=key+'_prepare',type='primary'):
            nav.start_action('Analyse du bulletin CMF','segmentation:'+row['uid'],'segment_bulletin',row);st.rerun()
        return
    st.markdown(f'### {len(children)} publications détectées')
    if document['status']=='REVIEW_REQUIRED':st.warning('Certaines limites ne sont pas confirmées, notamment dans les annexes. Sélectionnez un titre et une plage de pages pour les examiner.')
    rows={r['uid']:r for r in workspace.get('child_rows',[])}
    for child in children:
        with st.container(border=True):
            st.write('**'+child['title']+'**')
            scoped=rows.get(child['child_id']);confirmed=child['segmentation_status']=='CONFIRMED'
            st.caption(f"Pages {child['page_start']}–{child['page_end']} · {child['category'] or 'Publication'} · "+(scoped.get('status','Non analysée') if scoped and confirmed else 'Plage à confirmer'))
            a,b=st.columns(2)
            if a.button('Voir',key=key+'_view_'+child['child_id']):st.session_state[key+'_selected']=child['child_id']
            if b.button('Analyser avec l’IA',key=key+'_analyze_'+child['child_id'],disabled=not confirmed or not scoped):
                nav.start_action('Analyse Conformité','ollama','run_analysis',scoped,['compliance']);st.rerun()
    chosen=next((c for c in children if c['child_id']==st.session_state.get(key+'_selected')),None)
    if chosen:
        with st.expander('Publication sélectionnée',expanded=True):
            st.write(chosen['title']);st.caption(f"Pages {chosen['page_start']}–{chosen['page_end']}")
            with st.expander('Texte source de la publication',expanded=False):
                with st.container(height=280):st.text(chosen['extracted_text'])
            scoped=rows.get(chosen['child_id']);record=(scoped or {}).get('business_results',{}).get('compliance')
            if record:
                from ui.pages.business_workspace import detail
                detail({'row':scoped,'service':'compliance','record':record,'key':chosen['child_id']+':compliance:primary'},workspace,key+'_result')
    with st.expander('Sélectionner une publication / plage de pages'):
        if document.get('source_url'):st.link_button('Ouvrir le PDF parent',document['source_url'])
        st.caption(f"{document['total_pages']} pages. Vérifiez visuellement que la plage contient une seule publication.")
        with st.form(key+'_manual'):
            title=st.text_input('Titre de la publication')
            a,b=st.columns(2)
            start=a.number_input('Première page',1,document['total_pages'],1)
            end=b.number_input('Dernière page',1,document['total_pages'],1)
            if st.form_submit_button('Confirmer la publication'):
                nav.execute(adapter.command,'select_publication',row,title,start,end);st.rerun()
    with st.expander('Détails techniques'):
        st.json({k:document.get(k) for k in ('status','pipeline_version','total_pages','timings','uncovered_pages')})
