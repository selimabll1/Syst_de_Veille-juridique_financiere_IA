# Diagnostics manuels

Les anciens `scripts/test_*.py` ont été déplacés ici car ce sont principalement des scripts à `main()` et non la suite automatisée maintenue. Certains utilisent des bases locales, des PDF ou des services authentifiés : lire le fichier avant toute exécution, utiliser des copies et ne pas lancer tous ces scripts en lot.

Depuis la racine : `python -m scripts.diagnostics.NOM_DU_SCRIPT` (sans `.py`). Les références au parent du dépôt ont été ajustées au déplacement ; la logique des diagnostics est conservée. La suite supportée est `python scripts/run_tests.py`.

`runtime_inventory.py` est une analyse AST sans import/exécution de l'application : `python scripts/diagnostics/runtime_inventory.py`. Elle produit les inventaires sous docs. Les références dynamiques non résolues demandent une revue humaine.

Le diagnostic CMF obsolète est conservé dans l'archive locale et ne doit pas être exécuté contre la production.
