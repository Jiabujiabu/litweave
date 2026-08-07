import os
import json
import time
import arxiv
import requests
from openai import OpenAI
from dotenv import load_dotenv
from langgraph.types import interrupt

from state import ResearchState
from i18n import t

load_dotenv()

_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
MOCK_MODE = (not _API_KEY) or _API_KEY == "your_key_here"

client = OpenAI(
    api_key=_API_KEY or "mock",
    base_url="https://api.deepseek.com"
)


# ---------------------------------------------------------------------------
# LLM call (with offline MOCK fallback when no real API key is configured)
# ---------------------------------------------------------------------------

def _mock_llm(task: str, language: str, **ctx) -> str:
    """Demo/offline fallback used when DEEPSEEK_API_KEY isn't configured.
    Returns structurally-correct placeholder content in the requested language."""

    if task == "decompose":
        topic = ctx["topic"]
        lower = topic.lower()
        humanities_kw = ["历史", "文学", "哲学", "艺术", "社会学", "政治", "法学",
                          "history", "literature", "philosophy", "art", "sociology", "politics", "law"]
        cs_kw = ["ai", "机器学习", "算法", "计算机", "神经网络", "编程", "数据",
                 "machine learning", "algorithm", "computer", "neural network", "programming", "data"]
        if any(k in topic or k in lower for k in humanities_kw):
            domain = "humanities"
        elif any(k in topic or k in lower for k in cs_kw):
            domain = "cs"
        else:
            domain = "interdisciplinary"

        if language == "zh":
            directions = [
                f"{topic}的研究现状与主要挑战",
                f"{topic}的关键方法与技术路径",
                f"{topic}的典型应用场景",
                f"{topic}的未来发展趋势",
            ]
        else:
            directions = [
                f"Current state and key challenges of {topic}",
                f"Core methods and approaches in {topic}",
                f"Representative applications of {topic}",
                f"Future directions for {topic}",
            ]
        return json.dumps({"domain": domain, "directions": directions}, ensure_ascii=False)

    if task == "summarize":
        if language == "zh":
            return (
                "[MOCK] 当前相关研究主要围绕方法演进、应用落地与理论基础三条主线展开。"
                "多数论文关注在真实场景中的有效性验证，但对长期影响和跨领域迁移能力的讨论较少，"
                "不同研究团队在评价标准上尚未形成统一共识，仍存在方法论层面的争议。"
                "整体来看，该领域正处于从探索性研究向系统化应用过渡的阶段。"
            )
        return (
            "[MOCK] Existing work clusters around three themes: methodological evolution, "
            "applied deployment, and theoretical grounding. Most papers validate effectiveness "
            "in real-world settings, but long-term impact and cross-domain transfer are "
            "under-explored. Evaluation standards vary across research groups, leaving open "
            "methodological disagreements. Overall the field is moving from exploratory work "
            "toward systematic application."
        )

    if task == "report":
        if language == "zh":
            return (
                "## 引言\n\n（本部分为 MOCK 模式生成的占位报告，用于演示 LangGraph 流程是否能端到端跑通，"
                "配置真实 DEEPSEEK_API_KEY 后将由大模型生成正式内容。）\n\n"
                "## 各研究方向分析\n\n各子方向均已检索到相应文献，详见下方参考文献列表。\n\n"
                "## 综合讨论\n\n不同方向之间存在方法上的互补性，但评价体系尚不统一。\n\n"
                "## 结论\n\n该主题具备进一步深入研究的价值，建议后续补充真实文献总结与引用分析。\n"
            )
        return (
            "## Introduction\n\n(This section is MOCK placeholder content used to demonstrate that "
            "the LangGraph pipeline runs end to end. Configure a real DEEPSEEK_API_KEY to get an "
            "actual generated report.)\n\n"
            "## Analysis by Research Direction\n\nRelevant literature has been retrieved for each "
            "sub-direction; see the reference list below.\n\n"
            "## Discussion\n\nThe directions are complementary in method, though evaluation "
            "standards are not yet unified across the literature.\n\n"
            "## Conclusion\n\nThis topic warrants further investigation; a real API key would let "
            "the model produce an actual literature synthesis and citation analysis here.\n"
        )

    return "[MOCK] unrecognized task"


def call_llm(messages: list[dict], *, task: str, language: str, **ctx) -> str:
    """调用 DeepSeek，返回 content 字符串。未配置 API Key 时自动降级为 MOCK 模式。"""
    if MOCK_MODE:
        return _mock_llm(task, language, **ctx)
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages
    )
    return response.choices[0].message.content


# ---------------------------------------------------------------------------
# Node 1: decompose_directions
# ---------------------------------------------------------------------------

def decompose_directions(state: ResearchState) -> dict:
    topic = state["topic"]
    lang = state.get("language", "en")
    print(t(lang, "node_decompose_directions"))

    if lang == "zh":
        prompt = f"""你是学术研究助手。请分析以下研究主题，严格按照 JSON 格式返回，不要有任何多余文字。

主题：{topic}

返回格式：
{{
  "domain": "cs 或 humanities 或 interdisciplinary 之一",
  "directions": ["研究方向1", "研究方向2", "研究方向3"]
}}

domain 判断标准：
- cs：计算机科学、AI、机器学习、工程、数学、物理等理工科
- humanities：历史、文学、哲学、艺术、社会学、政治学、法学等人文社科
- interdisciplinary：明显跨越理工科和人文社科的主题（例如：AI 伦理、科技与社会）

directions 要求：分解出 3-5 个具体、可检索的研究子方向，不要泛泛而谈。directions 的内容请用中文书写。"""
        system_msg = "你是学术研究助手，只返回 JSON，不返回任何其他文字。"
    else:
        prompt = f"""You are an academic research assistant. Analyze the research topic below and
respond STRICTLY in JSON, with no extra text.

Topic: {topic}

Response format:
{{
  "domain": "one of: cs, humanities, interdisciplinary",
  "directions": ["direction 1", "direction 2", "direction 3"]
}}

Domain criteria:
- cs: computer science, AI, machine learning, engineering, math, physics and other STEM fields
- humanities: history, literature, philosophy, art, sociology, political science, law, etc.
- interdisciplinary: topics that clearly span both STEM and humanities/social science (e.g. AI ethics, technology & society)

directions requirement: break the topic into 3-5 concrete, searchable sub-directions — avoid vague generalities. Write the directions in English."""
        system_msg = "You are an academic research assistant. Return ONLY JSON, no other text."

    content = call_llm(
        [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt}
        ],
        task="decompose", language=lang, topic=topic,
    )

    # 容错处理：去掉可能的 markdown 代码块
    content = content.strip().strip("```json").strip("```").strip()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        print(f"[decompose_directions] JSON parse failed, raw content:\n{content}")
        raise

    return {
        "domain": data["domain"],
        "research_directions": data["directions"],
    }


# ---------------------------------------------------------------------------
# Node 2: search_arxiv
# ---------------------------------------------------------------------------

def search_arxiv(state: ResearchState) -> dict:
    directions = state["research_directions"]
    lang = state.get("language", "en")
    print(t(lang, "node_search_arxiv"))

    arxiv_client = arxiv.Client()
    papers = []

    for i, direction in enumerate(directions, start=1):
        print(t(lang, "searching_direction", source="arXiv", i=i, n=len(directions), direction=direction))
        search = arxiv.Search(query=direction, max_results=3)
        for result in arxiv_client.results(search):
            papers.append({
                "title": result.title,
                "summary": result.summary[:500],
                "url": result.entry_id,
                "source": "arXiv"
            })
        time.sleep(3)

    print(t(lang, "found_papers", source="arXiv", count=len(papers)))
    return {"collected_papers": papers}


# ---------------------------------------------------------------------------
# Node 3: search_crossref
# ---------------------------------------------------------------------------

def search_crossref(state: ResearchState) -> dict:
    directions = state["research_directions"]
    domain = state["domain"]
    lang = state.get("language", "en")
    print(t(lang, "node_search_crossref"))

    papers = []

    for i, direction in enumerate(directions, start=1):
        print(t(lang, "searching_direction", source="CrossRef", i=i, n=len(directions), direction=direction))
        response = requests.get(
            "https://api.crossref.org/works",
            params={
                "query": direction,
                "rows": 3,
                "select": "title,abstract,URL,author,published-print"
            },
            headers={"User-Agent": "AcademicResearchAgent/1.0"}
        )
        items = response.json().get("message", {}).get("items", [])
        for item in items:
            title = item.get("title", [""])[0]
            abstract = item.get("abstract", "N/A")[:500]
            url = item.get("URL", "")
            if title:
                papers.append({
                    "title": title,
                    "summary": abstract,
                    "url": url,
                    "source": "CrossRef"
                })
        time.sleep(1)

    print(t(lang, "found_papers", source="CrossRef", count=len(papers)))

    if domain == "interdisciplinary":
        return {"collected_papers": state["collected_papers"] + papers}
    else:
        return {"collected_papers": papers}


# ---------------------------------------------------------------------------
# Node 4: search_semantic_scholar
# ---------------------------------------------------------------------------

def search_semantic_scholar(state: ResearchState) -> dict:
    directions = state["research_directions"]
    lang = state.get("language", "en")
    print(t(lang, "node_search_semantic_scholar"))

    papers = []

    for i, direction in enumerate(directions, start=1):
        print(t(lang, "searching_direction", source="Semantic Scholar", i=i, n=len(directions), direction=direction))
        response = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={
                "query": direction,
                "limit": 3,
                "fields": "title,abstract,url,year"
            }
        )
        data = response.json().get("data", [])
        for item in data:
            papers.append({
                "title": item.get("title", ""),
                "summary": (item.get("abstract") or "N/A")[:500],
                "url": item.get("url", ""),
                "source": "Semantic Scholar"
            })
        time.sleep(2)

    print(t(lang, "found_papers", source="Semantic Scholar", count=len(papers)))
    return {"collected_papers": state["collected_papers"] + papers}


# ---------------------------------------------------------------------------
# Node 5: summarize_literature
# ---------------------------------------------------------------------------

def summarize_literature(state: ResearchState) -> dict:
    papers = state["collected_papers"]
    topic = state["topic"]
    lang = state.get("language", "en")
    print(t(lang, "node_summarize_literature"))

    papers_text = "\n\n".join([
        f"Title: {p['title']}\nSource: {p['source']}\nAbstract: {p['summary']}"
        for p in papers
    ])

    if lang == "zh":
        user_msg = f"""请根据以下论文，对主题「{topic}」的文献做综合总结。
要求：
1. 概述当前研究的主要方向和发现
2. 指出不同研究之间的联系或争议
3. 总结在 500 字以内，使用中文

论文列表：
{papers_text}"""
        system_msg = "你是学术研究助手，善于归纳文献核心观点。"
    else:
        user_msg = f"""Based on the papers below, write a synthesized literature summary for the topic "{topic}".
Requirements:
1. Summarize the main research directions and findings
2. Point out connections or disagreements between different studies
3. Keep it under 350 words, in English

Papers:
{papers_text}"""
        system_msg = "You are an academic research assistant skilled at synthesizing literature."

    content = call_llm(
        [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg}
        ],
        task="summarize", language=lang,
    )

    return {"literature_summary": content}


# ---------------------------------------------------------------------------
# Node 6: human_approval
# ---------------------------------------------------------------------------

def human_approval(state: ResearchState) -> dict:
    count = state["iteration_count"]
    lang = state.get("language", "en")

    if count >= 3:
        print(t(lang, "max_iterations_warning"))
        return {
            "approval_status": "approved",
            "human_feedback": t(lang, "max_iterations_note"),
            "iteration_count": count
        }

    # Pauses graph execution here; the CLI driver (main.py) and the Streamlit
    # app both resume it by sending back {"choice": ..., "feedback": ...}.
    response = interrupt({
        "literature_summary": state["literature_summary"],
        "domain": state["domain"],
        "papers_count": len(state["collected_papers"]),
        "iteration_count": count,
    })

    choice = response.get("choice", "1")
    feedback = response.get("feedback", "")

    status_map = {
        "1": "approved",
        "2": "redo_search",
        "3": "redo_directions"
    }
    status = status_map.get(choice, "approved")

    new_count = count if status == "approved" else count + 1

    return {
        "approval_status": status,
        "human_feedback": feedback,
        "iteration_count": new_count
    }


# ---------------------------------------------------------------------------
# Node 7: generate_report
# ---------------------------------------------------------------------------

def generate_report(state: ResearchState) -> dict:
    topic = state["topic"]
    directions = state["research_directions"]
    papers = state["collected_papers"]
    summary = state["literature_summary"]
    feedback = state["human_feedback"]
    lang = state.get("language", "en")
    print(t(lang, "node_generate_report"))

    papers_ref = "\n".join([
        f"- {p['title']} ({p['source']}) {p['url']}"
        for p in papers
    ])

    has_real_feedback = feedback and feedback != t(lang, "max_iterations_note")

    if lang == "zh":
        feedback_section = f"\n用户补充说明：{feedback}" if has_real_feedback else ""
        user_msg = f"""请为主题「{topic}」生成一份完整的学术调研报告。

研究方向：
{chr(10).join(f"- {d}" for d in directions)}

文献总结：
{summary}
{feedback_section}

要求：
1. 包含引言、各研究方向分析、综合讨论、结论四个部分
2. 在正文中引用论文（格式：[论文标题]）
3. 结尾附参考文献列表
4. 使用中文，学术风格，1000-1500 字

参考文献（用于生成引用）：
{papers_ref}"""
        system_msg = "你是学术写作助手，帮助用户生成有引用的调研报告。"
    else:
        feedback_section = f"\nAdditional user comments: {feedback}" if has_real_feedback else ""
        user_msg = f"""Write a complete academic research report on the topic "{topic}".

Research directions:
{chr(10).join(f"- {d}" for d in directions)}

Literature summary:
{summary}
{feedback_section}

Requirements:
1. Include four sections: Introduction, Analysis by Research Direction, Discussion, Conclusion
2. Cite papers inline (format: [Paper Title])
3. Append a reference list at the end
4. Academic style, in English, 800-1200 words

References (for citation):
{papers_ref}"""
        system_msg = "You are an academic writing assistant that produces well-cited research reports."

    content = call_llm(
        [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg}
        ],
        task="report", language=lang,
    )

    return {"final_report": content}
