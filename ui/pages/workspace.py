"""Shared notification master/detail for all four business services."""
from datetime import date, timedelta
import math
import re
import streamlit as st
from services import ui_adapter as adapter
from ui import navigation as nav
from ui.components import presentation as p
from ui.components.documents import render_documents
from ui.components.icons import icon as svg_icon

from services.result_presentation import BUSINESS_LABELS


@st.dialog("Filtres avancés", width="large")
def advanced_filters(rows):
    current = st.session_state.get("ugfs_advanced", {})
    with st.form("advanced_filter_form"):
        a, b = st.columns(2)
        start = a.date_input("À partir du", value=current.get("start"))
        end = b.date_input("Jusqu’au", value=current.get("end"))
        keywords = st.text_input("Mots-clés (séparés par des virgules)", value=current.get("keywords", ""))
        tags = st.multiselect("Tags", sorted({t for r in rows for t in r["tags"]}), default=current.get("tags", []))
        a, b = st.columns(2)
        services = a.multiselect("Affectation aux services", list(adapter.SERVICES), default=current.get("services", []), format_func=adapter.service_label)
        ai_options = ["Tous", "Sans analyse", "Analysé", "En cours", "Échec"]
        ai = b.selectbox("État IA", ai_options, index=ai_options.index(current.get("ai", "Tous")))
        a, b = st.columns(2)
        doc_options = ["Tous", "PDF local", "Lien source", "Aucun document"]
        docs = a.selectbox("Documents / source", doc_options, index=doc_options.index(current.get("docs", "Tous")))
        languages = ["Toutes", "Français / latin", "Arabe"]
        language = b.selectbox("Langue du contenu", languages, index=languages.index(current.get("language", "Toutes")))
        a, b = st.columns(2)
        apply = a.form_submit_button("Appliquer les filtres", type="primary", width="stretch")
        reset = b.form_submit_button("Réinitialiser", width="stretch")
        if apply or reset:
            if apply and start and end and start > end:
                st.error("La date de début doit précéder la date de fin.")
                return
            st.session_state["ugfs_advanced"] = {} if reset else dict(start=start, end=end, keywords=keywords, tags=tags, services=services, ai=ai, docs=docs, language=language)
            st.rerun()


def filter_rows(rows, selections, advanced, search="", service=None):
    """Pure filtering used by the UI and offline behavioral tests."""
    result = []
    for row in rows:
        row = adapter.service_view(row, service)
        if any(value != "Toutes" and row.get(field) != value for field, value in selections.items() if field in {"source", "type", "priority", "status"}):
            continue
        selected_service = selections.get("service", "Toutes")
        if selected_service != "Toutes" and selected_service not in row["services"]:
            continue
        reading = selections.get("reading", "Toutes")
        if (reading in {"Lu", "Lues"} and not row["read"]) or (reading in {"Non lu", "Non lues"} and row["read"]):
            continue
        treatment = selections.get("treatment", "Toutes")
        if (treatment == "Traitées" and not row["treated"]) or (treatment == "Non traitées" and row["treated"]):
            continue
        from services.lifecycle import ai_status
        ai_filter = selections.get('ai', 'Toutes')
        if ai_filter != 'Toutes' and ai_status(row) != ai_filter:
            continue
        when = adapter.date_obj(row["date"])
        days = {"7 derniers jours": 7, "30 derniers jours": 30, "90 derniers jours": 90}.get(selections.get("period"))
        if days and (not when or when < date.today() - timedelta(days=days)):
            continue
        if advanced.get("start") and (not when or when < advanced["start"]):
            continue
        if advanced.get("end") and (not when or when > advanced["end"]):
            continue
        blob = " ".join(str(row.get(field) or "") for field in ("entity", "title", "summary", "source", "metadata", "tags")).casefold()
        words = search.split() + [k.strip().casefold() for k in advanced.get("keywords", "").split(",") if k.strip()]
        if any(word.casefold() not in blob for word in words):
            continue
        if advanced.get("tags") and not set(advanced["tags"]).issubset(row["tags"]):
            continue
        if advanced.get("services") and not set(advanced["services"]).intersection(row["services"]):
            continue
        ai = advanced.get("ai")
        if ai == "Sans analyse" and row.get("analysis"):
            continue
        if ai == "Analysé" and not row.get("analysis"):
            continue
        if ai in {"En cours", "Échec"} and row.get("ai_state") != {"En cours": "running", "Échec": "failed"}[ai]:
            continue
        docs = advanced.get("docs")
        if (docs == "PDF local" and not row.get("pdf_path")) or (docs == "Lien source" and not row.get("source_url")) or (docs == "Aucun document" and row["documents"]):
            continue
        arabic = bool(re.search(r"[\u0600-\u06ff]", blob))
        if (advanced.get("language") == "Arabe" and not arabic) or (advanced.get("language") == "Français / latin" and arabic):
            continue
        result.append(row)
    return result


def main_filters(rows):
    chosen = {}
    with st.container(key="main_filters"):
        columns = st.columns(4)
        definitions = [("source", "Source"), ("service", "Service concerné"), ("type", "Type d’information"), ("priority", "Priorité"), ("status", "Traitement"), ("reading", "Lecture"), ("period", "Période"), ('ai','Statut IA')]
        columns = list(columns) + list(st.columns(4))
        for column, (field, label) in zip(columns, definitions):
            if field == "service":
                values = ["Toutes", *adapter.SERVICES]
            elif field == "reading":
                values = ["Toutes", "Non lu", "Lu"]
            elif field == "priority":
                values = ["Toutes", "Critique", "Haute", "Moyenne", "Basse"]
            elif field == "status":
                values = ["Toutes", "Nouveau", "À analyser", "Analyse terminée", "À valider", "Traité", "Partiellement traité", "Erreur d’analyse"]
            elif field == "period":
                values = ["Toutes", "7 derniers jours", "30 derniers jours", "90 derniers jours"]
            elif field == 'ai':
                values = ['Toutes','Non analysée','Analyse en cours','Analysée','Erreur d’analyse']
            else:
                values = ["Toutes", *sorted({str(r[field]) for r in rows if r.get(field)})]
            key = "filter_" + field
            if st.session_state.get(key) not in values:
                st.session_state[key] = "Toutes"
            chosen[field] = column.selectbox(label, values, key=key, format_func=(lambda v: adapter.service_label(v) if v != "Toutes" else "Tous") if field == "service" else str)
    return chosen


@st.dialog("Affectation & suivi", width="large")
def assignment_dialog(row):
    with st.form("assignment_form"):
        services = st.multiselect("Services concernés", row.get("eligible_services", list(adapter.SERVICES)), default=row["services"], format_func=adapter.service_label)
        old = row.get("assignment") or {}
        a, b = st.columns(2)
        assignee = a.text_input("Responsable", value=old.get("assignee") or "")
        team = b.text_input("Équipe", value=old.get("team") or "")
        due = st.text_input("Échéance", value=old.get("due_at") or "", placeholder="AAAA-MM-JJ")
        statuses = ["open", "in_progress", "done"]
        status = st.selectbox("Avancement", statuses, index=statuses.index(old.get("status")) if old.get("status") in statuses else 0, format_func=lambda x: {"open": "À faire", "in_progress": "En cours", "done": "Terminé"}[x])
        if st.form_submit_button("Enregistrer", type="primary"):
            nav.execute(adapter.assign_services, row, services, assignee=assignee, team=team, due_at=due, status=status)
            st.rerun()


def detail(row, workspace, context="workspace", preferred_service=None):
    if not row:
        st.info("Aucune notification ne correspond aux filtres.")
        return
    uid = row["uid"]
    if row.get('document_status'):
        st.markdown('### '+p._esc(row['title']))
        from ui.pages.publications import render
        render(row,workspace,context)
        return
    export_key = uid
    st.markdown(f'<div class="ug-detail-title" dir="auto">{p._esc(row["title"])}</div><div class="ug-detail-subtitle">{p._esc(row["entity"])} &nbsp; • &nbsp; {p._esc(row["source"])} &nbsp; • &nbsp; {p._esc(row["date"])}</div>', unsafe_allow_html=True)
    st.markdown(p.status_stack(row), unsafe_allow_html=True)
    st.caption("Origine de la priorité : " + row.get("priority_provenance", {}).get("explanation", "Aucune règle applicable"))
    original = row
    choices = list(row["services"])
    if row.get("legacy_result"):
        choices.append("legacy")
    selected_service = st.selectbox("Résultat métier / besoin", choices, index=choices.index(preferred_service) if preferred_service in choices else 0, format_func=lambda s: "Analyse historique" if s == "legacy" else adapter.service_label(s), key=f"{context}_business_{uid}") if choices else None
    row = adapter.business_view(row, selected_service) if selected_service else row
    export_key = f"{uid}:{selected_service}:{(row.get('record') or {}).get('revision', '')}"
    if original.get("business_results"):
        for service, state in original.get("service_states", {}).items():
            st.caption(f"{adapter.service_label(service)} · {state}")
    result_count=sum(bool(r and r.get('analysis')) for r in original.get('business_results',{}).values())
    tabs = st.tabs(["Vue d’ensemble", "Source", "Analyses IA", f"Résultats ({result_count})", "Historique"], key=f"{context}_detail_tabs_{uid}_{selected_service}")
    if selected_service and selected_service != 'legacy':
        with st.popover('Priorité métier'):
            st.caption(row.get('priority_provenance',{}).get('explanation','Aucune règle applicable'))
            choices_priority=['Automatique','Critique','Haute','Moyenne','Basse']
            current_priority=original.get('priority_overrides',{}).get(selected_service) or 'Automatique'
            choice=st.selectbox('Choix humain', choices_priority,index=choices_priority.index(current_priority),key=f'{context}_priority_{uid}_{selected_service}')
            if st.button('Enregistrer la priorité',key=f'{context}_save_priority_{uid}_{selected_service}'):
                nav.execute(adapter.command,'set_priority',original,selected_service,None if choice=='Automatique' else choice)
                st.rerun()
    with tabs[0]:
        p._overview(original)
        if selected_service in {"investment", "portfolio"}:
            st.caption(original.get("referential_status", "Aucune correspondance confirmée"))
            for event in original.get("identification", {}).get("events", []):
                st.caption(f"Événement détecté : {event['label']} · terme source : {event['trigger']}")
        if original.get("matches"):
            st.caption("Rapprochements du référentiel UGFS")
            st.dataframe(original["matches"], hide_index=True, width="stretch")
        if original.get("routing_reasons"):
            for reason in original["routing_reasons"]:
                st.caption("Routage : " + reason["rule"])
    with tabs[1]:
        p._source_tab(row)
        if row["kind"] == "cmf" and row["raw"].get("detail_url"):
            if st.button("Actualiser l’extrait CMF", key=f"{context}_excerpt_{uid}"):
                nav.execute(adapter.command, "fetch_cmf_excerpt", row)
                st.rerun()
    with tabs[2]:
        p._ai_tab(row)
        message = adapter.result_presentation(row.get("analysis") or {})["selection_message"]
        if message: st.info(message)
    with tabs[3]:
        p._results_tab(row)
        if row.get("analysis"):
            business_output = adapter.result_presentation(row["analysis"])["output"]
            if business_output:
                for field, value in business_output.items():
                    st.markdown("**" + BUSINESS_LABELS.get(field, field.replace("_", " ").capitalize()) + "**")
                    st.write(value)
                reliability=row['analysis'].get('reliability',{})
                if reliability.get('factual_score') is not None:
                    st.caption(f"Fiabilité factuelle : {reliability['factual_score']}/100 · Pertinence métier : {reliability['service_relevance']['label']} · Indice global : {reliability['score']}/100")
                    st.caption(reliability['meaning'])
                with st.expander("Correction humaine du résultat métier"):
                    with st.form(f"{context}_correction_{uid}_{selected_service}"):
                        corrected = {field: st.text_area(BUSINESS_LABELS.get(field, field.replace("_", " ").capitalize()), str(value), disabled=field in {"validation_status", "evidence", "referential_match_reason", "matched_portfolio_entity"}) for field, value in business_output.items()}
                        note = st.text_input("Motif de correction")
                        if st.form_submit_button("Enregistrer la correction"):
                            nav.execute(adapter.set_review_status, original, "pending", selected_service, corrected=corrected, note=note)
                            st.rerun()
                if row.get("review_status") == "draft" and st.button("Soumettre à validation", key=f"{context}_submit_{uid}"):
                    nav.execute(adapter.set_review_status, original, "pending", selected_service)
                    st.rerun()
            grounding = row["analysis"].get("grounding")
            if grounding:
                with st.expander("Données techniques de l’analyse", expanded=False):
                    st.caption("Citations exactes de la source ; interprétations de règles et recommandations distinctes. Une correction humaine n’est pas automatiquement certifiée par ces preuves.")
                    st.dataframe(grounding["evidence"], hide_index=True, width="stretch")
                    st.json(row["analysis"], expanded=False)
                    if row["analysis"].get("pipeline_version"):
                        st.json({key:row["analysis"].get(key) for key in ("pipeline_version", "metrics", "reliability", "canonical_facts", "claims", "timings")})
                    if grounding.get("human_changes"):
                        st.json(grounding["human_changes"])
            a, b, c = st.columns(3)
            for column, status, label in [(a, "validated", "Valider"), (b, "correction", "À corriger")]:
                if column.button('✓ Validé' if status=='validated' and row.get('review_status')=='validated' else label, key=f"{context}_review_{status}_{uid}", disabled=status=='validated' and row.get('review_status')=='validated', width="stretch"):
                    nav.execute(adapter.set_review_status, original, status, None if selected_service == "legacy" else selected_service)
                    st.rerun()
            if c.button("Exporter Excel", key=f"{context}_export_{uid}", width="stretch"):
                path = nav.execute(adapter.export_excel, original, None if selected_service == "legacy" else selected_service)
                if path:
                    st.session_state.setdefault("ugfs_exports", {})[export_key] = str(path)
            if st.session_state.get("ugfs_exports", {}).get(export_key):
                from pathlib import Path
                path = Path(st.session_state["ugfs_exports"][export_key])
                if path.is_file():
                    st.download_button("Télécharger l’export Excel", path.read_bytes(), file_name=path.name, on_click="ignore", key=f"{context}_download_{uid}")
            if row.get("review_status") == "correction":
                if st.button("Repasser à valider", key=f"{context}_pending_{uid}"):
                    nav.execute(adapter.set_review_status, original, "pending", None if selected_service == "legacy" else selected_service)
                    st.rerun()
    with tabs[4]:
        events = adapter.workflow_history(row, workspace)
        if events:
            st.dataframe(events, hide_index=True, width="stretch")
        else:
            st.caption("Aucun événement de workflow enregistré.")
        notes = [n for n in workspace["notes"] if n.get("alert_uid") in {row["uid"], row["stable_uid"], row["source_key"]}]
        for note in notes:
            st.write(note.get("body") or "")
            st.caption(f"{note.get('author', '')} · {note.get('created_at', '')}")
        with st.form(f"{context}_note_{uid}", clear_on_submit=True):
            note = st.text_area("Ajouter une note", key=f"{context}_note_body_{uid}")
            if st.form_submit_button("Enregistrer la note") and note.strip():
                nav.execute(adapter.command, "save_note", row, note.strip())
                st.rerun()
    a, b, c = st.columns([1.4, 1.1, 1])
    portfolio_unconfirmed = selected_service == "portfolio" and not original.get("portfolio_confirmed")
    if a.button("Analyser avec l’IA", icon=":material/auto_awesome:", type="primary", key=f"{context}_analyze_{uid}", disabled=not selected_service or selected_service == "legacy" or portfolio_unconfirmed, width="stretch"):
        nav.start_action("Analyse " + adapter.service_label(selected_service), "ollama", "run_analysis", original, [selected_service])
        st.rerun()
    if b.button("Affecter", icon=":material/edit_square:", key=f"{context}_assign_{uid}", width="stretch"):
        assignment_dialog(original)
    with c:
        with st.popover("Actions", icon=":material/more_horiz:", width="stretch"):
            if row.get("analysis") and selected_service and selected_service != "legacy":
                if st.button("Recalculer explicitement l’analyse", key=f"{context}_force_analysis_{uid}", disabled=portfolio_unconfirmed):
                    nav.start_action("Réanalyse " + adapter.service_label(selected_service), "ollama", "run_analysis", original, [selected_service], force=True)
                    st.rerun()
            if not original.get("manual_routing") and not original.get("routing_suggestions"):
                if st.button("Proposer un routage IA", key=f"{context}_routing_{uid}"):
                    nav.start_action("Proposition de routage", "ollama", "suggest_routing", original)
                    st.rerun()
            if st.button("Marquer non lue" if row["read"] else "Marquer lue", key=f"{context}_read_{uid}"):
                nav.execute(adapter.mark_read, row, not row["read"])
                st.rerun()
            st.button("Diffuser", key=f"{context}_diffuse_{uid}", on_click=nav.navigate_to_diffusion, args=(uid, selected_service))
    if not selected_service:
        st.caption("Affectez un service éligible pour activer l’analyse métier.")
    elif portfolio_unconfirmed:
        st.info("Référentiel UGFS non renseigné ou aucune correspondance confirmée. L’affectation manuelle reste possible ; l’analyse portefeuille attend une preuve de participation.")
    elif selected_service == "legacy":
        st.caption("Analyse historique conservée. Choisissez un service affecté pour une nouvelle analyse métier.")
    render_documents(row["documents"], f"{context}_{uid}")


def render(workspace, service=None, rows_override=None, title=None):
    if service == 'portfolio' and not any(r.get('portfolio_confirmed') for r in workspace['rows']) and not any('portfolio' in r['services'] for r in workspace['rows']):
        st.title('Suivi portefeuille')
        st.markdown('<div class="ug-admin-empty-reference"><h2>Référentiel UGFS requis</h2><p>Le routage automatique vers Suivi portefeuille nécessite des participations confirmées dans le référentiel UGFS.<br>Aucune participation faisant autorité n’est actuellement renseignée.</p></div>',unsafe_allow_html=True)
        st.button('Compléter le référentiel',key='portfolio_reference',on_click=nav.navigate,args=('reference',),type='primary')
        st.caption('Une affectation manuelle reste possible mais ne constitue pas une preuve de participation.')
        return
    rows = rows_override if rows_override is not None else workspace["rows"]
    if service:
        rows = [adapter.service_view(r, service) for r in rows if service in r["services"]]
    with st.container(key="master_columns"):
        left, right = st.columns([1.28, 1], gap="small")
        with left:
            heading, filters = st.columns([5, 1.2], vertical_alignment="center")
            heading.markdown(f'# {title or (adapter.service_label(service) if service else "Notifications")}')
            heading.markdown('<div class="ug-subtitle">Toutes les informations collectées et routées</div>', unsafe_allow_html=True)
            if filters.button("Filtres", icon=":material/tune:", key="advanced_filters", width="stretch", help="Ouvrir les filtres avancés"):
                advanced_filters(rows)
            chosen = main_filters(rows)
            search, sort, treatment = st.columns([2.2, 1.3, 2])
            text = search.text_input("Rechercher dans les notifications", placeholder="Rechercher dans les notifications…", icon=":material/search:", label_visibility="collapsed", key="ugfs_list_search")
            order = sort.selectbox("Tri", ["Date (plus récente)", "Date (plus ancienne)", "Priorité"], label_visibility="collapsed", key="ugfs_order")
            with treatment:
                quick = st.segmented_control('Analyses', ['Toutes','Non analysées','Analysées'],default='Toutes',key='ugfs_ai_quick',label_visibility='collapsed') or 'Toutes'
                if quick != 'Toutes': chosen['ai'] = {'Non analysées':'Non analysée','Analysées':'Analysée'}[quick]
            filtered = filter_rows(rows, chosen, st.session_state.get("ugfs_advanced", {}), " ".join([st.session_state.get("ugfs_global_search", ""), text]),service=service)
            filtered.sort(key=lambda r: adapter.date_obj(r["date"]) or date.min, reverse=order != "Date (plus ancienne)")
            if order == "Priorité":
                filtered.sort(key=lambda r: {"Critique": 0, "Haute": 1, "Moyenne": 2, "Basse": 3}.get(r["priority"], 4))
            signature = repr((chosen, st.session_state.get("ugfs_advanced"), text, st.session_state.get("ugfs_global_search"), service, title, order))
            if st.session_state.get("ugfs_filter_signature") != signature:
                st.session_state["ugfs_filter_signature"] = signature
                st.session_state["ugfs_list_page"] = 1
            page_count = max(1, math.ceil(len(filtered) / 20))
            page = min(st.session_state.get("ugfs_list_page", 1), page_count)
            st.session_state["ugfs_list_page"] = page
            selected = nav.selected_row(filtered)
            st.markdown(f'<div class="ug-list-count">{len(filtered)} notification(s) trouvée(s)</div>', unsafe_allow_html=True)
            with st.container(height=535, border=False, key="notification_list"):
                for row in filtered[(page - 1) * 20:page * 20]:
                    active = selected and row["uid"] == selected["uid"]
                    with st.container(key=f"alertrow_{'selected_' if active else ''}{row['uid']}"):
                        icon, body, badges = st.columns([.35, 3.5, 1.6], vertical_alignment="center")
                        icon.markdown(f'<div class="ug-row-icon {"cmf" if row["kind"] == "cmf" else ""}">{svg_icon("document" if row["kind"] == "cmf" else "building")}</div>', unsafe_allow_html=True)
                        with body:
                            st.button(p._clean(row["title"], 125) or "Notification", key="select_" + row["uid"], type="tertiary", on_click=nav.select_row, args=(row,), width="stretch")
                            st.markdown(f'<div class="ug-rowmeta"><span class="ug-row-source">{p._esc(row["source"])}</span><span>{p._esc(p._clean(row["entity"], 30))}</span><span>{p._esc(str(row["date"])[:10])}</span>{p._services_badges(row["services"], row.get("triage_services", []))}</div>', unsafe_allow_html=True)
                        badges.markdown(p.status_stack(row), unsafe_allow_html=True)
                        if service in {"investment", "portfolio"}:
                            business = (row.get("business_results", {}).get(service) or {}).get("analysis", {}).get("business_output", {})
                            state = row.get("service_states", {}).get(service, "À analyser")
                            signal = business.get("investment_signal" if service == "investment" else "monitoring_severity", "Non déterminé")
                            st.caption(f"{adapter.service_label(service)} · {state} · {signal}")
                            reasons = [r["rule"] for r in row.get("routing_reasons", []) if service in r.get("services", [])]
                            if reasons:
                                st.caption("Routage : " + " · ".join(reasons))
                if not filtered:
                    st.info("Aucune notification ne correspond aux filtres.")
            a, b, c = st.columns([2, 1, 2])
            a.button("Précédent", icon=":material/chevron_left:", key="page_previous", disabled=page <= 1, on_click=nav.set_page_number, args=(page - 1,))
            b.caption(f"{page} / {page_count}")
            c.button("Suivant", icon=":material/chevron_right:", key="page_next", disabled=page >= page_count, on_click=nav.set_page_number, args=(page + 1,))
        with right:
            with st.container(key="notification_detail"):
                detail(selected, workspace, context=service or "workspace", preferred_service=service)
