import os
import json
import re
import time
import arxiv
import requests
from dotenv import load_dotenv
from langgraph.types import interrupt

from state import ResearchState
from i18n import t

load_dotenv()

# ---------------------------------------------------------------------------
# LLM provider selection — bring your own key.
#
# This project never ships with a working API key. LLM_PROVIDER picks which
# provider's key to read; the matching *_API_KEY must be supplied by whoever
# runs the project (see .env.example). No key for the selected provider ->
# MOCK_MODE, same offline fallback as before, so the graph/UI still runs.
# ---------------------------------------------------------------------------

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek").strip().lower()

_PROVIDERS = {
    "deepseek": {
        "key_env": "DEEPSEEK_API_KEY",
        "model_env": "DEEPSEEK_MODEL",
        "default_model": "deepseek-chat",
        "base_url": "https://api.deepseek.com",
    },
    "openai": {
        "key_env": "OPENAI_API_KEY",
        "model_env": "OPENAI_MODEL",
        "default_model": "gpt-4o-mini",
        "base_url": None,  # official OpenAI endpoint
    },
    "anthropic": {
        "key_env": "ANTHROPIC_API_KEY",
        "model_env": "ANTHROPIC_MODEL",
        "default_model": "claude-opus-5",
        "base_url": None,
    },
}

if LLM_PROVIDER not in _PROVIDERS:
    print(f"[nodes] Unknown LLM_PROVIDER '{LLM_PROVIDER}', falling back to 'deepseek'.")
    LLM_PROVIDER = "deepseek"

_provider_cfg = _PROVIDERS[LLM_PROVIDER]
_API_KEY = os.getenv(_provider_cfg["key_env"], "")
_MODEL = os.getenv(_provider_cfg["model_env"], _provider_cfg["default_model"])
MOCK_MODE = (not _API_KEY) or _API_KEY == "your_key_here"

client = None
if not MOCK_MODE:
    if LLM_PROVIDER == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=_API_KEY)
    else:
        from openai import OpenAI
        client = OpenAI(api_key=_API_KEY, base_url=_provider_cfg["base_url"])


# ---------------------------------------------------------------------------
# LLM call (with offline MOCK fallback when no real API key is configured)
# ---------------------------------------------------------------------------

def _mock_llm(task: str, language: str, **ctx) -> str:
    """Demo/offline fallback used when no API key is configured for the
    selected LLM_PROVIDER. Returns structurally-correct placeholder content
    in the requested language."""

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
                "在 .env 中配置任意一个受支持的 LLM 提供商的真实 API Key 后将由大模型生成正式内容。）\n\n"
                "## 各研究方向分析\n\n各子方向均已检索到相应文献，详见下方参考文献列表。\n\n"
                "## 综合讨论\n\n不同方向之间存在方法上的互补性，但评价体系尚不统一。\n\n"
                "## 结论\n\n该主题具备进一步深入研究的价值，建议后续补充真实文献总结与引用分析。\n"
            )
        return (
            "## Introduction\n\n(This section is MOCK placeholder content used to demonstrate that "
            "the LangGraph pipeline runs end to end. Configure a real API key for any supported "
            "LLM_PROVIDER in .env to get an actual generated report.)\n\n"
            "## Analysis by Research Direction\n\nRelevant literature has been retrieved for each "
            "sub-direction; see the reference list below.\n\n"
            "## Discussion\n\nThe directions are complementary in method, though evaluation "
            "standards are not yet unified across the literature.\n\n"
            "## Conclusion\n\nThis topic warrants further investigation; a real API key would let "
            "the model produce an actual literature synthesis and citation analysis here.\n"
        )

    return "[MOCK] unrecognized task"


def call_llm(messages: list[dict], *, task: str, language: str, **ctx) -> str:
    """调用配置好的 LLM 提供商（DeepSeek / OpenAI / Anthropic，见 LLM_PROVIDER），
    返回 content 字符串。未配置对应 API Key 时自动降级为 MOCK 模式。"""
    if MOCK_MODE:
        return _mock_llm(task, language, **ctx)
    # decompose_directions feeds every downstream search call -- run-to-run
    # wording drift there (at the API's default temperature) was observed to
    # swing a single topic's measured precision by 60 points between two
    # otherwise-identical eval runs. Lower temperature trades a little
    # direction diversity for much more reproducible retrieval quality.
    temperature = 0.3 if task in ("decompose", "filter", "translate") else 1.0

    if LLM_PROVIDER == "anthropic":
        # Anthropic takes the system prompt as its own top-level parameter,
        # not a "system"-role message, and current Claude models reject
        # temperature/top_p/top_k entirely -- omit it rather than send one.
        system_msg = next((m["content"] for m in messages if m["role"] == "system"), None)
        turns = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]
        response = client.messages.create(
            model=_MODEL,
            max_tokens=4096,
            system=system_msg,
            messages=turns,
        )
        # Claude Opus 5 thinks by default, so content[0] may be a thinking
        # block rather than text -- find the text block explicitly.
        return next((block.text for block in response.content if block.type == "text"), "")

    response = client.chat.completions.create(
        model=_MODEL,
        messages=messages,
        temperature=temperature,
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

directions 要求：分解出 3-5 个方向，每个方向写成简短、具体的检索关键词短语（大致 5-10 个词），
围绕主题相关的具体方法、技术、理论或实体名词展开——就像你会直接输入进论文搜索引擎的短语，
不要写成"……及其对……的影响/意义"这类描述性的综述句子。
重要：每个方向都必须保留主题本身的核心限定词（比如主题指定的人群、学科对象等），
不能因为加了具体方法/理论词就把核心限定词换掉或冲淡。例如主题是关于"青少年（adolescents）"的，
每个方向的短语里都要保留"adolescents"，不能因为某个具体方法在"年轻成年人（young adults）"
群体的文献里更常见，就把人群换成 young adults。
directions 的内容请用英文书写（arXiv/CrossRef/Semantic Scholar 的语料以英文为主，
用英文关键词检索命中率明显更高）。"""
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

directions requirement: break the topic into 3-5 directions, each phrased as a SHORT, SPECIFIC
search-engine-style query (roughly 5-10 words) built around a concrete named method, technique,
theory, or entity relevant to the topic. Avoid descriptive survey framing like "X and its
implications for Y" or "the role of X in Y" -- name the specific method/concept/entity directly,
the way you'd actually type it into a literature search box.
IMPORTANT: every direction must still keep the topic's core subject anchor (e.g. its named
population, discipline, or object of study) explicit in the query -- do not let an added
method/theory keyword replace or drift away from that anchor. For example, if the topic is about
"adolescents", every direction should still say "adolescents" rather than switching to a
methodologically-related but different population like "young adults" or "emerging adults" just
because that population is more common in a given sub-method's literature.
Write the directions in English."""
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

def _arxiv_search_with_backoff(client: "arxiv.Client", query: str, max_results: int = 3, max_retries: int = 3) -> list:
    """arxiv.Client already retries transient HTTP errors internally (default
    3 attempts, 3s apart) before giving up and raising arxiv.HTTPError -- but
    search_arxiv previously let that exception propagate uncaught, crashing
    the whole node (and the graph run) on a single rate-limited request. This
    adds an outer retry with a longer cooldown, and degrades to an empty
    result for this direction instead of taking down the run."""
    for attempt in range(max_retries):
        try:
            search = arxiv.Search(query=query, max_results=max_results)
            return list(client.results(search))
        except (arxiv.HTTPError, requests.exceptions.RequestException) as e:
            # arxiv.HTTPError covers bad-status responses (429/503/...);
            # RequestException covers failures before any response exists
            # (DNS resolution, connection reset, timeout) -- both are
            # transient and should degrade to "no results", not crash.
            if attempt < max_retries - 1:
                wait = 15 * (attempt + 1)
                print(f"  [arXiv] request failed ({e}), retrying in {wait}s...")
                time.sleep(wait)
                continue
            print(f"  [arXiv] giving up after {max_retries} attempts: {e}")
            return []
    return []


def search_arxiv(state: ResearchState) -> dict:
    directions = state["research_directions"]
    lang = state.get("language", "en")
    print(t(lang, "node_search_arxiv"))

    arxiv_client = arxiv.Client()
    papers = []

    for i, direction in enumerate(directions, start=1):
        print(t(lang, "searching_direction", source="arXiv", i=i, n=len(directions), direction=direction))
        for result in _arxiv_search_with_backoff(arxiv_client, direction, max_results=6):
            papers.append({
                "title": result.title,
                "summary": result.summary[:500],
                "url": result.entry_id,
                "source": "arXiv"
            })
        time.sleep(5)

    print(t(lang, "found_papers", source="arXiv", count=len(papers)))
    return {"collected_papers": papers}


# ---------------------------------------------------------------------------
# Node 3: search_crossref
# ---------------------------------------------------------------------------

def _crossref_search(query: str, rows: int = 3, max_retries: int = 3) -> list[dict]:
    """Same defensive pattern as _semantic_scholar_search/_arxiv_search_with_backoff:
    check the status code and back off on 429/5xx instead of assuming any
    response body is a valid 200 result (CrossRef hasn't been observed to
    rate-limit this app yet, but arXiv and Semantic Scholar both did within
    the same afternoon of testing, so treating this one as exempt would just
    be the next silent failure waiting to happen)."""
    for attempt in range(max_retries):
        try:
            response = requests.get(
                "https://api.crossref.org/works",
                params={
                    "query": query,
                    "rows": rows,
                    "select": "title,abstract,URL,author,published-print"
                },
                headers={"User-Agent": "AcademicResearchAgent/1.0"},
                timeout=15,
            )
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait = 15 * (attempt + 1)
                print(f"  [CrossRef] network error ({e}), retrying in {wait}s...")
                time.sleep(wait)
                continue
            print(f"  [CrossRef] giving up after {max_retries} attempts: {e}")
            return []

        if response.status_code == 200:
            return response.json().get("message", {}).get("items", [])
        if response.status_code in (429, 503) and attempt < max_retries - 1:
            wait = int(response.headers.get("Retry-After", 15))
            print(f"  [CrossRef] HTTP {response.status_code}, retrying in {wait}s...")
            time.sleep(wait)
            continue
        print(f"  [CrossRef] request failed: HTTP {response.status_code} - {response.text[:200]}")
        return []
    return []


def search_crossref(state: ResearchState) -> dict:
    directions = state["research_directions"]
    domain = state["domain"]
    lang = state.get("language", "en")
    print(t(lang, "node_search_crossref"))

    papers = []

    for i, direction in enumerate(directions, start=1):
        print(t(lang, "searching_direction", source="CrossRef", i=i, n=len(directions), direction=direction))
        items = _crossref_search(direction, rows=6)
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

    if domain == "humanities":
        # humanities routes straight here without ever calling search_arxiv,
        # so there's nothing to append to yet.
        return {"collected_papers": papers}
    else:
        # cs and interdisciplinary both arrive here after search_arxiv already
        # ran -- combine rather than discard those results (eval data showed
        # CrossRef contributes real hits for cs topics too, not just
        # interdisciplinary ones).
        return {"collected_papers": state["collected_papers"] + papers}


# ---------------------------------------------------------------------------
# Node 4: search_semantic_scholar
# ---------------------------------------------------------------------------

def _semantic_scholar_search(query: str, limit: int = 3, max_retries: int = 3) -> list[dict]:
    """GET with 429 backoff. Semantic Scholar's unauthenticated tier is
    aggressively rate-limited (observed: a handful of rapid requests is
    enough to trigger it); the previous version of this function read
    `response.json().get("data", [])` unconditionally, which silently turned
    a 429 error body into "0 papers found" -- indistinguishable from a
    genuine empty result. That masked every rate-limit hit as a retrieval
    quality problem. This version checks the status code, honors
    Retry-After on 429, and logs a real failure instead of guessing zero."""
    headers = {}
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    if api_key:
        headers["x-api-key"] = api_key

    for attempt in range(max_retries):
        try:
            response = requests.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params={"query": query, "limit": limit, "fields": "title,abstract,url,year"},
                headers=headers,
                timeout=15,
            )
        except requests.exceptions.RequestException as e:
            # Network-level failure (DNS, connection reset, timeout) --
            # never reached the point of getting a status code at all.
            if attempt < max_retries - 1:
                wait = 15 * (attempt + 1)
                print(f"  [Semantic Scholar] network error ({e}), retrying in {wait}s...")
                time.sleep(wait)
                continue
            print(f"  [Semantic Scholar] giving up after {max_retries} attempts: {e}")
            return []

        if response.status_code == 200:
            return response.json().get("data", [])
        if response.status_code == 429 and attempt < max_retries - 1:
            wait = int(response.headers.get("Retry-After", 15))
            print(f"  [Semantic Scholar] rate limited (429), retrying in {wait}s...")
            time.sleep(wait)
            continue
        print(f"  [Semantic Scholar] request failed: HTTP {response.status_code} - {response.text[:200]}")
        return []
    return []


def search_semantic_scholar(state: ResearchState) -> dict:
    directions = state["research_directions"]
    lang = state.get("language", "en")
    print(t(lang, "node_search_semantic_scholar"))

    papers = []

    for i, direction in enumerate(directions, start=1):
        print(t(lang, "searching_direction", source="Semantic Scholar", i=i, n=len(directions), direction=direction))
        data = _semantic_scholar_search(direction, limit=6)
        for item in data:
            papers.append({
                "title": item.get("title", ""),
                "summary": (item.get("abstract") or "N/A")[:500],
                "url": item.get("url", ""),
                "source": "Semantic Scholar"
            })
        time.sleep(5)

    print(t(lang, "found_papers", source="Semantic Scholar", count=len(papers)))
    return {"collected_papers": state["collected_papers"] + papers}


# ---------------------------------------------------------------------------
# Node (new): process_papers — dedupe by URL, shortlist by embedding
# similarity (cheap, offline, no API key), then have the LLM directly judge
# relevance on that shortlist before truncating to the final TOP_K_PAPERS.
#
# Embedding cosine similarity alone plateaued at ~65% delivered precision in
# eval/ (three different retrieval-side fixes all landed on the same number,
# which is the signature of a ranking-method ceiling, not a query-wording
# problem) -- it's a fast, free coarse filter but not a fine one. The LLM
# judge was separately validated at 100% agreement with human relevance
# labels (see eval/check_agreement.py), so this reuses that same judgment
# call in production instead of only in offline evaluation. Trade-off: every
# real run now costs 1-3 extra LLM calls and a few seconds of latency.
# ---------------------------------------------------------------------------

TOP_K_PAPERS = 10
MIN_PAPERS = 5  # floor below which we backfill from the embedding shortlist rather than ship a thin report
EMBEDDING_SHORTLIST_SIZE = 20  # keeps the LLM filter's input (and cost) bounded
_EMBEDDER = None


def _get_embedder():
    global _EMBEDDER
    if _EMBEDDER is None:
        from sentence_transformers import SentenceTransformer
        # Multilingual: topics/directions can be Chinese while abstracts from
        # arXiv/CrossRef/Semantic Scholar are almost always English.
        _EMBEDDER = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    return _EMBEDDER


def _embedding_shortlist(topic: str, papers: list[dict], k: int) -> list[dict]:
    if len(papers) <= k:
        return papers

    import numpy as np

    embedder = _get_embedder()
    topic_vec = embedder.encode([topic])[0]
    paper_vecs = embedder.encode([p["summary"] for p in papers])

    def cosine(a, b):
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8)

    scored = sorted(
        zip(paper_vecs, papers),
        key=lambda pair: cosine(topic_vec, pair[0]),
        reverse=True,
    )
    return [p for _, p in scored[:k]]


def _llm_filter_relevant(topic: str, papers: list[dict], lang: str) -> list[dict]:
    """Judges each shortlisted paper's relevance directly with the LLM,
    keeping only the ones a literature review on this exact topic would
    actually cite. Falls back to returning the shortlist unfiltered in MOCK
    mode (there's no real model to ask) or if a batch's response can't be
    parsed (fail open rather than silently dropping good papers)."""
    if MOCK_MODE:
        return papers

    relevant = []
    chunk_size = 10
    for start in range(0, len(papers), chunk_size):
        chunk = papers[start:start + chunk_size]
        numbered = "\n".join(
            f"{i}. Title: {p['title']}\n   Abstract: {p.get('summary', '') or '(no abstract)'}"
            for i, p in enumerate(chunk)
        )
        if lang == "zh":
            prompt = f"""主题：{topic}

请判断下面每篇论文是否是研究该主题时真正会引用的直接相关文献（不是仅有关键词表面重合）。
只返回一个 JSON 数组，每个元素形如 {{"index": <int>, "relevant": "y" 或 "n"}}，
顺序与原文一致，不要有其他文字。

{numbered}"""
            system_msg = "你是学术文献筛选助手，只返回 JSON 数组。"
        else:
            prompt = f"""Topic: {topic}

For each paper below, judge whether it is literature a researcher writing on this exact topic
would actually cite as directly relevant (not just superficially related by a shared keyword).
Return ONLY a JSON array, each item shaped like {{"index": <int>, "relevant": "y" or "n"}},
in the same order, with no other text.

{numbered}"""
            system_msg = "You are an academic literature screening assistant. Return ONLY a JSON array."

        try:
            content = call_llm(
                [{"role": "system", "content": system_msg}, {"role": "user", "content": prompt}],
                task="filter", language=lang,
            )
            judgments = json.loads(content.strip().strip("```json").strip("```").strip())
        except (json.JSONDecodeError, TypeError):
            print(f"  [process_papers] LLM filter batch failed to parse, keeping it unfiltered")
            relevant.extend(chunk)
            continue

        for j in judgments:
            idx = j.get("index")
            if idx is not None and 0 <= idx < len(chunk) and j.get("relevant") == "y":
                relevant.append(chunk[idx])

    return relevant


def process_papers(state: ResearchState) -> dict:
    papers = state["collected_papers"]
    topic = state["topic"]
    lang = state.get("language", "en")
    print(t(lang, "node_process_papers"))

    seen_urls = set()
    deduped = []
    for p in papers:
        url = p.get("url", "")
        if url and url in seen_urls:
            continue
        seen_urls.add(url)
        deduped.append(p)

    print(t(lang, "dedup_result", before=len(papers), after=len(deduped)))

    shortlist = _embedding_shortlist(topic, deduped, EMBEDDING_SHORTLIST_SIZE)
    print(t(lang, "rerank_result", count=len(shortlist)))

    filtered = _llm_filter_relevant(topic, shortlist, lang)
    print(t(lang, "filter_result", kept=len(filtered), shortlisted=len(shortlist)))

    if len(filtered) < MIN_PAPERS:
        # A strict LLM filter can leave a topic with too few citations for a
        # substantive report (seen in eval: one topic dropped to 2). Backfill
        # from the embedding shortlist -- still similarity-ranked, just not
        # LLM-confirmed -- rather than shipping a thin report.
        needed = MIN_PAPERS - len(filtered)
        filtered_urls = {p["url"] for p in filtered}
        backfill = [p for p in shortlist if p["url"] not in filtered_urls][:needed]
        if backfill:
            print(t(lang, "backfill_result", count=len(backfill)))
        filtered = filtered + backfill

    final = filtered[:TOP_K_PAPERS]
    return {"collected_papers": final}


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


# ---------------------------------------------------------------------------
# Node (new): verify_citations — catches citations to papers that were never
# retrieved (LLM hallucination). Loops back to generate_report on failure,
# up to MAX_CITATION_RETRY times, then falls back to flagging the report
# instead of looping forever.
# ---------------------------------------------------------------------------

MAX_CITATION_RETRY = 2


def verify_citations(state: ResearchState) -> dict:
    report = state["final_report"]
    papers = state["collected_papers"]
    lang = state.get("language", "en")
    print(t(lang, "node_verify_citations"))

    retry_count = state.get("citation_retry_count", 0)
    valid_titles = {p["title"] for p in papers}
    # Only treat reasonably long bracketed spans as citation candidates, to
    # avoid false positives on short emphasis-style [brackets] in the prose.
    cited = [c for c in re.findall(r"\[([^\]]+)\]", report) if len(c) > 8]
    invalid = [c for c in cited if c not in valid_titles]

    if not invalid:
        print(t(lang, "citation_check_passed"))
        return {"citation_check": "passed", "citation_retry_count": retry_count}

    if retry_count >= MAX_CITATION_RETRY:
        print(t(lang, "citation_check_forced", count=len(invalid)))
        warning = t(lang, "citation_warning_suffix", titles="; ".join(invalid))
        return {
            "final_report": report + warning,
            "citation_check": "passed",
            "citation_retry_count": retry_count,
        }

    print(t(lang, "citation_check_retry", count=len(invalid), attempt=retry_count + 1))
    return {"citation_check": "failed", "citation_retry_count": retry_count + 1}
