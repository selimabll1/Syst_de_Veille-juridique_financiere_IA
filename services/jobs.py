"""Background business actions with progress and resource serialization."""
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from copy import deepcopy
from threading import RLock
import time
import uuid

_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="ugfs-action")
_lock = RLock()
_jobs = {}
_current = ContextVar("ugfs_job", default=None)


def report(message):
    token = _current.get()
    if token:
        with _lock:
            _jobs[token]["messages"].append(str(message))
            _jobs[token]["messages"] = _jobs[token]["messages"][-160:]


def start(label, resource, function, *args, **kwargs):
    with _lock:
        for token, job in _jobs.items():
            if job["resource"] == resource and job["state"] == "running":
                raise ValueError(f"{job['label']} est déjà en cours. Attendez son compte rendu.")
        token = uuid.uuid4().hex
        _jobs[token] = dict(id=token, label=label, resource=resource, state="running", started=time.time(), messages=[], result=None, error="")
        if len(args)>2 and args[0]=='run_analysis' and isinstance(args[1],dict):
            _jobs[token].update(notification_uid=args[1]['uid'],services=list(args[2] or args[1]['services']))
    def run():
        _current.set(token)
        try:
            result = function(*args, **kwargs)
            failed = (isinstance(result, tuple) and len(result) == 2 and result[0] is False) or (isinstance(result, dict) and result.get("ok") is False)
            with _lock:
                _jobs[token].update(state="failed" if failed else "complete", result=result, finished=time.time())
        except Exception as exc:
            with _lock:
                _jobs[token].update(state="failed", error=str(exc), finished=time.time())
    _executor.submit(run)
    return token


def status(token):
    with _lock:
        return deepcopy(_jobs.get(token))


def active():
    with _lock:
        return deepcopy([j for j in _jobs.values() if j['state']=='running'])


def stage(name, service=None):
    token=_current.get()
    if token:
        with _lock:
            previous=_jobs[token].get('stage')
            if previous and previous!=name:_jobs[token].setdefault('completed_stages',[]).append(previous)
            _jobs[token]['stage']=name
            if service:_jobs[token]['service']=service
