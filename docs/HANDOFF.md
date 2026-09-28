# Passation développeur

| Domaine | Fichiers / point d'entrée |
|---|---|
| Lancement | `app.py`, `ui/app_ui.py` |
| UI et CSS | `ui/pages/`, `ui/components/`, `ui/theme.py`, `.streamlit/config.toml` |
| Requêtes UI | `services/ui_adapter.py` (lecture seule) |
| Actions | `services/operations.py`, `services/jobs.py` |
| Routage / configuration | `services/routing.py`, `services/pipeline_config.py`, `config/business_pipeline.json` |
| IA commune | `services/business_analysis.py`, `services/intelligence.py`, `modules/llm_analyzer.py` |
| Faits / contrôles | `services/canonical_facts.py`, `services/event_profiles.py`, `services/correctness_gates.py`, `services/financial_intelligence.py` |
| Publications composites | `services/composite_documents.py`, `modules/document_segmenter.py` |
| Collecte LegalTech | `modules/legaltech_notifications_network_collector.py`, `scripts/sync_legaltech_notifications_v5.py` |
| Cloche distante | `modules/legaltech_remote_watcher.py`, `scripts/check_legaltech_remote_v29.py` |
| Collecte CMF | `modules/cmf_collector_v1.py`, `modules/cmf_registry_v1.py` |
| PDF/OCR | `modules/ocr_engine.py`, `modules/pdf_preview.py` |
| Résultats/versions | `modules/business_pipeline_registry.py`, `services/lifecycle.py` |
| Excel | `modules/business_export.py` |
| Administration/référentiel | `services/administration.py`, `modules/admin_registry.py`, `ui/pages/administration.py` (vérifier l'inventaire pour les autres helpers) |

Les bases SQLite sont locales sous `data/` ; les fichiers de collecte, workflow, résultats métier, CMF et administration restent distincts. Ne pas remplacer les identifiants stables. `RUNTIME_INVENTORY.csv` et `RUNTIME_IMPORTS.json` permettent de suivre les imports réels.

Lancement : README. Synchronisation : bouton Synchroniser ou commandes documentées du runbook. Tests maintenus : `python scripts/run_tests.py`. Les diagnostics déplacés sont hors de cette suite ; les lire avant exécution. Ne pas réintroduire d'import d'une UI historique pour réutiliser du backend.

Le dépôt était déjà fortement modifié/non suivi avant cette passe. `.gitignore` protège les données privées mais ne publie pas les sources : avant un commit de livraison, examiner `git status`, ajouter seulement code/configuration/templates/docs voulus, et contrôler le diff indexé. Ne pas utiliser `git add .` sans revue. Aucun push réalisé par cette passe.

À reprendre : limitations d'environnement, collecte externe et périmètre de validation dans `KNOWN_LIMITATIONS.md`. Aucun nouveau métier, moteur IA, politique d'investissement ou transport email ajouté pendant le nettoyage.
