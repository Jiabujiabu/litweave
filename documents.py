"""Open-access/local PDFs -> page-addressable evidence, with content/config caches."""
import hashlib
import importlib.metadata
import io
import json
import re
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit
import requests
from papers import stable_id
from runtime import ACTIVE, BudgetExceeded


def sha(data):
    return hashlib.sha256(data).hexdigest()


def token_spans(text):
    # Conservative units: each four ASCII characters, each non-ASCII character.
    # Not a provider tokenizer; context limits use the still-safer character bound.
    return list(re.finditer(r"[\x21-\x7e]{1,4}|[^\x00-\x7f]", text))


def chunks_from_pages(paper_id, pages, cfg, evidence_level="fulltext"):
    repeated = Counter()
    for page in pages:
        lines = [x.strip() for x in page.splitlines() if x.strip()]
        repeated.update(set(lines[:2] + lines[-2:]))
    boilerplate = {line for line, n in repeated.items() if len(pages) >= 3 and n >= max(3, len(pages) * .7)}
    chunks, section = [], None
    for page_no, page in enumerate(pages, 1):
        cleaned = "\n".join(line for line in page.splitlines() if line.strip() not in boilerplate and not re.fullmatch(r"\s*\d+\s*", line))
        # PDF extractors often lose blank lines: isolate recognizable headings first.
        cleaned = re.sub(r"(?im)^((?:\d+(?:\.\d+)*\.?\s+)?(?:abstract|introduction|methods?|results?|discussion|conclusions?|references|bibliography|参考文献))\s*$", r"\n\n\1\n\n", cleaned)
        for paragraph in re.split(r"\n\s*\n", cleaned):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            first_line = paragraph.splitlines()[0].strip()
            if re.match(r"^(?:\d+(?:\.\d+)*\.?\s+)?(?:abstract|introduction|methods?|results?|discussion|conclusions?|references|bibliography|参考文献)\b", first_line, re.I):
                section = first_line[:100]
                if paragraph == first_line:
                    continue
            spans = token_spans(paragraph)
            step = cfg.chunk_tokens - cfg.chunk_overlap
            for start in range(0, max(1, len(spans)), step):
                subset = spans[start:start + cfg.chunk_tokens]
                if not subset:
                    continue
                text = paragraph[subset[0].start():subset[-1].end()]
                loc = page_no if evidence_level == "fulltext" else None
                content_hash = sha(text.encode())
                key = [paper_id, evidence_level, section, loc, content_hash, start, cfg.chunk_tokens, cfg.chunk_overlap]
                chunks.append({"chunk_id": stable_id("c_", key), "paper_id": paper_id, "text": text,
                               "evidence_level": evidence_level, "section": section, "page_start": loc, "page_end": loc,
                               "location_status": "page" if loc else "abstract_no_page", "content_hash": content_hash,
                               "is_reference": bool(section and re.search(r"references|bibliography|参考文献", section, re.I))})
                if start + cfg.chunk_tokens >= len(spans):
                    break
    return chunks


def valid_pdf(data, cfg):
    if len(data) > cfg.max_download_mb * 1024 * 1024:
        raise ValueError("pdf_too_large")
    if not data.lstrip().startswith(b"%PDF-"):
        raise ValueError("not_a_pdf")


def fetch_pdf(paper, cfg):
    url = paper.get("open_access_url")
    parts = urlsplit(url or "")
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.hostname in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("no_valid_open_access_url")
    active = ACTIVE.get()
    if active:
        active.request()
    started = time.monotonic()
    with requests.get(url, timeout=cfg.timeout, stream=True, headers={"User-Agent": "AcademicResearchAgent/2.0"}) as response:
        response.raise_for_status()
        if int(response.headers.get("Content-Length", 0)) > cfg.max_download_mb * 1024 * 1024:
            raise ValueError("pdf_too_large")
        mime = response.headers.get("Content-Type", "").split(";")[0].lower()
        if mime not in ("application/pdf", "application/octet-stream"):
            raise ValueError("invalid_pdf_mime")
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > cfg.max_download_mb * 1024 * 1024 or time.monotonic() - started > cfg.timeout:
                raise ValueError("download_limit_exceeded")
            chunks.append(chunk)
        data = b"".join(chunks)
    valid_pdf(data, cfg)
    return data


def prepare_document(paper, cfg, local_pdf=None, *, allow_download=True):
    cache = Path(cfg.cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    status = {"paper_id": paper["paper_id"], "source_url": paper.get("open_access_url"), "paper_version": paper.get("arxiv_version"), "cache_hit": False}
    try:
        if not cfg.fulltext:
            raise ValueError("fulltext_disabled")
        if local_pdf:
            path = Path(local_pdf)
            if path.stat().st_size > cfg.max_download_mb * 1024 * 1024:
                raise ValueError("pdf_too_large")
            data = path.read_bytes()
            status["source_url"] = "local_pdf"  # do not leak private local filenames in logs
        else:
            if not allow_download or not paper.get("open_access_url"):
                raise ValueError("fulltext_unavailable")
            download_key = stable_id("download_", [paper["paper_id"], paper.get("open_access_url"), paper.get("arxiv_version")])
            pointer = cache / (download_key + ".json")
            if pointer.exists():
                metadata = json.loads(pointer.read_text())
                data = (cache / (metadata["content_hash"] + ".pdf")).read_bytes()
                if sha(data) != metadata["content_hash"]:
                    raise ValueError("download_cache_integrity_failure")
                status["download_cache_hit"] = True
            else:
                data = fetch_pdf(paper, cfg)
                content_hash = sha(data)
                (cache / (content_hash + ".pdf")).write_bytes(data)
                pointer.write_text(json.dumps({"content_hash": content_hash, "source_url": paper["open_access_url"]}), encoding="utf-8")
        valid_pdf(data, cfg)
        from pypdf import PdfReader
        parser = "pypdf-" + importlib.metadata.version("pypdf") + "/cleaner-v2"
        content_hash = sha(data)
        key = stable_id("parsed_", [paper["paper_id"], content_hash, parser, cfg.chunk_tokens, cfg.chunk_overlap, cfg.max_pages])
        path = cache / (key + ".json")
        status.update(content_hash=content_hash, parser_version=parser)
        if path.exists():
            cached = json.loads(path.read_text(encoding="utf-8"))
            return cached["chunks"], {**status, "cache_hit": True, "evidence_level": "fulltext"}
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            raise ValueError("encrypted_pdf")
        if len(reader.pages) > cfg.max_pages:
            raise ValueError("page_limit_exceeded")
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(pages)
        visible = [c for c in text if not c.isspace()]
        if len(visible) < 80 or sum(c.isalnum() for c in visible) / max(1, len(visible)) < .5 or text.count("\ufffd") / max(1, len(text)) > .02:
            raise ValueError("low_quality_or_scanned_pdf")
        lines = [line for page in pages for line in page.splitlines() if line.strip()]
        if len(lines) > 30 and sum(len(line.strip()) < 4 for line in lines) / len(lines) > .6:
            raise ValueError("severely_fragmented_pdf")
        chunks = chunks_from_pages(paper["paper_id"], pages, cfg)
        if not any(not c["is_reference"] for c in chunks):
            raise ValueError("no_scientific_text")
        path.write_text(json.dumps({"chunks": chunks, "provenance": status}, ensure_ascii=False), encoding="utf-8")
        return chunks, {**status, "evidence_level": "fulltext"}
    except Exception as error:
        # A document failure degrades locally; no exception/body/path enters prompts/logs.
        reason = str(error) if isinstance(error, ValueError) and re.fullmatch(r"[a-z_]+", str(error)) else type(error).__name__
        abstract = paper.get("abstract", "")
        chunks = chunks_from_pages(paper["paper_id"], [abstract], cfg, "abstract") if abstract else []
        return chunks, {**status, "evidence_level": "abstract" if chunks else "unavailable", "reason": reason}
