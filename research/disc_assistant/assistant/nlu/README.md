# Assistant NLU

Natural-language understanding is part of the Assistant. Moving it out of the
experiment directory does not promote a learned model to device control.

| Location | Responsibility |
| --- | --- |
| `intents.py`, `interpreter.py`, `languages.py` | Typed intentions, validated provider boundary and executing literal rules |
| `understanding.py` | Shared single-action guard and diagnostic slot extraction |
| `interpretation_sources.py`, `structured_source.py` | Optional shadow evidence; never replaces the executing interpreter |
| `command_catalog.py`, `command_features.py`, `explain.py` | Explicit command snapshots, portable diagnostic scoring and explanation |
| `../locales/` | Translator/developer-facing command dictionaries, reply templates and optional extraction patterns |
| `data/command_references/` | Optional labelled training/reference examples, outside localization resources |
| `data/datasets/`, other `data/*.json` | Frozen corpora, splits and authored evaluation cases |
| `evaluation/` | Explicit offline comparison, training and report tools; optional ML requirements |
| `evaluation/reports/` | Historical sanitized results, preserved unchanged |

Application owns orchestration, preferences, responses and journal storage. NLU
returns intentions and evidence; it does not import Controller, open a player
connection or dispatch a mutation. Evaluation retrieval may explicitly exercise
catalog ranking in disposable services; ordinary commands do not import ML tools.
Controller remains independent of the entire Assistant.

Use the normal launcher for commands. For offline studies, replace the former
`research.disc_assistant.experiments.nlu` module prefix with
`research.disc_assistant.assistant.nlu.evaluation`. See
[the evaluation guide](evaluation/README.md). Existing private model files are not
moved or retrained. Logical snapshot hashes include their source content; a path
move alone does not change it. New command grammar does invalidate old command
snapshots: rebuild explicitly and retrain an optional diagnostic model if needed.

The existing [locale guide](../../../../docs/ASSISTANT_LOCALES.md) explains language
contributions. A new language does not require a training/reference dataset.
