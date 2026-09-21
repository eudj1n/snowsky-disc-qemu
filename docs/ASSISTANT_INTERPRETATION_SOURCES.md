# Independent interpretation sources and shadow comparison

Implemented in the research prototype on **2026-09-18**. Experiments now share an
interpretation-evidence contract. They remain independent sources, not sequential
stages that silently reuse another source's decision. A future selector may learn
which evidence to trust. No score weighting, learned selector or automatic model
promotion is implemented.

## Execution boundary and MVP scope

The primary `Interpreter` still owns the executable typed intention. Optional
shadow sources see the same text and immutable `InterpretationContext` (one active
locale, observed playback, optional catalog hints). They receive no application,
Controller, search client or writable catalog. These are architectural interfaces,
not a sandbox for untrusted Python plugins.

The MVP accepts **one action with its arguments**. It has no command list, planner,
conditional execution, delayed actions or clarification dialogue. A shared policy
runs before the primary provider for text and post-STT input, even with shadow off.
It rejects known sequencing/alternative connectors followed by another action,
commas/semicolons followed by recognized actions and unclosed double quotes.
Semicolons inside a captured artist credit remain part of its music reference.
`Find and play song Clouds` names one semantic action. `Play Blur and then stop`
or `Stop the music or maybe resume instead` is unsupported, without partial execution.

Double quotes, guillemets and smart double quotes protect music references:
`Play song "Stop and Play"` is allowed. This is a bounded literal grammar, not a
proof that every compound sentence will be detected. Unsupported phrasing can
still look like a title. New locales without this optional grammar keep ordinary
literal parsing; they do not acquire compound/context coverage automatically.
Negation, reported-speech and non-music-target guards in the **slots source** are
currently diagnostic; only the shared single-action policy is applied to live rules.

## Evidence contract

`assistant/nlu/interpretation_sources.py` defines `Source.evaluate(text, context)` and
`Evidence`. Adding a provider does not require modifying Controller or dispatch.
Register it in `default_sources`; provide source-specific tests and measurements.

| Field | Contract |
| --- | --- |
| `source`, `version` | Stable implementation identity |
| `status` | `recognized`, `rejected`, `unsupported`, `incomplete` or `unavailable` |
| `label`, `intent` | Known label; only recognized results carry a validated typed intention |
| `spans` | Exact original-text character offsets, exclusive end; at most four |
| `reason` | Stable machine-readable explanation |
| `scores` | Optional value, margin, kind and `calibrated: false`; source-local evidence |
| `provenance` | Rules/grammar hash, model hash, snapshot/source hash and thresholds as applicable |
| `elapsed_ms` | Measured source evaluation time |

Current sources:

- `literal`: existing locale parser; reports its own raw decision.
- `slots`: locale-authored context and argument extraction, including inflected
  language names, quoted titles and explicit artist/track/album qualifiers.
- `command_model`: existing imported portable classifier, opened through read-only
  SQLite without migrations, seeding or lock waiting. A play/language class alone
  is `incomplete`; this source never borrows slots or invents arguments.

- `structured_model` (opt-in): local schema-constrained model extracting one label,
  target kind and original text span. Separate model, prompt and schema hashes;
  it is never included in the diagnostic priority selector or live execution.

Missing, locked, stale or untrained model storage produces `unavailable`. Invalid
provider output and ordinary provider exceptions are isolated; exception bodies
are not recorded. Raw scores are **not comparable probabilities** and are not
summed. The collector accepts at most eight unique source identities.

`/explain` exposes all sources and a diagnostic candidate. Its versioned preview
policy prefers complete slots, then literal rules, then classified controls,
subject to context/single-action vetoes. This is a deterministic preview, not the
future learned selector and not an execution provider. Legacy `rules` and
`classifier` fields remain for inspection. The historical `explain.decide` runner
is unchanged so earlier model studies remain reproducible.

## Try shadow mode

In an existing console:

```text
/shadow on
/debug on
пауза
/explain Отвечай мне теперь по-английски
/history show REQUEST_ID
/shadow off
```

`/shadow` reports the current setting. The toggle lasts for this console session.
For startup and one-shot `ask`/`rank`, add to the Assistant TOML:

```toml
[interpretation]
shadow = true
shadow_timeout_ms = 100
```

Default is off. `/explain` always evaluates its diagnostic sources independently
of this flag and never executes the explained request. Import previously trained
bundles explicitly with `/commands import PATH`; no model is installed by enabling
shadow. Source-only snapshots still allow literal/slot comparison.

The journal's `interpretation_shadow` event records the primary decision, input
context, each source, agreement and `execution_source: primary_only`, including
primary rejection. Existing retention/privacy settings apply; journal disabled
means no saved evidence. `/debug on` streams the same bounded event. No raw audio,
extra device request, automatic retry or feedback training is introduced.

Sources are collected concurrently with the primary where it yields. Collection
is awaited before returning so no task survives the per-request event loop. The
1–2000 ms timeout is **cooperative**: synchronous CPU/filesystem work cannot be
preempted. Future network providers must yield and honor cancellation; cancellation
of the request cancels source tasks. This is not a hard real-time latency guarantee.

## Reproduce the offline comparison

No device, Typesense or ML environment is required; use the normal Assistant venv.
The output directory must be new. `--models` is optional; without it the model
source is unavailable and the report still compares rules and slots.

```sh
experiments/disc_assistant/assistant/.venv/bin/python \
  -m experiments.disc_assistant.assistant.nlu.evaluation.compare_sources \
  --models /tmp/disc-command-study-v2-release \
  --output /tmp/disc-source-comparison
```

Import files are the earlier v2 study's `ru-commands.json` and `en-commands.json`.
The runner creates an isolated catalog and writes `report.json` with per-case
source evidence, hashes, timings and exact complete-intent/rejection measures.
It never trains, selects or installs a model into user runtime storage.

The 40 new cases are **implementation acceptance**, authored after grammar design.
The 110 previously inspected v2 test cases are now **regression**, not a holdout.
Initial regression found the compound phrase `Stop the music or maybe resume
instead` was accepted by the classifier fallback. A shared modifier rule and a
regression check were added; the final figures below include that correction.
They must not be presented as independent model-quality estimates.

| Diagnostic preview, final run | RU | EN |
| --- | --- | --- |
| Acceptance: exact complete positive intentions | 12/12 | 12/12 |
| Acceptance: false activations | 0/8 | 0/8 |
| Examined v2 regression: exact complete positive intentions | 21/35 | 22/35 |
| Examined v2 regression: false activations | 0/20 | 0/20 |
| Examined v2 regression: exact language arguments | 5/5 | 5/5 |
| Examined v2 regression: exact music arguments | 5/5 | 5/5 |

The argument source alone covers the ten music/language positives in each
acceptance locale; the other two controls come from independent sources. The
classifier alone still activates on 4/8 acceptance negatives per locale, showing
why its score is insufficient for execution. Live literal rules also retain
non-music-target limitations. No new weight training or independent human/Pi
acceptance occurred. The earlier nine private request annotations were reviewed
by the assistant, marked regression and kept outside Git; they are not independent
human labels or new training data.

The firmware-free prototype suite passes **265 tests**, including 12 source/shadow
checks for isolation, cancellation, read-only model access, journaling, typed/voice
compound rejection and session-only configuration. No physical player was used.

## Next decision gate

[Offline shadow reports and review-queue exports](ASSISTANT_SHADOW_REPORTS.md) are
now implemented. They read recorded evidence without rerunning sources, and
quality requires explicitly reviewed labels.

Collect shadow disagreements and independently annotate complete intentions,
arguments and rejection reasons. Freeze fresh evaluation data before adjusting
providers or a selector. Keep source predictions and model versions as features,
never as ground truth. Compare calibrated per-source policies against a learned
selector on false activations, complete-intent accuracy, abstention and latency.
A selector must return the same validated intention contract and remain behind
single-action/Controller boundaries. Complex commands remain outside this MVP.

## Optional structured local model

The ordinary requirements already include its HTTP dependency; Torch and a model
are not installed automatically. Start a dedicated compatible llama.cpp server
explicitly with an installed GGUF (the measured runtime/model are pinned in the
[comparison report](ASSISTANT_REVIEW_EVALUATION.md)):

```sh
llama-server -m /absolute/path/model.gguf --alias disc-commands \
  --host 127.0.0.1 --port 18120 -c 2048 -np 1 -t 4 -n 192
```

```toml
[interpretation]
shadow_timeout_ms = 1000

[structured]
enabled = true
endpoint = "http://127.0.0.1:18120/v1/chat/completions"
model = "disc-commands"
model_path = "/absolute/path/model.gguf"
timeout = 10
```

`/explain TEXT` now includes the fourth source. `/shadow on` also records it during
normal requests. Primary rules still decide; model disagreement cannot replace a
rejection, fill missing arguments or execute an action. `structured.enabled=false`
is the default. The service receives only input text, interaction locale and the
cached playback label, not catalog contents or command history. Only explicit
loopback IP endpoints are accepted; redirects/environment proxies are disabled.

The schema is `{label, kind, query}`. Music and language queries must be original
input substrings. The shared music parser creates track/album typed arguments;
language names resolve through installed locale dictionaries. Controls/rejections
must have an empty query and `kind=none`. Extra fields, truncated output, a wrong
model alias, invalid locale/arguments or an oversized response become unavailable
evidence. Response validation is bounded to 64 KiB and 192 output tokens. No raw
SDK bodies or exception messages are journaled. A file digest identifies the
operator-configured model; the server does not attest that it loaded that file.

Prompt and schema hashes are retained by offline shadow reports, so changing a
prompt does not silently merge measurements. Scores are absent: there is no
fabricated confidence. New locale support still requires corpus evidence for that
model; accepting the locale dictionary does not prove model comprehension.

The existing shared shadow deadline is 100 ms by default, explicitly configurable
up to 30 seconds. It covers all sources; the model request also has its own timeout.
`/explain` and shadow collection wait up to this chosen deadline, so a larger value
can add command latency. Cancellation is propagated, no request is retried, and
server lifecycle remains operator-owned. Use `/explain` for model experiments
without live-command latency.
