from typing import TypedDict, Literal

class ResearchState(TypedDict):
    topic: str
    language: Literal["en", "zh"]
    domain: Literal["cs", "humanities", "interdisciplinary"]
    research_directions: list[str]
    collected_papers: list[dict]
    literature_summary: str
    human_feedback: str
    approval_status: Literal["approved", "redo_search", "redo_directions"]
    final_report: str
    iteration_count: int
