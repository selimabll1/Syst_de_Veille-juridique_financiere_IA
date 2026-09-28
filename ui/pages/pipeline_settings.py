"""Source eligibility, business prompts and rule configuration."""
from copy import deepcopy
import json
import streamlit as st
from services import ui_adapter as adapter
from ui import navigation as nav


def render(workspace):
    from services import pipeline_config
    config = deepcopy(workspace.get("pipeline_config") or pipeline_config.load())
    st.caption("Source → collecte → extraction → notification unique → rapprochement → services → résultats métier → validation → diffusion → historique")
    st.caption("Moteur local commun : " + adapter.model_configuration()["model"])
    source_rows = []
    for source in workspace["sources"]:
        source_rows.append({"Source": source["label"], "Type": source["type"], "Connexion": source["status"], "Active": source["active"], "Dernière synchronisation": source["last_check_at"], "Services éligibles": " · ".join(adapter.service_label(s) for s in source["eligible_services"])})
    st.dataframe(source_rows, hide_index=True, width="stretch")
    with st.form("pipeline_sources"):
        for key, source in config["sources"].items():
            a, b = st.columns([1, 3])
            source["active"] = a.checkbox(source["label"], value=source["active"], disabled=not source.get("implemented"), key="source_active_" + key)
            source["eligible_services"] = b.multiselect("Services éligibles · " + key, ["compliance"] if key == "cmf" else list(adapter.SERVICES), default=source["eligible_services"], format_func=adapter.service_label, disabled=key == "cmf", key="source_eligible_" + key)
        if st.form_submit_button("Enregistrer les sources"):
            nav.execute(adapter.command, "save_pipeline_config", config)
            st.rerun()
    st.subheader("Services & prompts spécialisés")
    for key, service in config["services"].items():
        with st.expander(adapter.service_label(key)):
            st.caption("Sources : " + " · ".join(s for s, value in config["sources"].items() if key in value["eligible_services"]))
            st.caption(f"{sum(key in r['services'] for r in workspace['rows'])} notifications affectées · Prompt version {service['prompt_version']}")
            st.json([r for r in config["routing_rules"] if key in r.get("services", [])])
            with st.form("business_prompt_" + key):
                service["prompt"] = st.text_area("Prompt métier actif", service["prompt"], height=160)
                schema_text = st.text_area("Schéma des sélecteurs de preuves/actions (JSON)", json.dumps(service["output_schema"], ensure_ascii=False, indent=2), height=160) if service.get("grounded") else None
                st.caption("Champs du résultat : " + " · ".join(service["output_fields"]))
                if st.form_submit_button("Enregistrer le prompt"):
                    try:
                        if schema_text:
                            service["output_schema"] = json.loads(schema_text)
                        nav.execute(adapter.command, "save_pipeline_config", config)
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
    with st.expander("Événements, interprétations prudentes et actions métier"):
        with st.form("event_policies"):
            policies = st.text_area("Événements et déclencheurs (JSON)", json.dumps(config.get("event_types", {}), ensure_ascii=False, indent=2), height=240)
            actions = st.text_area("Actions métier disponibles (JSON)", json.dumps(config.get("business_actions", {}), ensure_ascii=False, indent=2), height=180)
            if st.form_submit_button("Enregistrer les politiques métier"):
                try:
                    config["event_types"] = json.loads(policies)
                    config["business_actions"] = json.loads(actions)
                    nav.execute(adapter.command, "save_pipeline_config", config)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
    with st.expander("Règles de routage & fichiers du référentiel"):
        st.caption("Règles avant IA. Une affectation manuelle est prioritaire. Les chemins doivent désigner des données réelles, jamais un modèle de démonstration.")
        with st.form("pipeline_rules"):
            rules = st.text_area("Règles de routage (JSON)", json.dumps(config["routing_rules"], ensure_ascii=False, indent=2), height=220)
            files = st.text_area("Fichiers du référentiel (un chemin par ligne)", "\n".join(config.get("referential_files", [])))
            if st.form_submit_button("Enregistrer le routage"):
                try:
                    config["routing_rules"] = json.loads(rules)
                    config["referential_files"] = [f.strip() for f in files.splitlines() if f.strip()]
                    nav.execute(adapter.command, "save_pipeline_config", config)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
