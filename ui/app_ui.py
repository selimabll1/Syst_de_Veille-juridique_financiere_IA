"""Final entry point: one theme, one state owner and one service adapter."""
import streamlit as st
from services import ui_adapter as adapter
from ui import navigation as nav
from ui.theme import apply_theme
from ui.components.shell import sidebar, topbar, kpis
from ui.pages import secondary, workspace as master


def render():
    nav.initialize()
    apply_theme()
    workspace = adapter.load_workspace()
    sidebar(workspace)
    topbar(workspace)
    from ui.components.action_status import render as action_status
    action_status()
    if workspace["errors"]:
        with st.expander("Données temporairement indisponibles", expanded=True):
            for error in workspace["errors"]:
                st.error(error)
    page = st.session_state[nav.PAGE]
    if page in adapter.SERVICES:
        kpis(workspace)
    if page in adapter.SERVICES:
        master.render(workspace, service=page)
    elif page == "notifications":
        master.render(workspace)
    elif page == "validation":
        secondary.results(workspace, validation=True)
    else:
        renderer = {"home": secondary.home, "sources": secondary.sources, "ai": secondary.analysis, "results": secondary.results, "history": secondary.history, "diffusion": secondary.diffusion, "reference": secondary.reference, "settings": secondary.settings}.get(page)
        if renderer:
            renderer(workspace)
        else:
            nav.navigate("notifications")
            st.rerun()
