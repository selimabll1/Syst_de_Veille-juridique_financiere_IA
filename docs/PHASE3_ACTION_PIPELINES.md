# Phase 3 — implementation and verification

Verification completed through 14 September 2026. The architecture remains `app.py → ui.app_ui → services.ui_adapter → backend`. The approved UI has been retained. No historical UI imports were introduced into this chain, and no historical application files were deleted or archived.

This is a functional implementation with explicit remaining integration and analysis-quality limits. It is **not a blanket production certification**: the remote LegalTech session still requires user reconnection, and real model outputs demonstrated factual issues requiring human review.

## Implemented behavior

- List rows and detail distinguish **Priorité**, **Traitement**, **Lecture**. Priority is Critique/Haute/Moyenne/Basse/Non classée; reading is Lu/Non lu. Neither affects treatment eligibility.
- Canonical processing states are Nouveau, À analyser, Analyse terminée, À valider, Traité, Erreur d’analyse. For a notification assigned to multiple services, Traité requires a saved, human-validated result for **every assigned service**. A historical generic result is preserved but is not silently reused as four specialized results.
- A qualified central notification identity links source records, service assignments, independent business results, revisions, analysis attempts and history. Existing source registries remain in place; collection is not duplicated per service.
- Source eligibility, routing rules, referential paths and four business prompts are configured in `config/business_pipeline.json`, editable through Organisation & Paramétrage. CMF is constrained to Conformité in configuration validation and action validation. LegalTech is eligible for all four services. Unimplemented sources are inactive and shown as À configurer.
- Referential matching uses actual configured records/watchlists. The UGFS referential is an enrichment layer, not a collector. Rules run first; ambiguous routing can request a local AI proposal, with manual application/correction.
- AI uses the existing shared `modules.llm_analyzer` transport. Each assigned service supplies its own prompt/context/output fields. CMF extracts its actual official text/PDF and uses the Conformité configuration through this same engine.
- Background jobs expose progress/errors and refresh the workspace on completion. Resource locks prevent overlapping LegalTech browser operations or local model jobs. No fabricated success substitutes for failure.
- Human corrections preserve prior versions and record events. Revision checks reject stale validation. Excel includes a dedicated service result sheet. Diffusion accepts only validated results for the selected service; sending remains an explicit separate action.
- PDF pages are rendered locally from the real document through `modules.pdf_preview`. This replaces a blank embedded-browser PDF iframe; download remains available. Source PDFs are never overwritten.
- The topbar click obstruction was removed. Detail tabs have stable keys, and Excel/PDF downloads avoid unnecessary reruns. Diffuser carries the selected business service into its destination page.

## Action verification matrix

“Live copy” means browser interaction with the real UI and real persistence/export code using a consistent isolated copy of existing data. No model responses were mocked for the two production draft analyses. No production result was human-validated by these checks.

| Action | UI works | Backend works | Persistence works | Tested live/mocked | Remaining issue |
|---|---|---|---|---|---|
| Topbar Synchroniser | Yes, click reaches collector | Collector launches; authentication failure is reported | No successful fresh LT collection verified | Live failure path | Refreshed LegalTech login required |
| Vérifier LegalTech / remote bell | Bell opens and check is wired | Last-known missing/new-results count preserved on error | Error history and prior pending flag preserved | Live failure discovered; corrected guard regression-tested | Successful remote check must be repeated after login |
| LegalTech synchronization | Same real existing sync script | Dependencies installed; AUTH_REQUIRED reached | Existing local records retained | Live failure + orchestration tests | Login confirmation pending |
| CMF synchronization | Yes, progress/completion and refresh | 50 real publications fetched in successful rerun | Sync history saved; 30 existing bulletins gained PDF links | Live | Larger page limits not exhaustively checked |
| LegalTech AI from notification detail | Yes | Actual local qwen3:1.7b completed Commerce analysis | Draft, attempt and history saved | Live on collected French FERTIMED announcement | Factual quality requires review; no production validation |
| CMF Conformité AI | Yes | Official PDF extracted; shared local model completed | Conformité draft and history saved | Live | Initial timeout retained as failure; draft contains factual issues |
| Analyses IA page action | Common action gateway | Same shared backend | Same result registry | UI regression + shared backend live | Independent click path not exhaustively repeated for each service |
| PDF/source opening | Actual local document dialog, page controls and visible raster preview verified | Real PDF rendering and source bytes | Read-only | Live real FERTIMED PDF screenshot; two-page rendering regression | External LegalTech links depend on login; not every PDF tested |
| Excel export | Export and download controls exercised | Real eight-sheet workbook reopened successfully | Corrected result/model/service/review status saved in workbook and export event | Live copy | Original workbook scoring remains preliminary |
| Correction / validation | Fields saved; row advanced À valider → Traité | Real revisioned review backend | Correction, validated revision 3 and history confirmed | Live copy + stale-revision tests | No production human approval performed |
| Résultats / history | Saved drafts visible; KPI increased to 4 including 2 historical results | Real business result and event queries | Verified from SQLite and refreshed UI | Live / live copy | All historical result permutations not exhaustively exercised |
| Diffusion / actions | Validated CMF result selectable; preview and queue work | Real queue backend; SMTP absence explained | Conformité queued record and digest_queued event confirmed on copy | Live copy; no email sent | SMTP is not configured; actual sending untested |

## Service verification matrix

| Service | Sources | Routing | AI result | Validation | Status |
|---|---|---|---|---|---|
| Investissement | LegalTech; future sources only when configured | Configurable eligibility/rules and manual correction | Specialized schema/prompt exercised with mocked transport | Independent result isolation covered by temporary registry tests | Implemented; live investment analysis not performed |
| Conformité | LegalTech + CMF | CMF forced to Conformité; LegalTech rule/manual routing | Real CMF result from shared local model | Correction/validation/export/diffusion exercised on copy | Functional pipeline; draft quality needs human review |
| Suivi portefeuille | LegalTech; future configured sources | Actual referential/portfolio rule + manual correction | Specialized schema/prompt exercised with mocked transport | Independent result isolation covered by temporary registry tests | Implemented; live portfolio analysis not performed |
| Commerce | LegalTech; future configured sources | Existing assignments preserved; configurable rules | Real LegalTech Commerce draft persisted | Common validation implementation tested on copy | Functional analysis path; draft quality needs review |

## Concrete live evidence and limits

The first CMF live collection added seven source publications (180 → 187 central display rows). It exposed an older production sync-history schema (`found_count` rather than `item_count`); the action now supports that existing schema without a database reset/migration. The subsequent successful run recorded 50 fetched publications and 30 existing bulletin updates, retaining 187 rows. The completion wording now distinguishes additions, updates and unchanged publications rather than calling every changed item new.

The remote LegalTech bell means missing local notifications or remote cards with additional results (NEW_NOTIFICATION/NEW_RESULTS), never unread count. The last-known pending count was 1 while local unread count was 149. An expired-login redirect returned an empty remote page; the previous watcher incorrectly treated that as an empty successful check. The guard now rejects empty/partial collection before clearing flags. The single prior pending flag was recovered from the checkpoint and checked against unchanged detection metadata. The successful authenticated check remains outstanding; the user said they would reconnect but has not confirmed completion.

Real drafts exist for CMF Conformité and LegalTech Commerce using **qwen3:1.7b**, with no fake model name. Ollama reported CPU-only execution (`size_vram=0`). The CMF success took about 258 seconds after an earlier 240-second timeout. The configurable request timeout is now `OLLAMA_TIMEOUT_SECONDS` (default 600 seconds). Cached workspace loading measured approximately 0.13 seconds; a fresh uncached load measured approximately 18.6 seconds on this machine. These are individual measurements, not a performance SLA.

The CMF output incorrectly presented the publication date as a deadline and used an unrelated corporate-event classification in its generic scoring. The Commerce draft inferred growth/market strengthening beyond the collected capital-reduction text. Structured JSON validation proves shape, not truth. Both production results remain drafts. The isolated correction test changed the deadline field, preserved its predecessor, validated only the copy, exported the correction and queued it only in the copy. Further factual-grounding/evaluation work is needed before trusting these drafts or the generic scores operationally; no model was silently replaced.

The adapter exposes saved business results for active assigned notifications. Disconnected/orphaned specialized-result browsing and arbitrary multiple needs within one service are not fully implemented in the UI (the registry currently uses the primary need per service). Existing generic historical results remain preserved. No historical file should be archived based solely on this phase.

## Data protection and rollback

Pre-change checkpoint: `backups/phase3_20260912_191751`, containing source/config hashes and consistent copies of 13 SQLite databases. The independent final preservation check found **zero missing original rows**, **zero missing protected files**, **zero changed protected non-database files**, and **zero changed historical UI files** relative to this checkpoint. Row-presence checks are not an assertion that all fields remained unchanged: authorized collection, extracted source text, read interactions, draft analyses and their history were deliberately persisted.

The technical browser verification copy and export are outside the application data directory, under the task's `phase3_live_validation` artifact directory. An earlier test isolation fault inserted two temporary identities into the new business tables; those exact verified test records/events were removed and the tests now redirect the registry to temporary storage. No collected source records were deleted. No databases were reset, no source data was seeded, and no emails were sent.

Rollback checkpoints:

1. Stop only the affected preview/job process after checking there are no active actions.
2. Preserve current SQLite files, WAL state and exports with a new consistent backup before any rollback decision.
3. Compare the code checkpoint manifest with the intended Phase 3 files; restore only reviewed code/config changes. Preserve pre-existing user modifications and all historical modules.
4. Do **not** restore whole old databases over newer collected data. Keep additive business tables and versions; disabling the new UI must not destroy newly collected publications or draft results.
5. Restart the selected code version, verify read-only counts and remote-bell semantics, and run the relevant isolated regression suite. No migration/reset scripts are required for this rollback.

## Automated checks

The 31-test adapter/UI/operations/pipeline suite passed together. After the PDF preview change, the six UI tests plus the real two-page PDF rendering/source-preservation test also passed. This covers 32 distinct tests. Tests use temporary databases or explicitly mocked external transport; live checks are listed separately above.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_final_adapter tests.test_final_ui tests.test_final_operations tests.test_phase3_pipeline tests.test_pdf_preview -q
```

The final preview runs at `http://127.0.0.1:8504/`. The older tab/server on port 8503 may still display an earlier version. No attempt was made to stop an unrelated pre-existing process.
