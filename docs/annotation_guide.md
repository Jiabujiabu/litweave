# Independent annotation and metrics

The existing ten topics are development/history, including the repeated experiments
in log4 (76/92 = 82.61%) and log5 (71/90 = 78.89%). Those proportions were obtained
from selected papers and a model judge; they are not report factual accuracy.
Earlier agreement on one historical sample does not validate all future judgments.

`eval/splits.json` contains 10 CS/AI development topics and 20 heldout topic clusters.
It is frozen before tuning; `eval/splits.sha256` records its byte hash. Do not use
heldout failures for prompt tuning without promoting them to development and replacing
the affected heldout clusters. The historical ten remain outside this formal split.
The split is an engineering proposal, not a validated benchmark.

Annotators receive only `blind_candidates.csv`, randomized with a saved seed. Keep
`evaluator_mapping.json` with the evaluator. Do not expose system variant, score,
model labels or suggestions before independent human labeling.

Fill human_label with exactly:

- `direct`: directly studies the specified task/population/constraints.
- `partial`: relevant context or only a subset of constraints.
- `irrelevant`: does not address the question.
- `insufficient_information`: metadata/abstract cannot establish relevance.

Only direct counts as binary relevant. Partial is judged nonrelevant for binary
precision and is also reported separately. Missing labels and insufficient information
remain unjudged; provider/parser failures are errors, not negative labels. Label source
is recorded as human, model or none and must never be inferred from agreement.

Selected-paper relevance = direct / judged selected papers for the requested label
source. P@5 uses fixed denominator 5 and treats absent slots as nonrelevant; any returned
but unjudged slot makes P@5 unavailable. A known reference set provides only known-set
coverage, never whole-field recall. Unknown/duplicate IDs fail validation; omitted IDs
remain unjudged. Zero denominators produce null, not invented 0%/100% success.

Report metrics use actual structured claims and used evidence IDs: citation integrity,
coverage, used-paper relevance and supported/partial/unsupported/insufficient/not-checked
distribution. An uncited substantive report has 0 citation integrity/coverage. No claims
is not_applicable. Scientific support still needs independent human review.

`eval/replay.py` runs fixed-document single-factor fixture comparisons. Its hash
embedder and scripted judge are test doubles. It demonstrates reproducibility, not
semantic retrieval superiority or accuracy improvement. Real-model ranking, end-to-end
network experiments, independent judge comparisons, repeated stochastic runs and human
heldout labels remain pending. Run IDs/config/commit/source/snapshot hashes and per-case
errors accompany each new JSONL/CSV result. Never overwrite historical logs.
