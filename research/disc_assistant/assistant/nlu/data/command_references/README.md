# Diagnostic command references

Curated RU/EN labelled examples for command snapshots and offline model studies.
These are training/reference data, not independent evaluation evidence. The move
from `assistant/locales/commands/` preserves every example ID, label and text.

Locale extraction templates remain in `assistant/locales/commands/<locale>.toml`.
`command_catalog.source()` combines templates, live grammar and these optional
references into the same hashed snapshot payload. A new locale does not need
training examples to support ordinary commands or diagnostic literal extraction.
Do not add failed holdout examples here and continue calling them held out.
Frozen evaluation corpora remain in their existing dataset directories.
