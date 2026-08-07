from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from state import ResearchState
from nodes import (
    decompose_directions, search_arxiv, search_crossref,
    search_semantic_scholar, summarize_literature,
    human_approval, generate_report
)

SUFFICIENT_THRESHOLD = 6  # 至少 6 篇论文视为充足

def route_by_domain(state: ResearchState) -> str:
    """decompose_directions 之后，根据领域选择首要搜索库"""
    domain = state["domain"]
    if domain == "humanities":
        return "search_crossref"
    else:  # cs 或 interdisciplinary 都先搜 arXiv
        return "search_arxiv"

def route_after_arxiv(state: ResearchState) -> str:
    """search_arxiv 之后：interdisciplinary 继续搜 CrossRef，cs 判断是否充足"""
    if state["domain"] == "interdisciplinary":
        return "search_crossref"
    if len(state["collected_papers"]) >= SUFFICIENT_THRESHOLD:
        return "summarize_literature"
    return "search_semantic_scholar"

def is_sufficient(state: ResearchState) -> str:
    """search_crossref 之后：判断是否充足（humanities 和 interdisciplinary 共用）"""
    if len(state["collected_papers"]) >= SUFFICIENT_THRESHOLD:
        return "summarize_literature"
    return "search_semantic_scholar"

def route_after_approval(state: ResearchState) -> str:
    """human_approval 之后：三条出路"""
    status = state["approval_status"]
    if status == "approved":
        return "generate_report"
    elif status == "redo_directions":
        return "decompose_directions"
    else:  # redo_search：根据 domain 回到对应的首要搜索节点
        domain = state["domain"]
        if domain == "humanities":
            return "search_crossref"
        else:
            return "search_arxiv"


def build_graph():
    graph = StateGraph(ResearchState)

    graph.add_node("decompose_directions", decompose_directions)
    graph.add_node("search_arxiv", search_arxiv)
    graph.add_node("search_crossref", search_crossref)
    graph.add_node("search_semantic_scholar", search_semantic_scholar)
    graph.add_node("summarize_literature", summarize_literature)
    graph.add_node("human_approval", human_approval)
    graph.add_node("generate_report", generate_report)

    graph.add_edge(START, "decompose_directions")
    graph.add_edge("search_semantic_scholar", "summarize_literature")
    graph.add_edge("summarize_literature", "human_approval")
    graph.add_edge("generate_report", END)

    graph.add_conditional_edges(
        "decompose_directions",
        route_by_domain,
        {"search_arxiv": "search_arxiv", "search_crossref": "search_crossref"}
    )

    graph.add_conditional_edges(
        "search_arxiv",
        route_after_arxiv,
        {
            "search_crossref": "search_crossref",
            "summarize_literature": "summarize_literature",
            "search_semantic_scholar": "search_semantic_scholar"
        }
    )

    graph.add_conditional_edges(
        "search_crossref",
        is_sufficient,
        {
            "summarize_literature": "summarize_literature",
            "search_semantic_scholar": "search_semantic_scholar"
        }
    )

    graph.add_conditional_edges(
        "human_approval",
        route_after_approval,
        {
            "generate_report": "generate_report",
            "decompose_directions": "decompose_directions",
            "search_arxiv": "search_arxiv",
            "search_crossref": "search_crossref"
        }
    )

    # Checkpointer is required for interrupt()/Command(resume=...) in human_approval:
    # it persists state between the pause and the resume call, keyed by thread_id.
    return graph.compile(checkpointer=MemorySaver())

app = build_graph()
