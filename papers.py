"""Source adapters and conservative, reproducible paper identity resolution."""
import hashlib
import html
import json
import re
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import unquote


def stable_id(prefix, value):
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    return prefix + hashlib.sha256(encoded).hexdigest()[:20]


def clean_abstract(value):
    if not isinstance(value, str) or value.strip().lower() in ("n/a", "none", "null", "not available"):
        return ""
    value = re.sub(r"</?(?:jats:)?(?:p|sec|title)[^>]*>", "\n\n", value, flags=re.I)
    value = html.unescape(re.sub(r"<[^>]+>", "", value))
    return re.sub(r"\n\s*\n(?:\s*\n)+", "\n\n", value).strip()


def normalize_doi(value):
    value = unquote(str(value or "")).strip().lower()
    value = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value)
    return value if re.fullmatch(r"10\.\d{4,9}/\S+", value) else None


def normalize_arxiv(value):
    match = re.search(r"(?:arxiv:|arxiv\.org/(?:abs|pdf)/)?((?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[a-z-]+)?/\d{7}))(v\d+)?(?:\.pdf)?$", str(value or "").strip(), re.I)
    return (match[1].lower(), match[2] or None) if match else (None, None)


def normalized_title(title):
    return " ".join(re.findall(r"\w+", str(title).casefold()))


def normalize_paper(raw, source=None):
    source = source or raw.get("source", "unknown")
    title = raw.get("title") or ""
    title = title[0] if isinstance(title, list) and title else title
    title = raw.get("raw_title", title)
    raw_title = raw.get("raw_title", str(title))
    # Decode source entities once before rendering; retain Unicode/math characters.
    title = html.unescape(str(title))
    title = re.sub(r"</?(?:jats:)?(?:i|b|em|strong|sup|sub|title|span)(?:\s[^>]*)?>", "", title, flags=re.I)
    title = " ".join(unicodedata.normalize("NFC", title).split())
    url = raw.get("landing_url") or raw.get("url") or raw.get("URL") or ""
    external = raw.get("externalIds") or {}
    doi = normalize_doi(raw.get("doi") or raw.get("DOI") or external.get("DOI") or url)
    arxiv_id, arxiv_version = normalize_arxiv(raw.get("arxiv_id") or external.get("ArXiv") or url)
    if not url:
        url = f"https://doi.org/{doi}" if doi else f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else ""
    if arxiv_id and not arxiv_version:
        url_id, url_version = normalize_arxiv(url)
        if url_id == arxiv_id:
            arxiv_version = url_version
    authors = raw.get("authors") or raw.get("author") or []
    authors = authors if isinstance(authors, list) else []
    authors = [a if isinstance(a, str) else str(a.get("name") or " ".join(str(x) for x in (a.get("given"), a.get("family")) if x)) for a in authors if isinstance(a, (str, dict))]
    authors = sorted(set(a.strip() for a in authors if a and a.strip()), key=str.casefold)
    year = raw.get("year")
    if not year:
        for field in ("published-print", "published-online", "published", "issued"):
            parts = (raw.get(field) or {}).get("date-parts", [])
            if parts and parts[0]:
                year = parts[0][0]
                break
    try:
        year = int(year) if year else None
    except (TypeError, ValueError):
        year = None
    abstract = clean_abstract(raw.get("abstract") or raw.get("summary"))
    oa = raw.get("open_access_url") or (raw.get("openAccessPdf") or {}).get("url")
    if arxiv_id and not oa:
        oa = f"https://arxiv.org/pdf/{arxiv_id}{arxiv_version or ''}"
    identity = "doi:" + doi if doi else "arxiv:" + arxiv_id if arxiv_id else json.dumps([normalized_title(title), authors, year, url], sort_keys=True)
    record = {"source": source, "url": url, "doi": doi, "arxiv_id": arxiv_id, "arxiv_version": arxiv_version}
    return {**raw, "paper_id": stable_id("p_", identity), "title": title, "raw_title": raw_title, "authors": authors, "year": year,
            "doi": doi, "arxiv_id": arxiv_id, "arxiv_version": raw.get("arxiv_version") or arxiv_version,
            "source_records": raw.get("source_records") or [record], "landing_url": url,
            "open_access_url": oa, "abstract": abstract, "abstract_status": "available" if abstract else "missing",
            "quality_flags": [f for f, missing in (("missing_title", not title), ("missing_abstract", not abstract), ("missing_year", not year), ("replacement_character_in_title", '\ufffd' in title)) if missing],
            "summary": abstract, "url": url, "source": source,
            "related_versions": raw.get("related_versions", []), "identity_conflicts": raw.get("identity_conflicts", []),
            "merge_reasons": raw.get("merge_reasons", [])}


def deduplicate(records):
    # Strong identifiers first; stable source order makes merges input-order independent.
    candidates = sorted((normalize_paper(p) for p in records), key=lambda p: (not bool(p["doi"]), p["paper_id"], -len(p["abstract"]), p["source"]))
    merged = []
    for paper in candidates:
        target, reason = None, None
        for other in merged:
            conflict = any(paper[k] and other[k] and paper[k] != other[k] for k in ("doi", "arxiv_id"))
            shared = next((k for k in ("doi", "arxiv_id") if paper[k] and paper[k] == other[k]), None)
            if not shared and paper["paper_id"] == other["paper_id"]:
                shared = "record_fingerprint"
            same_title = bool(paper["title"] and other["title"]) and SequenceMatcher(None, normalized_title(paper["title"]), normalized_title(other["title"])).ratio() >= .98
            shared_author = bool({a.casefold() for a in paper["authors"]} & {a.casefold() for a in other["authors"]})
            same_year = paper["year"] is not None and paper["year"] == other["year"]
            version_pair = bool(paper["arxiv_id"]) != bool(other["arxiv_id"]) and bool(paper["doi"]) != bool(other["doi"])
            if same_title and conflict:
                other["identity_conflicts"] = sorted(set(other["identity_conflicts"] + [paper["paper_id"]]))
                paper["identity_conflicts"] = sorted(set(paper["identity_conflicts"] + [other["paper_id"]]))
            if same_title and shared_author and version_pair and not conflict:
                other["related_versions"] = sorted(set(other["related_versions"] + [paper["paper_id"]]))
                paper["related_versions"] = sorted(set(paper["related_versions"] + [other["paper_id"]]))
            if not conflict and (shared or (same_title and shared_author and same_year and not version_pair)):
                target, reason = other, shared or "title_author_year"
                break
        if target is None:
            merged.append(paper)
            continue
        target["merge_reasons"] = sorted(set(target["merge_reasons"] + paper["merge_reasons"] + [reason]))
        for record in paper["source_records"]:
            if record not in target["source_records"]:
                target["source_records"].append(record)
        target["source_records"].sort(key=lambda r: json.dumps(r, sort_keys=True))
        if len(paper["abstract"]) > len(target["abstract"]):
            target["abstract"] = target["summary"] = paper["abstract"]
            target["abstract_status"] = "available"
        for k in ("doi", "arxiv_id", "arxiv_version", "open_access_url", "year"):
            if not target[k]:
                target[k] = paper[k]
        target["authors"] = sorted(set(target["authors"] + paper["authors"]), key=str.casefold)
        target["related_versions"] = sorted(set(target["related_versions"] + paper["related_versions"]))
        target["identity_conflicts"] = sorted(set(target["identity_conflicts"] + paper["identity_conflicts"]))
        target["query_question_ids"] = sorted(set(target.get("query_question_ids", []) + paper.get("query_question_ids", [])))
        target["quality_flags"] = [f for f, missing in (("missing_title", not target["title"]), ("missing_abstract", not target["abstract"]), ("missing_year", not target["year"])) if missing]
    # Conflicting identifiers can share the preferred DOI key. Preserve both records
    # with deterministic disambiguated IDs instead of emitting duplicate paper IDs.
    counts = {}
    for p in merged:
        counts[p["paper_id"]] = counts.get(p["paper_id"], 0) + 1
    aliases = {}
    for p in merged:
        old = p["paper_id"]
        if counts[old] > 1:
            p["paper_id"] = stable_id("p_", [old, p["doi"], p["arxiv_id"], p["title"], p["authors"], p["year"], p["landing_url"]])
        aliases.setdefault(old, []).append(p["paper_id"])
    for p in merged:
        for field in ("identity_conflicts", "related_versions"):
            p[field] = sorted({pid for old in p[field] for pid in aliases.get(old, [old]) if pid != p["paper_id"]})
    return sorted(merged, key=lambda p: p["paper_id"])
