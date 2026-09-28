"""Open only real local PDFs or collected source URLs."""
from pathlib import Path
import streamlit as st
from services import ui_adapter as adapter


@st.dialog("Document source", width="large")
def preview_pdf(path):
    pdf = Path(path)
    if not pdf.is_file() or pdf.suffix.lower() != ".pdf":
        st.error("Ce document n’est plus disponible à cet emplacement.")
        return
    st.caption(pdf.name)
    data = pdf.read_bytes()
    st.download_button("Télécharger le PDF", data, file_name=pdf.name, mime="application/pdf", on_click="ignore", key="preview_download")
    try:
        preview = adapter.pdf_preview(str(pdf))
        page = st.number_input("Page du document", min_value=1, max_value=preview["pages"], value=1, step=1, key="preview_page_" + str(pdf))
        if page != 1:
            preview = adapter.pdf_preview(str(pdf), page)
        st.image(preview["image"], caption=f"Page {preview['page']} / {preview['pages']}", width="stretch")
    except Exception as exc:
        st.warning(f"Aperçu indisponible : {exc}. Le téléchargement du PDF reste disponible.")


def render_documents(documents, context):
    st.markdown(f"**Documents & sources ({len(documents)})**")
    if not documents:
        st.caption("Aucun PDF ni lien source disponible dans les données collectées.")
        return
    for i, document in enumerate(documents):
        if document["kind"] == "pdf":
            if st.button(document["label"], icon=":material/picture_as_pdf:", key=f"{context}_pdf_{i}", width="stretch"):
                preview_pdf(document["path"])
        else:
            st.link_button(document.get("label") or "Ouvrir la source", document["url"], icon=":material/open_in_new:", width="stretch", help=document["url"])
