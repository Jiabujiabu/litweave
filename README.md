# Academic Research Agent

A CLI + web research assistant built on **LangGraph**. Give it a topic, and it
classifies the academic domain, decomposes it into sub-directions, searches
arXiv / CrossRef / Semantic Scholar, synthesizes a literature summary, pauses
for **human-in-the-loop approval**, and generates a cited research report.

Two front ends share one graph: a terminal CLI ([main.py](main.py)) and a
lightweight web UI ([streamlit_app.py](streamlit_app.py)).

## Why this design

**LangGraph state machine.** Each step (classify → search → summarize →
review → report) is a node; routing between them is a small set of pure
functions (`route_by_domain`, `route_after_arxiv`, `is_sufficient`,
`route_after_approval`) in [graph.py](graph.py). This makes the control flow
declarative and easy to reason about — e.g. humanities topics skip arXiv
entirely, interdisciplinary topics query both arXiv and CrossRef and merge
results, and any domain falls back to Semantic Scholar if fewer than 6 papers
are found.

**Human-in-the-loop via `interrupt()`.** `human_approval` in
[nodes.py](nodes.py) calls LangGraph's `interrupt()` rather than reading
`input()` directly. That decouples the node from any particular front end:
the graph pauses and hands a payload (the summary, domain, paper count) back
to whichever driver is running it. The CLI resumes it with terminal
`input()`; the Streamlit app resumes it with a button click. Same node, two
UIs, no duplicated approval logic. This requires a checkpointer
(`MemorySaver`, see [graph.py](graph.py)) to persist state across the pause.

**Progress feedback everywhere the graph blocks.** The original version ran
silently for the ~15-90s it takes to hit multiple LLM calls and rate-limited
search APIs — indistinguishable from a hang. Every node now prints/renders a
status line before it starts work, and the search nodes report per-direction
progress. The CLI gets this via `print()`; the web UI gets it via
`app.stream(..., stream_mode="updates")`, which yields one chunk per
completed node so the status panel updates live without any custom callback
plumbing.

**Bilingual (EN default / ZH opt-in).** All UI strings live in
[i18n.py](i18n.py) (`t(lang, key, **kwargs)`), and `language` is part of the
graph state, so the LLM prompts for domain classification, summarization,
and report generation are also written in the selected language — not just
the surrounding UI chrome. CLI asks once at startup; the web UI has a sidebar
toggle (locked once a run starts, so a session doesn't switch languages
mid-report).

**Offline MOCK mode.** If `DEEPSEEK_API_KEY` is missing/placeholder,
`call_llm` in [nodes.py](nodes.py) transparently returns templated
placeholder text instead of calling DeepSeek, so the whole graph — routing,
the approval loop, real arXiv/CrossRef/Semantic Scholar network calls — can
be demoed and tested with zero API cost. Flip a real key into `.env` and
nothing else changes.

## Scope decisions (this is a portfolio project, not a hosted product)

Built to demonstrate LangGraph/agent design competently, not to survive
production traffic. Deliberately **not** done: auth, rate limiting, a
persistent database (checkpointer is in-memory — state resets when the
process restarts and isn't shared across processes), multi-user concurrency
tuning, deployment/CI. If you want to extend this into something
demo-hostable for others to hit concurrently, the natural next step is
swapping `MemorySaver` for a `SqliteSaver`/`PostgresSaver` checkpointer —
the rest of the graph doesn't need to change.

## Project layout

```
academic_research_agent/
├── requirements.txt
├── .env                  # DEEPSEEK_API_KEY=... (falls back to MOCK mode if absent)
├── state.py               # ResearchState TypedDict
├── i18n.py                 # EN/ZH string tables
├── nodes.py                # all node functions + LLM call (with MOCK fallback)
├── graph.py                 # routing functions + graph construction (+ checkpointer)
├── main.py                   # CLI entry point
└── streamlit_app.py           # web UI entry point
```

## Running it

```bash
pip install -r requirements.txt
```

Put a real key in `.env` for actual LLM calls:

```
DEEPSEEK_API_KEY=sk-...
```

(Get one at platform.deepseek.com. Without a key the app still runs fully,
using MOCK placeholder text — good for a quick structural demo.)

**CLI:**

```bash
python main.py
```

On Windows, set UTF-8 output first (otherwise emoji/Chinese text can raise
`UnicodeEncodeError` in some terminals):

```powershell
$env:PYTHONIOENCODING="utf-8"; python main.py
```

**Web UI:**

```bash
streamlit run streamlit_app.py
```

Opens at `http://localhost:8501`. Pick a language in the sidebar, enter a
topic, watch progress live, review the literature summary when prompted
(approve / redo search / redo direction breakdown), then download the final
report as `.md`.

## Notes

- arXiv enforces a minimum ~3s gap between requests; with 3-5 directions,
  search alone can take 10-20s. This is expected, not a bug — hence the
  progress indicators.
- The approval loop auto-approves after 3 iterations to guarantee
  termination.
- CrossRef entries are frequently missing an abstract; `summary` falls back
  to a placeholder string rather than `None` so downstream prompts never see
  empty fields.
