import streamlit as st

from ui.app_ui import render
st.set_page_config(
    page_title="Système de Veille UGFS",
    page_icon="📘",
    layout="wide",
    initial_sidebar_state="expanded",
)

render()
