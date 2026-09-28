"""Source-independent golden cases for deterministic gate regression.

These are constraints, not production notifications and contain no real
identifiers.  Model output is never trained from this table.
"""

GOLDEN_EVENTS = [
    {"name": "capital reduction", "event": "CAPITAL_REDUCTION", "required": ["company", "capital_before", "capital_change", "capital_after"], "forbidden": ["growth_claim"]},
    {"name": "capital increase", "event": "CAPITAL_INCREASE", "required": ["company", "capital_before", "capital_change", "capital_after"], "forbidden": ["growth_claim"]},
    {"name": "liquidation", "event": "LIQUIDATION", "required": ["company"], "forbidden": ["financial_impact"]},
    {"name": "incorporation", "event": "INCORPORATION", "required": ["company"], "forbidden": ["portfolio_match"]},
    {"name": "litigation", "event": "LITIGATION", "required": ["company", "source_evidence"], "forbidden": ["liability_conclusion"]},
    {"name": "public warning", "event": "PUBLIC_WARNING", "required": ["issuing_authority", "warning_subject", "warning_content"], "forbidden": ["company_required"]},
    {"name": "regulatory guidance", "event": "REGULATORY_GUIDANCE", "required": ["issuing_authority", "warning_content"], "forbidden": ["deadline_invented"]},
    {"name": "reporting obligation", "event": "REPORTING_OBLIGATION", "required": ["issuing_authority", "obligations_identified"], "forbidden": ["deadline_invented"]},
    {"name": "financial results", "event": "FINANCIAL_RESULTS", "required": ["company", "source_evidence"], "forbidden": ["trend_without_periods"]},
    {"name": "governance", "event": "GOVERNANCE", "required": ["company", "source_evidence"], "forbidden": ["person_invented"]},
    {"name": "composite bulletin", "event": "SEGMENTATION_REQUIRED", "required": ["parent_source_record_id", "child_publication_id"], "forbidden": ["cross_child_evidence"]},
    {"name": "long Arabic", "event": "UNKNOWN", "required": ["source_evidence"], "forbidden": ["translation_as_fact"]},
    {"name": "mixed French Arabic", "event": "UNKNOWN", "required": ["source_evidence"], "forbidden": ["language_assumption"]},
    {"name": "ambiguous event", "event": "EVENT_AMBIGUOUS", "required": ["competing_candidates"], "forbidden": ["single_event_claim"]},
    {"name": "irrelevant commerce", "event": "INSUFFICIENT_EVIDENCE", "required": ["commercial_context"], "forbidden": ["opportunity"]},
    {"name": "portfolio without referential", "event": "INSUFFICIENT_EVIDENCE", "required": ["authoritative_match"], "forbidden": ["holding_claim"]},
    {"name": "multi-service notification", "event": "SUCCESS_REVIEW_REQUIRED", "required": ["one_notification", "independent_service_results"], "forbidden": ["duplicated_notification"]},
]
