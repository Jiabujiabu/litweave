# Academic Research Agent

A CLI + web research assistant built on **LangGraph**. Give it a topic, and it
classifies the academic domain, decomposes it into sub-directions, searches
arXiv / CrossRef / Semantic Scholar, deduplicates and filters the results for
topical relevance, synthesizes a literature summary, pauses for
**human-in-the-loop approval**, generates a cited research report, and
verifies that report's citations against the retrieved papers before
returning it.

Two front ends share one graph: a terminal CLI ([main.py](main.py)) and a
lightweight web UI ([streamlit_app.py](streamlit_app.py)). Retrieval quality
was measured and iterated on with a real evaluation harness (see
[Evaluation](#evaluation) below), not just eyeballed.

**Bring your own LLM key.** The project ships with zero working API keys.
Pick DeepSeek, OpenAI, or Anthropic via `LLM_PROVIDER` in `.env` — see
[Choosing an LLM provider](#choosing-an-llm-provider).

## Why this design

**LangGraph state machine.** Each step (classify → search → summarize →
review → report) is a node; routing between them is a small set of pure
functions (`route_by_domain`, `is_sufficient`, `route_after_approval`,
`route_after_citation_check`) in [graph.py](graph.py). This makes the
control flow declarative and easy to reason about — e.g. humanities topics
route straight to CrossRef, cs/interdisciplinary topics query both arXiv and
CrossRef and merge results, and either path falls back to Semantic Scholar
if fewer than 6 papers are found.

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
the surrounding UI chrome. `decompose_directions`' search-direction prompt
always asks for **English** directions regardless of UI language, because
arXiv/CrossRef/Semantic Scholar are English-dominant corpora — a Chinese
query against them measurably under-retrieves. CLI asks once at startup; the
web UI has a sidebar toggle (locked once a run starts, so a session doesn't
switch languages mid-report).

**Multi-provider LLM, MOCK mode if none configured.** `call_llm` in
[nodes.py](nodes.py) dispatches to DeepSeek, OpenAI, or Anthropic based on
`LLM_PROVIDER` in `.env`. If the selected provider has no key configured, it
transparently returns templated placeholder text instead of calling out, so
the whole graph — routing, the approval loop, real arXiv/CrossRef/Semantic
Scholar network calls — can be demoed and tested with zero API cost. Flip a
real key into `.env` and nothing else changes.

**Dedup, embedding shortlist, then an LLM relevance filter
(`process_papers`).** The three search sources often return the same paper
(matched by URL) or papers only loosely related to the topic, especially
once the Semantic Scholar fallback kicks in. `process_papers` runs three
stages: dedupe by URL; cheaply shortlist to ~20 candidates by cosine
similarity between the topic and each abstract using a local
`sentence-transformers` model (`paraphrase-multilingual-MiniLM-L12-v2` — no
API cost, multilingual because a Chinese topic still needs to compare
against English abstracts); then send that shortlist to the LLM to judge
relevance directly, keeping only papers a real literature review would cite.
The embedding-only version of this pipeline was measured (see
[Evaluation](#evaluation)) to plateau around 65% delivered precision across
three different retrieval-side fixes — a ranking-method ceiling, not a
query-wording problem. Adding the LLM filter pushed it past 80% in the same
harness. If the filter is too strict and a topic drops below
`MIN_PAPERS` (5), the node backfills from the embedding shortlist rather
than shipping a report with too few citations.

**Citation verification with bounded retry (`verify_citations`).**
`generate_report`'s prompt asks the LLM to cite papers inline as
`[Paper Title]`, but nothing stops it from citing a paper it never actually
retrieved — a common hallucination failure mode in RAG-style report writing.
`verify_citations` extracts every bracketed citation and checks it against
the titles in `collected_papers`; on a mismatch it routes back to
`generate_report` for a retry (up to `MAX_CITATION_RETRY`, currently 2), and
if retries are exhausted it appends a visible warning listing the
unverified citations rather than silently shipping a hallucinated report.
This is not theoretical — the retry loop fires regularly in real runs (see
`eval/`).

## Evaluation

`eval/` is a standalone measurement harness, deliberately kept out of the
production graph's import path. It answers three questions with data instead
of intuition:

1. **What fraction of the final report's citations are actually topically
   relevant?** Measured with an LLM-as-judge that was first validated against
   137 hand-labeled examples spanning all 10 test topics, reaching **100%
   agreement** with human judgment before being trusted for further rounds
   (`eval/check_agreement.py`).
2. **Does retrieval quality have a ceiling, and where does it come from?**
   Three independent fixes to the retrieval side (adding CrossRef to the cs
   route, an anchor-preserving direction prompt, lower temperature for more
   reproducible direction generation) all landed on the same **65% delivered
   precision** — the signature of a ranking-method ceiling, not a
   query-wording problem. Replacing the embedding-only rerank with an LLM
   relevance filter broke through it, reaching **82.6%** in the same harness
   (`eval/measure_final_precision.py`).
3. **Does a specific, diagnosed regression actually get fixed?** When a
   prompt change caused one topic's precision to collapse (80% → 30%), the
   failure was traced to query wording drifting off the topic's population
   anchor (`adolescents` → `young adults`), fixed, and re-measured on the
   same topic in isolation to confirm the fix worked before rolling it out
   (`eval/diagnose_topic.py`).

Key scripts, in the order a full evaluation round runs:

| Script | What it does |
|---|---|
| `collect_candidates.py` | Bypasses domain routing to pool all 3 sources per topic, for source-comparison experiments |
| `llm_judge.py` | Batches candidates through the configured LLM as a relevance judge |
| `export_excel_zh.py` / `finalize_labels.py` | Human-review workflow: bilingual Excel export with a dropdown, then merge human + LLM-extrapolated labels with a `标注来源` provenance column |
| `check_agreement.py` | Compares human labels to LLM-judge labels per topic before trusting the judge for a larger round |
| `score_labels.py` | Precision by topic and by source, from whichever label set is ready |
| `measure_final_precision.py` | Runs the **real production graph** end-to-end and judges the actual final report papers — the number that matters |
| `diagnose_topic.py` | Single-topic deep dive: dumps retrieved papers, LLM verdicts, and reasons for one topic |

None of this runs as part of a normal `python main.py` invocation — it's a
separate, git-tracked record of how the retrieval design got tuned, meant to
be read alongside the code, not executed by an end user.

## Scope decisions (this is a portfolio project, not a hosted product)

Built to demonstrate LangGraph/agent design and evaluation methodology
competently, not to survive production traffic. Deliberately **not** done:
auth, rate limiting, a persistent database (checkpointer is in-memory — state
resets when the process restarts and isn't shared across processes),
multi-user concurrency tuning, deployment/CI. If you want to extend this into
something demo-hostable for others to hit concurrently, the natural next
step is swapping `MemorySaver` for a `SqliteSaver`/`PostgresSaver`
checkpointer — the rest of the graph doesn't need to change.

## Project layout

```
academic_research_agent/
├── requirements.txt
├── .env.example            # copy to .env; pick a provider, add its key
├── state.py                # ResearchState TypedDict
├── i18n.py                 # EN/ZH string tables
├── nodes.py                # all node functions + multi-provider LLM call (with MOCK fallback)
├── graph.py                # routing functions + graph construction (+ checkpointer)
├── main.py                 # CLI entry point
├── streamlit_app.py        # web UI entry point
└── eval/                   # offline evaluation harness (see Evaluation above)
```

## Running it

```bash
pip install -r requirements.txt
cp .env.example .env
```

Without any key configured, the app still runs fully using MOCK placeholder
text for LLM calls — real arXiv/CrossRef/Semantic Scholar network calls still
happen, so it's a genuine structural demo, not a fake one.

### Choosing an LLM provider

Edit `.env` and set `LLM_PROVIDER` to one of the following, then fill in that
provider's key (leave the others blank):

| Provider | `.env` setting | Get a key | Notes |
|---|---|---|---|
| DeepSeek | `LLM_PROVIDER=deepseek` | [platform.deepseek.com](https://platform.deepseek.com) | Cheapest option here; what this project was built and evaluated against |
| OpenAI | `LLM_PROVIDER=openai` | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) | Default model `gpt-4o-mini`, override via `OPENAI_MODEL` |
| Anthropic (Claude) | `LLM_PROVIDER=anthropic` | [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) | Default model `claude-opus-5`, override via `ANTHROPIC_MODEL` — a cheaper/faster model like `claude-haiku-4-5` is worth considering given how many LLM calls one research run makes |

All three are wired through the same `call_llm` function in
[nodes.py](nodes.py), so switching providers is a `.env` change, not a code
change. DeepSeek and OpenAI both speak the OpenAI-compatible chat completions
API; Anthropic uses its own SDK and message format (system prompt as a
top-level parameter, no `temperature` override — current Claude models
reject it).

**Never commit your `.env`.** It's gitignored; only `.env.example` (with no
real keys) is tracked.

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

- arXiv enforces a minimum ~3-5s gap between requests; with 4-5 directions
  and two sources per topic, search alone can take 20-40s. This is expected,
  not a bug — hence the progress indicators.
- Both arXiv and Semantic Scholar were observed to return HTTP 429 under
  sustained testing in the same session; `nodes.py`'s search functions all
  retry with backoff and degrade to an empty result rather than crashing the
  graph. Semantic Scholar's free tier is aggressively rate-limited — set
  `SEMANTIC_SCHOLAR_API_KEY` in `.env` (free, see `.env.example`) if you hit
  this regularly.
- The approval loop auto-approves after 3 iterations to guarantee
  termination.
- CrossRef entries are frequently missing an abstract; `summary` falls back
  to a placeholder string rather than `None` so downstream prompts never see
  empty fields.
- `process_papers`' first run downloads the `sentence-transformers` model
  (~450MB) from Hugging Face; subsequent runs use the local cache. This
  requires network access even in MOCK mode, since only LLM calls are mocked.
- The citation-verification retry loop is bounded (`MAX_CITATION_RETRY = 2`
  in [nodes.py](nodes.py)) so a persistently hallucinating model can't loop
  forever — it falls back to a flagged warning instead.
- The LLM relevance filter in `process_papers` adds 1-3 extra LLM calls (and
  a few seconds of latency) per run compared to embedding-only reranking — a
  deliberate quality-for-cost trade documented and measured in `eval/`, not
  an accident.
