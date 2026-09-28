"""Client HTTP générique pour une intégration LegalTech autorisée.

Aucun endpoint ni secret n'est codé en dur. La session est chargée depuis
``secrets/legaltech_session.local.json`` et les endpoints depuis
``config/legaltech_endpoints.local.json``.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import time
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

LEGALTECH_CLIENT_VERSION = "legaltech_http_client_v1"


class LegalTechError(RuntimeError):
    pass


class LegalTechConfigurationError(LegalTechError):
    pass


class LegalTechAuthenticationError(LegalTechError):
    pass


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    sha256: str
    size_bytes: int
    source_url: str


def _load_json(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LegalTechConfigurationError(f"Fichier introuvable : {file_path}") from exc
    except json.JSONDecodeError as exc:
        raise LegalTechConfigurationError(f"JSON invalide : {file_path} — {exc}") from exc
    if not isinstance(data, dict):
        raise LegalTechConfigurationError(f"{file_path} doit contenir un objet JSON")
    return data


def deep_get(data: Any, path: str, default: Any = None) -> Any:
    current = data
    if not path:
        return current
    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                return default
            current = current[part]
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            if index >= len(current):
                return default
            current = current[index]
        else:
            return default
    return current


def safe_filename(value: str, fallback: str = "document.pdf") -> str:
    name = Path(value or fallback).name
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .") or fallback
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name[:180]


class LegalTechHTTPClient:
    def __init__(self, endpoints: dict[str, Any], secrets: dict[str, Any]) -> None:
        self.base_url = str(endpoints.get("base_url", "")).rstrip("/")
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise LegalTechConfigurationError("base_url doit être une URL HTTPS")

        self.requests_config = endpoints.get("requests", {})
        if not isinstance(self.requests_config, dict):
            raise LegalTechConfigurationError("requests doit être un objet JSON")

        self.allowed_hosts = {parsed.hostname.casefold()}
        self.allowed_hosts.update(
            str(host).casefold()
            for host in endpoints.get("allowed_download_hosts", [])
            if str(host).strip()
        )
        self.timeout = int(endpoints.get("timeout_seconds", 45))
        self.delay = float(endpoints.get("min_delay_seconds", 1.5))
        self.max_bytes = int(endpoints.get("max_download_mb", 150)) * 1024 * 1024
        self.last_request = 0.0

        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "UGFS-LegalTech-Collector/1.0",
        })
        ignored = {
            "cookie", "host", "content-length", "connection", "accept-encoding",
            "sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform",
            "sec-fetch-dest", "sec-fetch-mode", "sec-fetch-site",
        }
        for key, value in secrets.get("headers", {}).items():
            if str(key).casefold() not in ignored and str(value).strip():
                self.session.headers[str(key)] = str(value)
        for key, value in secrets.get("cookies", {}).items():
            if str(key).strip() and str(value).strip():
                self.session.cookies.set(str(key), str(value))

        retry = Retry(
            total=4,
            backoff_factor=1,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "HEAD", "OPTIONS", "POST"}),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    @classmethod
    def from_files(
        cls,
        endpoints_path: str | Path,
        session_path: str | Path,
    ) -> "LegalTechHTTPClient":
        return cls(_load_json(endpoints_path), _load_json(session_path))

    def _wait(self) -> None:
        remaining = self.delay - (time.monotonic() - self.last_request)
        if remaining > 0:
            time.sleep(remaining)

    def _check_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or (parsed.hostname or "").casefold() not in self.allowed_hosts:
            raise LegalTechConfigurationError(f"URL refusée : {url}")

    def _request_definition(self, name: str) -> dict[str, Any]:
        value = self.requests_config.get(name)
        if not isinstance(value, dict):
            raise LegalTechConfigurationError(f"Requête '{name}' absente")
        return value

    def request(
        self,
        name: str,
        *,
        params: dict[str, Any] | None = None,
        body: Any = None,
        url_values: dict[str, Any] | None = None,
        stream: bool = False,
    ) -> requests.Response:
        definition = self._request_definition(name)
        raw_url = str(definition.get("url") or definition.get("path") or "")
        if not raw_url:
            raise LegalTechConfigurationError(f"URL absente pour '{name}'")
        url = urljoin(self.base_url + "/", raw_url.lstrip("/"))
        url = url.format(**(url_values or {}))
        self._check_url(url)
        self._wait()

        method = str(definition.get("method", "GET")).upper()
        mode = str(definition.get("body_mode", "none")).lower()
        effective_body = definition.get("default_body") if body is None else body
        kwargs: dict[str, Any] = {
            "method": method,
            "url": url,
            "params": params,
            "timeout": self.timeout,
            "allow_redirects": True,
            "stream": stream,
        }
        if mode == "json":
            kwargs["json"] = effective_body
        elif mode in {"form", "raw"}:
            kwargs["data"] = effective_body

        response = self.session.request(**kwargs)
        self.last_request = time.monotonic()
        if response.status_code in {401, 403, 419}:
            raise LegalTechAuthenticationError(
                f"Session refusée ou expirée (HTTP {response.status_code})"
            )
        expected = {int(x) for x in definition.get("expected_statuses", [200])}
        if response.status_code not in expected:
            preview = "" if stream else response.text[:250].replace("\n", " ")
            raise LegalTechError(
                f"{name}: HTTP {response.status_code}; réponse={preview!r}"
            )
        return response

    def check_session(self) -> dict[str, Any]:
        response = self.request("session_check")
        text = response.text.casefold()
        if any(x in text for x in ("connexion membre", "mot de passe", "accès refusé")):
            raise LegalTechAuthenticationError("La réponse n'est pas authentifiée")
        markers = self._request_definition("session_check").get("authenticated_markers", [])
        if markers and not any(str(marker).casefold() in text for marker in markers):
            raise LegalTechAuthenticationError("Marqueur de session authentifiée absent")
        return {
            "status_code": response.status_code,
            "content_type": response.headers.get("Content-Type", ""),
            "final_url": response.url,
        }

    def search(self, *, params: dict[str, Any] | None = None, body: Any = None) -> Any:
        response = self.request("search", params=params, body=body)
        if "json" in response.headers.get("Content-Type", "").casefold():
            return response.json()
        return response.text

    def download_pdf(
        self,
        *,
        target_dir: str | Path,
        filename: str,
        direct_url: str | None = None,
        url_values: dict[str, Any] | None = None,
    ) -> DownloadResult:
        if direct_url:
            self._check_url(direct_url)
            self._wait()
            response = self.session.get(
                direct_url,
                timeout=self.timeout,
                stream=True,
                allow_redirects=True,
            )
            self.last_request = time.monotonic()
            if response.status_code in {401, 403, 419}:
                raise LegalTechAuthenticationError("Téléchargement refusé")
            response.raise_for_status()
        else:
            response = self.request("download", url_values=url_values, stream=True)

        self._check_url(response.url)
        target = Path(target_dir)
        target.mkdir(parents=True, exist_ok=True)
        destination = target / safe_filename(filename)
        partial = destination.with_suffix(".pdf.part")
        digest = sha256()
        size = 0
        first = b""
        try:
            with partial.open("wb") as handle:
                for chunk in response.iter_content(128 * 1024):
                    if not chunk:
                        continue
                    if not first:
                        first = chunk[:8]
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise LegalTechError("PDF trop volumineux")
                    digest.update(chunk)
                    handle.write(chunk)
            if not first.startswith(b"%PDF"):
                raise LegalTechError("Le fichier téléchargé n'est pas un PDF")
            partial.replace(destination)
            return DownloadResult(destination, digest.hexdigest(), size, response.url)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
