# Review follow-up comparisons, 2026-09-18

These are examined synthetic regressions, not independent acceptance, physical
playback success rates or Raspberry Pi measurements. Raw private reports retain
all rows, inputs, hashes and errors. No personal catalog was used.

## Retrieval

`python -m research.disc_assistant.experiments.search_compare --output NEW_DIR`
uses a disposable Typesense 30.2 server on loopback port 18118 and the explicit
`TYPESENSE_API_KEY` environment variable. It builds/removes only its own random
collection and creates a new local SQLite fixture directory. Start a disposable
server with an existing data directory (e.g. `--data-dir=/tmp` inside a temporary
container); do not point this experiment at a personal catalog.

The 84-recording fixture contains 80 titles mentioning another artist's name.
Five cases cover top-k pressure, a collaboration member, Cyrillic, a joined title
and a missing requested edition. Ranking and query text are identical across
variants; only one retrieval option changes.

| Variant | Correct final candidates / cases |
| --- | --- |
| Existing retrieval, post-filter artist | 3/5 |
| `split_join_tokens=fallback` | 3/5 |
| `split_join_tokens=always` | 3/5 |
| Exact known artist filter before top-50 | 4/5 |

In the pressure case, 81 documents matched; the old top-50 contained zero rows
from the requested artist. Prefiltering returned the correct single row. The
joined-title case remained unresolved in this isolated retrieval test (the live
catalog resolver has its own fused-name rules). This is not evidence that all
split/join queries fail, only no benefit on this small set.

Promoted: prefiltering a catalog-resolved artist. Schema 4 adds a derived SHA-256
raw-credit key so names never become filter syntax. `/index` rebuilds the
projection; `/sync` is unnecessary. Post-read SQLite checks and the local artist
constraint remain. No default split/join, token-set scoring, phonetics, synonym
server state or margin-based rejection was introduced. Lexical policy is v5.

Reports: `/tmp/disc-review-search-02` and `-03`. The first case used a three-letter
typo token outside default Typesense typo length rules and returned zero in every
variant. The revised diagnostic uses a four-letter token; the first report is
retained and neither is an independent holdout.

## Speech

`python -m research.disc_assistant.experiments.speech_compare --samples DIR
--model MODEL --executable WHISPER_CLI --server http://127.0.0.1:18119/inference
--output NEW_DIR` replays the same six saved WAVs per locale twice (24 observations
per variant, **12 unique samples**, not 24 independent utterances).

Runtime: existing whisper.cpp v1.9.4 source build, multilingual base, CPU, four
threads, beam size 5, best-of 5, temperature 0, no fallback or token timestamps.
Server startup/model loading is excluded from resident timings; CLI process/model
startup is included. Repeat 1 is warm; individual first-request timings remain in
the report. Files are fingerprint-checked. Fixed vocabulary uses synthetic music
names and never reads expected transcripts or labels to form a prompt.

| Variant | Exact typed intentions / 24 | Median STT ms | Warm-repeat median ms |
| --- | --- | --- | --- |
| CLI | 12/24 | 318.115 | 318.068 |
| Resident | 12/24 | 225.953 | 225.953 |
| Resident + catalog names | 18/24 | 251.248 | 249.697 |

Exact slot text is required here: a phonetic query recoverable by the catalog may
still fail this measure. Conversely, a correct intention does not prove successful
device playback. The no-command samples also contribute to this measure. Full
command latency still includes the approximately 2.1-second device settling guard.
No firmware timer was shortened to improve these figures.

`/tmp/disc-review-speech-01` used mismatched upstream CLI/server decoder defaults;
it is exploratory and retained. `/tmp/disc-review-speech-02` explicitly matches
beam/timestamp settings and is the table above. The small synthetic set supports
an optional backend, not a default model change or a hardware performance claim.
Resident mode and hints remain opt-in. Hint truncation and snapshot fingerprint
are logged; the endpoint cannot attest its loaded model, so that binding is
explicitly operator-configured.
