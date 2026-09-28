"""Read-only readiness check; never imports the app, logs in or prints secrets."""
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
from urllib.parse import urlsplit, urlunsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def main():
    failures = 0
    def report(level, name, message):
        print(f'{level:4} | {name}: {message}')
    report('OK' if (3,11) <= sys.version_info[:2] < (3,14) else 'WARN', 'Python', sys.version.split()[0]+' ; utiliser 3.11–3.13')
    for line in (ROOT/'requirements.txt').read_text(encoding='utf8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        name = re.split(r'[<>=!~;\[]', line)[0]
        try:
            version = importlib.metadata.version(name)
            try:
                from packaging.requirements import Requirement
                valid = version in Requirement(line).specifier
            except ImportError:
                valid = True
                report('WARN','Vérification de version','packaging absent ; version installée affichée sans contrôle de contrainte')
            report('OK' if valid else 'FAIL', name, version)
            failures += not valid
        except importlib.metadata.PackageNotFoundError:
            report('FAIL', name, 'absent — installer requirements.txt')
            failures += 1
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT/'.env')
    except ImportError:
        pass
    model = os.getenv('OLLAMA_MODEL','qwen3:1.7b')
    try:
        parts = urlsplit(os.getenv('OLLAMA_URL','http://localhost:11434/api/chat'))
        with urlopen(urlunsplit((parts.scheme,parts.netloc,'/api/tags','','')),timeout=4) as response:
            models = json.load(response).get('models',[])
        present = any(m.get('name') == model or m.get('model') == model for m in models)
        report('OK' if present else 'WARN','Ollama / modèle configuré','disponible' if present else 'modèle absent')
    except Exception:
        report('WARN','Ollama','indisponible — consultation possible, analyse IA indisponible')
    for name, executable, arguments in [('Tesseract','tesseract',['--version']),('Poppler','pdftoppm',['-v'])]:
        available = shutil.which(executable)
        if not available:
            report('WARN',name,'absent du PATH')
            continue
        try:
            result = subprocess.run([available,*arguments],capture_output=True,text=True,timeout=5,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            report('OK' if result.returncode == 0 else 'WARN',name,'exécutable accessible')
        except (OSError,subprocess.TimeoutExpired):
            report('WARN',name,'exécution non disponible')
    try:
        distribution = importlib.metadata.distribution('playwright')
        package = Path(distribution.locate_file('playwright/driver/package'))
        browsers = json.loads((package/'browsers.json').read_text(encoding='utf8'))['browsers']
        revision = next(b['revision'] for b in browsers if b['name']=='chromium')
        override = os.getenv('PLAYWRIGHT_BROWSERS_PATH')
        cache = package/'.local-browsers' if override=='0' else Path(override) if override else Path(os.getenv('LOCALAPPDATA',Path.home()/'.cache'))/'ms-playwright'
        installed = any((cache/('chromium-'+revision)).glob('**/chrome.exe'))
        report('OK' if installed else 'WARN','Chromium Playwright','installé' if installed else 'python -m playwright install chromium')
    except Exception:
        report('WARN','Chromium Playwright','non vérifiable ; collecte navigateur indisponible')
    for name in ('ui','services','modules','config','assets','data/reference/import_templates'):
        exists = (ROOT/name).is_dir()
        report('OK' if exists else 'FAIL',name,'présent' if exists else 'dossier livré manquant')
        failures += not exists
    for name in ('data/pdf_raw','data/ocr_text','data/output_excel','data/legaltech_pdfs'):
        report('OK' if (ROOT/name).is_dir() else 'WARN',name,'présent' if (ROOT/name).is_dir() else 'créé au premier usage')
    databases = list((ROOT/'data').glob('*.sqlite3'))
    if not databases:
        report('OK','Bases de données','aucune — démarrage vide attendu')
    for path in databases:
        try:
            connection = sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
            try:
                valid = connection.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
            finally:
                connection.close()
            report('OK' if valid else 'FAIL','SQLite',path.name+(' accessible' if valid else ' intégrité à vérifier'))
            failures += not valid
        except sqlite3.Error:
            report('FAIL','SQLite',path.name+' inaccessible en lecture seule')
            failures += 1
    auth = all((ROOT/'secrets'/name).is_file() for name in ('legaltech_storage_state.json','legaltech_session_storage.json'))
    report('OK' if auth else 'WARN','Session LegalTech','fichiers présents (validité non vérifiée)' if auth else 'absente — connexion manuelle requise')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
