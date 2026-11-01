from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from state import ResearchState
from workflow import (decompose_directions, search_arxiv, search_crossref, process_papers,
                      summarize_literature, supplementary_search, prepare_feedback)
from review_workflow import (review_papers, freeze_corpus, prepare_approved_evidence,
                             extract_evidence_cards, generate_outline, check_outline, review_outline,retry_card_extraction)
from directions import suggest_directions, select_directions
from settings import Settings


def route_by_domain(state):
    return "search_crossref" if state.get("domain") == "humanities" else "search_arxiv"


def is_sufficient(state):
    cfg = Settings.load(state.get('settings'))
    if not state.get('results_shown') and state.get('retrieval_status')!='sufficient' and state.get('search_round',0)<min(cfg.initial_supplement_rounds,cfg.max_search_rounds):
        return 'supplementary_search'
    return "summarize_literature"


def start_at(state):
    return {"papers":"review_papers", "directions":"select_directions", "outline":"review_outline", "done":END,'retry_cards':'retry_card_extraction'}.get(state.get("resume_stage"), "decompose_directions")


def route_papers(state):
    return {"confirm":"freeze_corpus", "search":"supplementary_search", "rescope":"prepare_feedback", "review":"review_papers"}.get(state.get("review_action"), END)


def route_outline(state):
    return {"search":"supplementary_search", "papers":"review_papers", "directions":"select_directions", "check":"check_outline", "review":"review_outline",'retry_cards':'retry_card_extraction'}.get(state.get("outline_action"), END)


def route_directions(state):
    return {'generate':'prepare_approved_evidence', 'papers':'review_papers', 'search':'supplementary_search',
            'retry':'suggest_directions', 'review':'select_directions'}.get(state.get('direction_action'), END)


def build_graph():
    graph = StateGraph(ResearchState)
    for fn in (decompose_directions, search_arxiv, search_crossref, process_papers,
               supplementary_search, summarize_literature, review_papers, freeze_corpus,
               prepare_approved_evidence, extract_evidence_cards, generate_outline, check_outline,
               review_outline, prepare_feedback, suggest_directions, select_directions,retry_card_extraction):
        graph.add_node(fn.__name__, fn)
    graph.add_conditional_edges(START, start_at)
    graph.add_conditional_edges("decompose_directions", route_by_domain)
    graph.add_edge("search_arxiv", "search_crossref")
    graph.add_edge("search_crossref", "process_papers")
    graph.add_edge("supplementary_search", "process_papers")
    graph.add_conditional_edges("process_papers", is_sufficient)
    graph.add_edge("summarize_literature", "review_papers")
    graph.add_conditional_edges("review_papers", route_papers)
    graph.add_edge("prepare_feedback", "decompose_directions")
    graph.add_edge('freeze_corpus', 'suggest_directions')
    graph.add_edge('suggest_directions', 'select_directions')
    graph.add_edge('retry_card_extraction','generate_outline')
    graph.add_conditional_edges('select_directions', route_directions)
    for source, target in (
                          ("prepare_approved_evidence", "extract_evidence_cards"),
                          ("extract_evidence_cards", "generate_outline"),
                          ("generate_outline", "check_outline"), ("check_outline", "review_outline")):
        graph.add_edge(source, target)
    graph.add_conditional_edges("review_outline", route_outline)
    return graph.compile(checkpointer=MemorySaver())


app = build_graph()
