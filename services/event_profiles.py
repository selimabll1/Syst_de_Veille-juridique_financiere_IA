"""Versioned deterministic fact profiles. No company-specific exceptions."""
from services.event_taxonomy import normalize

CAPITAL=['capital_before','capital_change','capital_after']
CORPORATE={'CAPITAL_REDUCTION','CAPITAL_INCREASE','INCORPORATION','ACQUISITION','DISPOSAL','MERGER','LIQUIDATION','DIRECTOR_APPOINTMENT','SHAREHOLDING','FINANCING','DIVIDEND','FINANCIAL_RESULTS','FINANCIAL_STATEMENTS_FILING','FINANCIAL_REPORTING_PUBLICATION','FINANCIAL_STATEMENTS_APPROVAL','GOVERNANCE','RESTRUCTURING','DEBT'}
from services.financial_vocabulary import FINANCIAL_EVENTS, GOVERNANCE_EVENTS
CORPORATE |= FINANCIAL_EVENTS | GOVERNANCE_EVENTS
PROFILES={
 'FINANCIAL_RESULTS':dict(required=['event_type','company','performance_facts','source_evidence'],important=['publication_date'],not_applicable=CAPITAL+['share_counts','nominal_values'],requires_subject_entity=True),
 'FINANCIAL_STATEMENTS_FILING':dict(required=['event_type','company','source_evidence'],important=['publication_date','accounting_year'],not_applicable=CAPITAL+['share_counts','nominal_values','performance_facts'],requires_subject_entity=True),
 'FINANCIAL_REPORTING_PUBLICATION':dict(required=['event_type','company','performance_facts','source_evidence'],important=['publication_date'],not_applicable=CAPITAL+['share_counts','nominal_values'],requires_subject_entity=True),
 'FINANCIAL_STATEMENTS_APPROVAL':dict(required=['event_type','company','source_evidence'],important=['publication_date','accounting_year'],not_applicable=CAPITAL+['share_counts','nominal_values','performance_facts'],requires_subject_entity=True),
 'UNKNOWN':dict(required=['source_evidence'],important=['publication_date'],not_applicable=CAPITAL+['share_counts','nominal_values'],requires_subject_entity=False,allows_unknown=True),
 'PUBLIC_WARNING':dict(required=['event_type','issuing_authority','warning_subject','warning_content','source_evidence'],important=['publication_date','affected_audience','recommended_precautions'],not_applicable=['company',*CAPITAL,'share_counts','nominal_values'],requires_subject_entity=False),
 'REGULATION':dict(required=['event_type','issuing_authority','warning_subject','affected_audience','warning_content','source_evidence'],important=['publication_date','effective_dates','deadlines'],not_applicable=CAPITAL+['share_counts','nominal_values'],requires_subject_entity=False),
 'REGULATORY_GUIDANCE':dict(required=['event_type','issuing_authority','warning_content','source_evidence'],important=['publication_date','affected_audience','effective_dates'],not_applicable=CAPITAL+['share_counts','nominal_values'],requires_subject_entity=False),
 'REPORTING_OBLIGATION':dict(required=['event_type','issuing_authority','affected_audience','obligations_identified','source_evidence'],important=['publication_date','effective_dates','deadlines'],not_applicable=CAPITAL+['share_counts','nominal_values'],requires_subject_entity=False),
}

def profile(event):
    value=dict(PROFILES.get(event,dict(required=['event_type','source_evidence']+(['company'] if event in CORPORATE else []),important=['publication_date'],not_applicable=[] if event in {'CAPITAL_REDUCTION','CAPITAL_INCREASE'} else CAPITAL+['share_counts','nominal_values'],requires_subject_entity=event in CORPORATE)))
    value={k:list(v) if isinstance(v,list) else v for k,v in value.items()}
    value.setdefault('allows_unknown', False)
    if event in {'CAPITAL_REDUCTION','CAPITAL_INCREASE'}:
        value['required']+=CAPITAL;value['important']+=['share_counts','nominal_values','dates']
    value['name']=event;value['version']='6.1.0';value['gates']={'missing_entity':60,'missing_required':55,'inconsistent':30}
    return value

def enrich(facts):
    evidence=facts['source_evidence']
    from services.event_taxonomy import performance_evidence
    facts['performance_facts'] = [{'value':e['quote'], 'evidence_ids':[e['id']]} for e in performance_evidence(evidence)]
    def matching(terms):
        return [{'value':e['quote'],'evidence_ids':[e['id']]} for e in evidence if any(t in normalize(e['quote']) for t in terms)]
    authority=matching(['conseil du marche financier','هيئة السوق المالية'])
    facts['issuing_authority']={'value':'Conseil du Marché Financier (CMF)','evidence_ids':authority[0]['evidence_ids']} if authority and (facts.get('source')=='cmf' or any('publie' in normalize(a['value']) for a in authority)) else None
    # A field is present only through an exact, explicit source clause.
    facts['warning_subject']=matching(['mise en garde','تحذير','reglement','reglementation','obligation','يجب','precisions','توضيحات'])
    facts['warning_content']=facts['warning_subject']
    facts['affected_audience']=matching(['public','investisseur','societes','personnes','entreprises','العموم','المستثمر','الشركات'])
    facts['recommended_precautions']=matching(['vigilance','verifier','ne pas','precaution','الحذر','التثبت'])
    facts['obligations_identified']=matching(['doit','doivent','obligation','يجب'])
    return facts
