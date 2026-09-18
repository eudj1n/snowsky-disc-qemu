# Command data, annotation and reproducible training

Implemented **2026-09-18**. The second supervised study adds an explicit annotation
workflow and a frozen bilingual corpus. Training runs locally in the isolated NLU
environment; normal Assistant dependencies and execution behavior are unchanged.
The resulting text models can be imported into `/explain`, not into live `ask`.

## Current corpus and evidence

[`commands-v2`](../research/disc_assistant/experiments/nlu/datasets/commands-v2/README.md)
contains **609 rows** with original text, label, typed intention, argument spans,
locale, split, related-example group, origin and review identity/rationale.
Train/development/test were committed as `cad202b` before the first v2 model run.
Revision v2.1 subsequently restores one omitted old RU regression example with its
language span; fitting and new-test data are unchanged. Its exact
bytes are pinned by the manifest, and the report pins dataset, source, code and
embedding model/pipeline hashes.

| Locale | Training | Development | New test | Earlier regression |
| --- | ---: | ---: | ---: | ---: |
| RU | 109 | 40 | 55 | 100 |
| EN | 110 | 40 | 55 | 100 |

Training now has 9–11 examples for each positive class and 35 negatives per locale.
Development has four per positive class and 12 negatives; test has five per
positive class and 20 negatives. New bilingual example families stay in the same
split. Previously examined text sets and native STT outputs from synthetic audio
are regression only. Some regression phrases occur in training; the audit exposes
that overlap, and these scores are not holdout evidence.

**Labels are assistant-authored.** This is a larger reproducible baseline, not
independent human collection. The new test is fresh only for the first v2 study;
once inspected, use it as regression during subsequent redesign and collect a
new holdout. Do not move failed test phrases into training and continue reporting
them as independent evaluation.

The [full report](../research/disc_assistant/experiments/nlu/evaluations/2026-09-18-commands-v2.json)
compares ordinary and class-balanced multinomial logistic regression on shared
word/character TF-IDF features and frozen multilingual MiniLM embeddings. The
encoder is not fine-tuned. Every variant uses the same splits, C/threshold/margin
grid and development-only selection policy, fixed in the corpus README before
training. Both locale text variants selected for export are ordinary C=10,
threshold 0.35, margin 0.10. No test score chooses the exported model.

| Standalone accepted classifier | RU correct / 35 | RU false activations / 20 | EN correct / 35 | EN false activations / 20 |
| --- | ---: | ---: | ---: | ---: |
| Text, ordinary | 18 | 2 | 16 | 2 |
| Text, balanced | 10 | 1 | 0 | 1 |
| Embeddings, ordinary | 12 | 2 | 10 | 0 |
| Embeddings, balanced | 5 | 0 | 11 | 1 |

These are class labels, not complete executable intentions. The report separately
counts rejected valid commands, wrong accepted actions, raw predictions, per-class
confusion and the upper bound compatible with zero observed negative failures.
Zero failures on 20 negatives still permits an approximately 13.9% one-sided 95%
upper bound; it does not establish a reliable false-activation rate. Balancing
is not automatically better: the EN text variant recognizes no correct test
commands at its selected threshold while still making mistakes.

| Full diagnostic pipeline | RU complete / 35 | RU false activations / 20 | EN complete / 35 | EN false activations / 20 |
| --- | ---: | ---: | ---: | ---: |
| Current extraction templates/guards | 2 | 2 | 2 | 1 |
| Templates/guards + selected text model | 12 | 3 | 14 | 2 |

The combined preview extracts correct music intentions in only 2/5 new cases per
locale and language arguments in **0/5**. A correct learned `play`/`language` label
without an extraction pattern remains incomplete. Expanding classification alone
cannot solve slot extraction. The current grammar also accepts “Включи свет в
комнате” as a music query and takes “Play Moby and then stop the music” as one
music reference. A classifier may accept conflicting actions such as “Stop the
music or maybe resume instead”. These are interpretation false activations, not
evidence that a device command was sent; no predictions in this study execute.

On earlier synthetic-speech STT transcripts, the combined preview gets 9/10 RU
and 9/9 EN positive intentions correct with no false activations on two/three
negative transcript rows. These are correlated outputs from six synthetic samples
per locale evaluated with two STT models, not new human audio. The isolated EN
transcript `cause` is rejected rather than taught as a `pause` alias. Music gold
preserves the recognized spelling; these intention scores do not measure whether
`Lincoln Park` resolves to the correct artist in the music library.

Portable JSON scoring agrees with scikit-learn to 1e-10 on 390 RU / 390 EN
comparisons across the two text variants. Selected bundles are 1,269,048 bytes RU
and 1,109,692 bytes EN, including reference vectors and provenance. On this desktop,
165 warm probes per locale measured text-scoring p50/p95 0.168/0.191 ms RU and
0.159/0.193 ms EN. This excludes model/DB loading, argument extraction, STT and
sentence embedding; no Pi memory or latency claim follows. Runtime scoring still
needs no Torch, sklearn or embedding encoder.

## Reproduce or import

Prepare the isolated Python 3.12 environment and pinned embedding model using the
[NLU setup](../research/disc_assistant/experiments/nlu/README.md#reproduce), then:

```sh
lab=/tmp/disc-nlu-lab
"$lab/venv/bin/python" -m research.disc_assistant.experiments.nlu.dataset validate \
  research/disc_assistant/experiments/nlu/datasets/commands-v2
"$lab/venv/bin/python" -m research.disc_assistant.experiments.nlu.study_commands \
  --work "$lab" --output "$lab/commands-v2-run"
```

Use a new output directory each time. After model preparation the study requires
no network, Docker, device, user settings or music index. It writes a report,
ordinary/balanced text bundles, the development-selected `ru-commands.json` and
`en-commands.json`, and a separate import-check SQLite database. An explicit
`--dataset DIRECTORY` can select another validated version and installed locales;
there are no RU/EN branches in this runner.

With Russian active in the regular console:

```text
/commands import /tmp/disc-nlu-lab/commands-v2-run/ru-commands.json
/explain Давай пока сделаем паузу
```

This phrase now reaches the trained control fallback in the recorded model.
`/commands rebuild` restores a source-only preview snapshot. Neither operation
changes the live interpreter. The original `train_commands` runner remains
available to reproduce the first small experiment.

## Collect a private annotation queue

History stores what was requested and what happened, not verified intent labels.
Collect failures as well as successes; a failed search does not mean the command
itself was a non-command. Do not use the assistant's selected action as gold.

```sh
./research/disc_assistant/run.sh history export /tmp/disc-history.jsonl
assistant_python=research/disc_assistant/assistant/.venv/bin/python
"$assistant_python" -m research.disc_assistant.experiments.nlu.dataset collect \
  --history /tmp/disc-history.jsonl --output /tmp/disc-pending.jsonl
```

Collection reads only the explicitly supplied export. It retains text and locale
from `ask`, `rank` and `explain`, preferring the normalized speech transcript when
present. It omits truncated inputs, maintenance commands and audio requests that
never produced text. It deduplicates NFC/case/whitespace equivalents, preserving
quotes and question marks because they can change intent. Predictions, playback
state, device addresses and file paths are not copied. Each row has a hashed source
reference and **pending** review, with no label/split/intent assigned.

When available, the audio and STT model fingerprints are retained; different
transcripts of the same recording automatically share an audio group. Reviewers
must also group related paraphrases, synthetic derivatives and translations.
Speaker/session separation for future human speech evaluation needs additional
collection metadata; a recording hash alone does not establish that separation.
Files are created exclusively with private permissions outside the repository.
The tool never opens a player connection or uploads history.

## Review and freeze a version

Edit a separate JSONL annotation file, one reviewed row per ID. For an unambiguous
pause request, an annotation looks like this (replace ID/group and reviewer):

```json
{"id":"history-COPY_ID","group":"family-COPY_ID","split":"train","review":{"status":"reviewed","by":"reviewer-name","note":"Explicit temporary pause request."},"label":"pause","intent":{"action":"pause"},"slots":[]}
```

Apply only those explicit annotations; other queue rows remain pending:

```sh
"$assistant_python" -m research.disc_assistant.experiments.nlu.dataset review \
  --queue /tmp/disc-pending.jsonl --annotations /tmp/disc-labels.jsonl \
  --output /tmp/disc-reviewed.jsonl
```

Music intentions must include all four canonical fields, for example
`{"query":"Линкин Парк","kind":"artist","artist":null,"title":null}`.
Add a `query` slot with `start`, exclusive `end` and exact `text` from the original
input. Language intentions use `{"locale":"en"}` and a `language` slot containing
the target's original wording. A clear class with no target has `intent: null`
and no slots. Reject has no executable intent or slots. Do not silently correct
artist/title spelling in the gold query; catalog resolution is a separate task.

Assign related examples to one group and split. Review ambiguity against the
single-command policy rather than guessing an action. Preserve negated controls,
reported speech, unsupported requests and conflicting/multiple actions as negative
examples. Negation inside a song title is not automatically a negative command.

Assemble a fully reviewed JSONL corpus, with every class and negatives represented
in train/development/test for each locale. A small queue of recent requests is not
sufficient on its own. Retain earlier examined cases in regression. Then freeze:

```sh
"$assistant_python" -m research.disc_assistant.experiments.nlu.dataset freeze \
  --input /tmp/disc-reviewed-corpus.jsonl --output /tmp/disc-corpus-v3 --name commands-v3
```

Validation rejects pending rows, malformed typed intentions, inconsistent spans,
normalized duplicate text or related-group leakage across fitting/evaluation
splits. A token-overlap audit flags cross-split near duplicates; regroup or replace
them before freezing. This heuristic does not prove semantic independence.
The snapshot hashes exact data bytes and never overwrites an existing version.
The trainer also requires all current locale reference examples in training so
its exported command bundle agrees with the runtime source snapshot.

## Status and next gates

Done: frozen annotations, private collection/review/versioning, four-way supervised
comparison, separate class/argument/rejection measures, recorded STT regression,
portable export/import and normal-runtime smoke check. The prototype suite has
253 tests, including 12 new corpus/annotation checks; no physical-player run was
needed for this stage.

Next: independently reviewed human phrasing and actual microphone STT data.
[Argument/context extraction and independent shadow sources](ASSISTANT_INTERPRETATION_SOURCES.md)
are now implemented; the former v2 test set is regression for this later work. Encoder fine-tuning
remains a later measured comparison after data review, not an implemented backend.
Live learned execution, microphone capture, automatic feedback training and Pi
resource acceptance are still pending. No runtime model was automatically installed
into the user's Assistant by this study.
