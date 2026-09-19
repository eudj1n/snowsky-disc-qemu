# Queue confirmation diagnostics

A matching artist in `confirmation.last_observed` does not prove that the later
queue and fresh playback state agreed. Failed Controller queue guards now provide
`confirmation.queue` in Assistant responses/traces/history and typed Controller
`CommandResult` responses. The observed values come from the actual failing read.

Example (synthetic data):

```json
{
  "stage": "queue_verification",
  "code": "state_mismatch",
  "failed_checks": ["position", "title"],
  "mark": 1,
  "total": 2,
  "expected": {"state": 0, "playerflag": 7, "pos_id": 2, "title": "Second", "artist": "Artist"},
  "observed": {"state": 0, "playerflag": 7, "pos_id": 1, "title": "First", "artist": "Artist", "album": "Album"}
}
```

`mark` is zero-based; `pos_id` is one-based. Missing playback state remains null.
Codes distinguish `invalid_mark`, `unstable_queue`, `mode_changed`,
`membership_mismatch`, `state_mismatch`, `selection_mismatch`,
`position_mismatch`, `album_mismatch` and `album_resolution_race`.
For state mismatches all failed playing/source/mark/position/title/artist checks
are listed. Membership differences report counts, not complete track inventories.
Names are bounded to 200 characters; no file paths, credentials or full response
bodies are added. Other catalog/transport errors can lack queue diagnostics.

Guard conditions, deadlines and mutation count are unchanged. No automatic retry
or relaxed confirmation is introduced. Retain this evidence on the next naturally
requested command returning uncertain; do not replay an uncertain selection merely
to obtain a fresh `/status`. Tests cover missing fresh state, stale marks, wrong
titles, membership/mode races, typed responses and journal preservation.
