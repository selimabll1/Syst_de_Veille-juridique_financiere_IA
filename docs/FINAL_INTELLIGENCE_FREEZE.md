# Final intelligence freeze — 27 September 2026

The shared Phase 6/6.1 pipeline now enriches canonical facts once before métier inference with financial context, normalized values, role-labelled entities, deterministic calculations and evidence-derived métier notes. The configured local model remains `qwen3:1.7b`. No model was downloaded, no email was sent, no collector was run, and no portfolio membership was fabricated.

## Delivered behavior

- Financial event vocabulary covers equity, transactions/control, debt/financing, performance, distress, governance and financial regulation. A bare vocabulary term remains a candidate; surrounding source context is required. Hypothetical/definition prefixes and negation prevent confirmation. A dividend line in financial statements does not establish a distribution event. Required company/authority/fact gates still apply downstream.
- `financial_context` groups source clauses without converting their presence into a confirmed event or impact. Every populated item has source evidence IDs.
- Financial amounts preserve original wording, normalized Decimal values, currency, units, periods and evidence. DT/TND/dinars, MDT, thousands/millions, Arabic digits and percentages are supported. Financial concepts and explicit roles are extracted conservatively; unlabeled or ambiguous values remain unassigned.
- Python checks capital balances and shares × nominal, computes issue premiums, compatible period changes, net margin, payout and debt/equity. Zero/nonpositive denominators and incompatible periods/currencies prevent the relevant ratio. No H1/full-year growth comparison is produced. No EBITDA reconstruction is attempted without explicit EBITDA.
- Materiality is quantified only with a supported reference, such as the relative capital change. It is separate from priority and makes no valuation/return claim. Missing reference context remains `NON_DETERMINEE` with a reason.
- Model output remains constrained to evidence/action identifiers. The common instruction now emphasizes evidence-constrained financial reasoning; supported finance inputs are included only when their evidence fits the existing bounded prompt. Professional recommendations and financial prose are deterministic, event-conditioned templates, not unrestricted model-generated claims.
- Investment results expose capital before/change/after, shares, nominal, mechanism, quantified change, vigilance and a specific review action. ESG guidance exposes scope, reporting, transition and explicit absence of a new obligation; the section is **Précisions / attentes documentées**. Warning results preserve unknown UGFS exposure and deadlines while recommending concrete compliance checks.
- Portfolio still requires an authoritative match. Commerce still requires supported commercial context. No new portfolio or commercial production analysis was run.
- Results show event, service, priority, reliability, compact key facts, action and event-aware details. Long regulatory text wraps instead of being forced into numeric metric cards. Human corrections suppress the old generated note overlay. Persisted summaries are not silently regenerated with a newer template.

## Three real local-model replays

These are real source records and real Ollama calls, not mocked results. The CMF warning PDF was fetched from the official CMF URL into the local verification checkpoint. The ESG analysis used only the confirmed child pages 3–8 of bulletin N°7686. FERTIMED used the already-collected French announcement `jrletemps-fr-2026-08-29-PT260477`.

| Case | Before | After |
|---|---|---|
| FERTIMED event | Older textual reduction classification with citations | `CAPITAL_REDUCTION` |
| Finance facts | Source quotations; no canonical financial metrics in that saved version | Before 3,840,000 TND; signed change −479,900 TND; after 3,360,100 TND; 47,990 shares; nominal 10 TND |
| Derived metrics | Not recorded | 3,840,000 − 479,900 = 3,360,100; 47,990 × 10 = 479,900; −12.4973958% capital change; verified by Python |
| Métier insight | Generic capital-structure caution | Repurchase and cancellation are explicit; quantified capital change; no inference about valuation, cash distribution or returns |
| Recommendation | Examine terms and motives | Reconcile resolutions, amounts and shares; verify mechanism, cash effects and shareholder rights before revising the investment thesis |
| Evidence count | 3 | 5 |
| Unsupported claims | Not measurable with the legacy claim contract | 0 rejected claims under the current validator; deterministic finance checks passed |
| Factual/global reliability | Not recorded | 96 / 94 |
| Runtime | Not recorded | 146.64 seconds analysis; 146.76 seconds total replay |

| Case | Before | After |
|---|---|---|
| CMF ESG event | `REGULATORY_GUIDANCE` | `REGULATORY_GUIDANCE` |
| Extracted facts | Generic guidance statement | CMF; ESG notes to financial statements; public-issuer scope; transition; financial year closed 31 December 2025; no new normative obligation |
| Derived financial metrics | None | None applicable; reporting date is not invented as a deadline |
| Métier insight | “Les incidences métier restent à confirmer…” | Specific reporting scope and transitional clarification; applicability to UGFS remains to be confirmed |
| Recommendation | Examine cited documents | Identify followed companies within the public-issuer scope and verify incorporation of the ESG clarifications into the relevant reporting |
| Evidence count | 10 | 21, all inside the same child pages 3–8 |
| Unsupported claims | 0 under existing validator | 0 under current validator; child boundary assertions passed |
| Factual/global reliability | 96 / 94 | 96 / 94 |
| Runtime | 50.68 seconds | 84.83 seconds analysis; 85.09 seconds total replay |

Actual new ESG synthesis:

> Le Conseil du Marché Financier (CMF) précise les informations ESG attendues dans les notes aux états financiers des sociétés faisant appel public à l’épargne. Le document précise que ces attentes ne créent pas de nouvelles obligations normatives. Il décrit une logique transitoire. L’exercice concerné est clos au 31 décembre 2025.

| Case | Before | After |
|---|---|---|
| CMF warning event | `PUBLIC_WARNING` | `PUBLIC_WARNING` |
| Extracted facts | CMF warning; no company/deadline required | Same conservative facts plus explicitly surfaced warning subject and documented vigilance precautions |
| Derived metrics | None | None applicable |
| Métier insight | General legal review | Warning-specific checks of cited practices, documented exposure and relevant authorizations; no invented UGFS exposure |
| Recommendation | Examine cited documents | Reconcile cited actors/practices with an actually documented exposure and have Conformité check relevant authorizations |
| Evidence count | 10 | 11 |
| Unsupported claims | 0 under existing validator | 0 under current validator; no fake company or deadline |
| Factual/global reliability | 95 / 93 | 95 / 93 |
| Runtime | 41.12 seconds | 66.54 seconds analysis; 66.61 seconds total replay |

The inference runs were slower than the earlier saved timings. This is a content-quality pass, not a demonstrated latency improvement. Timings come from separate runs and are not a controlled model benchmark. Reliability values are deterministic completeness/coherence indices, not calibrated probabilities of correctness. “0 unsupported claims” describes validator results and the inspected three-case outputs, not a guarantee of accuracy on unseen documents.

## Persistence and preservation

Three new draft versions were saved, without human approval: FERTIMED Investissement revision 4, ESG Conformité revision 2, warning Conformité revision 4. FERTIMED revision 3 remains archived with `review_status=validated`. New drafts do not inherit that validation. The previous ESG/warning revisions remain in version history.

No source notification was duplicated by the replay. CMF child identity and parent/page provenance remain intact. The shared PDF was not rewritten. A read-only logical SQLite comparison against the checkpoint found the following 12 registries unchanged: CMF compliance, LegalTech AI results, alert links, browser collection, notifications (original/v4/v5), registry, remote watch, watch rules, workflow, and PDF library. The business workflow registry changed only through the requested analysis attempts/results/history. No reset or migration was performed.

## Verification

- Full active regression suite: **147 tests passed** across final adapter/UI/operations, Phase 3/4/5/6/6.1, product freeze, correctness gates, golden events, composite workflow, home dashboard, financial enrichment and PDF preview.
- Executable financial golden evaluation: **14/14 events**, **13/13 expected numerical facts**, **33/33 cited IDs within the case evidence**. Expected calculations and specific recommendation constraints pass. Separate tests verify exact arithmetic results, currency/period incompatibility, zero denominators, conflicting values, roles, no invented EBITDA, hypothetical-event abstention, provenance failures and ESG no-new-obligation semantics.
- The fixture suite is synthetic and isolated. These metrics describe explicit regression constraints, not real-world accuracy rates or human-rated investment usefulness. Real evidence was used only in the three requested replay checks.
- Live Streamlit Results: opened the saved FERTIMED and ESG child results. Verified real amounts, child pages 3–8, specific ESG synthesis/action, separate reliability and unvalidated state. No validation, correction, export or diffusion was triggered during this visual check.
- The in-app preview is narrow; long-form content was checked with scrolling. A larger viewport override did not provide a usable desktop capture and was reset. Full-width presentation acceptance remains with the user.

Commands:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_final_adapter tests.test_final_ui tests.test_final_operations tests.test_phase3_pipeline tests.test_phase4_grounding tests.test_phase5_administration tests.test_phase61_semantics tests.test_phase6_intelligence tests.test_product_freeze tests.test_correctness_gates tests.test_golden_events tests.test_composite_workflow tests.test_home_dashboard tests.test_financial_intelligence tests.test_pdf_preview -q
.\.venv\Scripts\python.exe -X utf8 scripts/evaluate_financial_golden.py
```

## Changed source files in this pass

`services/financial_intelligence.py`, `services/financial_vocabulary.py` (new); `services/canonical_facts.py`, `services/event_taxonomy.py`, `services/event_profiles.py`, `services/intelligence.py`, `services/result_presentation.py`; `services/routing.py` (bounded classification cache increased from 512 to 2048 entries to cover the current 609-row workspace); `ui/pages/business_workspace.py`; `tests/test_financial_intelligence.py`; `scripts/verify_financial_freeze.py`; `scripts/evaluate_financial_golden.py`; this report.

No historical UI files, collectors, configured model, SMTP logic, reference data or source database schemas were changed.

## Rollback checkpoint

`backups/FINAL_INTELLIGENCE_FREEZE_20260927_025653/` contains the before-source copies, consistent SQLite backups, before-row snapshots, official verification PDF, replay JSON and final verification artifacts. These are local and potentially confidential; do not commit them.

The `source/` directory is the **before** checkpoint; `final_source/` captures this completed pass. Rollback is deliberate, not automatic: stop the app, compare the listed changed files with the checkpoint, restore only this pass's source changes, and restart. Do not replace current production databases wholesale: that would discard later user work. Use the existing result-version workflow for any approved result rollback and retain the newer attempts/history. No rollback or cleanup has been executed.

Stop here for visual and semantic approval. No email integration, Git cleanup, historical-file deletion or new product phase is started.
