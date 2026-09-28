# Démarrage rapide

La procédure maintenue est dans [README.md](README.md).

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe scripts/check_environment.py
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

Installer/configurer Ollama, OCR et Chromium selon le README avant leurs usages respectifs. Un clone neuf s'ouvre sans données. Ne pas exécuter les anciens installeurs UI archivés.
