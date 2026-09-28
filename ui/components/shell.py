"""Sidebar, search, remote watcher and KPIs owned by the final UI."""
import base64
from functools import lru_cache
import os
from pathlib import Path
import streamlit as st
from services import ui_adapter as adapter
from ui import navigation as nav
from ui.components.presentation import _esc
from ui.components.icons import icon

GROUPS = [
    ("PILOTAGE", [("home", "Accueil", "home")]),
    ("VEILLE PAR SERVICE", [("investment", "Investissement", "bar_chart"), ("compliance", "Conformité", "verified_user"), ("portfolio", "Suivi portefeuille", "donut_large"), ("commercial", "Commerce", "person_outline")]),
    ("TRAITEMENT", [("notifications", "Notifications", "notifications_none"), ("sources", "Sources / Documents", "description"), ("ai", "Analyses IA", "auto_awesome"), ("results", "Résultats", "article"), ("validation", "Validation", "task_alt"), ("history", "Historique", "history"), ("diffusion", "Diffusion / Actions", "send")]),
    ("ADMINISTRATION", [("reference", "Référentiel UGFS", "database"), ("settings", "Organisation & Paramétrage", "settings")]),
]


@lru_cache(maxsize=1)
def logo():
    path = Path(__file__).resolve().parents[2] / "assets" / "ugfs_logo_clean.png"
    if path.is_file():
        return '<img alt="UGFS North Africa" src="data:image/png;base64,' + base64.b64encode(path.read_bytes()).decode() + '">'
    return '<strong>UGFS</strong>'


def sidebar(workspace):
    with st.sidebar:
        st.markdown('<div class="ug-brand"><span class="ug-logo-frame">' + logo() + '</span><p>Veille juridique & financière<br>augmentée par l’IA</p></div>', unsafe_allow_html=True)
        for group, links in GROUPS:
            st.markdown(f'<div class="ug-nav-group">{group}</div>', unsafe_allow_html=True)
            for page, label, icon in links:
                if page == "notifications":
                    label += f" · {len(workspace['rows'])}"
                st.button(label, icon=f":material/{icon}:", key="nav_" + page, width="stretch", type="primary" if st.session_state[nav.PAGE] == page else "tertiary", on_click=nav.navigate, args=(page,))
        name = os.getenv("UGFS_USER_NAME", "Espace UGFS")
        initials = "".join(p[0] for p in name.split()[:2]).upper()
        st.markdown(f'<div class="ug-profile"><span class="ug-avatar">{_esc(initials)}</span><div>{_esc(name)}<small>Veille & analyse</small></div></div>', unsafe_allow_html=True)


def topbar(workspace):
    remote = workspace["remote"]
    pending = remote["pending"]
    with st.container(key="topbar"):
        search, status, sync, bell, avatar = st.columns([5.6, 1.55, 1.3, .62, .35], vertical_alignment="center")
        with search:
            st.text_input("Recherche globale", placeholder="Rechercher une société, une personne, un sujet…", icon=":material/search:", key="ugfs_global_search", label_visibility="collapsed")
        with status:
            run = workspace.get("run") or {}
            date = str(run.get("finished_at") or run.get("started_at") or "Aucune synchronisation")[:19].replace("T", " ")
            st.markdown(f'<div class="ug-sync">Dernière synchronisation<strong>{_esc(date)}</strong></div>', unsafe_allow_html=True)
        with sync:
            if st.button("Synchroniser", icon=":material/sync:", key="top_sync", width="stretch"):
                nav.start_action("Synchronisation LegalTech", "legaltech_browser", "sync_legaltech", workspace["alerts"])
                st.rerun()
        with bell:
            with st.popover(str(len(pending)), icon=":material/notifications:", help="Notifications distantes absentes localement ou présentant de nouveaux résultats"):
                st.markdown("**Veille distante LegalTech**")
                checked = remote["status"].get("checked_at") or "Jamais vérifiée"
                st.caption(f"Dernière vérification : {checked}")
                if remote["status"].get("status") == "ERROR":
                    st.error(remote["status"].get("message") or "Vérification indisponible. Dernier état connu conservé.")
                st.caption("Notifications absentes localement et augmentations du nombre de résultats sur LegalTech.")
                if not pending:
                    st.info("Aucun écart enregistré lors de la dernière vérification.")
                for item in pending[:20]:
                    label = item.get("company_or_query") or item.get("card_title") or item.get("title") or "Notification LegalTech"
                    reason = "Nouveaux résultats" if item.get("pending_reason") == "NEW_RESULTS" else "Nouvelle notification"
                    st.write(f"**{label}**")
                    st.caption(f"{reason} · +{item.get('result_delta', 0)} résultat(s)")
                if len(pending) > 20:
                    st.caption(f"… et {len(pending) - 20} autres notifications.")
                if st.button("Vérifier LegalTech", key="remote_check", icon=":material/refresh:"):
                    nav.start_action("Vérification LegalTech", "legaltech_browser", "check_remote")
                    st.rerun()
        with avatar:
            st.markdown('<span class="ug-avatar">UG</span>', unsafe_allow_html=True)


def kpis(workspace):
    rows = workspace["rows"]
    values = [
        (len(rows), "Notifications totales", "Informations collectées", "document", ""),
        (sum(not r["read"] for r in rows), "Nouvelles alertes", "Notifications non lues", "bell", ""),
        (len(workspace["results"]) + sum(r['notification_uid'] not in {p['uid'] for p in workspace['rows'] if p.get('document_status')} for r in workspace.get("business_results", [])), "Analyses IA complétées", "Résultats métier et historiques", "chart", "purple"),
        (sum(r["priority"] in {"Haute", "Critique", "Élevée"} for r in rows), "Éléments prioritaires", "Nécessitent votre attention", "shield", "red"),
        (sum(a.get("status") not in {"done", "closed", "completed"} for a in workspace["assignments"]), "Actions en attente", "Affectations enregistrées", "check", "amber"),
    ]
    with st.container(key="kpis"):
        for column, (value, label, note, symbol, color) in zip(st.columns(5), values):
            column.markdown(f'<div class="ug-kpi"><div class="ug-kpi-icon {color}">{icon(symbol)}</div><div><strong>{value}</strong><span>{label}</span><small>{note}</small></div></div>', unsafe_allow_html=True)
