"""Small local corpus: cached dense vectors + BM25 + reciprocal rank fusion."""
import json
import math
import re
from collections import Counter
from pathlib import Path
import numpy as np
from papers import stable_id


def terms(text):
    return re.findall(r"[a-z0-9_-]+|[\u4e00-\u9fff]", text.casefold())


def cosine(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def bm25(query, texts):
    corpus = [terms(t) for t in texts]
    average = sum(map(len, corpus)) / max(1, len(corpus))
    result = []
    for tokens in corpus:
        counts = Counter(tokens)
        score = 0.
        for term in set(terms(query)):
            df = sum(term in doc for doc in corpus)
            idf = math.log(1 + (len(corpus) - df + .5) / (df + .5))
            tf = counts[term]
            score += idf * tf * 2.5 / (tf + 1.5 * (.25 + .75 * len(tokens) / max(1, average)))
        result.append(score)
    return result


def build_index(chunks, embedder, cfg):
    chunks = sorted((c for c in chunks if not c["is_reference"]), key=lambda c: c["chunk_id"])
    model_name = getattr(embedder, "model_id", None) or getattr(embedder, "model_name_or_path", None)
    # Explicit model identity required for persistent reuse; stubs may provide one.
    key = stable_id("vectors_", [model_name, [(c["chunk_id"], c["content_hash"]) for c in chunks]])
    path = Path(cfg.cache_dir) / (key + ".json")
    if model_name and path.exists():
        cached = json.loads(path.read_text(encoding="utf-8"))
        if len(cached["vectors"]) == len(chunks):
            return chunks, np.asarray(cached["vectors"]), True
    vectors = np.asarray(embedder.encode([c["text"] for c in chunks])) if chunks else np.empty((0, 0))
    if model_name:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"model": model_name, "vectors": vectors.tolist(), "chunk_ids": [c["chunk_id"] for c in chunks]}), encoding="utf-8")
    return chunks, vectors, False


def retrieve(chunks, questions, embedder, cfg, reranker=None):
    indexed, vectors, cache_hit = build_index(chunks, embedder, cfg) if embedder is not None else (sorted((c for c in chunks if not c["is_reference"]), key=lambda c:c["chunk_id"]), None, False)
    if not indexed:
        return [], [{"reason": "no_usable_chunks"}], [q["question_id"] for q in questions]
    evidence, trace, gaps, used_budget = [], [], [], 0
    for q in questions:
        query = q.get("query") or q["text"]
        query_vector = embedder.encode([query])[0] if embedder is not None else None
        dense = [cosine(query_vector, v) for v in vectors] if embedder is not None else [0.]*len(indexed)
        lexical = bm25(query, [c["text"] for c in indexed])
        dense_order = sorted(range(len(indexed)), key=lambda i: (-dense[i], indexed[i]["chunk_id"]))
        sparse_order = sorted(range(len(indexed)), key=lambda i: (-lexical[i], indexed[i]["chunk_id"]))
        scores = {i: dense[i] for i in dense_order}
        if embedder is None:
            scores = {i:lexical[i] for i in sparse_order}
        elif cfg.retrieval_mode == "hybrid":
            scores = {i: 0. for i in dense_order}
            for order in (dense_order, sparse_order):
                for rank, i in enumerate(order, 1):
                    scores[i] += 1 / (60 + rank)
        order = sorted(scores, key=lambda i: (-scores[i], indexed[i]["chunk_id"]))
        rerank_scores = {}
        if cfg.rerank:
            if reranker is None:
                raise ValueError("rerank requires an explicit reranker")
            shortlist = order[:20]
            ranked = reranker(query, [indexed[i] for i in shortlist])
            expected = {indexed[i]["chunk_id"] for i in shortlist}
            if not isinstance(ranked, dict) or set(ranked) != expected or any(not isinstance(v, (float, int)) or not math.isfinite(v) for v in ranked.values()):
                raise ValueError("invalid reranker output IDs/scores")
            rerank_scores = ranked
            order = sorted(shortlist, key=lambda i: (-ranked[indexed[i]["chunk_id"]], indexed[i]["chunk_id"]))
        per_paper, hashes, selected = Counter(), set(), []
        candidates = []
        for i in order:
            c = indexed[i]
            candidates.append({"chunk_id": c["chunk_id"], "dense": dense[i], "bm25": lexical[i], "fused": scores[i], "rerank": rerank_scores.get(c["chunk_id"])})
            if len(selected) >= cfg.top_evidence or c["content_hash"] in hashes or per_paper[c["paper_id"]] >= cfg.per_paper_chunks:
                continue
            # Deterministic skip, never cut off text without changing its ID/location.
            cost = len(c["text"]) + 512
            if used_budget + cost > cfg.context_tokens:
                continue
            used_budget += cost
            per_paper[c["paper_id"]] += 1
            hashes.add(c["content_hash"])
            eid = stable_id("e_", [q["question_id"], c["chunk_id"]])
            evidence.append({**c, "evidence_id": eid, "question_id": q["question_id"], "original_text": c["text"],
                             "score": scores[i], "method": cfg.retrieval_mode if embedder is not None else "bm25_fallback", "rerank_method": getattr(reranker, "method", "none") if cfg.rerank else "off"})
            selected.append(eid)
        if not selected:
            gaps.append(q["question_id"])
        trace.append({"question_id": q["question_id"], "mode": cfg.retrieval_mode if embedder is not None else "bm25_fallback", "rerank": cfg.rerank,
                      "index_cache_hit": cache_hit, "candidates": candidates, "selected": selected, "context_units": used_budget})
    return evidence, trace, gaps


def lexical_reranker(query, chunks):
    """Optional local exact-term baseline, not an independent learned relevance judge."""
    return {c["chunk_id"]: score for c, score in zip(chunks, bm25(query, [c["text"] for c in chunks]))}


lexical_reranker.method = "local_bm25_rerank_baseline"
