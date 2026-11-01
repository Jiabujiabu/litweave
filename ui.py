"""Shared user-facing review options and redacted status summaries."""
from i18n import t


def review_choices(payload, lang):
    keys = {"1": "accept_partial" if payload.get("retrieval_status") != "sufficient" else "web_choice_approve",
            "2": "web_choice_redo_search", "3": "web_choice_redo_directions", "4": "end_research", "5": "rewrite_only"}
    return {code: t(lang, keys[code]) for code in payload.get("allowed_choices", ["1","2","3","4","5"])}


def status_line(state, lang):
    return t(lang, "run_status", candidates=state.get("candidate_count", 0), papers=len(state.get("collected_papers", [])),
             status=state.get("retrieval_status", "unknown"), report=state.get("citation_check", "not_checked"))
