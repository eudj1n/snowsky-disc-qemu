# Library prototype

Experimental catalog/search code in `experiments/disc_assistant/library/`.
See the [prototype guide](../README.md) for commands and limitations.

- `catalog.py`: bounded pagination of `all/song`, `album` and `album/song`;
  full membership comparison with duplicate multiplicities; two equal reads.
- `store.py`: SQLite schema 1, snapshot-scoped internal IDs, literal source
  observations, atomic snapshot/index publication and concurrent-import guards.
- `search/typesense.py`: official async SDK adapter, versioned search projection,
  title/artist/album/explicit and projected spellings, per-document import checks, matched-field
  evidence and stale-index rejection.
- `tests/`: synthetic fixtures and firmware-free component tests.

The catalog reader receives an HTTP client owned by the application session;
it opens no TCP connection. Store/search work offline from DISC. Library has no
assistant, voice, emulator or viewer dependency. Imports perform no I/O.

SQLite is durable; Typesense is rebuildable. A failed import/index never replaces
the previous published object. New snapshots intentionally invalidate old search
projections. A random collection is built completely before SQLite points to it;
there is no shared mutable Typesense alias or partial collection exposure.

Source rows do not expose reliable permanent recording identities. Duplicate
names/IDs are preserved, not merged; each row has a snapshot ID and exact source
scope/position. Old snapshots remain stored. Reconciliation, favorites, history,
lyrics, edition metadata and retention policies remain future work. Do not treat
these cached positions as playback selectors or a score as calibrated confidence.

Runtime data belongs outside the checkout; this package stores only source code
and synthetic tests. Production promotion will move reviewed modules and their
component tests together, with explicit CI registration.


Recording edition markers live in `version_markers.toml` and `versions.py`.
Their recognition is independent of the Assistant interaction locale; English
Live/Remastered labels remain visible when Russian commands are active. Locale
query-version phrases may extend this vocabulary. These are lexical conventions,
not authoritative recording identity or quality metadata.


Common recording labels also remain explicit query constraints across locales:
`Включи Linkin Park — Numb live` requires a live edition even in Russian mode.
Locale-specific version phrases extend those shared labels. A missing requested
edition is not silently replaced with a studio recording.

Search spelling projection lives in `transliteration.toml` and `transliteration.py`.
The current table folds Cyrillic to Latin for matching; it does not assert phonetic
or ISO transliteration equivalence. Exact source metadata is unchanged. The table
fingerprint participates in versioned index signatures. After changing it, restart
the process and rebuild the index; add paired spelling/collision tests before
extending the table. This Library utility has no dependency on command locales.

## Multiple artist credits

`artists.py` derives an ordered `artists` array from an explicit semicolon-delimited
source tag: `Eminem;Dido` becomes `["Eminem", "Dido"]`. Members are trimmed; blank
members and case-insensitive Unicode-equivalent duplicates are omitted. Commas,
slashes, ampersands and `feat.` are not separators: they may be part of an artist's
name. Changing separator policy requires evidence and regression coverage.

The literal `artist` and source row remain unchanged in SQLite. `Store.documents`
projects the array from existing snapshots, so no database migration or device
rescan is needed. Typesense schema 3 indexes both the full credit and the members;
each member also contributes configured aliases and spelling projections. Restart
the Assistant and run `/index` (or `run.sh index`) after upgrading. Old index
signatures are rejected until rebuilt.

Ranking policy `lexical-v4` matches a track by any credited member, including a
member followed by a title without a separator. Literal members outrank alias
collisions. The selected candidate retains the full original credit: fresh device
catalog checks and playback use the stock artist selector, never a fabricated
member-only selector. This does not create an aggregate queue of every solo and
collaborative recording by a person. Artist-only commands select one matching
native artist group under the existing deterministic ranking policy.

### Schema 4: prefilter known raw credits

Schema 4 / lexical-v5 add a derived SHA-256 `artist_key` for exact raw-credit
filtering before Typesense top-50 retrieval. This prevents unrelated artist names
inside titles from crowding out a requested artist. The full original credit and
semicolon member projection remain unchanged. Run `/index`, not `/sync`. The
SQLite schema remains version 1. Compare the [measured variants](../../../docs/ASSISTANT_REVIEW_EVALUATION.md).
