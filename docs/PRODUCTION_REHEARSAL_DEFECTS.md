# Production rehearsal defect register

Checkpoint: `backups/PRODUCTION_REHEARSAL_BEFORE_20260927_142403`.
No cleanup is permitted before the product regression and FINAL_PRODUCT_FREEZE.

| ID | Page | Scenario | Severity | Problem / root cause | Expected behavior | Fix | Test | Status |
|---|---|---|---|---|---|---|---|---|
| R01 | Sources | B | HIGH | CMF synchronization calls register_workspace, which can persist routing for unrelated historical LegalTech notifications. | Register and route only newly ingested CMF records; retain human overrides and historical routing. | Scope new CMF rows only | Isolated synchronization scope test passed | Fixed; live CMF rerun pending |
| R02 | Analyses IA | I | HIGH | ai_status checks an existing successful result before the latest failed attempt, hiding a failed reanalysis. | Keep the old successful result in Results, but expose the failed attempt and retry in AI operations. | Prioritize latest failed attempt in AI state | Regression passed | Fixed |
| R03 | Centre d’actions | J/K | HIGH | Voir le résultat sets only notification selection; an earlier result_selected can keep a different result open. | Open the completed task's specific métier result. | Navigate with notification + service + need identity | Regression and live completed Investment task passed | Fixed |
| R04 | Excel | M | MEDIUM | Export exposes raw field names and giant JSON financial/reliability structures; child page provenance is absent from the evidence sheet. | French business labels, readable financial facts/calculations, separate technical trace, page provenance. | French business sheets and bounded technical appendix | Live copied-result download and workbook inspection passed | Fixed |

Scenario coverage and final verification will be recorded in the handoff report. No finding is marked fixed until its verification passes.

## Additional findings (28 September 2026)

| ID | Page / scenario | Severity | Root cause and expected behavior | Fix / verification | Status |
|---|---|---|---|---|---|
| R05 | Notifications / B | HIGH | Elasticsearch wrapper and nested source emitted twice; one source article must have one central display identity. | Stop duplicate emission; conservative read-only aliases preserve protected records. Regression passed; 240 historical capture aliases on initial snapshot. | Fixed |
| R06 | Detail / B | MEDIUM | Unassigned did not distinguish evaluated routing from a display suggestion. | Explicit routing provenance; no query-time writes. | Fixed, final visual check pending |
| R07 | Results / C,F | MEDIUM | Historical or limited results could appear equivalent to current checked output. | Historical-gate and limited-reliability warnings; no saved-result rewrite. | Fixed, final visual check pending |
| R08 | Diffusion / N | MEDIUM | Raw JSON preview and child publications omitted. | Readable business preview, validated children eligible, no email transport added. Regression passed. | Fixed, final visual check pending |
| R09 | Administration / P | MEDIUM | Pending counts included historical whole-bulletin results excluded from Results. | Shared successful-results filter excludes composite parents and failed outcomes. Regression passed. | Fixed, final visual check pending |
| R10 | Synchronization / B | HIGH | Seven-minute cutoff interrupted real pagination; failure skipped routing for saved new records. | Bounded thirty-minute full-sync deadline; process only new saved records even on failure; preserve failure status. Isolated regression passed. | Live retry running |
| R11 | Remote bell / B | HIGH | Locally announced counts masked missing articles after incomplete collection. | Shared comparison against unique persisted article counts; read-only UI recomputation, latest remote snapshot only. Regression passed; copied live data correctly exposes one missing result. | Live retry running |

Latest full active regression: 159 tests passed (28 September 2026). This is not a product freeze: live scenario completion, classification policy follow-up, fresh-process visual checks and final preservation checks remain outstanding. No repository cleanup has started.

Latest additional user request: eliminate unclassified priority and give every notification at least one service. The conservative fallback is now provisional Conformité triage; preserve CMF-only compliance and authoritative Portfolio evidence, and do not reinterpret provisional triage as confirmed relevance.

## Semantic correction (28 September 2026)

The RNE HEXABYTE notice (`2026147091`) is now classified as `FINANCIAL_STATEMENTS_FILING`. The classifier requires performance evidence before using `FINANCIAL_RESULTS`; accounting year, capital, filing type, auditor and registration dates remain metadata. Structured RNE fields now take precedence over free-text guesses, with canonical name, Arabic name, responsible person, role and activity start date kept in separate fields. The investment output states that financial content is unavailable, impact and performance are undetermined, and instructs the analyst to retrieve the filed accounts before reviewing profitability, leverage, liquidity or cash generation.

For service coverage, every LegalTech notification receives an explicit provisional Conformité triage assignment when no rule establishes a supported métier. The UI labels this `Triage Conformité · pertinence à confirmer`; it does not imply legal applicability, portfolio ownership or a confirmed business opportunity. CMF remains Conformité-only and Portfolio still requires authoritative UGFS evidence. Unknown priority values now display `Moyenne` with provisional provenance. Production read-only projection audit: 369 rows, 0 unassigned, 0 `Non classée`, 173 provisional triage rows. Full active regression: 157 tests passed.

R12 HIGH — Real LegalTech pagination called a missing _fingerprint_notifications method after the last result card. Added a card-text fingerprint and verified changed-page/end-of-list behavior in an isolated regression. Live complete collector verification remains pending.

Live retry: copied workspace 659 to 766 central records; collector returned failure after pagination AttributeError and HTTP 500 source responses. New records were routed despite the failure; corrected remote bell retained one missing result. No successful full synchronization is claimed.

Live CMF: public site requests succeeded outside sandbox, but configured=false relevance policy intentionally prevented new ingestion. Application returned a clear configuration explanation. No arbitrary CMF relevance policy was enabled.

Live CMF output review: PUBLIC_WARNING identified CMF authority and avoided unsupported UGFS exposure/deadlines; ESG publication from bulletin 7686 showed independent pages 3-8, no-new-obligation statement and applicability to UGFS to confirm. Visible evidence remained within pages 3-8.

Classification follow-up: financial-results, share-cancellation and insolvency events added to the existing Investment routing rule; isolated configuration/eligibility regression passed. No production bulk routing rewrite.

Final check for this continuation: 161 active tests passed; 494 protected production files unchanged; all 13 production SQLite integrity checks OK. Fresh isolated server on port 8516 opens Accueil and shows 766 central notifications, 723 unread and remote bell 1. Port 8515 had retained stale process behavior; use 8516 for subsequent rehearsal checks. Classification fallback choices remain pending. No FINAL_PRODUCT_FREEZE or cleanup checkpoint created.


28 September cleanup handoff: user requested product freeze and portability-only work. See CLEANUP_VERIFICATION.md. The changed HEXABYTE records discovered earlier were legitimate real analysis/export activity, not test writes; no rollback of those records was performed. The financial filing replay succeeded in a copied registry.
