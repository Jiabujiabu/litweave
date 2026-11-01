"""Validated engineering limits. No network or model calls at import time."""
import os
from dataclasses import asdict, dataclass, fields


@dataclass(frozen=True)
class Settings:
    max_papers: int = 10
    min_papers: int = 5
    max_fulltexts: int = 10
    max_search_rounds: int = 2
    initial_supplement_rounds: int = 1
    max_review_rounds: int = 3
    max_claim_revisions: int = 1
    max_requests: int = 80
    max_model_calls: int = 30
    max_output_tokens: int = 4096
    max_total_tokens: int = 100000
    context_tokens: int = 12000
    timeout: int = 20
    max_download_mb: int = 20
    max_pages: int = 100
    chunk_tokens: int = 500
    chunk_overlap: int = 75
    top_evidence: int = 4
    per_paper_chunks: int = 2
    search_retries: int = 2
    retrieval_mode: str = "hybrid"
    rerank: bool = False
    check_claims: bool = True
    fulltext: bool = True
    cache_dir: str = ".research_cache"

    @classmethod
    def load(cls, overrides=None):
        values = {}
        defaults = cls()
        for f in fields(cls):
            raw = os.getenv("RESEARCH_" + f.name.upper())
            if raw is None:
                continue
            default = getattr(defaults, f.name)
            if isinstance(default, bool):
                if raw.lower() not in ("0", "1", "true", "false"):
                    raise ValueError(f"Invalid boolean: RESEARCH_{f.name.upper()}")
                values[f.name] = raw.lower() in ("1", "true")
            elif isinstance(default, int):
                values[f.name] = int(raw)
            else:
                values[f.name] = raw
        values.update(overrides or {})
        result = cls(**values)
        for f in fields(cls):
            value = getattr(result, f.name)
            if isinstance(getattr(defaults, f.name), bool):
                if not isinstance(value, bool):
                    raise ValueError(f"{f.name} must be boolean")
            elif isinstance(getattr(defaults, f.name), int):
                if type(value) is not int or value < 0:
                    raise ValueError(f"{f.name} must be a nonnegative integer")
        if result.chunk_tokens < 1 or result.chunk_overlap >= result.chunk_tokens:
            raise ValueError("Require 0 <= chunk_overlap < chunk_tokens")
        if result.min_papers > result.max_papers or result.timeout < 1:
            raise ValueError("Invalid paper limits/timeout")
        if result.retrieval_mode not in ("dense", "hybrid"):
            raise ValueError("retrieval_mode must be dense or hybrid")
        return result

    def to_dict(self):
        return asdict(self)
