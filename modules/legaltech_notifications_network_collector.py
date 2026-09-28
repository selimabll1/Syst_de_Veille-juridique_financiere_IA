
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import sqlite3
import time
from typing import Any
from urllib.parse import quote, urlparse

from modules.legaltech_browser_collector import (
    AuthenticationRequired,
    BrowserResult,
    normalize_space,
    parse_article_url,
)
from modules.legaltech_detail_parser import parse_detail_text
from modules.legaltech_notifications_collector import (
    DEFAULT_NOTIFICATIONS_URL,
    LegalTechNotificationsCollector,
    NotificationAlert,
    NotificationItem,
    NotificationsRegistry,
    stable_hash,
)

LEGALTECH_NETWORK_COLLECTOR_VERSION = "legaltech_notifications_v29_all_pages"
DEFAULT_V5_DB = Path("data/legaltech_notifications_v5.sqlite3")
DEBUG_DIR = Path("data/legaltech_network_debug")

REQUEST_RESULT_URL = (
    "https://annoncesbo.legaltech.tn/api/secure/request/result"
)

REQUEST_UUID_RE = re.compile(
    r"/api/secure/request/"
    r"(?P<id>[0-9a-fA-F]{8}-[0-9a-fA-F-]{20,})"
    r"(?:$|[?#])"
)


@dataclass
class CapturedRequest:
    url: str
    method: str
    headers: dict[str, str]
    post_data: str | None


class NetworkFirstNotificationsCollector(
    LegalTechNotificationsCollector
):
    """Collect notification results from the browser network first.

    Why:
    LegalTech can change the selected notification while failing to render the
    right-side result cards. In that state DOM scraping returns 0 cards even
    though the frontend attempted to load the saved alert.

    v5 listens to the authenticated browser's normal `/api/secure/request/...`
    traffic. If the browser receives a usable JSON response, it uses it
    directly. If the browser request is blocked by CORS/preflight but an
    authenticated request was attempted, v5 replays the SAME authorized
    request through Playwright's server-side APIRequestContext. It does not
    disable browser security and it does not invent/replace authentication.
    A server-side 401/403 remains a hard failure.
    """

    def __init__(self, browser):
        super().__init__(browser)
        self.registry = NotificationsRegistry(DEFAULT_V5_DB)
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        self._last_trace: dict[str, Any] = {}

    @staticmethod
    def _relevant_request_url(url: str) -> bool:
        try:
            parsed = urlparse(url)
        except Exception:
            return False

        return (
            parsed.netloc.casefold() == "annoncesbo.legaltech.tn"
            and parsed.path.startswith("/api/secure/request")
        )

    def _start_network_trace(self):
        page = self._page()
        trace: dict[str, Any] = {
            "active": True,
            "requests": [],
            "responses": [],
        }

        def on_request(request):
            if not trace["active"]:
                return
            if not self._relevant_request_url(request.url):
                return

            try:
                headers = dict(request.all_headers())
            except Exception:
                headers = {}

            trace["requests"].append(
                CapturedRequest(
                    url=str(request.url),
                    method=str(request.method or "GET").upper(),
                    headers=headers,
                    post_data=request.post_data,
                )
            )

        def on_response(response):
            if not trace["active"]:
                return
            if not self._relevant_request_url(response.url):
                return
            trace["responses"].append(response)

        page.on("request", on_request)
        page.on("response", on_response)
        return trace

    def _stop_network_trace(self, trace):
        trace["active"] = False
        self._last_trace = trace

    def _activate_notification_with_trace(
        self,
        notif: NotificationItem,
    ):
        trace = self._start_network_trace()
        try:
            changed, panel = super()._activate_notification(
                notif,
                retries=2,
            )
            # Allow any XHR that was triggered by the click to finish.
            self._page().wait_for_timeout(1000)
            return changed, panel, trace
        finally:
            self._stop_network_trace(trace)

    @staticmethod
    def _safe_replay_headers(
        headers: dict[str, str],
    ) -> dict[str, str]:
        """Keep auth/content headers, drop browser-only CORS/fetch headers.

        Header values are never printed or written to disk.
        """
        blocked = {
            "cookie",
            "host",
            "content-length",
            "origin",
            "referer",
            "connection",
        }
        out = {}

        for key, value in (headers or {}).items():
            lower = key.casefold()
            if lower in blocked:
                continue
            if lower.startswith("sec-"):
                continue

            if (
                lower in {
                    "accept",
                    "accept-language",
                    "authorization",
                    "content-type",
                    "user-agent",
                }
                or lower.startswith("x-")
            ):
                out[key] = value

        return out

    @staticmethod
    def _status_label(url: str, method: str, status: int):
        path = urlparse(url).path
        if len(path) > 85:
            path = path[:82] + "..."
        print(f"[NETWORK/UI] {method} {path} -> {status}")

    def _json_from_browser_responses(
        self,
        trace,
    ) -> list[Any]:
        payloads = []

        for response in trace.get("responses", []):
            try:
                request = response.request
                status = int(response.status)
                self._status_label(
                    str(response.url),
                    str(request.method),
                    status,
                )

                # IMPORTANT: GET /api/secure/request/<uuid> describes the saved
                # request itself. The actual article list comes from:
                # POST /api/secure/request/result
                #
                # Parsing both responses can duplicate the same five visible
                # articles. We keep logging both responses, but only feed the
                # POST result payload into the article parser.
                response_path = urlparse(str(response.url)).path
                response_method = str(request.method or "GET").upper()
                if not (
                    response_method == "POST"
                    and response_path == "/api/secure/request/result"
                ):
                    continue

                if status < 200 or status >= 300:
                    continue

                try:
                    payloads.append(response.json())
                except Exception:
                    try:
                        text = response.text()
                        payloads.append(json.loads(text))
                    except Exception:
                        pass
            except Exception:
                continue

        return payloads

    @staticmethod
    def _find_request_uuid(trace) -> str:
        for item in reversed(trace.get("requests", [])):
            if item.method == "OPTIONS":
                continue
            match = REQUEST_UUID_RE.search(item.url)
            if match:
                return match.group("id")
        return ""

    @staticmethod
    def _best_request_headers(trace) -> dict[str, str]:
        # Prefer a non-OPTIONS request containing Authorization/x-* headers.
        requests = [
            x for x in trace.get("requests", [])
            if x.method != "OPTIONS"
        ]
        requests.sort(
            key=lambda x: (
                "authorization" not in {
                    k.casefold() for k in x.headers
                },
                -len(x.headers),
            )
        )
        return requests[0].headers if requests else {}

    @staticmethod
    def _retry_after_seconds(response) -> int:
        try:
            headers = response.headers
            raw = (
                headers.get("retry-after")
                or headers.get("Retry-After")
                or ""
            )
            seconds = int(str(raw).strip())
            return max(0, min(seconds, 60))
        except Exception:
            return 0

    def _fetch_with_rate_limit_backoff(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        data: Any = None,
        label: str,
        allow_one_retry: bool = True,
    ):
        """One request + at most one respectful retry on HTTP 429."""
        api = self.browser.context.request

        def do_fetch():
            kwargs: dict[str, Any] = {
                "method": method,
                "headers": headers,
                "timeout": 15000,
            }
            if data not in (None, ""):
                kwargs["data"] = data
            return api.fetch(url, **kwargs)

        response = do_fetch()
        print(
            label,
            method,
            urlparse(url).path,
            "->",
            response.status,
        )

        if response.status != 429 or not allow_one_retry:
            return response

        wait_seconds = self._retry_after_seconds(response) or 12
        print(
            f"[RATE LIMIT] 429 reçu — attente {wait_seconds}s "
            "avant UNE seule nouvelle tentative."
        )
        time.sleep(wait_seconds)

        response = do_fetch()
        print(
            label,
            method,
            urlparse(url).path,
            "retry ->",
            response.status,
        )
        return response

    @staticmethod
    def _result_post_request(trace) -> CapturedRequest | None:
        """Return the exact POST /request/result emitted by the frontend."""
        for item in reversed(trace.get("requests", [])):
            parsed = urlparse(item.url)
            if (
                item.method == "POST"
                and parsed.path == "/api/secure/request/result"
            ):
                return item
        return None

    def _replay_result_request_only(
        self,
        trace,
    ) -> list[Any]:
        """Replay only the UI's exact result POST.

        v5 replayed both GET /request/<uuid> and POST /request/result, then
        additionally called request/result again. That tripled traffic and
        triggered 429. v5.1 performs at most one fallback result request.
        """
        item = self._result_post_request(trace)
        if item is None:
            return []

        headers = self._safe_replay_headers(item.headers)
        response = self._fetch_with_rate_limit_backoff(
            method="POST",
            url=item.url,
            headers=headers,
            data=item.post_data,
            label="[NETWORK/REPLAY-RESULT]",
        )

        if not response.ok:
            return []

        try:
            return [response.json()]
        except Exception:
            return []

    def _request_saved_alert_results(
        self,
        notif: NotificationItem,
        trace,
    ) -> list[Any]:
        """Fallback pagination when the UI emitted no result POST at all."""
        if self._result_post_request(trace) is not None:
            return []

        request_id = self._find_request_uuid(trace)
        if not request_id:
            print("[NETWORK] aucun request UUID observé pour", notif.company_or_query)
            return []

        headers = self._safe_replay_headers(self._best_request_headers(trace))
        headers.setdefault("Accept", "application/json")
        headers.setdefault("Content-Type", "application/json")
        payloads: list[Any] = []
        seen = 0
        total = None

        for page_no in range(0, 500):
            body = {"id": request_id, "limit": 50, "page": page_no}
            response = self._fetch_with_rate_limit_backoff(
                method="POST",
                url=REQUEST_RESULT_URL,
                headers=headers,
                data=body,
                label=f"[NETWORK/RESULT PAGE {page_no}]",
            )
            if response.status in (401, 403) or not response.ok:
                break
            try:
                payload = response.json()
            except Exception:
                break
            payloads.append(payload)
            alerts = self._alerts_from_payloads(notif, payloads)
            new_seen = len(alerts)
            total = self._extract_total(payloads) or total
            if new_seen <= seen:
                break
            seen = new_seen
            if total is not None and seen >= total:
                break
            time.sleep(0.65)

        return payloads

    @staticmethod
    def _walk_article_dicts(value: Any):
        """Yield article-like dictionaries from nested LegalTech/ES JSON."""
        if isinstance(value, list):
            for item in value:
                yield from (
                    NetworkFirstNotificationsCollector
                    ._walk_article_dicts(item)
                )
            return

        if not isinstance(value, dict):
            return

        # Elasticsearch hit: preserve _id alongside _source.
        source_obj = value.get("_source")
        if isinstance(source_obj, dict):
            merged = dict(source_obj)
            if value.get("_id") and not (
                merged.get("article_id")
                or merged.get("articleId")
                or merged.get("id")
            ):
                merged["_id"] = value.get("_id")
            yield merged

        keys = {str(k).casefold() for k in value}
        has_source = "source" in keys
        has_identifier = bool(
            {
                "articleid",
                "article_id",
                "docid",
                "doc_id",
                "_id",
            }
            & keys
        )
        has_content = bool(
            {
                "title",
                "articletext",
                "publishedat",
                "reference",
            }
            & keys
        )

        if has_source and (has_identifier or has_content):
            yield value

        for key, child in value.items():
            # The ES hit was already yielded with its authoritative _id.
            # Traversing _source again invents a second network-* identity.
            if key == "_source" and isinstance(source_obj, dict):
                continue
            if isinstance(child, (dict, list)):
                yield from (
                    NetworkFirstNotificationsCollector
                    ._walk_article_dicts(child)
                )

    @staticmethod
    def _pick(data: dict[str, Any], *names: str):
        lower_map = {
            str(key).casefold(): value
            for key, value in data.items()
        }
        for name in names:
            value = lower_map.get(name.casefold())
            if value not in (None, "", [], {}):
                return value
        return ""

    def _alerts_from_payloads(
        self,
        notif: NotificationItem,
        payloads: list[Any],
    ) -> list[NotificationAlert]:
        """Normalize + deduplicate LegalTech result objects.

        v5 could emit the same article twice because an ES wrapper and its
        nested _source were both traversed. v5.1 deduplicates primarily by
        (source, article_id, doc_id), falling back to content identity only
        when LegalTech omits identifiers.
        """
        merged: dict[str, dict[str, Any]] = {}

        for payload in payloads:
            for raw in self._walk_article_dicts(payload):
                source = normalize_space(
                    self._pick(raw, "source")
                )
                article_id = normalize_space(
                    self._pick(
                        raw,
                        "article_id",
                        "articleId",
                        "_id",
                    )
                )
                doc_id = normalize_space(
                    self._pick(
                        raw,
                        "doc_id",
                        "docId",
                    )
                )
                title = normalize_space(
                    self._pick(
                        raw,
                        "title",
                        "reference",
                    )
                )
                date = normalize_space(
                    self._pick(
                        raw,
                        "publishedAt",
                        "published_at",
                        "date",
                    )
                )

                summary_raw = self._pick(
                    raw,
                    "summary",
                    "articleText",
                    "article_text",
                    "description",
                    "text",
                )
                if isinstance(summary_raw, (dict, list)):
                    summary = json.dumps(
                        summary_raw,
                        ensure_ascii=False,
                    )
                else:
                    summary = normalize_space(summary_raw)

                if not source:
                    continue
                if not (
                    article_id
                    or doc_id
                    or (title and (date or summary))
                ):
                    continue

                if article_id:
                    # Surgical dedupe rule: within one source, the exact same
                    # article_id is the same article even if another response
                    # variant omits/adds doc_id. Nothing else in retrieval,
                    # network handling, parsing, enrichment, or UI is changed.
                    entity_key = stable_hash(
                        source.casefold(),
                        article_id,
                    )
                elif doc_id:
                    entity_key = stable_hash(
                        source.casefold(),
                        doc_id,
                        title,
                        date,
                    )
                else:
                    entity_key = stable_hash(
                        source.casefold(),
                        title,
                        date,
                        summary[:500],
                    )

                previous = merged.get(entity_key)
                current = {
                    "source": source,
                    "article_id": article_id,
                    "doc_id": doc_id,
                    "title": title,
                    "date": date,
                    "summary": summary,
                }

                if previous is None:
                    merged[entity_key] = current
                    continue

                # Merge the richer duplicate rather than emitting it twice.
                for field in (
                    "article_id",
                    "doc_id",
                    "title",
                    "date",
                    "summary",
                ):
                    old = normalize_space(previous.get(field, ""))
                    new = normalize_space(current.get(field, ""))
                    if not old or len(new) > len(old):
                        previous[field] = current[field]

        alerts: list[NotificationAlert] = []

        for entity_key, item in merged.items():
            source = item["source"]
            article_id = item["article_id"]
            doc_id = item["doc_id"]
            title = item["title"]
            date = item["date"]
            summary = item["summary"]

            article_url = ""
            if source and article_id:
                article_url = (
                    f"{self.browser.base_url}/article/"
                    f"{quote(source, safe='')}/"
                    f"{quote(article_id, safe='')}"
                )
                if doc_id:
                    article_url += (
                        "?docId=" + quote(doc_id, safe="")
                    )

            card_text = "\n".join(
                x for x in (
                    source,
                    date,
                    title,
                    summary,
                )
                if x
            )

            alert_key = stable_hash(
                notif.notification_key,
                entity_key,
            )

            alerts.append(
                NotificationAlert(
                    alert_key=alert_key,
                    notification_key=notif.notification_key,
                    source=source,
                    source_label=source,
                    article_id=(
                        article_id
                        or f"network-{alert_key[:16]}"
                    ),
                    doc_id=doc_id,
                    article_url=article_url,
                    alert_page=1,
                    card_text=card_text,
                    card_date=date,
                    card_title=title,
                    card_summary=summary,
                    notification_index=notif.notification_index,
                    card_index=len(alerts),
                )
            )

        return alerts

    @staticmethod
    def _extract_total(payloads: list[Any]) -> int | None:
        """Best-effort total count from ES/API responses."""
        candidates: list[int] = []

        def walk(value):
            if isinstance(value, list):
                for x in value:
                    walk(x)
                return
            if not isinstance(value, dict):
                return

            for key, child in value.items():
                lower = str(key).casefold()

                if lower in {
                    "total",
                    "totalhits",
                    "total_hits",
                    "totalresults",
                    "total_results",
                    "count",
                }:
                    if isinstance(child, int) and 0 <= child <= 100000:
                        candidates.append(child)
                    elif isinstance(child, dict):
                        val = child.get("value")
                        if isinstance(val, int) and 0 <= val <= 100000:
                            candidates.append(val)

                if isinstance(child, (dict, list)):
                    walk(child)

        for payload in payloads:
            walk(payload)

        # Prefer the largest plausible total because nested page counts can be
        # smaller than the overall result total.
        return max(candidates) if candidates else None

    def _save_payload_debug(
        self,
        notif: NotificationItem,
        payloads: list[Any],
    ):
        safe = re.sub(
            r"[^A-Za-z0-9._-]+",
            "_",
            notif.company_or_query,
        ).strip("_") or "notification"

        path = DEBUG_DIR / f"{safe}_result.json"
        try:
            path.write_text(
                json.dumps(
                    payloads,
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass

    @staticmethod
    def _decode_post_body(post_data: str | None) -> dict[str, Any] | None:
        if not post_data:
            return None
        try:
            parsed = json.loads(post_data)
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    @staticmethod
    def _pagination_values(body: dict[str, Any]) -> tuple[int, int, str]:
        """Return first observed page/limit values, including nested bodies."""
        page_value = None
        limit_value = None
        mode = "page"

        def walk(value):
            nonlocal page_value, limit_value, mode
            if isinstance(value, dict):
                for key, child in value.items():
                    lower = str(key).casefold()
                    if limit_value is None and lower in {"limit", "size", "pagesize", "page_size"}:
                        try:
                            n = int(child)
                            if n > 0:
                                limit_value = n
                        except Exception:
                            pass
                    if page_value is None and lower == "page":
                        try:
                            page_value = int(child or 0); mode = "page"
                        except Exception:
                            pass
                    elif page_value is None and lower in {"offset", "from"}:
                        try:
                            page_value = int(child or 0); mode = lower
                        except Exception:
                            pass
                    if isinstance(child, (dict, list)):
                        walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(body)
        limit = limit_value or 50
        if mode in {"offset", "from"}:
            page = int(page_value or 0) // limit
        else:
            page = int(page_value or 0)
        return page, limit, mode

    @staticmethod
    @staticmethod
    def _body_for_page(base: dict[str, Any], page_no: int, limit: int, mode: str) -> dict[str, Any]:
        body = json.loads(json.dumps(base))
        found_page = False
        found_limit = False

        def mutate(value):
            nonlocal found_page, found_limit
            if isinstance(value, dict):
                for key in list(value.keys()):
                    lower = str(key).casefold()
                    child = value[key]
                    if lower == "page":
                        value[key] = page_no; found_page = True; continue
                    if lower == "offset":
                        value[key] = page_no * limit; found_page = True; continue
                    if lower == "from":
                        value[key] = page_no * limit; found_page = True; continue
                    if lower in {"limit", "size", "pagesize", "page_size"}:
                        try:
                            int(child)
                            value[key] = limit; found_limit = True; continue
                        except Exception:
                            pass
                    if isinstance(child, (dict, list)):
                        mutate(child)
            elif isinstance(value, list):
                for child in value:
                    mutate(child)

        mutate(body)
        if not found_page:
            if mode == "offset": body["offset"] = page_no * limit
            elif mode == "from": body["from"] = page_no * limit
            else: body["page"] = page_no
        if not found_limit:
            body["limit"] = limit
        return body

    def _paginate_result_payloads(
        self,
        notif: NotificationItem,
        trace,
        initial_payloads: list[Any],
        *,
        max_pages: int = 0,
    ) -> list[Any]:
        """Fetch every result page using the exact authenticated frontend POST.

        max_pages=0 means continue until LegalTech's total is reached or the
        backend stops producing new article identities.
        """
        request = self._result_post_request(trace)
        if request is None:
            return initial_payloads

        base_body = self._decode_post_body(request.post_data)
        if base_body is None:
            return initial_payloads

        headers = self._safe_replay_headers(request.headers)
        headers.setdefault("Accept", "application/json")
        headers.setdefault("Content-Type", "application/json")

        page0, limit, mode = self._pagination_values(base_body)
        payloads = list(initial_payloads)
        total = self._extract_total(payloads)
        unique = self._alerts_from_payloads(notif, payloads)
        seen_count = len(unique)

        if total is not None and seen_count >= total:
            return payloads

        current_page = page0
        fetched = 1
        hard_guard = max_pages if max_pages and max_pages > 0 else 500

        while fetched < hard_guard:
            current_page += 1
            body = self._body_for_page(base_body, current_page, limit, mode)
            response = self._fetch_with_rate_limit_backoff(
                method="POST",
                url=request.url,
                headers=headers,
                data=body,
                label=f"[NETWORK/PAGE {current_page}]",
            )
            if response.status in (401, 403):
                break
            if not response.ok:
                break
            try:
                payload = response.json()
            except Exception:
                break

            payloads.append(payload)
            fetched += 1
            next_unique = self._alerts_from_payloads(notif, payloads)
            next_count = len(next_unique)
            total = self._extract_total(payloads) or total

            print(
                f"[NETWORK/PAGINATION] page={current_page} · "
                f"uniques={next_count}" + (f"/{total}" if total is not None else "")
            )

            # No new identities means pagination has ended or the API ignored
            # our page parameter. Never loop forever.
            if next_count <= seen_count:
                break
            seen_count = next_count
            if total is not None and seen_count >= total:
                break

            # Gentle pacing prevents the 429 regression seen in v5.
            time.sleep(0.65)

        return payloads

    def _fingerprint_notifications(self):
        """Identify the visible card page without depending on DOM node handles."""
        return tuple(normalize_space(row.get("text") or "")
                     for row in self._notification_candidates())

    def _click_next_notification_page(self) -> bool:
        page = self._page()
        before = self._fingerprint_notifications()
        clicked = page.locator("body").evaluate(
            r"""root => {
                const vw = window.innerWidth || 1500;
                const rows = [];
                for (const el of root.querySelectorAll('button,a,[role="button"]')) {
                    const txt = ((el.innerText || '') + ' ' +
                                 (el.getAttribute('aria-label') || '') + ' ' +
                                 (el.getAttribute('title') || '')).trim();
                    if (!/(suivant|suivante|next|^[>›»]$)/i.test(txt)) continue;
                    const r = el.getBoundingClientRect();
                    if (!r.width || !r.height) continue;
                    const center = r.left + r.width/2;
                    if (center >= vw*0.50) continue;
                    if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
                    rows.push({el,y:r.top});
                }
                rows.sort((a,b)=>b.y-a.y);
                if (!rows.length) return false;
                rows[0].el.scrollIntoView({block:'center'});
                rows[0].el.click();
                return true;
            }"""
        )
        if not clicked:
            return False
        deadline = time.time() + 7
        while time.time() < deadline:
            page.wait_for_timeout(300)
            now = self._fingerprint_notifications()
            if now and now != before:
                return True
        return False

    def _network_alerts(
        self,
        notif: NotificationItem,
        trace,
        *,
        max_alert_pages: int = 0,
    ) -> list[NotificationAlert]:
        payloads: list[Any] = []

        # Browser response = first page, no extra request.
        browser_payloads = self._json_from_browser_responses(trace)
        payloads.extend(browser_payloads)

        if not payloads:
            # One replay only when the browser did not provide a usable body.
            payloads.extend(self._replay_result_request_only(trace))

        if not payloads:
            payloads.extend(self._request_saved_alert_results(notif, trace))

        if payloads:
            payloads = self._paginate_result_payloads(
                notif,
                trace,
                payloads,
                max_pages=max_alert_pages,
            )

        alerts = self._alerts_from_payloads(notif, payloads)
        self._save_payload_debug(notif, payloads)
        total = self._extract_total(payloads)

        if alerts:
            print(
                f"[NETWORK] {len(alerts)} alerte(s) UNIQUE(S) récupérées"
                + (f" · total API={total}" if total is not None else "")
            )
        else:
            print("[NETWORK] aucune alerte exploitable récupérée pour", notif.company_or_query)

        return alerts

    def _wait_for_notification_items(
        self,
        *,
        max_notifications: int,
        timeout_seconds: int = 20,
    ):
        """Wait/retry until the left notification list is actually rendered.

        A previous diagnostic could silently produce zero items and immediately
        reach the final input() prompt. v5.2 makes that state explicit and
        retries the page once.
        """
        page = self.browser.goto(DEFAULT_NOTIFICATIONS_URL)
        if not self.browser.is_authenticated():
            raise AuthenticationRequired(
                "Connexion LegalTech requise."
            )

        attempts = 2

        for attempt in range(1, attempts + 1):
            deadline = time.time() + timeout_seconds

            while time.time() < deadline:
                rows = self._notification_candidates()
                if rows:
                    print(
                        f"[NOTIFICATIONS] {len(rows)} carte(s) détectée(s)"
                    )
                    return rows[:max_notifications]

                page.wait_for_timeout(500)

            print(
                f"[NOTIFICATIONS] aucune carte après "
                f"{timeout_seconds}s (tentative {attempt}/{attempts})"
            )

            if attempt < attempts:
                print("[NOTIFICATIONS] rechargement de /page-notifications")
                self.browser.goto(DEFAULT_NOTIFICATIONS_URL)
                page = self._page()
                page.wait_for_timeout(1200)

        # Save diagnostics instead of silently continuing with zero items.
        debug_dir = Path("data/legaltech_network_debug")
        debug_dir.mkdir(parents=True, exist_ok=True)

        try:
            debug_dir.joinpath(
                "notifications_page_body.txt"
            ).write_text(
                self._page().locator("body").inner_text(timeout=5000),
                encoding="utf-8",
            )
        except Exception:
            pass

        try:
            self._page().screenshot(
                path=str(
                    debug_dir / "notifications_page.png"
                ),
                full_page=False,
            )
        except Exception:
            pass

        current_url = str(self._page().url or "")
        title = ""
        try:
            title = self._page().title()
        except Exception:
            pass

        raise RuntimeError(
            "Aucune notification détectée après attente/rechargement. "
            f"URL actuelle={current_url!r}, titre={title!r}. "
            "Diagnostics: data/legaltech_network_debug/"
            "notifications_page_body.txt + notifications_page.png"
        )

    def enrich(self, alerts, *, download_documents=False):
        """Enrich only details that are still missing; persist parsed fields."""
        ok = failed = downloads_ok = downloads_failed = 0

        # Avoid re-opening hundreds/thousands of details already collected on
        # previous runs. This makes a full metadata sync incremental.
        existing: dict[str, dict[str, Any]] = {}
        try:
            con = sqlite3.connect(self.registry.path)
            con.row_factory = sqlite3.Row
            rows = con.execute(
                "SELECT alert_key,detail_status,detail_text,source_fields_json,download_status,download_path FROM notification_alerts"
            ).fetchall()
            con.close()
            existing = {str(r["alert_key"]): dict(r) for r in rows}
        except Exception:
            existing = {}

        for i, alert in enumerate(alerts, 1):
            row = existing.get(str(alert.alert_key), {})
            detail_done = row.get("detail_status") == "COLLECTED" and bool(str(row.get("detail_text") or "").strip())
            download_done = row.get("download_status") == "COLLECTED" and bool(str(row.get("download_path") or "").strip())

            if detail_done and (not download_documents or download_done):
                ok += 1
                if download_documents and download_done:
                    downloads_ok += 1
                continue

            print(f"[Détail {i}/{len(alerts)}] {alert.source} · {alert.card_title or alert.article_id}")
            parsed = parse_article_url(alert.article_url, self.browser.base_url)
            result = BrowserResult(
                result_key=parsed.result_key,
                alert_url=DEFAULT_NOTIFICATIONS_URL,
                source=parsed.source,
                article_id=parsed.article_id,
                doc_id=parsed.doc_id,
                article_url=parsed.article_url,
                list_page=alert.alert_page,
                list_text=alert.card_text,
            )
            try:
                if not detail_done:
                    detail = self.browser.collect_detail(result)
                    parsed_fields = parse_detail_text(
                        detail.visible_text,
                        detail.source_fields if isinstance(detail.source_fields, dict) else {},
                    )
                    self.registry.save_detail(
                        alert.alert_key,
                        detail.title,
                        detail.visible_text,
                        parsed_fields,
                    )
                ok += 1

                if download_documents and not download_done:
                    status, path = self.browser.try_download_visible_document(result)
                    self.registry.mark_download(alert.alert_key, status, path)
                    if status == "COLLECTED":
                        downloads_ok += 1
                    else:
                        downloads_failed += 1
            except AuthenticationRequired:
                raise
            except Exception as exc:
                self.registry.mark_detail_failed(alert.alert_key, str(exc))
                failed += 1

        return ok, failed, downloads_ok, downloads_failed

    def collect_first_notifications(
        self,
        *,
        max_notifications=0,
        max_alert_pages=0,
        safe_read_state=False,
    ):
        """Collect all left notification pages and all result pages.

        max_notifications=0 means no artificial notification-card cap.
        max_alert_pages=0 means continue API pagination until total/exhaustion.
        """
        page = self.browser.goto(DEFAULT_NOTIFICATIONS_URL)
        if not self.browser.is_authenticated():
            raise AuthenticationRequired("Connexion LegalTech requise.")

        run_id = self.registry.start_run()
        all_items: list[NotificationItem] = []
        all_alerts: list[NotificationAlert] = []
        loaded = 0
        failed = 0
        processed = 0
        notification_page = 1
        stop = False

        try:
            while not stop:
                candidates = self._notification_candidates()
                if not candidates:
                    if notification_page == 1:
                        # Preserve the explicit diagnostics of v5.2.
                        candidates = self._wait_for_notification_items(
                            max_notifications=(max_notifications or 999999),
                            timeout_seconds=20,
                        )
                    if not candidates:
                        break

                print(f"\n[NOTIFICATION PAGE {notification_page}] {len(candidates)} carte(s)")

                for local_idx, row in enumerate(candidates):
                    if max_notifications and processed >= max_notifications:
                        stop = True
                        break

                    notif = self._parse_notification(
                        row["text"],
                        notification_page,
                        notification_index=local_idx,
                    )
                    processed += 1
                    all_items.append(notif)

                    if processed > 1:
                        time.sleep(1.0)

                    print(
                        f"\n[Notification {processed}] {notif.company_or_query} · "
                        f"{notif.notification_date or 'date ?'}"
                    )
                    self.registry.upsert_notification(run_id, notif)

                    changed, panel, trace = self._activate_notification_with_trace(notif)

                    dom_alerts = []
                    if changed:
                        try:
                            dom_alerts = self._current_alerts(notif, 1)
                        except Exception:
                            dom_alerts = []

                    # Network pagination is authoritative whenever a result POST
                    # exists, because the DOM only contains the visible first page.
                    network_alerts = self._network_alerts(
                        notif,
                        trace,
                        max_alert_pages=max_alert_pages,
                    )
                    alerts = network_alerts or dom_alerts
                    load_status = (
                        "NETWORK_ALL_PAGES" if network_alerts
                        else "DOM_LOADED" if dom_alerts
                        else "NETWORK_FAILED"
                    )

                    if alerts:
                        unique_alerts = {}
                        for alert in alerts:
                            source_key = normalize_space(alert.source or alert.source_label).casefold()
                            article_id_key = normalize_space(alert.article_id).casefold()
                            if article_id_key and not article_id_key.startswith("network-"):
                                identity = ("article", source_key, article_id_key)
                            else:
                                identity = (
                                    "visible", source_key,
                                    normalize_space(alert.card_date),
                                    normalize_space(alert.card_title).casefold(),
                                    normalize_space(alert.card_summary).casefold(),
                                )
                            existing = unique_alerts.get(identity)
                            if existing is None:
                                unique_alerts[identity] = alert
                            else:
                                old_score = (int(bool(existing.article_url)), int(bool(existing.doc_id)), len(existing.card_summary or ""), len(existing.card_text or ""))
                                new_score = (int(bool(alert.article_url)), int(bool(alert.doc_id)), len(alert.card_summary or ""), len(alert.card_text or ""))
                                if new_score > old_score:
                                    unique_alerts[identity] = alert
                        alerts = list(unique_alerts.values())

                    if not alerts:
                        failed += 1
                        self.registry.update_notification_load(
                            notif.notification_key,
                            status=load_status,
                            error="Aucun résultat exploitable obtenu du DOM ou de l'API LegalTech.",
                            panel_total=None,
                        )
                        continue

                    loaded += 1
                    total = None
                    try:
                        total = self._extract_total(self._json_from_browser_responses(trace))
                    except Exception:
                        total = None
                    self.registry.update_notification_load(
                        notif.notification_key,
                        status=load_status,
                        panel_total=(total if total is not None else len(alerts)),
                    )
                    for alert in alerts:
                        self.registry.upsert_alert(run_id, alert)
                    all_alerts.extend(alerts)

                if stop:
                    break
                if not self._click_next_notification_page():
                    break
                notification_page += 1

            self.registry.finish_run(
                run_id,
                "COLLECTED",
                f"{loaded} notification(s) chargée(s), {failed} échec(s), {len(all_alerts)} alerte(s)",
            )
            return run_id, all_items, all_alerts, loaded, failed
        except Exception as exc:
            self.registry.finish_run(run_id, "FAILED", str(exc))
            raise
