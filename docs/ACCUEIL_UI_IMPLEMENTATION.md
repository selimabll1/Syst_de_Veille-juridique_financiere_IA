# Accueil — approved executive dashboard implementation

Implemented 21 September 2026 against the attached reference. This is a UI-only phase. The final architecture remains `app.py → ui.app_ui → services.ui_adapter → backend`; no historical UI module was reintroduced.

## What is now on Accueil

The page uses the approved sidebar/topbar and a scoped dashboard body: large Vue d’ensemble hero with understated CSS/SVG globe motif; five equal KPI cards; balanced 65/35 activity and attention columns; four clickable service cards; compact recent feed; recorded source health; and an authoritative referential empty state. The palette, borders, radius and density stay within the existing UGFS theme. At narrower laptop width the two-column composition remains readable and stacks only at the existing responsive breakpoint.

No reference-image values were copied. The dashboard reads the workspace projection only and does not run AI, PDF/OCR, collectors, reconciliation or expensive per-row canonical extraction.

## Backend source map

| Component | Backend source | UI state | Action checked | Limitation |
|---|---|---|---|---|
| KPI row | `ui.components.shell.kpis(workspace)` from cached adapter rows/results/assignments | 312 notifications; 269 unread; 6 recorded analyses; 1 high/critical item; 0 pending actions | Loaded on real app | No trend percentages because no defined historical comparison was available |
| Activity services | `workspace.rows[*].services`, `business_results`, `review_status` | Investment 75; Conformité 57; Portfolio 0; Commerce 130 | Each card opened its service page | Counts are assigned-notification counts and saved-result review counts |
| Recent feed | sorted `workspace.rows` by publication date | Five most recent real notifications | Row navigation opened the selected notification in Notifications | Feed is a compact five-row view |
| À examiner | saved business results with draft/pending/correction state | 2 real analyses requiring review | Shortcut opened Validation; item navigation preserves UID | Legacy/non-business results are included only when actually present |
| État des sources | `adapter.source_overview()` plus LegalTech/CMF run and watcher records | LegalTech/CMF recorded states and timestamps; future configured sources collapsed | “Toutes les sources” opened Organisation & Paramétrage → Sources | Status reports recorded collection state, not an unverified live health check |
| Référentiel UGFS | `workspace.referential_entities` | Empty authoritative referential state | Shortcut opened Référentiel UGFS | No holdings or company membership is inferred |
| AI task strip | `services.jobs`, explicit stages and action result | Running/completed/failed compact card; elapsed seconds; retry/view/dismiss | State fixtures tested; existing background action remains non-blocking | A live long Ollama run was not launched for this visual phase |

Export feedback is now a compact dismissible notice with a Télécharger control; filesystem paths are kept in expandable technical details.

## UI verification

- 105 tests passed: the existing Phase 6/6.1 suites plus 5 dashboard tests. Tests cover real counts, empty states, all service/validation/source/referential navigation shortcuts, task dismissal and path-safe operation notices.
- Real Streamlit app loaded at `http://127.0.0.1:8509/` with 312 production notifications. Desktop visual check used 1672×941; laptop check used 1100×800. No page exceptions or duplicate-key errors appeared.
- Measured Streamlit test-harness timings: cold app run 18.08 s; warm Notifications → Accueil navigation 0.17 s; dashboard projection 0.017 s. Cold time includes workspace initialization and is not a dashboard-render SLA.
- The real Accueil screenshot was captured after the final layout pass. The normal app is left open at Accueil for visual approval.

## Files changed

- `ui/app_ui.py`
- `ui/navigation.py`
- `ui/theme.py`
- `ui/components/action_status.py`
- `ui/components/icons.py`
- `ui/pages/secondary.py`
- `tests/test_phase61_semantics.py`
- `ui/pages/home.py`
- `tests/test_home_dashboard.py`

Only UI files, the dashboard test and the operation/task presentation paths are part of this phase. Phase 6 intelligence, canonical facts, event profiles, reliability, routing, collectors, databases and business-result schemas were not edited in this phase. Existing unrelated worktree modifications remain preserved.

## Rollback

Checkpoint: `backups/accueil_20260921_170855` (246 source/config files and 13 consistent SQLite snapshots). Production preservation comparison reports zero missing/modified rows, unchanged protected hashes, unchanged configuration and no historical UI changes. Restore source selectively only after stopping the app; do not restore database snapshots over later legitimate activity.
