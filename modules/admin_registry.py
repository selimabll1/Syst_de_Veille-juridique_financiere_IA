"""Administration persistence. Reads never create or migrate a database."""
from contextlib import contextmanager, closing
from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3

DATABASE = Path(__file__).resolve().parents[1] / 'data' / 'ugfs_administration.sqlite3'


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def read(table):
    if table not in {'reference_imports', 'reference_records', 'admin_events', 'configuration_versions', 'cmf_discovery'}:
        raise ValueError('Table administration inconnue.')
    if not DATABASE.exists():
        return []
    flags = '?mode=ro' if Path(str(DATABASE)+'-wal').exists() else '?mode=ro&immutable=1'
    with closing(sqlite3.connect(DATABASE.resolve().as_uri()+flags, uri=True)) as con:
        con.row_factory = sqlite3.Row
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
            return []
        columns = 'id,filename,domain,sha256,row_count,imported_at,actor' if table == 'reference_imports' else '*'
        return [dict(r) for r in con.execute('SELECT '+columns+' FROM '+table)]


@contextmanager
def transaction():
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(DATABASE, timeout=15)) as con:
        con.row_factory = sqlite3.Row
        con.executescript('''
        CREATE TABLE IF NOT EXISTS reference_imports(id TEXT PRIMARY KEY,filename TEXT NOT NULL,domain TEXT NOT NULL,sha256 TEXT NOT NULL UNIQUE,row_count INTEGER NOT NULL,imported_at TEXT NOT NULL,actor TEXT NOT NULL,original BLOB NOT NULL);
        CREATE TABLE IF NOT EXISTS reference_records(id TEXT PRIMARY KEY,import_id TEXT NOT NULL,domain TEXT NOT NULL,name_key TEXT NOT NULL,identifier_key TEXT NOT NULL,data_json TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS admin_events(id INTEGER PRIMARY KEY AUTOINCREMENT,event_type TEXT NOT NULL,details_json TEXT NOT NULL,event_at TEXT NOT NULL,actor TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS configuration_versions(id INTEGER PRIMARY KEY AUTOINCREMENT,snapshot_json TEXT NOT NULL,recorded_at TEXT NOT NULL,reason TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS cmf_discovery(uid TEXT PRIMARY KEY,title TEXT NOT NULL,section TEXT,decision TEXT NOT NULL,reason TEXT NOT NULL,checked_at TEXT NOT NULL);
        ''')
        con.execute('BEGIN IMMEDIATE')
        try:
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise


def event(con, kind, details, actor='Utilisateur local — non authentifié'):
    con.execute('INSERT INTO admin_events(event_type,details_json,event_at,actor) VALUES(?,?,?,?)', (kind,json.dumps(details,ensure_ascii=False),now(),actor))


def entities():
    return [json.loads(r['data_json']) for r in read('reference_records')]
