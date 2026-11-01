"""Offline evaluation primitives. Human/model/unjudged provenance is never conflated."""
import csv
import hashlib
import importlib.metadata
import json
import random
import subprocess
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from papers import deduplicate, stable_id
from reports import claims_in

LABELS = {"direct", "partial", "irrelevant", "insufficient_information", "error", "unjudged"}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def validate_labels(paper_ids, labels):
    expected = set(paper_ids)
    found = {}
    for label in labels:
        pid = label.get("paper_id")
        if pid not in expected or pid in found or label.get("label") not in LABELS or label.get("source") not in ("human", "model", "none"):
            raise ValueError("unknown/duplicate ID, label or provenance")
        if label["label"] in ("direct", "partial", "irrelevant") and label["source"] == "none":
            raise ValueError("judged labels need human/model provenance")
        found[pid] = label
    return {pid: found.get(pid, {"paper_id":pid, "label":"unjudged", "source":"none"}) for pid in paper_ids}


def relevance_metrics(ranked_ids, labels, k=5, *, source="human", known_relevant_ids=None):
    if len(set(ranked_ids)) != len(ranked_ids) or k <= 0:
        raise ValueError("duplicate ranking IDs or invalid k")
    table = validate_labels(ranked_ids, labels)
    judged = [pid for pid in ranked_ids if table[pid]["label"] in ("direct", "partial", "irrelevant") and table[pid]["source"] == source]
    direct = [pid for pid in judged if table[pid]["label"] == "direct"]
    # P@k is unavailable until every returned item up to k is judged by the requested source.
    complete = all(pid in judged for pid in ranked_ids[:k])
    return {"label_source":source, "selected_paper_relevance": len(direct) / len(judged) if judged else None,
            "judged":len(judged), "direct":len(direct), "unjudged":len(ranked_ids)-len(judged),
            "errors":sum(table[p]["label"] == "error" for p in ranked_ids),
            "precision_at_k":sum(pid in direct for pid in ranked_ids[:k]) / k if complete else None,
            "k":k, "short_list_policy":"missing slots count nonrelevant; unjudged returned slots make P@k unavailable",
            "known_set_coverage":len(set(ranked_ids) & set(known_relevant_ids)) / len(set(known_relevant_ids)) if known_relevant_ids else None}


def report_metrics(draft, evidence, papers, checks):
    claims = claims_in(draft)
    etable = {e["evidence_id"]:e for e in evidence}
    pids = {p["paper_id"] for p in papers}
    cited = [eid for c in claims for eid in c["evidence_ids"]]
    valid = [eid for eid in cited if eid in etable and etable[eid]["paper_id"] in pids]
    return {"scientific_claims":len(claims),
            "citation_integrity":len(valid)/len(cited) if cited else (0. if claims else None),
            "citation_coverage":sum(any(eid in etable and etable[eid]["paper_id"] in pids for eid in c["evidence_ids"]) for c in claims)/len(claims) if claims else None,
            "actual_cited_paper_ids":sorted({etable[eid]["paper_id"] for eid in valid}),
            "support_distribution":dict(Counter(c["status"] for c in checks)),
            "support_judgment_sources":dict(Counter(c.get("judgment_source", "none") for c in checks))}


def blind_export(cases, directory, seed=4131):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    rows, mapping = [], {}
    for case in cases:
        for p in deduplicate(case["papers"]):
            bid = stable_id("b_", [seed, case["topic"], p["paper_id"]])
            rows.append({"blind_id":bid, "topic":case["topic"], "title":p["title"], "abstract":p["abstract"],
                         "url":p["landing_url"], "human_label":"", "human_reason":""})
            mapping[bid] = {"paper_id":p["paper_id"], "topic":case["topic"]}
    random.Random(seed).shuffle(rows)
    with (directory / "blind_candidates.csv").open("w",encoding="utf-8-sig",newline="") as f:
        writer = csv.DictWriter(f,fieldnames=["blind_id","topic","title","abstract","url","human_label","human_reason"])
        writer.writeheader()
        writer.writerows(rows)
    # This file is retained by the evaluator, not distributed to annotators.
    (directory / "evaluator_mapping.json").write_text(json.dumps(mapping,ensure_ascii=False,indent=2),encoding="utf-8")
    return len(rows)


def save_run(config, snapshot, rows, root=".research_runs", *, mode="offline_replay", seed=4131):
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:8]
    path = Path(root) / run_id
    path.mkdir(parents=True, exist_ok=False)
    try:
        commit = subprocess.check_output(["git","rev-parse","HEAD"],text=True,stderr=subprocess.DEVNULL).strip()
        diff = subprocess.check_output(["git","diff","HEAD"],stderr=subprocess.DEVNULL)
        worktree_hash = hashlib.sha256(diff).hexdigest()
    except (OSError,subprocess.CalledProcessError):
        commit, worktree_hash = "unknown", "unknown"
    versions = {}
    for name in ("numpy","langgraph","pypdf","sentence-transformers"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "unavailable"
    sources = list(Path('.').glob('*.py')) + list(Path('eval').glob('*.py')) + [Path('requirements.txt'),Path('eval/splits.json')]
    source_files = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(sources) if p.exists()}
    manifest = {"run_id":run_id,"mode":mode,"time_utc":datetime.now(timezone.utc).isoformat(),
                "config":config,"config_hash":digest(config),"snapshot_hash":digest(snapshot),"commit":commit,
                "tracked_diff_hash":worktree_hash,"source_hash":digest(source_files),"dependencies":versions,"seed":seed,
                "model":"none" if mode in ("offline_replay","human_offline") else config.get("model", "unknown"), "embedding":config.get("embedding", "unknown"),
                "judge_prompt_version":"support-v1", "human_annotation":config.get("human_annotation", "pending")}
    (path / 'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (path / 'snapshot.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2),encoding='utf-8')
    (path / 'results.jsonl').write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows),encoding='utf-8')
    flat = [{k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()} for row in rows]
    with (path / 'summary.csv').open('w',encoding='utf-8-sig',newline='') as f:
        keys = sorted({k for row in flat for k in row})
        writer = csv.DictWriter(f,fieldnames=keys)
        writer.writeheader()
        writer.writerows(flat)
    return path
