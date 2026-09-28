# Common analysis correctness gates

Every explicit métier analysis now passes through `services/correctness_gates.py`
before `modules/business_pipeline_registry.save_result` can mark an attempt as
succeeded. The gates are shared by LegalTech, CMF and future sources.

The preflight checks source identity, document scope, event classification and
event-specific required facts. A composite CMF bulletin therefore returns
`SEGMENTATION_REQUIRED` until a child publication context is supplied. A
portfolio analysis requires an authoritative referential match, and Commerce
requires a confirmed commercial relationship. CMF eligibility remains
Conformité-only in the existing pipeline configuration.

The post-model checks evidence boundaries, deterministic numerical validation,
the reliability policy and the existing structured output schema/claim checks.
Normal output remains a human-review draft and is tagged
`SUCCESS_REVIEW_REQUIRED`; scores below 60 are retained only as failed attempts
with `INSUFFICIENT_EVIDENCE`. Failed attempts are recorded in the workflow
history with their outcome and explanation, while no business result row is
created.

`services/document_scope.py` wraps the existing page/reference segmenter to
produce parent-linked child contexts without duplicating central notifications
or modifying source registries.

The regression matrix in `tests/golden_events.py` covers the requested event,
language, ambiguity, composite-document, routing and multi-service cases using
isolated fixtures only.
