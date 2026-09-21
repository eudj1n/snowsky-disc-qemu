# Command corpus v2

Frozen before running supervised v2 models. These are **assistant-authored labels**,
not independently collected or human-reviewed language evidence. The manifest
hash covers exact JSONL bytes. No private user history is included.

Each row records locale, original text, semantic label, typed intention, exact
argument spans, split, related-example group, origin and annotation rationale.
Missing play/language arguments have a class but no complete intention. Reject
covers non-command conversation, negation, reported speech, capability questions,
unsupported operations and conflicting/multiple actions. This is a bounded
single-command product policy, not a universal linguistic interpretation.

Training contains the existing locale references plus additional formulations and
negatives. Development chooses parameters; test is newly authored for this study.
The bilingual new families share group IDs and split assignment. All previously
examined NLU evaluation phrases are explicitly regression. Regression also retains
native base/small STT results on earlier synthetic speech, with source/model IDs;
those correlated outputs are not human recordings or independent test examples.
The isolated ASR output `cause` is labeled reject: speaker intent was pause, but
that intent is unrecoverable from the text alone. Music query gold preserves ASR
spelling rather than silently replacing it with a catalog name.

Validation rejects unreviewed data, malformed intentions/spans, exact normalized
text duplication and related-group leakage among train/development/test. A token
Jaccard audit reports near duplicates across splits for review; it is not proof
of semantic independence. Earlier regression cases can overlap training and are
reported separately. Additional new human examples need their own review and a
new dataset version. Do not edit this test set after viewing its model results.

Run from the repository root:

```sh
python3 -m research.disc_assistant.assistant.nlu.evaluation.dataset validate \
  research/disc_assistant/assistant/nlu/data/datasets/commands-v2
```

The class-balanced and ordinary linear comparisons use C=0.1/1/10, score thresholds
0.15/0.25/0.35/0.45/0.55/0.65/0.75/0.85/0.95/1.01 and margins 0/0.05/0.10/0.15.
Selection uses development false activations first, then macro-F1 and correctness;
ties prefer smaller C and more conservative thresholds. Freeze these choices
before evaluation, and report raw predictions as well as abstentions. The normal
live interpreter and extraction templates are unchanged for this comparison.

Revision `commands-v2.1` restores the omitted legacy `ru-test-language-3`
regression row with its explicit `по-русски` span. This correction was made after
the initial run; train/development/test rows remain byte-for-byte those committed
in `cad202b`. The manifest pins the previous hash and records the correction. No
model hyperparameters or decision policy changed in response to test results.
