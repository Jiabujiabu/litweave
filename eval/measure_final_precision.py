"""Selected-paper model relevance, separate from actual report citations and support.
Historical values are not report factual accuracy or human validation.
Run only after explicitly authorizing ALLOW_PAID_EVAL=1 and RESEARCH_* budgets.
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from run_eval import load_test_set, run_case
from llm_judge import judge_chunk
from evaluation import relevance_metrics, report_metrics, save_run


def main():
    from nodes import MOCK_MODE
    if MOCK_MODE or os.getenv("ALLOW_PAID_EVAL") != "1":
        raise RuntimeError("Real evaluation disabled: configure a real provider, explicit ALLOW_PAID_EVAL=1 and local budgets")
    rows = []
    snapshots = []
    cases = load_test_set()
    for case in cases:
        try:
            state = run_case(case)
        except Exception as error:
            rows.append({"topic":case["topic"],"run_error":type(error).__name__,"selected_papers":None,"actual_citations":None})
            continue
        snapshots.append({"topic":case["topic"], **{k:state.get(k) for k in ("collected_papers","chunks","evidence","report_draft","claim_checks","settings","telemetry")}})
        papers = state["collected_papers"]
        labels, error = [], None
        try:
            judgments = judge_chunk(case["topic"], papers) if papers else []
            labels = [{"paper_id":papers[j["index"]]["paper_id"], "label":"direct" if j["relevant"] == "y" else "irrelevant", "source":"model"} for j in judgments]
        except Exception as e:
            error = type(e).__name__
            labels = [{"paper_id":p["paper_id"], "label":"error", "source":"none"} for p in papers]
        metrics = relevance_metrics([p["paper_id"] for p in papers],labels,source="model")
        report = report_metrics(state["report_draft"],state["evidence"],papers,state["claim_checks"])
        # Actual-citation relevance is computed on the used subset, never the whole selected list.
        used = report["actual_cited_paper_ids"]
        used_labels = [j for j in labels if j["paper_id"] in used]
        rows.append({"topic":case["topic"], "selected_papers":metrics, "actual_citations":relevance_metrics(used,used_labels,source="model"),
                     "report":report, "judge_error":error, "telemetry":state.get("telemetry")})
    from nodes import _MODEL, LLM_PROVIDER
    path = save_run({"harness":"selected_and_cited_model_relevance", "human_validation":"pending", "model":_MODEL,
                     "provider":LLM_PROVIDER,"judge_independence":"same configured provider; not independent"},snapshots,rows,mode="real_network")
    print(path)


if __name__ == "__main__":
    main()
