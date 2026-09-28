# Final UI / workflow freeze

The final pass keeps the approved architecture and makes the product pages express one workflow:

Sources → Notifications → Analyses IA → Résultats → Validation → Diffusion → Historique.

The default session page is now Accueil. Navigation pages remain read-only unless the user explicitly launches an action. Results are indexed from persisted métier results, while Analyses IA is indexed from service assignments and their attempts. Portfolio stays empty until authoritative UGFS participation data exists.

## Production diagnosis

| Measure | Value |
|---|---:|
| Central notifications | 609 |
| Unique notification UIDs | 609 |
| Exact duplicate candidates | 0 |
| Same source/entity/title/date candidates | 240 groups / 480 rows; retained for review, not deleted |
| Routing persisted as assigned | 348 |
| Routing never evaluated in persisted event history | 261 |
| Investment assignments | 188 |
| Compliance assignments | 57 |
| Portfolio assignments | 0 |
| Commerce assignments | 130 |
| Persisted métier results | 5 |
| Results awaiting validation/correction | 3 |
| Validated results | 2 |
| Failed AI attempts | 0 |

The 261 routing records are reported only. They were not bulk reassigned. New LegalTech synchronization now records a routing evaluation for newly ingested rows, including an explicit evaluated/unassigned outcome.

## Verification

- 115 regression tests passed.
- Freeze-specific tests cover service-scoped treatment, independent AI status, result exclusion, multi-service results, validation filtering, history ordering, portfolio empty state, and duplicate task cards.
- Isolated-copy integration checks passed for FERTIMED Investissement, FERTIMED Commerce, and CMF Conformité: correction, validation, export and history persistence.
- Warm navigation timings: Notifications 0.384 s, Analyses IA 0.153 s, Résultats 0.226 s, Validation 0.177 s, Historique 0.147 s, Portfolio 0.132 s, Accueil 0.153 s, Administration 1.102 s, Référentiel 0.142 s.
- Production SQLite snapshots compared read-only: no changed databases.
- Real Streamlit UI inspected at the desktop presentation size and the portfolio empty state was verified. The app is left on Accueil at `http://127.0.0.1:8512/`.

## Files changed in this pass

- `ui/app_ui.py`, `ui/navigation.py`, `ui/theme.py`
- `ui/pages/workspace.py`, `ui/pages/secondary.py`, `ui/pages/business_workspace.py`, `ui/pages/activity.py`
- `ui/components/action_status.py`, `ui/components/presentation.py`
- `services/lifecycle.py`, `services/operations.py`, `services/ui_adapter.py`, `services/jobs.py`, `services/result_presentation.py`
- `tests/test_final_ui.py`, `tests/test_phase61_semantics.py`, `tests/test_product_freeze.py`
- `scripts/audit_product_freeze.py`, `scripts/measure_freeze_navigation.py`, `scripts/verify_freeze_copy.py`

No source database, PDF, collector, email, AI model, or result record was modified during production verification.
