"""Deterministic business summary; exact citations remain in the evidence section."""
from decimal import Decimal
from services.event_taxonomy import TAXONOMY

RECOMMENDATIONS={'investment':'recommended_actions','compliance':'action_required','portfolio':'recommended_actions','commercial':'recommended_commercial_action'}

def synthesis(facts):
    ids={e['id'] for e in facts.get('source_evidence',[])}
    used=[]
    def value(key):
        fact=facts.get(key)
        if not isinstance(fact,dict) or not fact.get('evidence_ids') or not set(fact['evidence_ids'])<=ids:return None
        used.extend(fact['evidence_ids']);return fact.get('value')
    company=value('company');event=facts.get('event_type','UNKNOWN')
    label=TAXONOMY.get(event,('Événement non déterminé',))[0]
    amounts=[value(k) for k in ('capital_before','capital_change','capital_after')]
    def fmt(v):return format(abs(Decimal(v)),',f').replace(',',' ').rstrip('0').rstrip('.') if '.' in format(abs(Decimal(v)),',f') else format(abs(Decimal(v)),',f').replace(',',' ')
    if company and event in {'CAPITAL_REDUCTION','CAPITAL_INCREASE'} and all(v is not None for v in amounts) and facts.get('validation',{}).get('status')=='VERIFIED':
        currency=facts['capital_change'].get('currency','')
        text=f"{company} : {label.lower()} de {fmt(amounts[1])} {currency}, faisant passer le capital de {fmt(amounts[0])} à {fmt(amounts[2])} {currency}."
    elif event=='PUBLIC_WARNING':
        authority=value('issuing_authority')
        text=f"{authority or 'La source'} publie une mise en garde. Les précautions et le champ d’application sont à examiner dans les preuves source ; aucune exposition propre à UGFS n’est établie."
    else:
        text=f"{company+' : ' if company else ''}{label}. Les incidences métier restent à confirmer à partir des preuves source."
    used.extend(facts.get('classification',{}).get('evidence_ids',[]))
    return {'text':text,'evidence_ids':list(dict.fromkeys(used)),'method':'CANONICAL_TEMPLATE_6.1'}

def output_view(analysis):
    output=dict(analysis.get('business_output',{}))
    aliases={'signal_commercial':'commercial_signal','opportunite':'supported_opportunity','action_commerciale':'recommended_commercial_action','echeances':'deadlines'}
    for old,new in aliases.items():
        if old in output and new not in output:output[new]=output.pop(old)
    facts=analysis.get('canonical_facts')
    # Human corrections must remain visible, including on historical results.
    changes=analysis.get('grounding',{}).get('human_changes')
    if facts and not changes:
        output['summary']=(analysis.get('summary_derivation') or synthesis(facts))['text']
    return output

def selection_message(analysis):
    status=analysis.get('evidence_selection_status')
    if status=='FULL_SOURCE_SCANNED':return 'Analyse réalisée à partir d’extraits pertinents sélectionnés dans le document disponible. Consultez la source complète avant validation.'
    if status in {'PARTIAL_SOURCE_SCANNED','SOURCE_TRUNCATED','EXTRACTION_PARTIAL'}:return 'Couverture partielle du document disponible. Consultez les limites d’extraction et la source complète avant validation.'
    if analysis.get('business_schema')=='intelligence_v6':return 'Extraits sélectionnés dans le document disponible ; statut détaillé de couverture non enregistré pour cette version historique.'
    if analysis.get('source_truncated'):return 'Analyse historique : contenu fourni au modèle tronqué. Consultez la source complète avant validation.'
    return ''


BUSINESS_LABELS = {
    "summary": "Résumé métier", "event_type": "Type d’événement", "entities": "Entités",
    "sector": "Secteur", "investment_relevance": "Pertinence pour l’investissement",
    "investment_impact": "Incidence sur l’investissement", "financial_signals": "Signaux financiers",
    "strategic_signals": "Signaux stratégiques", "investment_signal": "Signal d’investissement",
    "materiality": "Importance pour la revue", "recommended_actions": "Actions recommandées",
    "confidence": "Indice de fiabilité et limites", "evidence": "Preuves source", "uncertainties": "Incertitudes",
    "validation_status": "État de validation", "matched_portfolio_entity": "Participation rapprochée",
    "referential_match_reason": "Justification du rapprochement", "portfolio_relevance": "Pertinence pour le portefeuille",
    "financial_impact": "Incidence financière", "operational_impact": "Incidence opérationnelle",
    "governance_impact": "Incidence sur la gouvernance", "legal_regulatory_impact": "Incidence juridique et réglementaire",
    "monitoring_severity": "Priorité de suivi",
    "applicability": "Applicabilité UGFS", "regulatory_legal_event": "Événement juridique / réglementaire",
    "obligations": "Obligations documentées", "effective_date": "Date d’effet", "echeances": "Échéances", "deadlines":"Échéances",
    "regulatory_impact": "Incidence réglementaire", "action_required": "Action de conformité",
    "commercial_relationship": "Relation commerciale confirmée", "commercial_relevance": "Pertinence commerciale",
    "commercial_signal": "Signal commercial", "supported_opportunity": "Opportunité étayée",
    "recommended_commercial_action": "Action commerciale recommandée",
}
