"""Static local-import inventory; never imports application modules or opens data."""
import ast
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXCLUDED = {'.venv', '.rehearsal', '.cleanroom', '.git', 'backups', '__pycache__', 'data'}


def inventory():
    paths = [p for p in ROOT.rglob('*.py') if not any(x in EXCLUDED or x.startswith('backup_before_') for x in p.relative_to(ROOT).parts)]
    modules = {'.'.join(p.relative_to(ROOT).with_suffix('').parts): p for p in paths}
    edges = {p: set() for p in paths}
    dynamic = []
    for path in paths:
        try:
            tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        except (SyntaxError, UnicodeError):
            continue
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ''
                if node.level:
                    package = list(path.relative_to(ROOT).parent.parts)
                    base = '.'.join(package[:len(package)-node.level+1] + ([base] if base else []))
                names = [base] + [base+'.'+a.name for a in node.names]
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                candidate = ROOT / node.value
                if node.value.endswith('.py') and candidate in edges:
                    edges[path].add(candidate)
                if node.value in modules:
                    edges[path].add(modules[node.value])
            elif isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute)):
                name = getattr(node.func, 'id', getattr(node.func, 'attr', ''))
                if name in {'__import__', 'import_module', 'run_path', 'run_module'}:
                    dynamic.append({'file':path.relative_to(ROOT).as_posix(), 'line':node.lineno, 'call':name})
            for name in names:
                if name in modules:
                    edges[path].add(modules[name])
    active, pending = set(), [ROOT/'app.py']
    while pending:
        p = pending.pop()
        if p in active:
            continue
        active.add(p)
        pending.extend(edges.get(p, ()))
    rows = []
    for p in sorted(paths):
        rel = p.relative_to(ROOT).as_posix()
        category = 'ACTIVE' if p in active else 'LEGACY' if rel.startswith('archive/') else 'TEST' if rel.startswith('tests/') else 'SCRIPT' if rel.startswith('scripts/') else 'UNKNOWN'
        rows.append({'file':rel, 'category':category, 'imported_by':'; '.join(q.relative_to(ROOT).as_posix() for q in paths if p in edges[q])})
    return rows, edges, dynamic


if __name__ == '__main__':
    rows, edges, dynamic = inventory()
    destination = ROOT/'docs'
    with (destination/'RUNTIME_INVENTORY.csv').open('w', encoding='utf-8', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=['file','category','imported_by'])
        writer.writeheader(); writer.writerows(rows)
    (destination/'RUNTIME_IMPORTS.json').write_text(json.dumps({'edges':{p.relative_to(ROOT).as_posix():sorted(q.relative_to(ROOT).as_posix() for q in refs) for p,refs in edges.items()},'dynamic_calls':dynamic}, indent=2),encoding='utf8')
    print({category:sum(r['category']==category for r in rows) for category in ('ACTIVE','TEST','SCRIPT','LEGACY','UNKNOWN')})
