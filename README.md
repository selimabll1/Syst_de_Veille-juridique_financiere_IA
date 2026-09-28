# UGFS North Africa — veille juridique et financière

Application interne Streamlit : collecte LegalTech/CMF, routage métier, analyse locale sourcée, correction et validation humaines. Les résultats sont des brouillons d'aide à la décision, jamais une décision automatique.

## Installation Windows (PowerShell)

Utiliser Python **3.13 64 bits** (version de validation), Git, et un terminal ouvert à la racine du clone. Python 3.11–3.13 est la plage recommandée ; les autres versions ne sont pas validées.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe -m playwright install chromium
```

Aucune activation PowerShell n'est nécessaire. Ne jamais remplacer un `.env` existant. L'exemple ne contient aucun secret.

### Services externes

- **Ollama** : installer la distribution Windows officielle, démarrer Ollama, puis `ollama pull qwen3:1.7b`. Si le service n'est pas lancé, `ollama serve`. La configuration locale `.env` choisit le modèle et l'URL ; aucune substitution automatique de modèle.
- **Tesseract OCR** : installer Tesseract 5 pour Windows et les langues `fra`, `ara`, `eng`. Ajouter le dossier contenant `tesseract.exe` au PATH du compte qui lance Streamlit. Vérifier `tesseract --version` puis `tesseract --list-langs`.
- **Poppler** : installer une distribution Windows et ajouter son dossier `Library/bin` (ou `bin`, selon la distribution) au PATH. Vérifier `pdftoppm -v`. L'extraction/aperçu courant utilise PyMuPDF ; Poppler est utile pour les chemins conservés utilisant pdf2image.
- **Playwright Chromium** : installé avec la commande ci-dessus. Nécessaire à la connexion et à la collecte LegalTech, pas à la consultation vide.

Ces programmes sont des dépendances de la machine, pas des fichiers à copier depuis le PC de Salima. Ouvrir un nouveau terminal après modification du PATH. Sans Ollama/OCR/session LegalTech, la consultation reste possible ; les actions concernées nécessitent leur configuration.

```powershell
.\.venv\Scripts\python.exe scripts/check_environment.py
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

Ouvrir http://127.0.0.1:8501. La page initiale est **Accueil**. Un clone neuf ne contient ni notifications, ni résultat, ni portefeuille réel : les états vides sont normaux. Ne pas importer les modèles CSV comme des participations réelles.

## Connexion et synchronisation LegalTech

Depuis la racine :

```powershell
.\.venv\Scripts\python.exe -m scripts.legaltech_browser_login_v4
```

Se connecter manuellement dans Chromium ; ouvrir la page des notifications puis revenir au terminal et appuyer sur Entrée. Les fichiers de session restent dans `secrets/`, exclus de Git. Ne pas les partager.

```powershell
.\.venv\Scripts\python.exe -m scripts.check_legaltech_remote_v29 --headless
.\.venv\Scripts\python.exe -m scripts.sync_legaltech_notifications_v5 --max-notifications 0 --headless
```

La commande CLI collecte les sources. Le bouton **Synchroniser** de l'application ajoute l'orchestration du routage des nouveaux éléments et le rafraîchissement. Préférer le bouton pour l'usage analyste. La cloche compare les cartes/résultats distants à la collecte locale, pas les notifications non lues. CMF se configure et se synchronise dans l'application ; sa politique de pertinence doit être renseignée et CMF reste Conformité uniquement.

## Tests maintenus

```powershell
.\.venv\Scripts\python.exe scripts/run_tests.py
.\.venv\Scripts\python.exe -m compileall -q app.py config.py ui services modules scripts
```

La suite sélectionne les tests isolés. Ne pas lancer une découverte aveugle de tous les anciens `test_*.py` : plusieurs diagnostics historiques ouvrent des données ou des services réels. Voir `scripts/diagnostics/README.md`.

## Orientation développeur

`app.py → ui/app_ui.py → services/ui_adapter.py → services / modules → SQLite et fichiers locaux`.

- [Architecture](docs/ARCHITECTURE.md)
- [Exploitation et récupération](docs/RUNBOOK.md)
- [Passation développeur](docs/HANDOFF.md)
- [Limites connues](docs/KNOWN_LIMITATIONS.md)
- [Inventaire Python](docs/RUNTIME_INVENTORY.csv), [imports](docs/RUNTIME_IMPORTS.json), [déplacements](docs/CLEANUP_MOVES.json)

Les archives locales ne font pas partie du produit supporté. Les documents de phases antérieures décrivent parfois des interfaces obsolètes ; les documents ci-dessus font autorité pour le lancement actuel. Ne pas exposer Streamlit sur Internet : le nom d'utilisateur affiché n'est pas un système d'authentification.
