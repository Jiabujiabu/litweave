# Data model and design choices

| Record | Key fields | Invariants |
| --- | --- | --- |
| Paper | paper_id, title, authors, year, doi, arxiv_id/version, source_records, landing_url, open_access_url, abstract/status | Stable content/identifier-based ID; full abstract; missing metadata explicit; provenance retained |
| Research plan | original_question, feedback, core_constraints, optional_methods, year, questions | Original input retained; English queries; explicit user year constraint enforced; question IDs unique |
| Chunk | chunk_id, paper_id, text, evidence_level, section, page_start/end, content_hash, is_reference | Original text slice; fulltext page or null for abstract; stable IDs include chunk settings |
| Evidence | evidence_id, question_id, paper_id, chunk_id, original_text, location, score, method | IDs reference retrieved whitelist; original text distinct from generated interpretation; references excluded |
| Claim | claim_id, text, evidence_ids, kind, required_level | Atomic scientific statement; citations required; author finding / synthesis / hypothesis distinguished |
| Support check | claim_id, status, reason, contradiction, judgment_source, model/prompt version when used | Model auxiliary judgment distinct from human labels; unavailable remains not_checked |
| Run | run_id, settings, telemetry, search/document events, retrieval trace, history | Request/model/token limits shared across loops; source failures separate from empty hits; no credentials/body in telemetry |
| Human decision | paper_id, decision, reason, screen_fingerprint, source | keep/exclude/undecided separate from machine judgment; changed inputs require reconfirmation |
| Corpus | corpus_input_version, corpus_version, approved_paper_ids, signatures, history | Frozen human-selected whitelist; final identity includes processed chunk/content hashes |
| Evidence card | card_id, paper_id, fields, evidence_level, excerpts, support_status | Eight fields including data and metrics; legacy six-field cards load with extras not_checked; found fields cite same-paper evidence; extraction is not support verification |
| Section material | writing_support.source_notes, comparison_rows, comparison_axes, status | Derived from validated same-paper card fields; exact source IDs, author-reported facts and source excerpts distinguished; missing fields not invented; no cross-study score ranking |
| Outline node | node_id, parent_id, order, section_type, title, purpose, question_ids, argument_points, counterevidence_ids, conditions, gaps, user_writing_tasks, status | Stable IDs, no cycles; factual arguments require whitelist citations; user wording preserved and stale citations invalidated |
| Project | schema_version, phase, state | Explicit portable JSON, validated references, atomic CLI save, no credentials/clients/private PDF paths; budgets preserved |

ResearchState uses ordinary typed dictionaries for LangGraph serialization; adapters and
explicit validators enforce the schemas at boundaries. Legacy `summary/url/source` aliases
remain populated to keep historical consumers compatible.

DOIs are normalized before URLs or title matching. Same identifiers merge only when other
identifiers do not conflict. Fuzzy title matches require a shared author and year and a
very high title similarity; incomplete records stay separate rather than merging on one
word. Preprint/publication pairs without a shared identity remain related versions.
Conflicts are retained with distinct stable IDs for review. Merges preserve all sources
and the longer full abstract. The original source data remains in the raw record.

Chunking allows evidence retrieval to select a passage rather than squeezing every paper
into a report prompt. Page/section provenance lets the user check it. Approximate chunk
units are not a provider tokenizer; a conservative character bound caps model context.
PDF text remains imperfect and no figure/table/OCR claims are made.

Hybrid RRF combines rank positions because dense cosine and BM25 scores have different
scales. It is a configurable comparison, not an assumption that hybrid always wins.
The default reranker is off; the optional local lexical baseline has no learned relevance
or independent judge guarantee. Cached vectors reuse a configured model identity; pin a
revision and change that identity if replacing weights.

A target paper count is a sufficiency threshold, never permission to backfill rejected
papers. Machine counts and question coverage propose bounded supplemental searches.
Only an explicit user action triggers them. Evidence gaps use the same search-round/request budget. When that is exhausted, partial
results retain insufficient_evidence and require explicit user acceptance.

Reference existence and scientific support are separate. Programmatic checks catch ID,
mapping, coverage and level errors; model checks assess the claim's scope against the
actual quoted passage. Limited local revision carries the failure reason and rechecks
the final text/IDs. Neither a real title nor a completed retry counter establishes truth.

Scope changes invalidate dependent state and save history, while preserving cumulative
budgets and search-round consumption. Supplemental searches retain the frozen corpus
until new human decisions are confirmed. User edits use stable node IDs and preserved
wording; removed citations require new support. MemorySaver is not restart recovery;
explicit project save/load resumes a human review gate and reuses portable processed text.
