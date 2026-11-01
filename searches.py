"""Bounded public-source requests. Failures and genuine empty hits stay distinct."""
import email.utils
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import requests
from papers import normalize_paper
from runtime import ACTIVE, BudgetExceeded

ENDPOINTS = {"arXiv": "https://export.arxiv.org/api/query", "CrossRef": "https://api.crossref.org/works",
             "Semantic Scholar": "https://api.semanticscholar.org/graph/v1/paper/search"}


def retry_delay(value, attempt):
    try:
        delay = float(value)
    except (TypeError, ValueError):
        try:
            delay = (email.utils.parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            delay = 2 ** attempt
    return max(0., delay)


def search(source, query, settings, *, get=None, sleep=time.sleep):
    get = get or requests.get
    events = []
    headers = {"User-Agent": "AcademicResearchAgent/2.0 (personal literature assistant)"}
    if source == "arXiv":
        params = {"search_query": "all:" + query, "max_results": 6}
    elif source == "CrossRef":
        params = {"query": query, "rows": 6}
    else:
        params = {"query": query, "limit": 6, "fields": "title,abstract,url,authors,year,externalIds,openAccessPdf"}
        from model_access import current_access
        access = current_access()
        if access is not None and access.semantic_scholar_key:
            headers["x-api-key"] = access.semantic_scholar_key
    for attempt in range(settings.search_retries + 1):
        status, detail, retry = "failed", "", False
        response = None
        started = time.monotonic()
        try:
            active = ACTIVE.get()
            if active:
                active.request()
                last = active.data.setdefault("source_last_request", {}).get(source, 0)
                interval = 3. if source == "arXiv" else 1.
                sleep(max(0., interval - (time.time() - last)))
                active.data["source_last_request"][source] = time.time()
            response = get(ENDPOINTS[source], params=params, headers=headers, timeout=settings.timeout)
            if response.status_code == 429:
                status, detail, retry = "rate_limited", "HTTP 429", True
            elif response.status_code >= 500:
                detail, retry = f"HTTP {response.status_code}", True
            elif response.status_code != 200:
                detail = f"HTTP {response.status_code}"
            else:
                if source == "arXiv":
                    ns = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom"}
                    root = ET.fromstring(response.content)
                    rows = []
                    for e in root.findall("a:entry", ns):
                        if e.findtext("a:title", "", ns).strip().lower() == "error":
                            raise ValueError("arXiv query error")
                        rows.append({"title": e.findtext("a:title", "", ns), "abstract": e.findtext("a:summary", "", ns),
                                     "url": e.findtext("a:id", "", ns), "doi": e.findtext("x:doi", "", ns),
                                     "year": e.findtext("a:published", "", ns)[:4],
                                     "authors": [a.findtext("a:name", "", ns) for a in e.findall("a:author", ns)]})
                else:
                    data = response.json()
                    rows = data.get("message", {}).get("items") if source == "CrossRef" else data.get("data")
                    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
                        raise ValueError("invalid source response schema")
                papers = [normalize_paper(r, source) for r in rows]
                events.append({"source": source, "query": query, "status": "success" if papers else "empty", "count": len(papers), "attempt": attempt, "seconds": round(time.monotonic() - started, 4)})
                return papers, events
        except requests.Timeout:
            status, detail, retry = "timeout", "request timeout", True
        except BudgetExceeded:
            detail = "request budget exhausted"
        except (requests.RequestException, ValueError, ET.ParseError):
            detail, retry = "network or response parsing failure", True
        events.append({"source": source, "query": query, "status": status, "detail": detail, "attempt": attempt,
                       "seconds": round(time.monotonic() - started, 4)})
        if not retry or attempt >= settings.search_retries:
            break
        delay = retry_delay(response.headers.get("Retry-After") if response is not None else None, attempt)
        if delay > 30:
            events[-1]["detail"] += "; Retry-After exceeds local wait bound; deferred rather than retried early"
            break
        sleep(delay)
    return [], events
