# Read-only language and retrieval experiment

This opt-in Python tool compares rules, character n-gram exemplar matching,
multilingual sentence embeddings and rules followed by embedding fallback. It
also compares lexical, vector and hybrid track retrieval using a disposable
Typesense 30.2 service. It has no device configuration or execution path, and
never modifies the Assistant's settings, catalog or model selection.

## Reproduce

Use an isolated **Python 3.12** environment. These dependencies do not belong to
the normal Assistant `requirements.txt`. The explicit `prepare` operation downloads
a pinned public model (roughly 470 MB for the weights, plus tokenizer files).
Evaluation loads only local files; there is no model fallback or automatic download.
All model/cache paths must be outside this repository.

```sh
lab=/tmp/disc-nlu-lab
python3.12 -m venv "$lab/venv"
"$lab/venv/bin/python" -m pip install -r research/disc_assistant/experiments/nlu/requirements.txt
"$lab/venv/bin/python" -m research.disc_assistant.experiments.nlu prepare --work "$lab"
"$lab/venv/bin/python" -m research.disc_assistant.experiments.nlu evaluate \
  --work "$lab" --output "$lab/report.json" --with-retrieval
```

Run from the repository root. `--with-retrieval` requires Docker and an already
available `typesense/typesense:30.2` image. It uses a random Compose project, private
random test key and ephemeral loopback port/volume; cleanup runs on ordinary errors
as well as success. It does not start or stop the normal `disc-assistant` stack.
Omit the flag for intent-only evaluation. Choose a new output path for every run;
existing reports are not overwritten. After an abrupt process kill, inspect Docker
for the uniquely named `disc-nlu-*` project before cleaning up only that project.

`embeddings.sqlite3` caches normalized text vectors by model/pipeline and exact
text hashes. Model revision, local file hashes and runtime versions identify the
pipeline; corrupted vectors fail validation. Model files are checked before every
load. The cache is reusable across fixture generations for identical text, while
each disposable search collection belongs to one catalog generation. The
catalog-to-vector projection is built afresh; this is not a deployed persistent
Library embedding index. Model files, caches, virtualenvs and generated reports
are not application assets. Curated synthetic evidence may be committed separately.

## Datasets and measures

`intents.json` has 182 authored RU/EN phrases, with **27 train, 26 development and
38 test cases per locale**. Train phrases are nearest-exemplar references, including
non-commands. Character TF-IDF vocabulary is fitted on train only. Development
chooses acceptance score and top-two-class margin, minimizing false activation
before maximizing macro-F1. Test data never selects thresholds. The rule-first
variant is evaluated as a whole: it cannot hide errors already accepted by rules.
This is an authored text holdout, not independent collection, speaker-disjoint
speech evaluation or evidence of general real-world quality.

The report retains the development threshold grid and unthresholded test diagnostics
(without selecting a new threshold from test). It includes per-class confusion,
false activations, rejected commands and
fully matching positive intents. A play/language class prediction alone cannot
invent slots: these variants reuse existing rule extraction where it succeeds.
Controls have no argument slots. Classification accuracy and complete-intent
accuracy are therefore separate. Unsupported volume commands count as rejection;
ambiguous phrases such as “Play nothing” reflect the authored test interpretation,
not a universal linguistic truth. No predictions are executed.

`music.json` contains 24 synthetic metadata rows, 8 development queries and 26
test queries. Development and test artists are separate. Earlier Linkin Park
speech failures are included only in test, alongside new collisions/negative
examples. This dataset covers names, not mood/lyrics semantics. All variants share the existing parser; learned interpretation is not involved.
One case deliberately exposes its qualifier ambiguity: `Play Artist E - Tishina`
is parsed as an explicit artist request, so retrieval alone cannot repair it.
Parsed/resolved intentions are retained to separate this from missing candidates.

Vectors encode `artist — title — album`. Lexical queries use projected spellings;
semantic queries preserve the resolved original spelling. The experiment compares
raw top-1/recall@10 and the final result after shared lexical-v3 constraints,
including exact-match fast paths, artist scope and edition checks. It does not
replace the final ranker with a vector score or add an artist-vector classifier.
Final preview retrieval can request up to 50 candidates; raw recall@10 is a separate
bounded diagnostic. Raw search then guarded search are both timed, so
`diagnostic_total_ms` is not a production single-request latency estimate.

Vector distance and hybrid alpha are selected using development queries only,
minimizing false selections, then maximizing correct selections and raw recall.
Grid: distance 0.3/0.5/0.7, hybrid alpha 0.3/0.7. Vector-only alpha is irrelevant.
Ties retain the first tested setting. The final report records every development
trial and one test pass per selected variant. Empty/failed vector search is not
silently converted to lexical success. Exact metadata matches still bypass search
in the common final ranker, and this is exposed in `guarded_retrieval`.

Resources include model files, process peak RSS, startup and warm uncached single
query embedding p50/p95. Those few sequential probes are descriptive, not a
controlled benchmark; RSS includes Python and experiment dependencies and excludes
the Docker service. Cached vector lookup/batched corpus encoding do not stand in
for online query latency. No Pi performance claim follows from desktop numbers.

## Boundaries and follow-up

The experiment does not enable semantic commands in `ask` or the console. It does
not train SetFit, generate natural-language Typesense filters, install an LLM,
record speech or add automatic vocabulary correction. See the
[research plan](../../../../docs/ASSISTANT_NLU_RESEARCH.md) for the remaining
Natural Language Search, slot extraction, phonetic and training comparisons.

Unit tests use no model or Docker and are included in `run.sh test`. They verify
split validation, calibration/rejection accounting, cache invalidation/corruption
and vector transport/snapshot failure handling. The full experiment supplies
separate actual-model and real-Typesense evidence.

## Recorded result: 2026-09-18

[Full evidence](evaluations/2026-09-18.json) includes model/file hashes, dataset
signatures, thresholds, development trials, confusion matrices and per-case
retrieval/selection evidence. Python 3.12/macOS arm64, CPU with four Torch threads.

| Intent strategy | RU correct commands / 22 | RU false activations / 16 | EN correct commands / 22 | EN false activations / 16 |
| --- | --- | --- | --- | --- |
| Current rules | 4 | 1 | 4 | 1 |
| Character n-grams, calibrated | 0 | 0 | 0 | 0 |
| Embeddings, calibrated | 0 | 0 | 2 | 0 |
| Rules then calibrated embeddings | 4 | 1 | 6 | 1 |

Low rule coverage is expected on deliberately unfamiliar paraphrases. The shared
false activation is “Play nothing” / “Включи ничего”: classified as a music request,
not evidence of a player mutation. Without rejection thresholds, embedding nearest
labels recognize 12/22 RU and 15/22 EN commands but falsely accept **12/16 RU and
13/16 EN non-commands**. Calibrating for minimum development false activations
selects reject-all for RU and character matching. Do not present zero false
activations from a reject-all model as success. English embedding classification
also confuses some actions and does not extract new music/language arguments.
Complete positive intents for rule-plus-embedding are only 4/22 in each locale.

| Track retrieval with common final guards | Correct expected recordings / 20 | False selections on absent targets / 6 | Raw recall@10 / 20 |
| --- | --- | --- | --- |
| Lexical-v3 | 15 | 0 | 16 |
| Vector | 17 | 0 | 19 |
| Hybrid, development-selected settings | 15 | 0 | 16 |

Vector candidates recover `Nom` → `Numb` and `In the And` → `In the End` without
aliases. Fused Russian names remain unresolved. The qualifier ambiguity described
above remains a shared parser failure. Vector raw top-1 is only 11/20 versus
13/20 lexical: the improvement depends on the common final constraints/ranker,
not blindly executing the nearest vector. Six hybrid configurations tied on
all development selection criteria; the conservative first-setting tie-break
chose distance 0.3/alpha 0.3. This does not show that hybrid search cannot help;
the small development set did not distinguish its settings.

The detailed run reports 7.26/8.60 ms warm uncached embedding p50/p95 on twelve
short **English** probes; startup 3.61 s, model files 499,557,407 bytes, process
peak RSS 1,138,180,096 bytes. The cache was populated by an earlier attempt; corpus
encoding was cached, while the twelve latency probes explicitly bypassed it.
These are descriptive desktop observations, not RU/Pi latency or service memory
budgets. No new hardware/backend recommendation is established by this run.

Decision: retain the live rules/lexical path. Vector fallback after a lexical miss
is worth a larger read-only test; the embedding intent classifier is not ready
for command execution. Next compare a classifier trained on explicit hard
negatives (including negation and reported speech), improve slot extraction and
exercise structured Natural Language Search on a typed metadata fixture. Do not
rewrite the test corpus to make the current model pass.
