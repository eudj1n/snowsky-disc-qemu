# Shadow reports and review queues

Implemented **2026-09-18**. This offline tool connects
[shadow observations](ASSISTANT_INTERPRETATION_SOURCES.md) to the existing
[annotation workflow](ASSISTANT_NLU_DATA.md). It reads only the supplied history
export; it never opens runtime SQLite/configuration, invokes an interpreter,
contacts DISC or Typesense, trains, or selects a winner.

## Collect and report

Enable `/shadow on` in the console. `/debug on` is optional for display; journal
persistence must be enabled to export evidence. Ordinary commands execute normally;
use `/rank TEXT` or `/rank --audio PATH` for interpretation/search without playback.
`/explain` is a separate diagnostic and does not produce a primary-vs-shadow event.

Export from the console:

```text
/history export /tmp/disc-history.jsonl
```

Or use the one-shot history command, then create a new report directory:

```sh
./research/disc_assistant/run.sh history export /tmp/disc-history.jsonl
./research/disc_assistant/run.sh shadow-report \
  --history /tmp/disc-history.jsonl --output /tmp/disc-shadow-report
```

`shadow-report` needs the normal Assistant venv, but no runtime config, device or ML
packages. Relative file arguments are resolved against the launcher's calling
directory. Outputs must be outside the repository in a new directory (0700); files
are exclusive and private (0600). A prior report is never overwritten.

| Output | Contents |
| --- | --- |
| `report.md` | Readable source counts, primary disagreements, p50/p95 and reviewed-quality tables when available |
| `report.json` | Full source identities, source/STT revisions, counts, reasons, denominators, exclusions and input-file fingerprints |
| `pending.jsonl` | Compatible annotation queue; no predictions, labels, intentions or split inferred |
| `evidence.jsonl` | Exact input, hashed request reference, context, source predictions/spans/scores/versions and disagreement reasons |

Device identifiers, network addresses, audio file paths, arbitrary SDK payloads,
playback/search outcomes and raw history records are not copied. Text and source
predictions remain personal data; files are local, with no automatic publication.
Audio/STT fingerprints allow related observations to be identified without audio.

## What the report means

Tables separate locale, text/speech, STT model fingerprint and source identity /
version / snapshot or grammar revision. Different model generations do not silently
share an accuracy or timing row. Unknown fingerprints stay unknown.

`recognized`, `rejected`, `unsupported`, `incomplete` and `unavailable` retain
separate counts. The report compares available sources against the observed primary
and checks source-to-source disagreement too. Recognition, label, complete-intent
and same-action argument disagreements are separate flags; flags can overlap.
Unavailability is an operational failure, **not a semantic vote or evidence of an
error by another source**. A negative search/playback outcome is not an intent label.

Without reviewed annotations, `quality` is null. The tool cannot claim which source
is correct. Latency uses nearest-rank p50/p95 with a sample count; both all observed
source durations and available-only durations are retained. Timeout/unavailable
observations remain visible. Missing duration is unknown, not zero. Primary duration
is not reconstructed from unrelated request stages. These are observed source
latencies, not end-to-end request latency or a Raspberry Pi benchmark.

Counts are **request-occurrence weighted** with unique-input counts alongside them.
Repeated exports of the same request ID count once; conflicting duplicates fail.
Repeated submissions with different request IDs count as separate observations.
Truncated/unusable inputs, missing/ambiguous shadow events, invalid evidence/context
and collector failure are explicitly counted in coverage, not treated as successful
rejection. A report with no eligible events is valid and has no quality claims.

## Review and rescore

By default only inputs with semantic disagreement enter `pending.jsonl`. Use
`--review-scope all` to include ordinary agreements and unanimously rejected cases:

```sh
./research/disc_assistant/run.sh shadow-report \
  --history /tmp/disc-history.jsonl --output /tmp/disc-shadow-all \
  --review-scope all
```

Exact locale/text repeats share one pending ID. Original spelling/spacing is retained
for reliable argument offsets; normalized variants remain separate rows but share
an annotation group. Related transcripts linked by a common audio hash also share
a group, including connections through repeated text. Reviewers still need to group
paraphrases/translations and future speaker/session relationships manually.

Annotate with the existing `dataset review` schema: explicit reviewer/rationale,
label, full typed intention (or null), exact slots and group/split. Queue inputs are
not silently replaced by predictions from the evidence file. Prefer independent
review of text before inspecting source predictions. Only mark ambiguous cases
reviewed after their intended meaning is resolved.

```sh
assistant_python=research/disc_assistant/assistant/.venv/bin/python
"$assistant_python" -m research.disc_assistant.assistant.nlu.evaluation.dataset review \
  --queue /tmp/disc-shadow-report/pending.jsonl \
  --annotations /tmp/disc-annotations.jsonl --output /tmp/disc-reviewed.jsonl
./research/disc_assistant/run.sh shadow-report \
  --history /tmp/disc-history.jsonl --output /tmp/disc-shadow-scored \
  --reviewed /tmp/disc-reviewed.jsonl
```

The reviewed file may contain pending rows; only explicit reviewed rows contribute
quality. IDs, locale and exact text must match the supplied export. Duplicate,
unknown or changed inputs are rejected before creating the output directory.
Partial review is allowed and denominators show its exact coverage.

Quality includes positive complete-intent correctness, positive abstention,
wrong-action and same-action wrong-argument counts; language/music argument
accuracy; and false activations on non-executable gold (including incomplete
requests). Source unavailability is retained separately. These are **predicted**
activations: shadow never dispatches actions. Repeated observations of one reviewed
input still contribute multiple occurrences; the unique-label count makes this visible.

A disagreement-selected queue is biased toward hard cases. Neither it nor an
agreement-only sample is an independent acceptance set. This tool does not fit or
calibrate weights, evaluate a newly selected model, infer quality from consensus,
or measure physical execution. The next product gate is the
[MVP end-to-end baseline](ASSISTANT_MVP.md), followed by agreed thresholds.

Structured-model evidence retains model, prompt and schema fingerprints as
separate revision identity. Changing only a prompt therefore splits report groups
even when the model file is unchanged. Invalid model output is unavailable
evidence, never a vote or a successful negative prediction.
