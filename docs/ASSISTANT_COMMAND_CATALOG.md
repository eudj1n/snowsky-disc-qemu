# Command catalog and explanation preview

Implemented **2026-09-18** in the research prototype. `explain` compares the live
literal grammar with a separate diagnostic candidate. It never dispatches a
command, searches the music library or changes language from the supplied text.
The normal `ask`, `rank` and voice execution paths still use the existing
`RuleInterpreter`. Importing a model does not change that provider.

## Use

With the desired interaction locale selected:

```text
/commands
/explain Пожалуйста включи трек Пауза
/explain Не ставь музыку на паузу
/explain Пожалуйста переключи язык на английский
```

The equivalent one-shot commands work offline, including while the console owns
the device connection:

```sh
./experiments/disc_assistant/run.sh commands
./experiments/disc_assistant/run.sh explain 'Пожалуйста включи трек Пауза'
```

`/explain` uses the saved interaction locale. The usual explicit `--language CODE`
launcher option still changes that saved preference; a language intention *inside*
the text being explained does not. The first `/commands` or `/explain` publishes
an untrained source snapshot locally. No model download, training or Typesense
startup occurs. `commands rebuild` republishes the current source **without a
classifier**, removing any trained model from the active head while retaining
previous snapshots.

The JSON includes:

| Field | Meaning |
| --- | --- |
| `rules` | Result of the existing literal parser for comparison |
| `candidate` | Diagnostic `recognized`, `rejected`, `unsupported` or `incomplete` intention, source, reason and extracted spans |
| `sources`, `policy`, `context` | Independent evidence, single-action policy and interpretation context; see [source contract](ASSISTANT_INTERPRETATION_SOURCES.md) |
| `classifier` | Optional model's label, runner-up, score, margin and threshold decision; otherwise unavailable |
| `snapshot`, `source_hash`, `locale` | Exact local reference generation |
| `mutation_attempted` | Always false for explanation |
| `request_id`, `timing` | Normal journal correlation and total request duration |

Spans are zero-based Python character offsets into `text`, with an exclusive end.
They cover the captured reference, which may include a target qualifier such as
`трек`; the typed intention contains the parsed query/artist/title. Intent class
accuracy and correct argument extraction are different measures. A learned `play`
or `language` label without an extraction template yields `incomplete`, never an
invented title or language. Rejection is a successful diagnostic result, so the
CLI exits zero; invalid input, missing locale files and stale snapshots are errors.
`/debug on` exposes the `explain` event, also retained in ordinary request history.

The current diagnostic candidate uses [independent sources](ASSISTANT_INTERPRETATION_SOURCES.md):
complete slot extraction, then literal rules, then classified controls, subject
to context and single-action checks. Scores remain separate. Music references
may contain command or negation words; quote ambiguous titles. This bounded
grammar does not parse arbitrary sentences. Preview recognition is not permission
to execute. The original `decide` evaluator remains available for reproducible
historical model studies; current `/explain` adds the newer source comparison.

## Storage and publication

Community files [`assistant/locales/commands/`](../experiments/disc_assistant/assistant/locales/commands/)
supply literal slot templates and rejection phrases. Optional labelled references
live separately in `experiments/disc_assistant/assistant/nlu/data/command_references/`;
they are not required for a locale contribution. The loader combines these sources
into the same logical payload before hashing. Definitions and required
arguments are shared code; language-specific matching text stays in TOML.

Assistant SQLite **schema 3** adds `command_snapshots`, `command_examples` and
`command_heads`. Migrations preserve settings and request/event history. Each
locale has an independent active head. A snapshot pins the full authored catalog,
live locale grammar, optional classifier parameters and embedding provenance.
Examples retain their labels and optional normalized reference vectors. Publication
inserts the complete snapshot and changes its head in one transaction; failed
validation or a database error leaves the previous head intact.

Changing the source or live grammar makes an old head stale. Rebuild it explicitly,
then retrain/import if a classifier is wanted. A model trained against a different
source hash is rejected. Publication hashes include the payload and vectors;
identical publication is idempotent. Old snapshots are retained; automatic snapshot
pruning is not implemented. Journal pruning/clearing does not remove them.

## Training and import

The isolated [supervised experiment](../experiments/disc_assistant/assistant/nlu/evaluation/README.md#supervised-command-study)
trains two multinomial logistic regression heads: shared word/character TF-IDF
features, and frozen multilingual MiniLM sentence embeddings. It does not
fine-tune the encoder. Only the text head is exported for diagnostic inference.
Normal Assistant requirements need no additions: portable JSON weights and a
standard-library scorer suffice. The optional ML stack is training/research only.

A bundle contains a version, locale, source hash, text feature vocabulary/IDF,
class weights/biases, acceptance threshold/margin, training provenance, embedding
pipeline identity/dimensions and a vector for every authored reference. Import
validates dimensions, finite values, normalized vectors, complete example IDs and
source/pipeline hashes. JSON contains data only; no pickle or executable model.
Checksums detect mismatches, not publisher authenticity.

After preparing the experiment environment/model as documented:

```sh
lab=/tmp/disc-nlu-lab
"$lab/venv/bin/python" -m experiments.disc_assistant.assistant.nlu.evaluation.train_commands \
  --work "$lab" --output "$lab/commands-study"
# Select the matching locale first; import only the bundle for that locale.
./experiments/disc_assistant/run.sh commands import "$lab/commands-study/ru-commands.json"
./experiments/disc_assistant/run.sh explain 'Сделай паузу в музыке'
```

Use a new output directory for each experiment. Model bundles, databases and
embedding caches stay outside the checkout. Import is explicit; a training run
never changes the configured Assistant. Stored reference vectors prepare the
future semantic provider but are not queried by the current text classifier.
Embedding a new incoming request would still require an encoder; storing the
reference matrix alone cannot remove that work.

The first run has 42 training examples per locale (21 commands, 21 negatives).
This is deliberately a small baseline, not a production model. See the recorded
study for low command coverage, the EN reject-all threshold and Pi validation
still outstanding. Next collect independent human phrasing and actual STT errors,
expand balanced per-intent examples and negative contexts, and compare training
variants against a new frozen holdout before enabling any execution provider.

## Expanded training checkpoint

The later [v2 data workflow](ASSISTANT_NLU_DATA.md) adds 609 annotated rows,
private history collection/review/freezing, and a generic four-way training runner.
It exports the same bundle format for `/commands import` and `/explain`. Current
locale reference files stay authoritative for runtime grammar/reference snapshots;
a versioned, reviewed training corpus can add examples and pins its own fingerprint
in classifier provenance. Source references must be represented in its train split.
The first small runner/results above remain historical, reproducible evidence.
Expanded models improve control coverage but still make false activations and
miss new language/music slots. A subsequent [argument/source increment](ASSISTANT_INTERPRETATION_SOURCES.md)
addresses these as examined regression; learned live execution remains disabled.
