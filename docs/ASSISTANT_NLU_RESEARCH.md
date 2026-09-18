# Language understanding and music reference research

Status: **proposed experiments, 2026-09-18**. The current implementation remains
rules plus lexical/transliterated catalog matching. No embedding model, learned
classifier, phonetic engine or automatic training is installed or enabled. The
owner requested a broader comparison before treating hand-authored aliases as
the long-term solution. [Catalog evaluation](ASSISTANT_VOICE.md#catalog-selection-evaluation)
is the implemented measurement foundation.

## Separate the problems

| Problem | Example | Candidate approach | Required output |
| --- | --- | --- | --- |
| Intent and slots | “Could you put on Numb by Linkin Park?” | Rules, embedding prototypes, trained classifier plus slot extraction, structured language model | Validated music/control/language intent, or rejection |
| Name recovery | “Lincoln Park Nom” | Character similarity, transliteration, phonetic candidates, learned name-pair similarity | Catalog candidates with evidence, never invented IDs |
| Semantic discovery | “Something calm” or a remembered lyric | Embeddings over curated descriptions/lyrics, hybrid retrieval | Available recordings and explicit provenance |
| Recognition | A music name corrupted before parsing | Better STT, bounded vocabulary hints, later domain adaptation | Original transcript plus separately identified hypotheses |

Semantic similarity measures meaning; it is not a guarantee of spelling,
pronunciation or recording identity. This is why we hypothesize that embeddings
will help intent paraphrases and descriptive requests more reliably than short
proper-name correction. We must measure that hypothesis, not install a semantic
encoder as an assumed repair for `Nom` → `Numb`. Transliteration is also only a
spelling projection, not phonetics. User aliases remain optional, explicit facts.

## Experiments and ordering

1. **Freeze evaluation data.** Retain current synthetic WAVs as a development set.
   Add varied command formulations, ordinary speech, negation, quoted commands,
   partial utterances, same-name songs/artists, missing versions and unavailable
   music. Label intended action, source text spans and target metadata/absence.
   Keep separate tuning and held-out sets; group paraphrases, artists and speakers
   to avoid accidental leakage. Include held-out human recordings when available.
2. **Embedding intent baseline.** Embed locale-specific example utterances for
   each allowed intent; compare a request to examples/prototypes. Begin with
   `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` as a candidate,
   not a selected deployment model. Compare against current exact rules and a
   lightweight character n-gram classifier. The active locale still constrains
   interpretation; multilingual model support does not enable language detection.
3. **Name retrieval comparison.** Run lexical-v3, character/phonetic matching,
   embeddings and hybrid candidates on the same recognized queries/catalog.
   Keep separate artist and recording representations, preserve original text,
   explicit artist/version constraints, duplicates and snapshot identity. A
   semantic match must not silently substitute a related artist or live edition.
4. **Few-shot intent training.** Compare SetFit only after labeled examples and
   baselines exist. Few supported actions make a small classifier plausible;
   they do not eliminate varied phrasing or out-of-domain rejection. Classification
   alone cannot extract arbitrary artist/title/language slots. Keep rules for
   slots initially, then evaluate span extraction or a structured interpreter
   provider. Missing/invalid slots must reject, not guess an executable command.
5. **Promote measured winners.** Run candidates in read-only shadow evaluation
   first. Choose per-stage providers using held-out accuracy, false activations,
   latency and memory. Keep lexical/rule operation available if an optional model
   cannot load. Fine-tuning STT or a generative model is a later experiment if
   stage-level evidence shows a bottleneck that simpler approaches do not fix.

The current alias-tuned music experiment is **in-sample**: its aliases came from
already observed transcripts. It is useful to verify architecture and reveal
remaining errors, but cannot establish generalization. Automatically selected
tracks, absence of complaints and journal predictions are not ground-truth labels.
Reviewed corrections can become training examples with provenance and dataset
versions. Training runs are explicit offline actions, never automatic on startup.

## Proposed contracts and boundaries

Use the existing `Interpreter` provider boundary for an experimental composite
interpreter: precise rules first, optional learned fallback, then the same typed
intent validation. It receives text and the active locale/context and has no
Controller access. A separate slot extractor must preserve artist/title spans;
command embeddings must not swallow the music query. Quoted/negated/out-of-domain
examples must be tested across the entire pipeline, including the rules path.

Keep name candidate generation in `library`/search and final constraints/selection
in Assistant. Future candidate sources return snapshot IDs, bounded scores and
source evidence; a shared ranker merges them. Keep STT text, normalized text,
resolver hypotheses and final selection distinct in the journal. Record provider,
model revision, dataset/pipeline signature and timings. Similarity is not a
probability; calibrate acceptance threshold and top-two margin per task/locale on
held-out data. Rejection does not require implementing interactive dialogue.

Command exemplar vectors are small and can be cached locally. Catalog embeddings
belong to a versioned Library projection: source generation, content hash, model
revision, dimensions, normalization/pooling and template signature. Reuse vectors
only for identical inputs/pipelines. Persist snapshots, embed only the new query
at request time, and report cold/warm costs separately. No claim of faster total
voice response follows from vector search alone.

Typesense can store externally generated vectors and combine vector/keyword
results, so a second database is not required. Prototype generation outside the
search engine keeps model selection replaceable. Do not add vector fields to the
active index until an experiment needs them; publish complete new collections
atomically as with the lexical projection. See the existing
[embedding snapshot plan](ASSISTANT.md#planned-embedding-snapshots).

## Acceptance measures

- Intent macro-F1, per-action confusion and slot exact match; track pause/resume,
  stop and next/previous confusions separately.
- False activation on non-commands, negation, silence/noise and unavailable music;
  rejection/coverage at each chosen threshold. Nearest-neighbor systems always
  have a nearest result, which is not sufficient reason to execute it.
- Candidate recall@k, correct top-1 recording/artist and false substitutions,
  separately from transcript/reference agreement and word error rate.
- Per-stage warm/cold p50/p95 latency, peak RAM, startup and model/index footprint,
  first on the computer, later on the actual Pi. No extrapolated Pi promises.
- Model-unavailable behavior, index/model generation mismatch and unchanged
  playback freshness/no-replay guarantees.

Select thresholds and any hybrid weights on development data before looking at
the held-out result. Compare all variants on identical input/catalog generations.
The first goal is evidence for selecting a provider, not immediate autonomous
execution of a newly trained model.

## Primary references

- [Sentence Transformers: semantic similarity](https://sbert.net/docs/sentence_transformer/usage/semantic_textual_similarity.html)
  describes embedding comparison; [pretrained models](https://sbert.net/docs/sentence_transformer/pretrained_models.html)
  lists the multilingual MiniLM candidate. Neither establishes music-name accuracy.
- [SetFit concept](https://huggingface.co/docs/setfit/en/conceptual_guides/setfit)
  describes sentence-transformer fine-tuning and a classification head with few
  labeled examples. Our dataset size and quality threshold still need measurement.
- [Typesense 30.2 vector search](https://typesense.org/docs/30.2/api/vector-search.html)
  supports external vectors, hybrid rank fusion and distance thresholds. That
  supplies infrastructure, not a validated music matching policy.

## Typesense options reviewed with the owner

The [Natural Language Search guide](https://typesense.org/docs/guide/natural-language-search.html)
shows LLM conversion from a request to search parameters. Its application-level
orchestration is the older approach; the guide points to the built-in API. This
is a separate experiment from nearest-neighbor intent classification.

| Capability | Proposed place in our system | Boundary / experiment |
| --- | --- | --- |
| Natural Language Search | Optional music-query planner after action recognition | Compare constraints and resulting recordings, including model failure |
| Complex filtering | Library projection and retrieval | Add verified typed metadata before promising year/favorite/history filters |
| Vector/hybrid search | Optional Library candidate source | Compare exact-name preservation, recall and top-1 against lexical-v3 |
| Voice Query | Alternative STT/search adapter experiment | Compare identical WAVs and language control with standalone STT |

The [30.2 Natural Language Search API](https://typesense.org/docs/30.2/api/natural-language-search.html)
uses `nl_query` and `nl_model_id`, supports a self-hosted vLLM provider as well as
remote providers, and reports generated/final parameters plus parsing time.
Explicit filters are AND-combined with generated filters. On model failure the
API can return ordinary-search fallback results and an error. These behaviors
must be tested rather than treating any hits as successful interpretation.
Our adapter should retain this evidence, enforce allowed fields and reject a
constraint-bearing request when required interpretation failed. Built-in mode
searches before application inspection; its results stay previews until validated.

A future request such as “Play my favorite Linkin Park recordings from before
2010, excluding live versions” needs an action, artist, year bound, favorite flag
and edition constraint. Those fields must exist with known provenance. Today's
projection contains names and search spellings, not verified favorite/year/history
features. Neither an LLM nor a vector index can supply the missing observations.
Pause/next/language changes remain interpreter operations with no catalog dependency.

The [AI Agents guide](https://typesense.org/docs/guide/ai-agents-typesense.html#problem-4-complex-filtering)
illustrates combined filtering, ranking and hybrid retrieval. We use it to identify
experiments, not as measured latency or music-recognition evidence. Search merging
inside Typesense can simplify a provider, while Controller freshness and one-time
execution remain application responsibilities.

[Voice Query](https://typesense.org/docs/30.2/api/voice-search-query.html)
accepts base64-encoded 16 kHz, 16-bit WAV through multi-search and associates a
Whisper model with a collection. The shown `ts/whisper/base.en` configuration does
not establish RU support. Verify multilingual model names, explicit language
selection, returned transcript, timing and model lifecycle in the pinned server
before implementing a provider. This is STT plus search, not a documented pause/
next interpreter or TTS interface. For our general command path, standalone STT
currently preserves clearer stage visibility and works without an available index.

Priority adjustment: test **hybrid retrieval and structured NL search alongside
the local intent baseline before choosing to fine-tune**. Compare local versus
server-managed embeddings without introducing another vector database. Model
availability, hardware cost and exact adapter support remain unvalidated; the
review has not enabled providers or transmitted user data to them.
