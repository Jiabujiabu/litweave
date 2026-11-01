"""Credential-free portable project snapshots and exports (not LangGraph memory)."""
import copy
import csv
import io
import json
import os
import tempfile
from pathlib import Path
from state import ResearchState

SCHEMA_VERSION = 1
SECRET_NAMES = {"api_key", "byok_api_key", "semantic_scholar_key", "authorization", "access_token", "client", "sdk_client", "credentials", "password"}
# Local paths and cached derived results are not trusted when imported.
OMIT = {"local_pdfs", "resume_stage", "document_cache", "card_cache", "support_cache"}


def reject_secrets(value):
    if isinstance(value, dict):
        for key,item in value.items():
            if str(key).lower() in SECRET_NAMES or str(key).lower().endswith("_api_key"):
                raise ValueError("Credentials/clients cannot be stored in a project")
            reject_secrets(item)
    elif isinstance(value, list):
        for item in value:
            reject_secrets(item)
    elif value is not None and type(value) not in (str, int, float, bool):
        raise ValueError("Project contains a non-JSON object")


def project_json(state, phase=None):
    data = {k:copy.deepcopy(v) for k,v in state.items() if k in ResearchState.__annotations__ and k not in OMIT}
    reject_secrets(data)
    stage = phase or state.get("project_phase", "papers")
    if stage not in ("papers", "directions", "outline", "done"):
        # Evidence extraction is synchronous; save a resumable human gate.
        stage = "papers"
    return json.dumps({"schema_version":SCHEMA_VERSION, "phase":stage, "state":data}, ensure_ascii=False, indent=2)


def load_project(data):
    if isinstance(data, bytes):
        if len(data)>20*1024*1024:
            raise ValueError("Project exceeds 20 MB")
        data = data.decode("utf-8-sig")
    if not isinstance(data, str) or len(data)>20*1024*1024:
        raise ValueError("Invalid project size")
    raw = json.loads(data)
    reject_secrets(raw)
    if not isinstance(raw, dict) or raw.get("schema_version")!=SCHEMA_VERSION or raw.get("phase") not in ("papers", "directions", "outline", "done") or not isinstance(raw.get("state"), dict):
        raise ValueError("Unsupported project format")
    state = raw["state"]
    if set(state)-set(ResearchState.__annotations__) or not isinstance(state.get("topic"), str) or not state["topic"].strip():
        raise ValueError("Invalid project state")
    from settings import Settings
    cfg = Settings.load(state.get("settings"))
    # Project files cannot choose a new filesystem destination for later cache writes.
    state["settings"] = {**cfg.to_dict(), "cache_dir":Settings.load().cache_dir}
    for field in ("paper_decisions", "collected_papers", "evidence", "chunks", "evidence_cards"):
        if not isinstance(state.get(field, []), list):
            raise ValueError("Invalid project collection")
    pids = [p.get("paper_id") for p in state.get("collected_papers", []) if isinstance(p, dict)]
    approved = state.get("approved_paper_ids", [])
    if len(pids)!=len(state.get("collected_papers", [])) or any(not isinstance(p,str) for p in pids) or len(pids)!=len(set(pids)):
        raise ValueError("Invalid project papers")
    if approved and set(approved)!=set(pids):
        raise ValueError("Corpus/paper mismatch")
    import hashlib
    chunk_map = {}
    for c in state.get("chunks", []):
        if not isinstance(c,dict) or c.get("paper_id") not in approved or not isinstance(c.get("text"),str) or not isinstance(c.get("chunk_id"),str) or c.get("content_hash")!=hashlib.sha256(c["text"].encode()).hexdigest():
            raise ValueError("Invalid project chunks")
        if c["chunk_id"] in chunk_map:
            raise ValueError("Duplicate project chunks")
        chunk_map[c["chunk_id"]] = c
    for e in state.get("evidence", []):
        if not isinstance(e, dict) or e.get("paper_id") not in approved or e.get("original_text")!=e.get("text") or not isinstance(e.get("text"),str) or e.get("evidence_level") not in ("abstract", "fulltext"):
            raise ValueError("Invalid project evidence")
        chunk = chunk_map.get(e.get("chunk_id"))
        if not chunk or any(e.get(k)!=chunk.get(k) for k in ("paper_id", "text", "content_hash", "evidence_level", "page_start", "page_end", "section", "is_reference")):
            raise ValueError("Evidence/chunk mismatch")
    eids = [e.get("evidence_id") for e in state.get("evidence", [])]
    if len(set(eids))!=len(eids) or any(not isinstance(eid,str) for eid in eids):
        raise ValueError("Invalid/duplicate evidence IDs")
    library={e['evidence_id']:e for e in state.get('evidence',[])}
    inputs=state.get('card_evidence',[])
    if not isinstance(inputs,list):raise ValueError('Invalid extraction inputs')
    seen=set()
    for e in inputs:
        eid=e.get('evidence_id') if isinstance(e,dict) else None
        if eid not in library or eid in seen or any(e.get(k)!=library[eid].get(k) for k in ('paper_id','chunk_id','text','original_text','content_hash','evidence_level','page_start','page_end','section','is_reference')):
            raise ValueError('Extraction input/library mismatch')
        seen.add(eid)
    if sum(len(e['text'])+512 for e in inputs)>cfg.context_tokens:
        raise ValueError('Extraction input context exceeds configured bound')
    # Persisted judgments are displayed as previous judgments, never a fresh validation.
    if state.get("outline"):
        from review_workflow import validate_outline
        validate_outline(state["outline"], state)
    if raw["phase"]=="outline" and not state.get("outline"):
        raise ValueError("Outline project has no outline")
    for e in state.get('direction_evidence',[]):
        if not isinstance(e,dict) or e.get('paper_id') not in approved or not isinstance(e.get('text'),str) or e.get('original_text')!=e['text'] or e.get('content_hash')!=hashlib.sha256(e['text'].encode()).hexdigest() or e.get('evidence_level') not in ('abstract','fulltext'):
            raise ValueError('Invalid direction source')
        if e['evidence_level']=='abstract' and e.get('page_start') is not None:raise ValueError('Invalid abstract location')
        if e['evidence_level']=='fulltext':
            c=chunk_map.get(e.get('chunk_id'))
            if not c or any(e.get(k)!=c.get(k) for k in ('paper_id','text','content_hash','page_start','page_end','evidence_level')):raise ValueError('Invalid fulltext direction mapping')
    if state.get('direction_options'):
        from directions import validate_directions
        validate_directions(state['direction_options'],state)
        options={d['direction_id']:d for d in state['direction_options']}
        if any(d!=options.get(d.get('direction_id')) for d in state.get('selected_directions',[])) or set(state.get('selected_direction_ids',[]))-set(options):
            raise ValueError('Invalid saved direction selection')
    for field in OMIT:
        state.pop(field, None)
    # Reuse portable processed text without re-reading private file paths from JSON.
    from papers import stable_id
    document_cache = {}
    for i,p in enumerate(state.get("collected_papers", [])):
        pid = p["paper_id"]
        signature = state.get("corpus_signatures", {}).get(pid)
        event = next((e for e in state.get("document_events", []) if e.get("paper_id")==pid), None)
        chunks = [c for c in state.get("chunks", []) if isinstance(c,dict) and c.get("paper_id")==pid and not c.get('card_input_window')
                  and not (event and event.get('evidence_level')=='fulltext' and c.get('source_role')=='metadata_abstract')]
        if signature and event and chunks and all(isinstance(c.get("text"),str) and isinstance(c.get("chunk_id"),str) and isinstance(c.get("content_hash"),str) and isinstance(c.get("is_reference"),bool) for c in chunks):
            document_cache[stable_id("doc_", [signature, event.get("fulltext_attempted", event.get("evidence_level")=="fulltext")])] = {"chunks":chunks, "event":event}
    state["document_cache"] = document_cache
    from review_workflow import validate_card
    card_cache = {}
    for card in state.get("evidence_cards", []):
        if not isinstance(card,dict) or card.get("paper_id") not in approved or not isinstance(card.get("card_id"),str):
            raise ValueError("Invalid evidence card")
        ev = [e for e in state.get("evidence", []) if e["paper_id"]==card["paper_id"]]
        validate_card(card.get("fields"), ev)
        card["excerpts"] = ev
        from card_inputs import cacheable
        if cacheable(card):
            card_cache[card["card_id"]] = card
    state["card_cache"] = card_cache
    state["local_pdfs"] = {}
    state["resume_stage"] = raw["phase"]
    state["project_phase"] = raw["phase"]
    state["restored_project"] = True
    return state


def save_project(path, state, phase=None):
    """Atomic replacement protects the previous snapshot if serialization fails."""
    payload = project_json(state, phase)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".project-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
        os.replace(temporary, path)
    finally:
        if Path(temporary).exists():
            Path(temporary).unlink()


def csv_text(rows, columns):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        # Avoid spreadsheet formula execution when opening untrusted paper text.
        clean = {}
        for key in columns:
            value = row.get(key, "")
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            value = str(value) if value is not None else ""
            clean[key] = "'"+value if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else value
        writer.writerow(clean)
    return "\ufeff"+stream.getvalue()


def exports(state):
    decisions = [{"paper_id":p["paper_id"], "title":p["title"], "landing_url":p.get("landing_url"), "doi":p.get("doi"),
                  "machine_status":p.get("relevance_status"), "machine_reason":p.get("relevance_reason"),
                  "human_decision":state.get("human_decisions", {}).get(p["paper_id"], {}).get("decision", "undecided"),
                  "human_reason":state.get("human_decisions", {}).get(p["paper_id"], {}).get("reason", ""),
                  "decision_source":state.get("human_decisions", {}).get(p["paper_id"], {}).get("source", "not_reviewed")} for p in state.get("paper_decisions", [])]
    cards = [{"paper_id":c["paper_id"], "card_id":c["card_id"], "corpus_version":c["corpus_version"], "evidence_level":c["evidence_level"], "field":field,
              **item, "support_status":c["support_status"], "excerpts":c["excerpts"]} for c in state.get("evidence_cards", []) for field,item in c["fields"].items()]
    return {"outline.md":state.get("final_report", ""),
            "evidence_cards.csv":csv_text(cards, ["paper_id", "card_id", "corpus_version", "evidence_level", "field", "status", "kind", "text", "evidence_ids", "support_status", "excerpts"]),
            "paper_decisions.csv":csv_text(decisions, ["paper_id", "title", "landing_url", "doi", "machine_status", "machine_reason", "human_decision", "human_reason", "decision_source"]),
            "project.json":project_json(state)}


def export_project(directory, state):
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    for name,data in exports(state).items():
        if name=="project.json":
            save_project(path/name, state)
        else:
            (path/name).write_text(data, encoding="utf-8")
    return path
