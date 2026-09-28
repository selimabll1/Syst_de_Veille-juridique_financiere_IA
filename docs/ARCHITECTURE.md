# Architecture active

```text
app.py
  ui.app_ui.render
    ui.components / ui.pages / ui.theme (propriétaire CSS)
    services.ui_adapter (lectures sans migration ni écriture)
      services.operations (actions explicites)
      services.routing + pipeline_config + priority + lifecycle
      services.business_analysis → intelligence → correctness_gates
        canonical_facts / event_profiles / financial_intelligence
        modules.llm_analyzer → Ollama local
      modules.*_registry → SQLite / fichiers
      collecteurs LegalTech et CMF / extraction PDF et OCR
```

Une notification centrale possède plusieurs affectations et résultats indépendants. La validation d'un service ne valide pas les autres. Lecture, priorité et traitement restent indépendants. Les résultats sont conservés/versionnés ; les échecs sont des tentatives, pas des résultats réussis. Les documents composites sont analysés par publication enfant, jamais comme un résultat métier unique.

`config/business_pipeline.json` contient éligibilité, règles, prompts et schémas. Le référentiel UGFS est une couche de rapprochement, pas une source. Sans référentiel faisant autorité, aucune appartenance au portefeuille n'est présumée. Le triage configurable donne une file de revue aux éléments sans pertinence confirmée.

L'inventaire CSV catégorise ACTIVE (fermeture des imports de app.py, y compris imports conditionnels et références littérales de scripts), TEST, SCRIPT, LEGACY, UNKNOWN. L'outil AST conserve les appels dynamiques dans le JSON. Ce graphe est une approximation conservative, pas une preuve qu'un fichier UNKNOWN est mort. Les modules historiques/compatibilité restent en place lorsqu'un script ou un test peut les utiliser. Aucun déplacement de base de données.

`cmf_compliance_prototype.py` est une ancienne entrée autonome conservée pour compatibilité ; ne pas l'utiliser comme application finale. Les anciens lanceurs/installeurs racine sont archivés localement, hors du runtime. L'archive n'est pas un ensemble de programmes maintenus à exécuter depuis son nouvel emplacement.
