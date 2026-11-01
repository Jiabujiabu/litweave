"""Atomic claims, deterministic citation validation, auxiliary support judgments."""
import copy
import html
from urllib.parse import urlsplit, quote

SUPPORT_STATES = {"supported", "partially_supported", "unsupported", "insufficient_evidence"}


def validate_draft(draft):
    if not isinstance(draft, dict) or not isinstance(draft.get("sections"), list):
        raise ValueError("draft must contain sections")
    ids = set()
    for section in draft["sections"]:
        if not isinstance(section, dict) or not isinstance(section.get("heading"), str) or not isinstance(section.get("claims"), list):
            raise ValueError("invalid section schema")
        for claim in section["claims"]:
            if not isinstance(claim, dict) or any(not isinstance(claim.get(k), str) or not claim[k].strip() for k in ("claim_id", "text")):
                raise ValueError("claim needs ID and text")
            if claim["claim_id"] in ids:
                raise ValueError("duplicate claim ID")
            ids.add(claim["claim_id"])
            if not isinstance(claim.get("evidence_ids"), list) or not all(isinstance(x, str) for x in claim["evidence_ids"]):
                raise ValueError("invalid evidence ID list")
            if claim.get("kind", "author_finding") not in ("author_finding", "synthesis", "hypothesis"):
                raise ValueError("invalid claim kind")
            if claim.get("required_level", "abstract") not in ("abstract", "fulltext"):
                raise ValueError("invalid required evidence level")
    return draft


def claims_in(draft):
    return [c for s in draft.get("sections", []) for c in s["claims"]]


def prompt_evidence(evidence):
    return [{k: e.get(k) for k in ("evidence_id", "paper_id", "chunk_id", "original_text", "section", "page_start", "page_end", "evidence_level")} for e in evidence]


def deterministic_checks(draft, evidence, papers):
    validate_draft(draft)
    table = {e["evidence_id"]: e for e in evidence}
    paper_ids = {p["paper_id"] for p in papers}
    issues = []
    if len(table) != len(evidence):
        issues.append({"claim_id": None, "reason": "duplicate evidence IDs"})
    for c in claims_in(draft):
        ids = c["evidence_ids"]
        reason = []
        if not ids:
            reason.append("missing evidence citation")
        if len(set(ids)) != len(ids):
            reason.append("duplicate evidence citation")
        for eid in ids:
            e = table.get(eid)
            if not e:
                reason.append("unknown evidence ID: " + eid)
            elif e["paper_id"] not in paper_ids or not e.get("chunk_id") or e.get("original_text") != e.get("text"):
                reason.append("invalid paper/chunk/original-text mapping")
            elif e.get("evidence_level") not in ("abstract", "fulltext") or e.get("is_reference"):
                reason.append("unusable evidence level or reference list")
        if c.get("required_level") == "fulltext" and not any(table.get(eid, {}).get("evidence_level") == "fulltext" for eid in ids):
            reason.append("fulltext claim has only abstract evidence")
        if reason:
            issues.append({"claim_id": c["claim_id"], "reason": "; ".join(reason)})
    return issues


def support_check(claim, evidence, ask, lang, enabled=True, demo=False):
    if not enabled or demo:
        return {"claim_id": claim["claim_id"], "status": "not_checked", "reason": "demo mode" if demo else "support checking disabled", "judgment_source": "none"}
    try:
        result = ask("support", {"task": "Does the quoted evidence support this single atomic claim? Evaluate scope, population, numbers, and contradictions. Return status (supported/partially_supported/unsupported/insufficient_evidence), reason, contradiction (boolean). This is an auxiliary model judgment, not human verification.", "claim": claim, "evidence": prompt_evidence(evidence)}, lang)
        if not isinstance(result, dict) or result.get("status") not in SUPPORT_STATES or not isinstance(result.get("reason"), str) or not result["reason"].strip() or type(result.get("contradiction")) is not bool:
            raise ValueError("invalid support judgment")
        if result["contradiction"] and result["status"] == "supported":
            result["status"] = "unsupported"
        return {**result, "claim_id": claim["claim_id"], "judgment_source": "model_auxiliary"}
    except Exception:
        return {"claim_id": claim["claim_id"], "status": "not_checked", "reason": "model unavailable or invalid judgment", "judgment_source": "none"}


def evaluate_report(draft, evidence, papers, ask, cfg, lang="en", demo=False, previous_revisions=None):
    draft = copy.deepcopy(draft)
    counts = dict(previous_revisions or {})
    whitelist = {e["evidence_id"]: e for e in evidence}

    def evaluate():
        issues = deterministic_checks(draft, evidence, papers)
        invalid = {i["claim_id"] for i in issues}
        checks = []
        for claim in claims_in(draft):
            if claim["claim_id"] in invalid:
                checks.append({"claim_id": claim["claim_id"], "status": "insufficient_evidence", "reason": "deterministic citation failure", "judgment_source": "deterministic"})
            else:
                checks.append(support_check(claim, [whitelist[e] for e in claim["evidence_ids"]], ask, lang, cfg.check_claims, demo))
        return issues, checks

    issues, checks = evaluate()
    for check in list(checks):
        cid = check["claim_id"]
        if demo or check["status"] in ("supported", "not_checked") or counts.get(cid, 0) >= cfg.max_claim_revisions:
            continue
        claim = next(c for c in claims_in(draft) if c["claim_id"] == cid)
        counts[cid] = counts.get(cid, 0) + 1
        try:
            revised = ask("revise", {"task": "Locally narrow or weaken this claim using only supplied evidence. Return a replacement claim with unchanged claim_id, text, evidence_ids, kind, required_level; or {delete:true}. Do not add experiments/numbers. Resolve the listed failure.",
                                     "claim": claim, "failure": check, "citation_failures": [i for i in issues if i["claim_id"] == cid],
                                     "evidence": prompt_evidence([whitelist[e] for e in claim["evidence_ids"] if e in whitelist])}, lang)
            if not isinstance(revised, dict):
                raise ValueError("invalid revision")
            if revised.get("delete") is True:
                for s in draft["sections"]:
                    s["claims"] = [c for c in s["claims"] if c["claim_id"] != cid]
            else:
                if revised.get("claim_id") != cid:
                    raise ValueError("changed claim ID")
                validate_draft({"sections": [{"heading": "revision", "claims": [revised]}]})
                claim.clear()
                claim.update(revised)
        except Exception:
            continue
    # Re-run on FINAL text/IDs after local revisions; never inherit a prior pass.
    if counts != dict(previous_revisions or {}):
        issues, checks = evaluate()
    if not claims_in(draft):
        status = "not_applicable"
    elif issues:
        status = "failed"
    elif all(c["status"] == "supported" for c in checks) and not demo:
        status = "passed"
    else:
        status = "needs_review"
    return draft, issues, checks, status, counts


def safe_url(url):
    return quote(url, safe=":/?=&%#@+~") if isinstance(url, str) and urlsplit(url).scheme in ("https", "http") else ""


def render_report(topic, draft, evidence, papers, status, checks, *, lang="en", demo=False, limitations=None):
    zh = lang == "zh"
    table = {e["evidence_id"]: e for e in evidence}
    paper_map = {p["paper_id"]: p for p in papers}
    used_eids = sorted({eid for c in claims_in(draft) for eid in c["evidence_ids"] if eid in table})
    used_pids = sorted({table[eid]["paper_id"] for eid in used_eids if table[eid]["paper_id"] in paper_map})
    numbers = {pid: i for i, pid in enumerate(used_pids, 1)}
    lines = [f"# {html.escape(topic)}", "", f"**{'报告状态' if zh else 'Report status'}: {status}**",
             "模型支持性判断仅供辅助，尚需人工审核。" if zh else "Model support judgments are auxiliary; independent human review is still required."]
    if demo:
        lines.append("**MOCK / DEMO — 合成数据演示，不是科研结果。**" if zh else "**MOCK / DEMO — synthetic workflow demonstration, not research results.**")
    if not claims_in(draft):
        lines.append("未生成可评估的科学结论。" if zh else "No scientific claims available for evaluation.")
    for section in draft.get("sections", []):
        lines.extend(["", "## " + html.escape(section["heading"])])
        for c in section["claims"]:
            refs = []
            for eid in c["evidence_ids"]:
                if eid in table:
                    refs.append(f"[{eid}](#{eid})")
            level = "fulltext" if any(table.get(e, {}).get("evidence_level") == "fulltext" for e in c["evidence_ids"]) else "abstract_only"
            kind = c.get("kind", "author_finding")
            lines.append(f"\n- {html.escape(c['text'])} {' '.join(refs)} ({kind}; {level}; {c['claim_id']})")
    lines.extend(["", "## " + ("检查与局限" if zh else "Checks and limitations")])
    for check in checks:
        lines.append(f"- {check['claim_id']}: {check['status']} — {html.escape(check['reason'])}")
    for limit in limitations or []:
        lines.append("- " + html.escape(str(limit)))
    lines.extend(["", "## " + ("实际引用文献" if zh else "References used")])
    for pid in used_pids:
        p = paper_map[pid]
        url = safe_url(p.get("landing_url"))
        title = html.escape(p["title"]).replace("[", "\\[").replace("]", "\\]")
        label = f"[{title}]({url})" if url else title
        lines.append(f"{numbers[pid]}. {label}. {html.escape(', '.join(p.get('authors', [])))} ({p.get('year') or '?'}) DOI: {p.get('doi') or 'unknown'}")
    lines.extend(["", "## " + ("可定位原文证据" if zh else "Original evidence")])
    for eid in used_eids:
        e = table[eid]
        location = f"p. {e['page_start']}" if e.get("page_start") else "abstract; no page"
        lines.extend(["", f'<a id="{eid}"></a>', f"### {eid}",
                      f"{e['paper_id']} / {e['chunk_id']} — {location}; {html.escape(e.get('section') or 'section unknown')}; {e['evidence_level']}", "",
                      "\n".join("> " + html.escape(line) for line in e["original_text"].splitlines())])
    return "\n".join(lines) + "\n"
