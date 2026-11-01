# Implementation log

## Baseline / task 0

- Repository found at `./academic-research-agent`.
- Clean original HEAD: `631f4690be80b624dc4ca6f3d0d9aa1b0628a61f`; no AGENTS.md found in repository or ancestors.
- `docs/baseline.json` records Python/dependency versions and offline baseline observations.
- Verified defects: 500-character abstract truncation, URL-only dedup, unsorted small shortlists,
  pre-filter sufficiency, rejected-paper backfill, fail-open relevance parsing, automatic approval
  at iteration 3, uncited report passing, exhausted citation failure marked passed.
- Baseline command: pure-function probes under Python 3.13.9; no network/model/embedding calls.
- Existing `.env` is preserved and never printed. All development checks explicitly set MOCK_MODE=1.
- Historical ten topics remain development/history only. Freeze new CS/AI topic clusters before tuning.
- Historical files are preserved. `final_precision_log4.txt` reports 76/92=82.61%; log5 reports
  71/90=78.89%. Both concern selected-paper relevance judged by a model on repeatedly used topics,
  not report factual accuracy or unseen-topic generalization. Different runs do not prove regression.
- Fixture provenance is in `tests/fixtures/README.md`; no new paid calls are authorized or executed.

## Stage A / tasks 1, 2, foundational 5 and 6

- Added normalized paper adapters with full abstracts, DOI/arXiv identity, provenance,
  conservative merges, explicit missing metadata and related-version records.
- Search results now pass normalization/ranking/screening before sufficiency. Stable-ID
  judgments validate complete batches; errors remain unjudged, no rejected-paper backfill.
- Added bounded gap search, per-source status events, request/model/token ceilings.
- Rejection no longer auto-approves at any count. Both redo choices preserve raw feedback,
  rebuild a visible plan, invalidate downstream state and save in-memory run history.
- New modules isolate required responsibilities while preserving provider selection and UI imports.
- Validation: `MOCK_MODE=1 python -m unittest discover -s tests -v`: 8 offline regressions pass.
  A failing Chinese year-boundary test exposed and fixed Unicode `\b` parsing.
- No network, embedding downloads or model calls. Limits remain engineering defaults.

## Stage B / tasks 3, 4, 5 and remaining 6

- Added OA/local PDF ingestion with file/type/size/page/download-time limits; content,
  paper version, parser/cleaner and chunk config participate in cache keys. Text-quality
  failures fall back to complete abstracts; metadata-only records produce no evidence.
- Page/section-aware chunks keep original text and stable IDs. Reference sections are
  retained but excluded from scientific retrieval. No OCR/figure/table interpretation.
- Dense baseline, BM25/RRF hybrid, optional local lexical rerank baseline, per-paper quotas,
  duplicate suppression, deterministic context bounds and component retrieval traces.
- Structured atomic claims use only evidence IDs. Program-rendered references include
  only used papers. Mapping/coverage/level checks and auxiliary support checks are separate.
  A bounded local revision receives its failure and is checked again on final text/IDs.
  Exhausted/unchecked support remains failed/needs_review; no claims is not_applicable.
- Both UIs expose review/end/style-only actions, local PDFs, source states and Markdown
  export with status/levels/limitations. Streamlit additionally exports evidence/check JSON.
- CLI and Streamlit share LangGraph and MemorySaver; redo invalidates all derived state,
  retains feedback/history and preserves the global request/model/token budget.
- Stage B validation: 16 offline tests passed, including local PDF locations/cache/config
  changes, semantic-paraphrase/proper-name stubs, reference exclusion, unsupported/partial
  claims, unknown/empty citations and invalid citations after revision.
- The first attempt hit sandbox default-temp permissions; rerunning with TEMP/TMP set to
  the workspace succeeded. This was an environment issue, not hidden as product success.
- No pypdf was in the original Python environment. Prepared a gitignored local `.venv`
  with system packages and the desktop's bundled pure-Python pypdf 6.10.0, without network
  or global environment changes. Standard clean-install commands are documented separately.

## Stage C / tasks 7 and 8

- Added provenance-aware relevance/report metrics: errors/unjudged separate, direct vs
  partial labels explicit, fixed P@5 short-list policy, zero denominators null, actual used
  citations separate from selected papers. Duplicate/unknown IDs are rejected.
- Froze an initial proposal of 10 CS/AI development and 20 disjoint heldout clusters with
  byte hash. Historical ten topics remain development/history, outside that proposal.
  The split's domain validity has not been independently assessed.
- Adapted current real evaluation/collection/judge runners to normalized Paper aliases,
  strict complete judgments, honest errors and new unique run outputs. Real evaluation
  rejects MOCK and requires explicit ALLOW_PAID_EVAL plus local budgets.
- Offline replay saves config/commit/diff/source/snapshot hashes, versions, UTC time, seed,
  exact input snapshot, per-variant trace, JSONL and CSV. Scripted checks are fixture_stub.
- Exported 276 randomized blind development/history annotation rows without system scores
  or model suggestions. Human labels remain empty. Heldout candidate collection, blind
  human labels, independent real judges and real stochastic ablations remain pending.
- Rewrote README around implemented behavior, configuration, install/run/export and limits;
  added data-model/design documentation and annotation guidelines. Three synthetic CC0
  demo paths cover fulltext, abstract fallback and insufficient evidence.

## Final verification / 2026-10-31 (America/Chicago)

Commands run from the repository, with MOCK_MODE=1 and PYTHONIOENCODING=utf-8:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe demo.py --scenario fulltext
.\.venv\Scripts\python.exe demo.py --scenario abstract
.\.venv\Scripts\python.exe demo.py --scenario insufficient
.\.venv\Scripts\python.exe eval/replay.py
.\.venv\Scripts\python.exe -m compileall -q -x '\.venv|\.git|\.research_cache' .
git diff --check
```

- **26 tests passed**, including automated CLI review/continue/export and Streamlit AppTest
  review/continue/two export controls. Streamlit emitted its expected bare-context warning;
  no application exception occurred. This is not a real-provider or visual browser test.
- Three demos: fulltext = sufficient/needs_review; abstract = sufficient/needs_review;
  insufficient = insufficient_evidence/not_applicable. Demo min_papers=1 is explicit.
- Five fixed-document fixture configurations: **0 errors**. Latest replay at verification:
  `.research_runs/20261101T002824Z_b980a3af` (UTC run ID; local date is still October 31).
  No research-quality improvement was measured. No human or production-model result exists.
- Compilation and whitespace checks passed. Original `.env`, historical logs, candidate
  CSV/XLSX/cache, test_set.json and results.json were verified unchanged against Git.
- Existing baseline commit retained; all changes remain local and uncommitted. No push,
  publication, paid calls, public search API calls or embedding downloads were performed.

Remaining limits: no clean-network dependency installation/provider/API integration test;
no measured ranking/support-model quality, independent heldout labels, stochastic repeats,
OCR/figures/formulas, checkpoint restart recovery or multi-user production deployment.
The optional reranker is a lexical engineering baseline, not a learned independent model.


## BYOK-only web update / 2026-10-31 (America/Chicago)

User requirement: visitors must supply their own model API key; the operator will not
pay for their model calls. Existing local modifications and .env are preserved.

- Added model_access.py with an ephemeral ContextVar credential boundary, explicit user
  provider/model selection and hidden key repr. No credential is passed in graph state,
  LangGraph config/checkpoints, reports, caches or exports.
- Web sidebar now has provider/model/password key inputs, explicit offline demo, disabled
  real-run button without a key and clear-key/end controls. Provider changes erase the
  previous key; active runs lock model/provider. Key clearing resets that browser's UI run.
- Removed the global provider SDK client and global API-key variable. Real transports
  require an explicit user credential context AND run budget. Failures never switch to
  an operator key or another provider. SDK failure text is replaced to avoid key echoes.
- Fixed provider endpoints prevent environment base-URL overrides. Real SDK construction
  explicitly suppresses inherited operator custom/auth/organization/project headers and
  admin keys. An httpx MockTransport regression tests all three provider request headers.
- Semantic Scholar requests from web do not inherit the operator's optional source key.
  Local CLI/evaluation may explicitly bind their own .env through local_model_session;
  the web entry never invokes it. Updated current local evaluation/translation entry points.
- Runtime telemetry and support judgments record session-selected provider/model, no keys.
- Tests cover absent user keys despite configured server keys, no fallback after failures,
  concurrent user contexts, cleanup, explicit demo, LangGraph interrupt/resume and all
  saved checkpoints excluding keys, SDK headers/endpoints, and Streamlit input/provider
  change/clear behavior. Total regression count: 33 (final command below).
- Tested SDK versions: openai 2.53.0, anthropic 0.121.0, httpx 0.28.1; requirements now
  constrain SDK minimums to the versions whose credential-override behavior was checked.
- No real model/public search requests or paid tests executed; network boundaries use
  synthetic clients/MockTransport. Live user-key verification remains a user-run check.
- Streamlit key entry is not client-only or end-to-end encrypted from the host: the host
  necessarily receives it in session memory and forwards it to the chosen provider. This
  is not a full production security audit, account/auth/rate-limit service or hosting setup.
  Model charges belong to the entered provider account; hosting/storage remain operator costs.
- Title display and qualified/unjudged issues discussed in the use-case document remain
  separate pending fixes; this update does not silently change their screening rules.

Validation command: MOCK_MODE=1 .\.venv\Scripts\python.exe -m unittest discover -s tests -v
plus compileall and git diff --check. Windows sandbox TEMP/TMP point into the workspace.
No commit, push or deployment.


## DeepSeek call-error and UI copy fix / 2026-10-31

User reported DeepSeek/deepseek-chat failing and requested removing the operator-key
sentence from the home page. Verified official API docs: old default model identifier
is retired, current model is deepseek-flash. Updated default/example, preserved explicit
model selection with an update button, and disabled default DeepSeek thinking for the
existing structured non-thinking workflow. User .env was not edited.

Added model_errors.py safe status/category classification and connection_check.py
user-triggered GET-only metadata/account-availability checks. UI/CLI display the safe
reason instead of only an exception class name. Raw error bodies and keys are not echoed.
Removed the requested sentence and equivalent verbose operator-key wording in both UI
languages. BYOK isolation remains unchanged. Full details/sources: docs/model_call_fix.md.

Validation: 41 offline tests passed; compileall and git diff --check passed. New eight
tests cover model retirement, explicit migration, DeepSeek parameters, HTTP/error categories,
UI feedback, secret redaction and metadata-only connection checks. No real user key,
network generation request, paid call, commit, push or deployment was used. The user's
actual account/authentication/balance result remains to be confirmed through the new UI.


## Model configuration and API validation round / 2026-10-31

Scope: requested model/API configuration only; defer retrieval-speed and other product
upgrades. Replaced list-only verification with explicit fee-noticed bounded generation.
Added independent dated/source-linked presets, display-name/API-ID separation, always
available custom IDs, non-destructive remote discovery and matching numbered CLI flow.
Preserve caller-selected configuration; no import-time global client/account fallback.
Added provider/model-specific protocol and parameter policies, local task schemas and
redacted request events. Removed name-only rejection of legacy custom DeepSeek IDs;
classify actual responses instead. UI start is gated on current real-generation pass.

DeepSeek was tested FIRST with the existing local key: one 32-output-token-capped request,
HTTP 200, reply OK, reported input/output 9/1 tokens, 3.379 seconds. No second real
request or other-provider call was made. OpenAI/Anthropic: no key, not live-verified.
Google has no adapter and is not displayed. Presets are developer-checked, not proof
that any visitor's credential has passed. Historical failure cannot be reconstructed.

Offline: 55 tests passed, including actual SDK MockTransport serialization, config
switching, model-ID/permission/rate/parameter errors, secret redaction, mock rejection,
fee-consent guards, metadata vs generation distinction, failure-tolerant list refresh,
CLI numbering and migration preserving old selected provider/custom ID. Compileall
and git diff --check passed. Earlier assertions expecting retired-ID pre-blocking and
start-before-validation were updated to the explicit new requested behavior.

Docs/record: docs/model_configuration_and_validation.md and
 docs/model_configuration_verification.json. Original .env/history retained. No
commit/push/deployment. Total research latency was not benchmarked or claimed improved.

## Human-selected literature review workflow / 2026-10-31

Implemented the approved academic literature-review workflow. Evidence gaps are shown
first and supplementary search requires a user action; new papers require new inclusion
decisions. This supersedes the older automatic-search/generic-report graph described above.

- A: original/DOI/OA links, entity/Unicode title normalization with raw-title retention,
  per-item machine judgments and incremental screening, out-of-shortlist visibility,
  separate keep/exclude/undecided decisions. Default undecided; rejection overrides require
  reasons. Confirmed corpus is retained while new candidates await review.
- B: documents processed only after inclusion; content-aware corpus versions; six-field
  evidence cards with exact excerpts, locations, author-finding/synthesis types and explicit
  missing/not-checked states. Reuse processed documents and unchanged extraction. Fulltext
  attempts accumulate across loops; metadata without any fulltext source consumes none.
- C: seven academic outline section types plus thematic children; citation whitelist,
  auxiliary support/coverage checks, honest not_checked checks, human outline review,
  local edits/reordering, user-triggered gap search, preserved user wording and invalidated
  removed-source citations. No automatic acceptance, budget increase or mock success.
- D: atomic CLI project save, portable JSON restore at either review gate, preserved
  budgets/history/processed text, credential/client/path exclusion, validated mappings,
  four exports. Existing provider/BYOK configuration retained. New research uses a fresh
  graph thread and scoped widget keys; review controls survive temporary progress views.

Validation from the repository with MOCK_MODE=1, PYTHONIOENCODING=utf-8 and TEMP/TMP set
to the Codex workspace work directory:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\.venv\Scripts\python.exe demo.py --scenario fulltext --output <deliverables>/demos
.\.venv\Scripts\python.exe demo.py --scenario abstract --output <deliverables>/demos
.\.venv\Scripts\python.exe demo.py --scenario insufficient --output <deliverables>/demos
.\.venv\Scripts\python.exe -m compileall -q graph.py state.py review_workflow.py projects.py review_ui.py review_cli.py workflow.py papers.py evidence.py model_schemas.py streamlit_app.py main.py demo.py tests eval/run_eval.py
git diff --check
```

- 80 offline tests passed (55 existing, with old single-gate expectations migrated, plus
  25 new workflow regressions). AppTest exercises default-undecided rejection, explicit
  inclusion, outline editing, manual supplementary search, reconfirmation, acceptance
  and four export controls. Expected Streamlit bare-context warnings only.
- Three synthetic demos: fulltext and abstract = needs_review/sufficient; insufficient =
  not_applicable/insufficient_evidence. No demo scientific support is marked passed.
- Compilation/whitespace checks passed. Original .env/history preserved, no commit/push,
  deployment, paid model calls, public search API calls or weight downloads this round.
- Previously tested DeepSeek connection is not a live end-to-end validation of this new
  workflow. OpenAI/Anthropic remain unverified without keys. Real extraction/outline
  quality, independent scientific review and total latency benchmarks remain unmeasured.

Guide: docs/literature_review_workflow.md. User deliverables:
`local deliverables: literature_review_implementation (not part of the source repository)`.

## Concise related literature and direction multi-select / 2026-10-31

User feedback supersedes mandatory per-paper inclusion and full candidate display.
Confirmed rules: below-five results may continue; related results default to included
with removal controls; multi-selected directions produce ONE integrated outline.

- Normal results contain only accepted directly/substantively related papers (synthetic
  demo judgments only in demo mode), capped at max_papers. Rejected/unjudged records stay
  in state/exports. Results show title, year, concise relevance and original links;
  abstract/upload/search diagnostics are collapsed. Removed the old review/metadata
  instruction and duplicate paper summary. Legacy saved summaries are not surfaced.
- Initial insufficient retrieval may use one extra source round by default, within the
  existing total search ceiling. Below five remains explicit and user-controlled;
  no irrelevant/unjudged backfill. Later searches require user action and retain removals.
- Added directions.py: one bounded, schema-backed proposal call over retained abstract
  excerpts, with strict paper/evidence mappings. Target 5–10 distinct options; honest
  partial options or unavailable on failure. No real-mode template/mock fallback.
- Added explicit multi-select to web/CLI. No fulltext download/extraction before selection;
  only documents supporting chosen directions are processed. One outline has thematic
  coverage for all choices and scoped evidence retrieval. Normal outline display omits
  raw IDs, full quotations and check JSON; optional details and full exports preserve them.
- Added direction-stage project save/load, selection/source provenance, stale-derived
  state invalidation and pending historical outline preservation. Same semantic direction
  scope retains user edits; source removal clears stale citations. Scope changes preserve
  prior versions. Defaults do not erase explicit exclusions during source metadata updates.
- Updated demos, explicitly automated evaluation choices, README and current Chinese guide.

Validation: MOCK_MODE=1, UTF-8, TEMP/TMP under workspace work. `python -m unittest discover
-s tests -q`: **99 tests passed**, including 19 new direction regressions and migrated
old-flow assertions. Actual SDK MockTransport tests, web/CLI tests and BYOK isolation
remain passing. Three demos: fulltext/abstract needs_review, insufficient not_applicable.
Compilation and git diff --check passed. Streamlit bare-context warnings only.

No paid requests, public literature requests, embedding downloads, commit, push or deployment.
Real direction/outline quality and end-to-end speed remain unmeasured. Guide:
docs/direction_selection_workflow.md; output artifacts in outputs/related_literature_directions.

## Concrete section material and removal of technical result panels / 2026-10-31

Continued the interrupted request to supply source-based substance instead of generic
writing assignments. Preserved the related-literature/direction-selection workflow.

- Removed Evidence and check details, outline check JSON, raw card panel and JSON outline
  editor from the normal writing frontend. Replaced normal search-plan JSON with readable
  scope text. Existing API-configuration diagnostics and offline exports remain available.
- Added writing_support.py: section-specific source notes, paper/field matrices, concrete
  reported values for comparison axes, exact abstract/PDF-page labels and source links.
  Identical comparison tables are reused; unsupported facts are not presented as supported
  author findings and partial support gets a plain-language scope note, not check code.
- Added data/experimental settings and evaluation metrics to card-v2 extraction. Legacy
  six-field cards get explicit not_checked defaults. Invalid per-field output is isolated
  so valid findings/data survive. Same-paper evidence and abstract/fulltext limits remain.
- Replaced generic fallback purposes/tasks with topic-specific scope and directly assembled
  material. Failed/over-budget outline synthesis keeps available facts, without extra
  default generation calls or budget increases. Reduced redundant synthesis prompt data.
  Removed generated personal hypotheses/homework; user-written notes remain supported.
- Source material participates in existing deterministic/auxiliary checks. Cache keys omit
  claim_id so the same statement across sections is checked once per model/source context.
  Removed/changed papers rebuild dependent material; new source IDs and levels are validated
  on project load. Uploaded-PDF pages never point to a different remote PDF's page fragment.
- Inspected sanitized existing application records: latest recorded plan had four screen,
  one direction and two card calls, all HTTP 200; no outline request was recorded. This
  observation does not establish the original cause; no paid reproduction was attempted.

Validation: MOCK_MODE=1 and UTF-8; TEMP/TMP in workspace work. Full suite **120 offline tests
passed**, including 21 new concrete-material tests plus migrated existing fixtures.
Compilation and git diff --check passed. Expected Streamlit bare-context warnings only.
No model/public-source request initiated by this agent, embedding download, Key change,
commit, push or deployment. Real extraction accuracy and scientific comparability remain
unmeasured. Guide: docs/concrete_outline_material.md. Deliverable example uses original
synthetic sources and explicitly does not represent actual research findings.

## Fix first-paper-only extraction / 2026-11-01

Found global topic top-k/context sharing used as the input gate for per-paper extraction,
unsent schema bytes counted against DeepSeek reservations, and blank/partial card caching.
Latest existing user log had only one card request; exact session state was unavailable,
so the specific trigger combination is not claimed proven for that session.

Added card_inputs.py with bounded per-paper first-excerpt allocation, exact window IDs and
hashes, explicit allocation/processing reasons, completed-only cache eligibility and safe
source preservation. Extraction uses its own paper-local inputs rather than query top-k.
Per-task output reservations match 2048 card / 384 support ceilings (or lower user ceiling).
Only actually serialized response-format/schema structures count as input reservation.
Global model/request/token limits and provider-specific adapters remain in force.

Added incomplete-extraction retry in web review, completed results and CLI. It reuses
successful fields, preserves sources and budgets, skips document/search downloads and
retains source/corpus history. Import validates extraction inputs against the source
library; scope invalidation clears stale inputs. Inactive papers no longer become empty
comparison rows. Readable status reasons replace ambiguous all-not-extracted cells.

137 offline tests passed, including 17 new focused regressions: exact old first-paper-only
top-k behavior, 5/10-paper coverage and stable order, fake SDK calls for all ten within the
existing budget, per-paper failures, budget shortfalls, foreign citations, selective retry,
cache empties, source absence, project tampering and both web retry entry points/CLI.
Compilation and git diff --check passed. No network model/search call, embedding download,
Key change, commit, push or deployment by this agent. Real extraction quality unmeasured.

A standalone fake-SDK test initially used the application diagnostic path. Its 12 exact
event IDs were archived separately as offline_test, with a byte-exact backup and verified
preservation of all other application records. Test modules now force the dedicated offline
diagnostic path. Guides/record: docs/per_paper_extraction_fix.md and
docs/per_paper_extraction_verification.json.

## Preserve default selection and valid direction options / 2026-11-01

Default-retained papers already enter the generation stage without manual edits. Existing
sanitized logs show two latest DeepSeek direction requests with HTTP 200; original response
bodies were not retained, so their exact validation failure cannot be retrospectively proven.
Reproduced the code-level all-or-nothing direction validator: one invalid option discarded
the entire set behind a generic ungrounded-directions message.

Added short, exact source/paper aliases, per-option strict validation, separate static failure
categories, source-coverage counts and sanitized local validation events. Unknown citations
and paper/source mismatches remain rejected. Partial options survive; budget-bound explicit
retry bypasses cached proposals, and failed retry preserves validated unchanged-source options.
No automatic retry, budget increase or mock fallback. Missing abstracts may use existing
local uploads only, sharing fulltext attempt limits/cache; source chunks survive later
extraction and project restore with exact source checks.

150 offline tests passed, including 13 new direction tests: unchanged default confirmation
through the graph, mixed valid/invalid options, wrapper and technical ID compatibility,
foreign and mismatched citations, empty/invalid JSON, budgets/context/material absence,
local PDF reuse and snapshot integrity, retry preservation and Streamlit failure text.
Compilation and git diff --check passed. No network model/search/download request or paid
live reproduction initiated; no Key change, commit, push or deployment. Guide:
docs/direction_generation_fix.md. Actual research quality remains unmeasured.

## Prepare GitHub update and bilingual documentation / 2026-11-01

The maintainer confirmed that the updated workflow passed their manual checks and
requested publication to the existing GitHub repository. Reorganized README.md as
the English entry point and added README.zh-CN.md, with reciprocal language links,
matching installation steps, workflow, model configuration, exports and troubleshooting.
Preserved the detailed prior README in docs/technical_reference.md. Replaced local
machine-specific instructions in published Markdown with clone-relative examples.
Corrected .env.example to describe explicit demo opt-in; added environment-variant
and Streamlit secret-file exclusions without changing the local .env. Marked PDF fixtures
as binary in .gitattributes to preserve byte offsets and hashes across platforms.

Re-ran the full suite: 150 offline tests passed. Python compilation, README local-link
checks and git diff --check passed. Inspected 104 publication-candidate files and 42
existing historical blobs: no matches to configured local credential values or the
checked API/token/private-key patterns, and no generated-cache/private-file candidates.
No model or literature API calls were initiated for publication. Fresh dependency
installation and hosted deployment are outside this upload.
