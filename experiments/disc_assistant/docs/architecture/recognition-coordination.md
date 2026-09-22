# Recognition coordination and speculative retrieval

Architecture groundwork, 2026-09-21. The proposed Python interfaces are in
[`assistant/recognition.py`](../../assistant/recognition.py). Only the immutable
plan and interface/data definitions exist: there is no multi-STT scheduler,
candidate assessor, selector implementation, live configuration or UI switch.
The application still uses one explicitly selected STT and its existing guarded
request flow. This does not enable fallback, learned execution or dialogue.

## Ownership and data flow

```text
One validated recording + captured request context
                    |
         RecognitionCoordinator
      single / sequential / parallel
                    |
       STT adapters -> candidates
                    |
        CandidateAssessor (Assistant)
     read-only NLU + catalog resolution
                    |
          CandidateSelector
         selected / abstain
                    |
       Application dispatch boundary
   fresh checks -> at most one operation
```

Coordination belongs to the Assistant application, above the
[speech adapters](../guides/voice-adapters.md). An STT adapter returns text and
model evidence; it must not rank catalog objects, choose a command, query a
Controller or invoke another engine. NLU owns typed intentions. Library code
owns snapshot retrieval; the Assistant owns semantic comparison and selection.
Controller owns the final fresh preflight, pacing and mutation.

`RecognitionContext` freezes request/audio identity, locale, device connection
generation and optional catalog/index revision before branching. An assessor
captures read-only snapshots behind that context, including any playback context
needed for album/artist preference. A revision string alone is not the snapshot.
All branches use the same snapshots. Missing context is explicit, not an excuse
to independently query the player from each branch. Reconnect, catalog changes
or superseding user input invalidate selection before dispatch.

`RecognitionCandidate` preserves each attempt, its instance, validated transcript
or explicit failure, provenance reference and elapsed time. A provenance record
must include provider/version, model/config identity and measured timing. No
speech, timeout, unsupported locale and invalid output are distinct outcomes.
Use ordinary bounded journal/privacy rules; raw audio persistence stays opt-in.

`CandidateAssessment` records a typed intention, resolution outcome and evidence.
An accepted assessment has a `SemanticKey` covering every argument; only music
keys carry a catalog revision and snapshot-scoped selector identity. Different
volume values, play scopes or language targets are not equivalent. Track title,
path and stock song ID are insufficient identities, particularly for CUE entries.
Do not pass an assessment or key directly to a Controller selection helper.

These are trusted Python interfaces, not a sandbox or runtime validation layer.
Implementations must validate candidate membership, locale, status/payload
consistency, semantic key scope and decision references before using results.
Execution must consume one validated assessed intent without reinterpreting text
under a different context, then freshly resolve/verify the device selection.
The existing `natural_request()` combines interpretation and execution: calling
it once for each candidate, even in Preview, is not a suitable assessor. Preview
can currently consult live playback context; extract a snapshot-only assessment
boundary before connecting this proposal to the application.

## Scheduling and selection are separate policies

`RecognitionPlan` lists explicit ordered instance IDs and a total latency budget.
The first instance is primary. Never automatically run every installed adapter:
availability, locale support, memory and thread costs differ. Resolve profiles
before scheduling; the absence of multi-STT settings preserves today's behavior.

| Mode | Intended behavior |
| --- | --- |
| `single` | One selected instance; current compatibility behavior. |
| `sequential` | Assess the primary, then conditionally try the next explicitly configured instance. |
| `parallel` | Run selected instances with bounded concurrency and a common deadline; assess independently. |

Sequential trigger policy must distinguish STT failure/no speech, unrecognized
intent, no catalog match and ambiguity. A safety rejection (negation, compound or
unsupported action) must not be silently reclassified as a recoverable miss.
Additional observations may aid diagnosis, but do not erase a rejection to obtain
an executable result. Stop on a sufficient result or exhausted budget. No model
is retried within the same request. This mode cannot detect every plausible but
wrong primary transcription.

Parallel mode must define completion policy explicitly. The first successful
response is not necessarily the best. At a deadline, preserve pending/timeout
outcomes and abstain when the configured evidence requirement is unmet. Late
responses never modify a returned decision. Cancel and drain owned work; a local
cancel of an external HTTP request does not prove server-side inference stopped.
Respect the existing adapter failure lifecycle and never stop operator services.

Candidate selection is a separate, versioned policy. Proposed initial rules:

- Compare semantic targets as well as text. Different phrasings may agree.
- Conflicting valid actions/targets cause abstention; majority voting alone must
  not override them. An ambiguous candidate may conceal a competing target.
- One catalog match is supporting evidence, not proof that STT heard correctly.
  No-match and unavailable search must remain distinct.
- Do not compare raw STT confidences, Typesense scores and lexical ratios as one
  probability. Agreement among related models is not independent evidence.
- Define quorum/eligibility and permitted failure combinations before enabling
  selection. No thresholds or model ranking are established by this document.

Shadow is independent of scheduling. Secondary candidates produce a diagnostic
counterfactual; live dispatch follows the original primary path and never waits
for them. The application must run the shadow evaluation as bounded, owned work
and collect/drain it independently; awaiting it before primary dispatch would
violate this requirement. Reuse the primary attempt rather than transcribing it
twice. Shadow work must not monopolize the primary's model handle or CPU budget.
Abstention initially returns a non-executing result. A clarification dialogue and
its confirmation lifetime require separate implementation.

Once a device mutation is attempted, recognition selection is closed. No STT
fallback, late result or uncertain confirmation can cause another operation.

## Current search behavior

- Locale grammar removes the recognized leading command phrase and optional
  target qualifier into a typed music intent. It preserves the original request
  and words inside the music reference; this is not global word deletion. Control,
  volume and language commands bypass music retrieval.
- Ranking first uses catalog-backed resolution, playback context and local exact
  matches. Albums and artists can be resolved from SQLite; Typesense is used for
  bounded fuzzy track retrieval when needed. Not every request reaches Typesense.
- `library/transliteration.py` projects Cyrillic characters into a deterministic
  Latin spelling for index aliases and ranked search queries. Literal matches
  and explicit aliases outrank projected spellings. The projection fingerprint
  participates in the index signature.
- `assistant/matching.py` uses `SequenceMatcher` on normalized names and projected
  spellings. Typesense requests allow up to two typos and prefixes, with automatic
  token dropping disabled. These are spelling comparisons, not phonetic matching.
- There is no general phoneme/G2P index or pronunciation distance. An explicit
  alias such as `Numb` -> `намб` may bridge a spoken form; letter transliteration
  alone does not supply English pronunciation. TTS normalization is separate.

## Speculative search alongside NLU

Typesense supports named [stopword sets](https://typesense.org/docs/30.0/api/stopwords.html),
applied to a search query, not removed from indexed documents. No such set is
configured by this change. A future speculative retrieval branch may search the
original transcription with a versioned command-word set while NLU runs.

Treat that output as candidate evidence, never an executable music intention.
Keep original text, quoted titles, negation and action qualifiers intact for NLU.
For example, `Play "Play"` must retain the title, and `Не включай ...` must not
become a playback request just because retrieval found an artist. Suppress empty
or wildcard queries after filtering. A query returning nothing after filtering
is not equivalent to a canonical music query returning nothing.

Prefetch reuse requires the same device/catalog/index revision, normalized music
query, fields, artist/album scope, locale and projection/stopword policy versions.
An approximate broad hit list cannot substitute for a scoped query: post-filtering
a limited top-k list may have already lost the intended result. Otherwise discard
the prefetch and perform canonical retrieval after interpretation. Re-score all
accepted hits under the final intent; preserve current exact-match coverage and
freshness checks. Control intents ignore all speculative hits. Search failure
must not prevent pause/resume or language commands.

The current literal NLU is cheap and many requests avoid Typesense altogether.
Measure the benefit before enabling extra traffic. The first experiment should
compare normal retrieval, speculative stopword retrieval and an unfiltered branch
on the same frozen inputs, including titles containing command words and negation.

## Phonetic retrieval extension

Reserve a separate candidate source for future pronunciation aliases/phonetic
keys. Preserve language, source, revision and match type; do not overwrite source
metadata or current spelling aliases. Search expansion remains bounded and must
retain artist/title/scope constraints. A phonetic hit is weaker retrieval evidence,
not an automatically exact identity or an STT transcript replacement. Any added
index fields must change the index signature and require an explicit rebuild.
Algorithm choice and multilingual quality are not decided here.

## Implementation gates

Follow-up experiments belong to [speech/platform issue #24](https://github.com/eudj1n/snowsky-disc-qemu/issues/24).
Implement the snapshot-only assessor and offline/shadow scheduler before live
arbitration. Compare identical recordings, preserving failures and measuring
semantic errors, false actions, abstentions, p50/p95 latency, model-load time,
peak memory and contention. Mac and board profiles need independent measurements.

Before live integration, cover conflicting valid commands, negation, ambiguity,
silence, all failures, deadline/cancellation cleanup, stale catalog/reconnect,
late results and exactly one mutation attempt. Existing defaults remain unchanged
until an explicit selection policy and its evaluation are agreed.
