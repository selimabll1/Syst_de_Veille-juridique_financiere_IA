# Repository guidelines

## Purpose and active architecture

UGFS LegalTech is a Python/Streamlit application for monitoring legal announcements, extracting PDF text with OCR, analyzing it through local Ollama models, scoring risk/opportunity, and reviewing results through Excel and human feedback. Analysis remains preliminary and subject to human validation. Keep user-facing text in French and preserve French/Arabic text handling.

- `app.py` is the main entry point. It calls `ui.app_ui.render`: final UI → `services.ui_adapter` → backend registries/services. See `docs/FINAL_UI_REFACTOR.md` for preservation contracts and rollback.
- `ui/theme.py` is the single injected CSS owner; `.streamlit/config.toml` provides native dark widget colors. Final UI/service code must not import historical UI modules. The historical V33.8 → V33.2/V27 → V1 chain is retained on disk for recovery and standalone references.
- Workspace queries are read-only and must not initialize, migrate, seed, reconcile or alter production databases. Only explicit user actions enter `services.operations`. Keep the remote bell's NEW_NOTIFICATION/NEW_RESULTS contract separate from local unread counts.
- `modules/` contains collectors, registries, workflow state, PDF/OCR processing, LLM analysis, scoring, Excel handling, and UI code.
- `config.py` loads environment settings and defines paths relative to the project. Importing it creates data directories. Its default Ollama model is `qwen3:1.7b`; the starter README suggests `qwen3:8b`. Respect the configured environment rather than assuming they match.
- `scripts/` contains operational commands and targeted checks; `tests/` contains scoring and V29 offline checks.
- `cmf_compliance_prototype.py` is a separate Streamlit entry point. CMF publications belong to Conformité only; preserve the separate CMF SQLite registry and consult `README_CMF_V1.md` for its documented scope.
- `docs/`, `README.md`, and `QUICK_START.md` provide background. Some describe earlier versions; verify behavior against active code.

## Working conventions

- Start by checking Git status. Preserve existing modified and untracked files; this workspace contains substantial ongoing work.
- Make focused changes to active modules. Do not rewrite the application, replace the active entry point with an older version, or run `install_v33_*.py` merely to make a code change.
- Treat `backups/`, `backup_before_*/`, `diagnostic_v29/`, `app_backup*`, and `.bak*` files as historical material unless the task explicitly concerns them. Exclude these, `.venv/`, and generated data from routine searches.
- Follow surrounding Python style: four-space indentation, snake_case functions, and existing type hints. Reuse service and registry helpers rather than duplicating persistence logic in the UI.
- Preserve Streamlit widget-key uniqueness, navigation/session state, stable alert identities, deduplication, and persisted read/workflow status.
- Use `pathlib` and existing configuration paths instead of hard-coded user-specific paths. In PowerShell, set the project directory explicitly with terminating errors before relative commands so a failed directory change cannot run a search elsewhere.

## Setup and execution

Run from the repository root. Prefer the existing virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

If no environment exists, create it with `python -m venv .venv`. Copy `.env.example` to `.env` only when `.env` does not already exist. OCR and inference require external Tesseract/Ollama installations and an appropriate local model; inspect configuration before changing these dependencies.

## Validation

Phase 3 adds `services/lifecycle.py`, `services/business_analysis.py`, `services/jobs.py`, `services/routing.py`, `config/business_pipeline.json` and the additive `modules/business_pipeline_registry.py`. Use one common local Ollama transport with service-specific prompts; CMF remains Conformité-only. A notification is treated only when every assigned business result exists and is human validated; reading and priority are independent. Never promote test reviews into production. See `docs/PHASE3_ACTION_PIPELINES.md` for live verification limits and data checkpoints.

Run the isolated Phase 3 regression suite with `.\.venv\Scripts\python.exe -m unittest tests.test_final_adapter tests.test_final_ui tests.test_final_operations tests.test_phase3_pipeline tests.test_pdf_preview -q`. The PDF preview renders actual pages read-only through the adapter; it must not overwrite source PDFs. Streamlit 1.58 or newer is required for the active UI APIs.

Choose checks for the affected subsystem and inspect scripts before executing them: some use live services or local databases. Do not assume all `test_*.py` files form a single pytest suite.

- Syntax-check changed Python files with `.\.venv\Scripts\python.exe -m py_compile <changed-files>`.
- Run the V29 offline harness with the project root on the import path:

  ```powershell
  $env:PYTHONPATH = (Get-Location).Path
  .\.venv\Scripts\python.exe tests/test_v29_offline.py
  ```

  This harness creates temporary databases and has its own `main()`; some functions take explicit paths rather than pytest fixtures.
- For scoring changes, run `.\.venv\Scripts\python.exe -m pytest tests/test_scoring.py` if pytest is available. Pytest is not declared in `requirements.txt`.
- For CMF parsing/registry changes, inspect and run `.\.venv\Scripts\python.exe archive/legacy/test_cmf_v1.py`.
- For UI changes, check the affected navigation, filters, actions, and state across Streamlit reruns. For pipeline changes, verify relevant extraction/scoring/export behavior with non-confidential fixtures.
- Final UI regression suite: `.\.venv\Scripts\python.exe -m unittest tests.test_final_adapter tests.test_final_ui tests.test_final_operations -v`. These use temporary storage/mocks. The full old V29 harness has a pre-existing assertion against duplicate keys in the retained V27 source. `archive/legacy/test_cmf_v1.py` uses obsolete APIs and does not redirect the current registry's default path safely; do not execute it against this workspace. Pass `database_path=` explicitly in CMF tests.
- Report checks actually performed and any dependency or service limitations. Documentation-only changes do not require starting the app or running integrations.

## Local data and secrets

- Treat `.env`, `secrets/`, session/cookie files, HAR captures, PDFs, OCR output, Excel exports, feedback, and SQLite databases as local potentially confidential material. Do not print credentials, commit them, or use production documents as test fixtures.
- `.gitignore` does not cover every generated file or database. Stage only intended source/documentation changes; inspect the diff before committing.
- Use temporary databases for tests. Preserve real records, stable identifiers, and human corrections when changing schemas; use explicit migrations rather than resetting databases.
- Live synchronization, PDF downloads, scheduled watchers, and email operations can have side effects. Do not trigger them as routine initialization or validation. Never send messages or email without explicit user authorization.
