# Phase 5 — Administration

Implemented 20 September 2026. Architecture remains `app.py → ui.app_ui → services.ui_adapter → backend`. Other pages retain their approved design. Administration uses the existing shell and the single CSS owner, `ui/theme.py`.

## Verification matrix

| Administration page | Feature | Backend source | Real/empty/configurable | Tested | Remaining limitation |
|---|---|---|---|---|---|
| Référentiel — overview | Six domain counts, provenance, confirmed matches | Configured reference files + administration registry | Real; production empty | Browser and isolated AppTest | Authoritative UGFS records must be supplied |
| Participations / Pipeline DD / Fonds / Dirigeants / Actionnaires / GICS L4 | Search, status filters, domain metadata | Reference import records, existing reference layer | Empty; import-ready | All tabs, schema tests | DD, funds and watchlists do not establish ownership |
| Imports | CSV/XLSX/JSON preview, validation, duplicates, explicit confirmation, original file and audit history | `reference_import` + `admin_registry` | Configurable | CSV upload/confirmation through real browser; SQLite persistence checked; JSON/XLSX and rejection tests isolated | No production import performed; ambiguous duplicates require source correction, no silent merge |
| Organisation — overview | Real source/rule/service/prompt counts and history | Pipeline config, workspace registries | Real | Browser, AppTest | Missing timestamps display unavailable |
| Sources | Activation and eligibility | `pipeline_config` | LegalTech: four services; CMF: Conformité only | Browser read checks; isolated save/validation tests | Existing future sources have no fabricated collectors |
| Sources — CMF | Discovery, deterministic relevance, then full document/OCR collection | `cmf_relevance`, existing CMF collector/registry | Configurable; production criteria not configured | Offline gating tests: excluded records never fetch documents or invoke AI; failed extraction never promotes | No live CMF collection during this phase. Configure positive relevance criteria before new discoveries can become notifications |
| Règles de veille | Create/edit/duplicate/toggle; source/event/entity/reference/sector/GICS criteria | Pipeline config + administration history | Real and configurable | Real browser rule edit on isolated config; CRUD/history/stale-write tests | Existing collector rules retained read-only |
| Services & routage | Four services, assignments/results/backlog, routing reasons and policy | Central workspace + pipeline config | Real | Browser, routing/ownership regressions | No portfolio auto-routing without confirmed ownership; manual correction remains available |
| Prompts IA | Actual model, schema, version edit/history/activation | Existing local engine config + version snapshots | Real and configurable | Browser: v2 → v3 → earlier content as v4; persisted audit verified in isolation | No historical analysis rerun; changing environment model requires controlled restart |
| Utilisateurs | Honest unavailable state; four role definitions | No account backend | Non configuré | Browser/AppTest | Authentication and account management not implemented; roles are not accounts |
| Paramètres généraux | Actual model/timeouts, source sync history, Excel/diffusion state, read-only database accessibility | Runtime config and read-only registries | Real | Browser/AppTest | Environment settings are read-only; database accessibility is not a full integrity scan on every render |

## Data and configuration preservation

Checkpoint: `backups/phase5_20260920_013953`, created before Phase 5 application changes: 228 code/configuration snapshots and 13 consistent SQLite backups, plus protected file hashes in `manifest.json`.

Read-only comparison after implementation found:

- 13 production databases checked; no original row missing or modified; all quick checks passed.
- No protected file missing or changed, including original collected files.
- No historical UI file changed during Phase 5.
- Production `config/business_pipeline.json` unchanged.
- No production administration database created by navigation or preview.
- No email, production import, model analysis, or live synchronization executed in this phase.

The new administration registry is created lazily by explicit write commands. Imports are append-only, record original bytes and provenance, and refuse duplicate or invalid batches. Configuration saves use optimistic concurrency, preserve snapshots, and add audit events. Actors are honestly labelled as local unauthenticated users.

The CMF collection path now applies the configured relevance gate before full collection. Existing publications remain intact. Because production configuration was deliberately not edited, CMF relevance currently displays **À configurer**. This is an operational prerequisite for future notification promotion, not an indication that the historical CMF records were removed.

## Files

Created:

- `modules/admin_registry.py`
- `services/reference_import.py`
- `services/administration.py`
- `services/cmf_relevance.py`
- `ui/pages/administration.py`
- `tests/test_phase5_administration.py`
- `docs/PHASE5_ADMINISTRATION.md`

Modified relative to the Phase 5 checkpoint:

- `services/pipeline_config.py`: validation, concurrency, version/history persistence.
- `services/routing.py`: GICS/role criteria, provenance, ownership guard for inactive/zero holdings.
- `services/ui_adapter.py`: administration read models, imported references, explicit commands, read-only maintenance status.
- `services/operations.py`: explicit administration commands and CMF relevance stage.
- `ui/app_ui.py`: administration-specific KPI ownership.
- `ui/pages/secondary.py`: delegate administration to its active page module.
- `ui/theme.py`: scoped administration layout and responsive cards.
- `tests/test_final_operations.py`: isolate administration persistence during integration tests.

Existing header-only templates were preserved. No production configuration file was modified. Test configuration, fixture uploads and administration SQLite writes live only under the separate Codex visualization output directory (`phase5_isolated`).

## Tests and evidence

Full isolated suite: **59 tests passed**:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_phase5_administration tests.test_final_ui tests.test_final_operations tests.test_final_adapter tests.test_phase3_pipeline tests.test_phase4_grounding tests.test_pdf_preview -q
```

After the final immediate-feedback and maintenance refinements, the **14 Phase 5 tests passed again**. Changed Python modules also passed syntax compilation. The administration navigation test passed once more after removing a redundant widget default on restored tab state.

Real browser checks covered the eight reference tabs and seven configuration tabs; production empty template preview refused import. A separate running app with isolated persistence completed an actual file chooser upload, preview, confirmation, reference insertion, rule editing, prompt revision and earlier-content activation. Its recorded events were `referential_import`, `rule_edit`, `prompt_version_change`, and `prompt_activation`. Network document/CMF checks used mocks, not live production collection.

Only the selected administration tab is rendered. Read-only page visits do not initialize registries, run collectors or inference. No duplicate widget keys or historical UI imports were found by the regression checks. Navigation was exercised through reruns; no production latency SLA is claimed.

## Rollback checkpoints

1. Stop the app before replacing code. Review the Phase 5 manifest and current diff; preserve any work performed after this phase.
2. Restore only the eight modified application/test files listed above from the checkpoint's code snapshots, after confirming their exact paths in the manifest. The seven new files can remain unused until an explicit archival decision.
3. Restart and run the prior Phase 3/4 regression suite.
4. Do not restore/reset production databases as a routine code rollback. Their consistent backups are recovery material only; later imports and configuration revisions must be preserved and handled separately.
5. No production configuration rollback is required for this phase. Future explicit changes retain snapshots and audit history. Never replace human-reviewed business results to roll back a prompt.
