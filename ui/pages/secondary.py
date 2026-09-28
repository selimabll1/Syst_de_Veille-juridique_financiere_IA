"""Home, source supervision, history and administration in final UI ownership."""
import json
import os
from pathlib import Path
import shutil
import streamlit as st
from services import ui_adapter as adapter
from ui import navigation as nav
from ui.components.documents import render_documents
from ui.pages import workspace as master


def table(rows, columns=None):
    if rows:
        if columns:
            rows = [{label: r.get(key, "") for key, label in columns.items()} for r in rows]
        st.dataframe(rows, hide_index=True, width="stretch")
    else:
        st.caption("Aucun enregistrement disponible.")


def home(workspace):
    from ui.pages.home import render
    render(workspace)


def sources(workspace):
    st.title("Sources / Documents")
    view = st.segmented_control("Espace documentaire", ["Documents collectés", "Supervision des sources", "Historique CMF"], default="Documents collectés", key="sources_view", label_visibility="collapsed")
    if view == "Supervision des sources":
        table(workspace["sources"], {"label": "Source", "status": "État", "note": "Informations", "last_check_at": "Dernier contrôle"})
        a, b, c = st.columns(3)
        if a.button("Synchroniser LegalTech", icon=":material/sync:", key="source_sync_lt", width="stretch"):
            nav.start_action("Synchronisation LegalTech", "legaltech_browser", "sync_legaltech", workspace["alerts"])
            st.rerun()
        if b.button("Collecter les PDF LegalTech", icon=":material/picture_as_pdf:", key="source_sync_pdf", width="stretch"):
            nav.start_action("Collecte PDF LegalTech", "legaltech_browser", "sync_pdfs")
            st.rerun()
        pages = c.number_input("Pages CMF à collecter", 1, 20, 1, key="cmf_pages")
        if c.button("Synchroniser CMF", icon=":material/sync:", key="source_sync_cmf", width="stretch"):
            nav.start_action("Synchronisation CMF", "cmf", "sync_cmf", pages)
            st.rerun()
        st.caption("CMF est rattaché à la Conformité. La première collecte réelle établit la base de référence existante.")
        return
    if view == "Historique CMF":
        table(workspace["cmf_runs"])
        return
    a, b = st.columns([3, 1])
    query = a.text_input("Rechercher un document", placeholder="Nom, société, référence…", key="doc_query")
    origin = b.selectbox("Source", ["Toutes", "LegalTech", "CMF"], key="doc_origin")
    documents, seen = [], set()
    for row in workspace["rows"]:
        if origin != "Toutes" and row["kind"] != origin.casefold():
            continue
        for document in row["documents"]:
            identity = document.get("path") or document.get("url")
            blob = f"{row['entity']} {row['title']} {document['label']} {identity}".casefold()
            if identity not in seen and all(word in blob for word in query.casefold().split()):
                seen.add(identity)
                documents.append((document, row))
    if origin == "Toutes":
        for document in workspace.get("registry_documents", []):
            identity = document.get("path") or document.get("url")
            if identity not in seen and all(word in str(identity).casefold() for word in query.casefold().split()):
                seen.add(identity)
                documents.append((document, None))
        for entry in workspace["catalog"]:
            path = str(entry["path"])
            if path not in seen and all(word in path.casefold() for word in query.casefold().split()):
                seen.add(path)
                documents.append(({"kind": "pdf", "path": path, "label": Path(path).name}, None))
    st.caption(f"{len(documents)} document(s) et lien(s) source")
    page_count = max(1, (len(documents) + 19) // 20)
    page = st.number_input("Page de documents", 1, page_count, key="doc_page")
    with st.container(height=650, border=False):
        for index, (document, row) in enumerate(documents[(page - 1) * 20:page * 20]):
            with st.container(border=True):
                if row:
                    st.caption(f"{row['source']} · {row['entity']} · {row['date']}")
                render_documents([document], f"library_{page}_{index}")


def analysis(workspace):
    from ui.pages.business_workspace import analysis as render
    render(workspace)


def results(workspace, validation=False):
    from ui.pages.business_workspace import results as render
    return render(workspace,validation)


def history(workspace):
    from ui.pages.activity import render
    return render(workspace)


def diffusion_candidates(workspace, service):
    from services.lifecycle import result_validated
    return [row for row in workspace['rows'] + workspace.get('child_rows', [])
            if service in row['services'] and result_validated(row.get('business_results', {}).get(service))]


def diffusion(workspace):
    st.title("Diffusion / Actions")
    service = st.selectbox("Service", list(adapter.SERVICES), format_func=adapter.service_label, key="digest_service")
    settings = next((r for r in workspace["digest_settings"] if r["service_id"] == service), {})
    with st.expander("Organisation du digest", expanded=True):
        with st.form("digest_settings_" + service):
            recipients = st.text_area("Destinataires (un par ligne)", value="\n".join(json.loads(settings.get("recipients_json") or "[]")))
            a, b, c = st.columns(3)
            cadences = ["daily", "weekly", "manual"]
            cadence = a.selectbox("Cadence", cadences, index=cadences.index(settings.get("cadence")) if settings.get("cadence") in cadences else 0, format_func=lambda v: {"daily": "Quotidienne", "weekly": "Hebdomadaire", "manual": "Manuelle"}[v])
            enabled = b.checkbox("Digest activé", value=bool(settings.get("enabled")))
            critical = c.checkbox("Alerte critique immédiate", value=bool(settings.get("critical_immediate", 1)))
            if st.form_submit_button("Enregistrer la configuration", type="primary"):
                nav.execute(adapter.command, "save_digest", service, recipients.splitlines(), cadence, enabled, critical)
                st.rerun()
    from services.lifecycle import result_validated
    candidates = diffusion_candidates(workspace, service)
    st.caption("La diffusion inclut uniquement les résultats métier validés pour le service choisi.")
    row_map = {r["uid"]: r for r in candidates}
    queued = {r["alert_uid"] for r in workspace["digest_queue"] if r.get("service_id") == service and r.get("status") == "queued"}
    default = [r["uid"] for r in candidates if r["stable_uid"] in queued or r["uid"] in queued or r["uid"] == st.session_state.get(nav.SELECTED)]
    picked = st.multiselect("Notifications à diffuser", list(row_map), default=default, format_func=lambda uid: f"{row_map[uid]['entity']} — {row_map[uid]['title']}", key="digest_picked_" + service)
    rows = [row_map[uid] for uid in picked]
    a, b = st.columns([1, 3])
    if a.button("Ajouter à la file", key="digest_queue", disabled=not rows):
        for row in rows:
            nav.execute(adapter.command, "queue_digest", row, service)
        st.rerun()
    if rows:
        subject, text, _ = adapter.digest_preview(service, rows)
        st.markdown(f"**{subject}**")
        st.text_area("Aperçu du message", text, height=250, disabled=True)
        st.download_button("Télécharger l’aperçu", text.encode("utf-8"), file_name="digest_ugfs.txt")
    smtp = adapter.smtp_status()
    st.caption("Diffusion email configurée." if smtp["configured"] else "Diffusion email non configurée.")
    targets = [line.strip() for line in recipients.splitlines() if line.strip()]
    if st.button("Envoyer le digest", icon=":material/send:", type="primary", key="digest_send", disabled=not (smtp["configured"] and targets and rows)):
        nav.execute(adapter.command, "send_digest", service, targets, rows)
        st.rerun()
    with st.expander("Affectations et actions enregistrées"):
        table(workspace["assignments"])


def reference(workspace):
    from ui.pages.administration import reference as render_admin_reference
    return render_admin_reference(workspace)


def settings(workspace):
    from ui.pages.administration import settings as render_admin_settings
    return render_admin_settings(workspace)
