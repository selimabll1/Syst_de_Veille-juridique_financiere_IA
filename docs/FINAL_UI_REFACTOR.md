# Final UI integration — Phase 2

The active entry point now uses **app.py → final UI → adapter → backend**. No historical UI is imported by the final UI, adapter, or their statically reachable backend/subprocess dependencies. Historical source remains in place.

## 1. Changed existing files

Changes are measured against the code-only checkpoint, including the pre-existing untracked source, rather than against Git HEAD.

| File | Change |
|---|---|
| `app.py` | Calls `ui.app_ui.render`; preserves the existing page configuration. |
| `modules/service_registry.py` | Imports the canonical four-service `SERVICES` model. No database path or schema change. |
| `AGENTS.md` | Documents the active architecture, preservation contracts and safe test commands. |

All other existing source files in the checkpoint are byte-for-byte unchanged. Existing user modifications were preserved. Nothing was committed, reset, deleted, moved, renamed or archived.

## 2. Created application and test files

| Files | Responsibility |
|---|---|
| `modules/service_model.py` | Canonical investment, compliance, portfolio and commercial identifiers, aliases and labels. |
| `services/__init__.py`, `services/normalization.py` | Service package and pure helpers extracted from V1/V27/V33.2. |
| `services/ui_adapter.py` | Read-only batched workspace queries, identities, workflow/read/review state, service routes, priority, source links, cached normalization and explicit action gateway. |
| `services/operations.py` | Extracted synchronization, remote check, PDF collection, AI/scoring/result persistence, Excel, assignment, notes, watchlists, rules and digest orchestration. |
| `ui/__init__.py`, `ui/app_ui.py`, `ui/navigation.py` | Final orchestration and one session-state navigation/selection contract. |
| `ui/theme.py` | The sole injected stylesheet, with no `!important` layering. |
| `.streamlit/config.toml` | Native Streamlit dark palette; not another CSS injector. |
| `ui/components/__init__.py`, `shell.py`, `icons.py` | Sidebar, topbar, remote bell, five KPI cards and local vector icons. |
| `ui/components/presentation.py` | Detail presentation extracted from V33.8 and adapted to the service layer. |
| `ui/components/documents.py` | Existing local PDF preview/download and actual collected source URLs. |
| `ui/pages/__init__.py`, `workspace.py` | Shared filtered master/detail view for notifications and all four services; dark advanced dialog, selection, pagination and review actions. |
| `ui/pages/secondary.py` | Home, sources/documents, AI, results, validation, history, diffusion, reference and settings pages. |
| `tests/test_final_adapter.py` | Eight isolated data/identity/cache/routing/document/bell checks. |
| `tests/test_final_ui.py` | Six Streamlit navigation, pagination, dialog, filter and import-boundary checks. |
| `tests/test_final_operations.py` | Seven mocked/temporary-registry action-contract checks. |
| `docs/FINAL_UI_REFACTOR.md` | This handoff report. |

Audit, profiling and verification scripts/results are stored outside application source in the task's visualization directory.

## 3. Historical UI removed from this active runtime

- `modules/ugfs_ui_master_v33_8.py`
- `modules/ugfs_ui_master_v33_2.py`
- `modules/ugfs_desktop_ui_v27_workflow.py`
- `modules/ugfs_desktop_ui_v1.py`
- `modules/notifications_dashboard_section_v3.py`
- `modules/cmf_compliance_ui_v1.py`

Their files were not edited. Standalone launchers and historical recovery scripts may still reference them. Main-app inactivity does not certify that an individual file can be removed independently.

## 4. Active dependency tree and preserved contracts

```text
app.py
└── ui.app_ui
    ├── ui.theme + ui.navigation
    ├── ui.components (shell, icons, presentation, documents)
    ├── ui.pages (workspace, secondary)
    └── services.ui_adapter
        ├── services.normalization
        ├── modules.service_model
        ├── modules.alert_identity
        ├── modules.legaltech_detail_parser
        ├── modules.alert_pdf_linker (pure matching helpers)
        ├── modules.watch_rules (pure rule matching)
        ├── modules.legaltech_remote_watcher (unchanged comparison)
        ├── existing SQLite registries, read-only
        └── services.operations (explicit actions only)
            ├── alert_workflow + analysis_results_registry
            ├── service_registry + watch_rules
            ├── llm_analyzer → scoring_engine → excel_manager
            ├── cmf_collector_v1 → cmf_registry_v1
            ├── email_digest_service
            └── existing subprocess entry points
                ├── scripts.check_legaltech_remote_v29
                ├── scripts.sync_legaltech_notifications_v5
                └── scripts.download_pdfs_v5_network_capture_v3
```

`phase2_final_verification.json` contains the expanded static internal import map, including conditional imports and the subprocess entry points. The runtime launch check separately confirms no historical UI modules were loaded.

**Remote bell.** `modules/legaltech_remote_watcher.py` is byte-for-byte unchanged. The adapter uses its `_pending_comparison` semantics over the existing remote registry and local notification identities. Missing cards produce `NEW_NOTIFICATION`; increased remote result counts produce `NEW_RESULTS`. The badge counts pending cards, not local unread items or the sum of result deltas. Rendering never performs a remote check or writes a reconciliation result. Manual check and synchronization retain their existing scripts and arguments.

**Identity and routing.** Canonical service assignment uses a stable UID string. All four services, including investment, round-trip through the existing registry in an isolated test. Explicit canonical routes override legacy/inferred routes, including deactivated routes. No schema migration is needed to recognize the fourth service.

**Repeated captures.** The read-only adapter groups captures sharing the backend's stable alert identity. It retains all source variants and legacy workflow keys in memory, merges real document links and preserves read/history state. The observed data contained 198 LegalTech captures representing 130 stable LegalTech alerts plus 50 CMF publications: 180 display rows. No database row was removed. Similar-looking titles with distinct backend identities remain distinct.

**Read state and navigation.** `ugfs_page` and `ugfs_selected_uid` are the state owners. Internal navigation uses callbacks, not `?page=` links. The initial displayed row is not marked read. An explicit row click selects it on the same page and marks it read. Read/unread actions are also available explicitly. Pagination uses callbacks and displays 20 rows inside a scrollable list.

**UI.** The reference's navy sidebar, search/synchronization topbar, five KPI cards, compact master/detail structure, service filters and blue tab indicator are now owned by one UI package. The detail panel sticks where screen space permits; narrower layouts stack it. The advanced dialog provides dates, keywords/tags, service assignment, AI state, source/PDF availability and language filtering. Actual collected text and missing-data labels replace illustrative content.

**Documents.** Source recovery examines nested metadata, linked records, legacy document registries and PDF activity paths. Existing PDF files can be previewed/downloaded. External links are limited to actual collected HTTP(S) URLs. No URL is fabricated from an article ID. Sources/Documents combines the library with LegalTech/PDF/CMF supervision and CMF sync history.

**Business actions.** Stored LegalTech text follows the existing analysis → scoring → Excel-row conversion → results/workflow persistence sequence. Saved results, correction/validation status, Excel export, notes, service assignments, watchlists, rules, digest configuration/preview/queue/send remain available through the adapter. Reopening a result does not invoke inference. Export status is recorded only after a successful export and uses the saved result identity.

**CMF.** The existing registry, real records, read flags, synchronization history and first-live baseline behavior are preserved. CMF remains Conformité-only. Neither demo seeding nor demo purging runs during startup. Existing PDF/OCR/Tesseract, fact/pipeline validation, scoring, collectors, configuration and export modules remain intact; no historical backend was deleted.

## 5. Verification performed

- Compiled the final application, UI/service packages and changed backend source successfully.
- **21 new tests passed**: eight adapter tests, six Streamlit tests, seven action tests.
- All **14 sidebar destinations** rendered against existing data through read-only snapshots, with persistent action commands blocked. No duplicate keys or application exceptions remained.
- The V29 backend subset passed: parsing, stable identities, notification identity, temporary workflow migration, rule deduplication, PDF linking and collector static checks.
- CMF parser, compliance routing, natural-publication deduplication, first-live baseline and subsequent-new-item behavior passed using an explicitly supplied temporary database path.
- A local Streamlit server launched successfully on `127.0.0.1:8503`. The dashboard and advanced modal were inspected in the browser at the reference size and the modal bounds were checked at a narrower width.
- Warm page renders measured roughly **0.1–0.8 seconds** in the read-only launch check. A separate adapter measurement recorded **5.55 seconds cold**, **0.035 seconds cached**, and **2.00 seconds after workspace invalidation with parsed text reused**. These are local measurements, not a latency guarantee; browser rendering, first imports and actual integration work add time.
- Static and runtime checks found **no historical UI dependency** in the new app. Service files import no Streamlit. Only `ui/theme.py` injects CSS.
- The original code checkpoint has **no missing files**. Every retained historical UI source and the remote watcher matched the checkpoint hash.
- **170 protected data/config/assets/secrets/model files matched their original hashes.** Production database paths were not changed. No real synchronization, email, inference, export, demo seeding or data migration was performed for testing.

The full historical `tests/test_v29_offline.py` command still fails its V27 source assertion because the retained V27 file contains the pre-existing duplicate literal `v33_global_search` keys. This is documented, not hidden by changing that historical file. Its backend checks pass separately. `scripts/test_cmf_v1.py` is also obsolete: it references removed parser APIs and assigns `DB_PATH`, which does not redirect the current registry's `DEFAULT_DB` function defaults. It was not executed against production; the relevant checks were adapted externally with explicit temporary paths.

## 6. Remaining limitations

- The reference is a design image; this is a working Streamlit implementation using the real data, not an exact bitmap reproduction.
- First-time loading and an explicit workflow refresh still cost more than cached navigation. Live collection, OCR, model inference and email duration remain governed by the retained backend integrations.
- Live LegalTech/CMF authentication, collection/downloads, Ollama output and SMTP delivery were intentionally not exercised. Their extracted call contracts were tested with mocks or isolated storage.
- CMF AI analysis and individual assignee persistence were not implemented in the original integration and remain visibly unavailable. CMF is still routed to Conformité.
- Missing source metadata, company portfolio/sector details, summaries or PDFs remain marked unavailable. They are not synthesized from the reference image.
- The language filter detects Arabic script in available text; it is not a language-classification model.
- Browser support for embedded PDF data varies; the download option remains available.
- Other standalone historical apps and installation scripts remain present. Running an old installer can restore the old runtime. The obsolete test issues above should be addressed separately from historical-file archiving.

## 7. Archive candidates — separate approval required

No archive operation was performed.

The V33.8/V33.2/V27 UI chain is now a candidate for **coordinated code-only archival after acceptance**, together with its old launchers/installers and reverse references. V1, the old notification dashboard and CMF UI must not be removed individually while retained standalone apps still depend on them.

Previously identified candidates remain: V33.3–V33.7 UI modules; UI `.bak*`/`.backup*` snapshots; `ugfs_desktop_ui_v22_backup.py`, `ugfs_desktop_ui_v24_goal_backup.py`, and V27 `before_*` snapshots; root `app_backup_before_*`/`app.py.bak_before_*` files; and the `install_v33_*.py` recovery scripts. Use an explicit file manifest, never a broad move of a mixed data/backup directory.

Keep standalone manual-PDF/feedback tools and `cmf_compliance_prototype.py` until their separate roles are retired explicitly. Canonical backend modules, runtime scripts, databases, PDFs, browser profiles, secrets, reference data and backups remain protected. Historical backend variants require a separate capability/reference comparison before archival.

## Rollback checkpoint

The pre-change code-only checkpoint is:

`backups/code_only_ui_refactor_20260911_224020/`

Its `manifest.json` preserves the exact original source hashes and Git status, including untracked active files; `source/` contains the recoverable source. Do not use `git reset --hard` to return to HEAD: that would discard pre-existing user work.

If rollback is approved later, first preserve any subsequent edits, then restore only the checkpoint versions of `app.py` and `modules/service_registry.py` (and the guidance if desired). New UI/service files can remain inactive on disk. Restore no databases or collected data. Relaunching the historical entry restores its historical startup behavior, so do not use a rollback launch as an unreviewed production-data test.
