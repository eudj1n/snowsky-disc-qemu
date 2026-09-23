# DISC Web implementation plan

Agreed continuation checkpoint, 2026-09-23. Keep this document updated when an
accepted stage is completed; dated validation belongs in [status](status.md).
Issues remain the home for individual actionable follow-ups. DISC Web stays in
`experiments/disc_web`; Controller owns device operations and Library owns catalog
observations and enrichment.

## 1. Now Playing and queue — complete

Expanded artwork and playback controls, album/artist navigation, adjacent desktop
queue and mobile player/queue switch. Shared queue refresh and guarded selection;
RU/EN and both themes. Implemented in `a9dfda4`, with synthetic and browser checks.
No physical playback acceptance is implied.

## 2. Library synchronization — complete

Make the existing sync understandable: distinguish saved collection, active sync,
offline/stale state and failure. Show the last successful observation separately
from current work, real sync stages and separate artwork/duration coverage.
Explain partial enrichment and preserve the previous snapshot on failure.

Acceptance: RU/EN and light/dark desktop/mobile presentation; synthetic checks for
partial metadata, empty snapshots, interrupted sync and storage failure. No fake
percentage, automatic sync, playback cycling or new physical connection.

Implemented the status badge, separate active/error messages, expandable stages
and saved field coverage. Validation is recorded in [status](status.md).

UI refinement on 2026-09-23 moved sync into a dedicated top-bar dialog and removed
the persistent banner. Album/artist placeholders now use decorative typography;
see [status](status.md#collection-ui-refinement--2026-09-23) for validation.

## 3. Folder import to a browsable collection — complete

Finish the existing folder upload → explicit device scan → Library sync flow.
Retain nested paths, skipped-file reporting and per-file confirmation. Make the
next action and the difference between transferred, indexed and saved metadata
clear. Preserve uncertain results without replaying writes. Folder upload already
exists; verified CUE/artwork sidecar transfer is a separate capability decision.

Acceptance: synthetic end-to-end transitions and narrow-screen review, plus the
relevant disposable firmware scenario if device-operation behavior changes.

Implemented three explicit steps in the import dialog, confirmed-file counts,
same-connection scan-to-sync admission and an open-collection action after a
fresh publication. Partial/uncertain transfers and reload limits remain visible;
demo does not fabricate a saved catalog. Controller operations are unchanged.

## 4. Sound settings — complete

Expose only reviewed Controller capabilities with fresh readback and clear
unsupported states. Start with volume-related settings and supported DAC options;
choose the exact controls against the public facade before implementation.
Unknown firmware must not inherit support. Bluetooth output identity/control and
paused PEQ research are not assumed available.

Implemented gain, L20..R20 balance, six DAC filters and DRE through a narrow
Controller facade with fresh firmware/value checks and one guarded setter.
Web requires explicit Apply and handles unavailable, stale and uncertain results.
Synthetic tests, browser checks, package/type checks and the complete disposable
V2.57 regression passed, including the new persistent settings scenario. See
[status](status.md) for the validation scope; physical audio remains unmeasured.

## Separate decisions

Local-file tags, external enrichment, lyrics, additional file management,
large-catalog improvements, shared Assistant ownership and promotion out of
experiments remain follow-ups. APK/cloud profile research is independent of this
UI sequence and is not a prerequisite for it.

All stages retain one Controller owner, explicit connection, guarded selections,
no replay of uncertain mutations, paired RU/EN and light/dark/system appearance.
