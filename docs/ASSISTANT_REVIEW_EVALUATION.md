# Review follow-up comparisons, 2026-09-18

These are examined synthetic regressions, not independent acceptance, physical
playback success rates or Raspberry Pi measurements. Raw private reports retain
all rows, inputs, hashes and errors. No personal catalog was used.

## Retrieval

`python -m experiments.disc_assistant.evaluation.search_compare --output NEW_DIR`
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

`python -m experiments.disc_assistant.evaluation.speech_compare --samples DIR
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
command pacing retains the 2.1-second stock interval. The 2026-09-19 follow-up
removed unconditional per-command sleeps; only the remaining interval is waited.
No firmware timer was shortened to improve these figures.

`/tmp/disc-review-speech-01` used mismatched upstream CLI/server decoder defaults;
it is exploratory and retained. `/tmp/disc-review-speech-02` explicitly matches
beam/timestamp settings and is the table above. The small synthetic set supports
an optional backend, not a default model change or a hardware performance claim.
Resident mode and hints remain opt-in. Hint truncation and snapshot fingerprint
are logged; the endpoint cannot attest its loaded model, so that binding is
explicitly operator-configured.

## Structured model evidence

Pinned runtime: official llama.cpp **b11039**, macOS ARM64 release asset SHA-256
`5e97da2172606284b390fb2bd2fedc03ec8bafd8eaa7d7e840bf46e3f675aa94`.
Pinned model: official [Qwen2.5-0.5B-Instruct-GGUF](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF),
revision `9217f5db79a29953eb74d5343926648285ec7e67`, Q4_K_M file SHA-256
`74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db`.
The desktop run used Metal, context 2048, one parallel slot, four CPU threads,
192 output tokens, temperature/seed zero. This is **not a Pi benchmark**.
The adapter uses the server's [schema-constrained chat API](https://github.com/ggml-org/llama.cpp/blob/b11039/tools/server/README.md).

`python -m experiments.disc_assistant.assistant.nlu.evaluation.structured_compare --model-path
MODEL_GGUF --output NEW_DIR` compares live rules (including the shared gate),
slots and structured evidence. It never connects to a player. The 40 existing
slot examples remain unchanged; 12 explicit album/credit/title/injection/sequence
regressions were added. No training, prompt tuning or source promotion occurred.
All 52 cases have examined regression status, not independent holdout status.

| Source | Exact positive intentions RU / 16 | EN / 16 | Undisputed negative activations RU / 9 | EN / 9 |
| --- | --- | --- | --- | --- |
| Live rules + guard | 7 | 7 | 0 | 0 |
| Diagnostic slots | 14 | 14 | 0 | 0 |
| Qwen structured evidence | 5 | 7 | 5 | 6 |

There are also two original rejection-only examples, one per locale, that the
owner previously disputed because they can be music titles (room lights).
Their original gold and results remain in the reports with explicit review flags;
they are not counted as established live-rule defects. Including that original
gold gives one activation per locale for live rules, zero for slots, and six/seven
for the model. These are interpretation outputs, **not unintended device writes**.

The model adapter marked **10 RU / 7 EN results unavailable due to invalid output**
(e.g. argument not an original substring or control with music arguments). These
are separately counted, not successful rejections. Model medians: **119.790 ms RU,
110.287 ms EN**, including validation. Valid JSON and an exact argument substring
still failed to prevent false semantic activations. This model/configuration is
therefore retained only as an optional shadow source, with no execution or
priority-selector promotion. Other model sizes/prompts need separate frozen
comparisons; these results do not establish that the whole approach is unsuitable.

Reports: `/tmp/disc-review-structured-01` and `-02`. The second records explicit
invalid-output counters and the existing gold dispute; model/prompt/schema remain
unchanged. Real CLI `explain` also returned all four sources with
`mutation_attempted=false` using an isolated configuration. Model artifacts and
raw local reports are outside Git.
