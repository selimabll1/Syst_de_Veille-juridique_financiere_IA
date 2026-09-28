"""Detail presentation retained from V33.8; final UI ownership only."""
from __future__ import annotations
import html
from typing import Any
import streamlit as st
from services import ui_adapter as adapter

def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def _clean(value: Any, limit: int | None = None) -> str:
    import re
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = " ".join(text.split()).strip()
    if limit and len(text) > limit:
        return text[: max(1, limit - 1)].rstrip() + "…"
    return text


def _priority_class(value: Any) -> str:
    raw = str(value or "").casefold()
    if "crit" in raw:
        return "critical"
    if "haut" in raw or "élev" in raw or "elev" in raw:
        return "high"
    if "moy" in raw:
        return "medium"
    if "faib" in raw or "bass" in raw or "info" in raw:
        return "low"
    return "muted"


def _status_class(value: Any) -> str:
    raw = str(value or "").casefold()
    if raw == "à valider":
        return "running"
    if "trait" in raw or "valid" in raw or "termin" in raw:
        return "success"
    if "cours" in raw:
        return "running"
    if "erreur" in raw or "échec" in raw or "echec" in raw:
        return "error"
    if "analys" in raw or "attente" in raw:
        return "waiting"
    if "nouveau" in raw:
        return "new"
    return "muted"


def _meta_find(value: Any, *wanted: str) -> str:
    targets = {x.casefold().replace("_", " ").strip() for x in wanted}
    found: list[str] = []

    def walk(obj: Any, depth: int = 0) -> None:
        if depth > 5 or found:
            return
        if isinstance(obj, dict):
            for key, child in obj.items():
                normalized = str(key).casefold().replace("_", " ").strip()
                if normalized in targets and child not in (None, "", [], {}):
                    found.append(_clean(child, 180))
                    return
                walk(child, depth + 1)
        elif isinstance(obj, (list, tuple)):
            for child in obj[:10]:
                walk(child, depth + 1)

    walk(value)
    return found[0] if found else ""


def _analysis_value(analysis: dict | None, *keys: str, default: Any = "—") -> Any:
    return adapter.analysis_value(analysis, *keys, default=default)


def _analysis_count(row: dict) -> int:
    return 1 if isinstance(row.get("analysis"), dict) and row.get("analysis") else 0


def _priority_badge(value: Any) -> str:
    return (
        f'<span class="f-badge {_priority_class(value)}">'
        f'<span class="f-dot"></span>{_esc(value or "À classer")}</span>'
    )


def _status_badge(value: Any) -> str:
    return f'<span class="f-badge {_status_class(value)}">{_esc(value or "—")}</span>'


def _reading_badge(is_read: bool) -> str:
    return f'<span class="f-reading {"read" if is_read else "unread"}">{"Lu" if is_read else "Non lu"}</span>'


def status_stack(row):
    from services.lifecycle import ai_status
    return ('<div class="ug-status-stack"><span>Priorité</span>' + _priority_badge(row["priority"])
            + '<span>IA</span>' + _status_badge(ai_status(row))
            + '<span>Traitement</span>' + _status_badge(row["status"])
            + '<span>Lecture</span>' + _reading_badge(row["read"]) + '</div>')


def _services_badges(services: list[str], triage_services=()) -> str:
    if not services:
        return '<span class="f-badge muted">Affectation à vérifier</span>'
    chunks = []
    for service in services:
        cls = {
            "compliance": "purple",
            "portfolio": "cyan",
            "investment": "blue",
            "commercial": "indigo",
        }.get(service, "blue")
        label = adapter.service_label(service)
        if service in triage_services:
            label += ' · triage à confirmer'
        chunks.append(f'<span class="f-badge {cls}">{_esc(label)}</span>')
    return "".join(chunks)


def _source_icon(row: dict) -> str:
    if row.get("kind") == "cmf":
        return "file-earmark-text"
    text = f"{row.get('title','')} {row.get('type','')}".casefold()
    if any(word in text for word in ("personne", "dirigeant", "nomination", "président", "president")):
        return "person"
    if any(word in text for word in ("justice", "judicia", "sanction", "condamn", "liquidation")):
        return "hammer"
    return "buildings"


def _overview(row: dict) -> None:
    meta=row.get("metadata") or {}
    sector=_meta_find(meta,"secteur","sector","gics","gics l4") or "Non disponible"
    country=_meta_find(meta,"pays","country") or "Non disponible"
    portfolio="Correspondance confirmée" if row.get("portfolio_confirmed") else "Aucune correspondance confirmée"

    st.markdown(
        f'<div class="f-info-grid"><div class="f-card"><div class="f-card-title">Informations générales</div>'
        f'<div class="f-kv"><div class="f-k">Société concernée</div><div class="f-v">{_esc(row.get("entity") or "—")}</div></div>'
        f'<div class="f-kv"><div class="f-k">Type d’information</div><div class="f-v">{_esc(row.get("type") or "—")}</div></div>'
        f'<div class="f-kv"><div class="f-k">Source</div><div class="f-v">{_esc(row.get("source") or "—")}</div></div>'
        f'<div class="f-kv"><div class="f-k">Date de publication</div><div class="f-v">{_esc(str(row.get("date") or "—")[:19].replace("T"," "))}</div></div>'
        f'<div class="f-kv"><div class="f-k">Services concernés</div><div class="f-v">{_services_badges(row.get("services") or [], row.get("triage_services", []))}</div></div>'
        f'<div class="f-kv"><div class="f-k">Statut</div><div class="f-v">{_status_badge(row.get("status"))}</div></div>'
        f'<div class="f-kv"><div class="f-k">Lecture</div><div class="f-v">{_reading_badge(bool(row.get("read")))}</div></div>'
        f'<div class="f-kv"><div class="f-k">Priorité</div><div class="f-v">{_priority_badge(row.get("priority"))}</div></div>'
        f'</div>'
        f'<div class="f-card"><div class="f-card-title">Société</div><div class="f-company">{_esc(row.get("entity") or "—")}</div>'
        f'<div class="f-kv"><div class="f-k">Secteur</div><div class="f-v">{_esc(sector)}</div></div>'
        f'<div class="f-kv"><div class="f-k">Pays</div><div class="f-v">{_esc(country)}</div></div>'
        f'<div class="f-kv"><div class="f-k">Dans le portefeuille UGFS</div><div class="f-v">{_esc(portfolio)}</div></div>'
        f'<div class="f-company-button">Données de la source collectée</div></div></div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        f'<div class="f-card" style="margin-top:.43rem"><div class="f-card-title">Résumé</div>'
        f'<div class="f-summary" dir="auto">{_esc(_clean(row.get("summary"),460) or "Aucun résumé source disponible.")}</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="f-card-title" style="margin-top:.5rem">Analyses et résultats par service</div>',unsafe_allow_html=True)
    services=row.get("services") or []
    if row.get('routing_status'):
        st.caption(row['routing_status'])
    if not services:
        st.markdown('<div class="f-empty">Aucun service affecté. Une affectation manuelle reste possible.</div>',unsafe_allow_html=True)
        return

    analysis=row.get("analysis")
    explicit=None
    if isinstance(analysis,dict):
        for key in ("service","service_key","business_service","target_service"):
            if analysis.get(key):
                explicit=adapter.service_key(analysis.get(key))
                break

    cards=[]
    for service in services:
        record = row.get("business_results", {}).get(service)
        current_analysis = record.get("analysis") if record else None
        available = bool(current_analysis)
        if available:
            output = current_analysis.get("business_output", {})
            txt = _clean(" · ".join(str(v) for v in output.values()) or _analysis_value(current_analysis,"Résumé_IA","resume",default="Résultat enregistré."),210)
            badge = _status_badge(row.get("service_states", {}).get(service, "Analyse terminée"))
        else:
            txt="Aucun résultat spécialisé persistant pour ce service."
            badge = _status_badge(row.get("service_states", {}).get(service, "À analyser"))
        cards.append(
            f'<div class="f-result"><div class="f-result-head"><div class="f-result-name">{_esc(adapter.service_label(service))}</div>{badge}</div>'
            f'<div class="f-result-text">{_esc(txt)}</div></div>'
        )
    st.markdown(f'<div class="f-results{" one" if len(cards)==1 else ""}">'+"".join(cards)+'</div>',unsafe_allow_html=True)


def _source_tab(row: dict) -> None:
    raw=row.get("raw") or {}
    meta_rows=[
        ("Source",row.get("source")),
        ("Référence",raw.get("article_id") or raw.get("reference") or raw.get("uid")),
        ("Société / entité",row.get("entity")),
        ("Type d'information",row.get("type")),
        ("Date",row.get("date")),
        ("PDF local",row.get("pdf_path") or "—"),
        ("URL source",row.get("source_url") or "—"),
    ]
    meta_rows.extend(adapter.flatten_metadata(row.get("metadata") or {},limit=20))
    body="".join(
        f'<div class="f-meta-row"><div class="f-meta-key">{_esc(str(k).replace("_"," ").title())}</div><div class="f-meta-val">{_esc(v or "—")}</div></div>'
        for k,v in meta_rows if v not in (None,"",[],{})
    )
    st.markdown(f'<div class="f-card"><div class="f-card-title">Métadonnées source</div><div class="f-meta-list">{body or "<div class=f-empty>Aucune métadonnée disponible.</div>"}</div></div>',unsafe_allow_html=True)
    st.markdown(f'<div class="f-card" style="margin-top:.43rem"><div class="f-card-title">Extrait source</div><div class="f-summary" dir="auto" style="-webkit-line-clamp:8;max-height:7rem">{_esc(_clean(row.get("summary"),1200) or "Aucun contenu source extrait.")}</div></div>',unsafe_allow_html=True)


def _ai_tab(row: dict) -> None:
    analysis=row.get("analysis")
    if not analysis:
        st.markdown('<div class="f-empty">Aucune analyse IA persistante pour cette notification.</div>',unsafe_allow_html=True)
        return
    if analysis.get('business_output'):
        shown=adapter.result_presentation(analysis)
        st.markdown('**Résumé métier**')
        st.write(shown['output'].get('summary','Non déterminé'))
        st.markdown('**Action recommandée**')
        st.write(shown['recommendation'])
        st.markdown('**Incertitudes**')
        st.write(shown['output'].get('uncertainties','Non déterminé'))
        reliability=analysis.get('reliability',{})
        if reliability.get('factual_score') is not None:
            st.caption(f"Fiabilité factuelle : {reliability['factual_score']}/100 · Pertinence métier : {reliability['service_relevance']['label']}")
        st.caption(shown['output'].get('confidence','Indice de fiabilité non enregistré'))
        st.markdown('**Preuves source**')
        st.write(shown['output'].get('evidence','Non disponible'))
    else:
        st.write(_analysis_value(analysis,'Résumé_IA','resume','summary',default='—'))
        st.write(_analysis_value(analysis,'Action_Recommandée_IA','action_recommandee',default='—'))
    with st.expander('Données techniques de l’analyse',expanded=False):
        st.json(analysis,expanded=False)


def _results_tab(row: dict) -> None:
    analysis=row.get("analysis")
    if not analysis:
        st.markdown('<div class="f-empty">Aucun résultat IA réel enregistré.</div>',unsafe_allow_html=True)
        return
    if analysis.get("business_schema") in {"grounded_v1", "intelligence_v6"}:
        st.caption("Résultat métier fondé sur des citations source. Les impacts non démontrés restent non déterminés ; aucun score financier automatique n’est produit.")
        return
    fields=[
        ("Résumé",_analysis_value(analysis,"Résumé_IA","resume","summary",default="—")),
        ("Confiance",_analysis_value(analysis,"Confiance_IA","confiance","confidence",default="—")),
        ("Action recommandée",_analysis_value(analysis,"Action_Recommandée_IA","action_recommandee",default="—")),
        ("Score risque existant",_analysis_value(analysis,"Score_Risque_IA","score_risque",default="—")),
        ("Score opportunité existant",_analysis_value(analysis,"Score_Opportunité_IA","score_opportunite",default="—")),
        ("Risques détectés",_analysis_value(analysis,"Risques_Détectés_IA","risques_detectes",default="—")),
        ("Justification du risque",_analysis_value(analysis,"Détail_Score_Risque",default="—")),
        ("Opportunités détectées",_analysis_value(analysis,"Opportunités_Détectées_IA","opportunites_detectees",default="—")),
    ]
    body="".join(
        f'<div class="f-meta-row"><div class="f-meta-key">{_esc(k)}</div><div class="f-meta-val">{_esc(_clean(v,680))}</div></div>'
        for k,v in fields
    )
    st.markdown(f'<div class="f-card"><div class="f-card-title">Résultat enregistré</div><div class="f-meta-list">{body}</div></div>',unsafe_allow_html=True)
