# DISC local protocol: controller capability summary

Research checkpoint: 2026-09-16, active firmware **V2.57**, physical-app evidence
from **FiiO Control 4.6.0 on iPhone**. This is the implementation contract for a
future locally hosted backend/frontend. The emulator viewer, diagnostic clients
and WebSocket adapter exist; a complete multi-browser web remote is subsequent
product work. M21/FiiO Music is a different implementation, not a DISC profile.

## Transports and ownership

- Stock **TCP 12100**: FiiO Link, handshake first, UTF-8 byte-counted frames.
  Stock **HTTP 12103**: files, images, catalog and playlist mutations.
- WebSocket is our optional TCP adapter, not a native DISC endpoint. Direct guest
  HTTP on host 12113 bypasses the adapter's proxy for diagnosis.
- Stock TCP is single-client. The future backend owns one connection and one
  reader; browser sessions subscribe to that backend. Serialize queries because
  frames have no request IDs and replies share tags with notifications.
- Discover through the documented UDP contract or configure the device address.
  App-to-emulator LAN access is opt-in and bounded; mDNS/general app compatibility
  is not established. Cloud login is outside the local command contract.

[Framing](PROTOCOL.md), [discovery](DISCOVERY.md), [adapter](WEBSOCKET.md).

## Capability matrix

“Emulator” means stock firmware acceptance in disposable tests, not a reimplemented
mock. “Physical” means specific observed app/device traffic or an explicitly
labelled owner observation; neither implies every variant or hardware output.

| Area | Available client/protocol behavior | Evidence and boundary |
| --- | --- | --- |
| Playback | Play/pause toggle, next/previous, volume, seek, five play modes; metadata/position and cover reads | Emulator + physical captures. Previous after >10 s restarts the track. Absolute play/pause is not established. [Playback](REMOTE_CONTROL.md). |
| Queue / favorites | Read queue, guarded positional selection, set/unset current-track favorite; V2.57 favorite positional selection | Emulator + physical captures. IDs are not interchangeable with positions. No arbitrary track-ID favorite setter. [Queue](REMOTE_CONTROL.md), [formats](FORMATS.md). |
| Catalog / scoped playback | Tracks, artists → albums → tracks, albums, genres → albums → tracks, folders; guarded `play_artist`, `play_genre`, `play_folder` | Emulator + physical hierarchy/selection captures. Preserve artist/genre filters and literal names; folder indices include directories. Folder Play all is nonrecursive. [Browsing](LIBRARY_BROWSING.md). |
| Play all | All indexed songs and named album/artist/genre/folder/custom-list contexts | Emulator covers selectors; physical scoped commands captured. Four root-tab buttons sent no playback request in the observed app state; this is not firmware rejection. Do not invent root selectors from those taps. |
| Custom playlists | Create/rename, guarded selection/playback, batch addition with source filters/ranges, remove members/delete list with files preserved | Emulator + physical track/group-add and rename captures. Destination/source positions need fresh reads; one physical 105-member list was read only through its first 100 rows. [Playlists](PLAYLISTS.md), [bulk add](LIBRARY_BROWSING.md). |
| File transfer | Browse, create folders, upload with progress checks, explicit single-file deletion under SD path guards | Stock HTTP + emulator checks; distinct from deleting an index/list entry. No claim of an atomic file/index transaction. [HTTP](HTTP_API.md). |
| Library scan/reset | Start/cancel scan; explicit-confirmation index reset; documented recovery | Emulator acceptance. Cancellation can leave a partial replacement index. Reset preserves files but does not preserve every library relationship. Exact app reset sequence unobserved; no personal-library reset requested. [Scan](LIBRARY_SCAN.md), [reset](LIBRARY_RESET.md). |
| Category Delete | Seven scopes and recovery effects documented; physical scoped-track flags 0/1 confirmed | Raw diagnostic contract, **no public general source-delete helper**. Album-group Delete is UI-unsupported; selected-list source deletion can affect other lists or leave stale references. [Deletion matrix](LIBRARY_DELETE.md). |
| Audio settings | Gain, DRE, filters, SPDIF, channel balance; device PEQ user-band/master controls and stock preset labels | All 21 supported codes/ten User slots checked over TCP/WS. Physical BYPASS=`00F0` only echoes/reapplies the previous mode; public writes remain rejected. Device Save is a no-op; edits persist directly. Reset restores current User bands/master. Local Save/Apply captured: bulk Apply format mismatch reproduced in V2.57; public JSON helper applies correctly. Disposable checks cover reconnect/isolation/restoration. Share requires login and is deferred by owner; editor/Auto EQ remain open; no DSP measurement. [Settings](REMOTE_SETTINGS.md), [PEQ](PEQ.md). |
| Playback preferences | Read gapless, folder jump and ReplayGain from common settings | Setters rejected by the network allowlist. Artist classification, track display and list gesture mode have no validated remote getter/setter. Local UI callbacks are not network APIs. [Restrictions](REMOTE_SETTINGS.md#playback-preferences-v257). |
| Work mode / Bluetooth | USB/local/AirPlay mode control and five Bluetooth source-codec preferences | Emulator transitions/persistence + physical app frames. No proof of USB/AirPlay audio, headphone negotiation or achieved bitrate. [Modes](REMOTE_MODES_THEMES.md). |
| Wallpapers | Five system slots and one custom slot; selection, system metadata editing, full custom PNG upload; opacity, exact RGB, four styles, independent overlays | System edits read/merge/write/verify and activate. Physical alpha/RGB saves confirmed; custom must resend full PNG. Locked display may require unlock/relock. [Theme contract](REMOTE_MODES_THEMES.md#system-theme-editing). |
| Formats / EOF | Ordinary audio plus CUE/DSF/DFF and one stereo SACD ISO metadata/selection; five ordinary local EOF modes | Generated fixtures and a separate owner-approved ISO test. Identity collisions and lossy favorites documented. Native DSD output, ISO EOF/seek, multichannel and DST remain unvalidated. [Formats](FORMATS.md), [SACD](SACD.md), [EOF](TRACK_END.md). |

Physical screenshot inventory and per-capture limitations: [FiiO Control evidence](FIIO_CONTROL_APP.md).

## Rules for the future backend

1. **Merge state events.** `a202` may be full, state-only or empty. Empty is not
   “stopped”; merge known fields without discarding track metadata. Repeated
   notifications are valid. Wire states: 0 playing, 1 paused, 2 stopped.
2. **Keep pending seeks separate.** Paused seeking may have no immediate position
   event. Show a pending target, reconcile on resume; do not resend to manufacture
   acknowledgement. Local progress has whole-second granularity.
3. **Observe completion, not timeouts alone.** Natural final stop can make `0202`
   silent while settings/queue reads still work. Do not classify every missing
   now-playing reply as a disconnected player or an empty library.
4. **Reconnect without replay.** Discard outstanding mutation intent, handshake
   again and refresh state/catalog. Never automatically replay toggles, seek,
   playlist additions or destructive operations after an uncertain response.
   Reconnection is not remote power-on. Diagnostic clients that drain queued
   notifications are not a production event-routing/state service.
5. **Respect stock pacing and identities.** Navigation has an integer-second
   gate (tests separate selections by 2.1 s). Verify outcomes. Positions can shift
   after edits/rescans; reread bounds/context and preserve duplicate labels.
   CUE/shared-path and favorites/queue IDs require their documented handling.
6. **Treat HTTP 200 as transport success only.** Unknown routes and unsupported
   actions can return empty 200. Read back metadata, counts, membership or files.
   An empty offset page with positive total is not an empty collection. Refresh
   from zero after removal; paginate rather than assuming one page is complete.
7. **Serialize read/modify/write operations.** There is no compare-and-swap or
   transaction across HTTP and TCP. Another phone can change the same state.
   A failed verification may follow a successful mutation; reread before deciding
   what to do, without automatic rollback or replay.
8. **Expose supported controls only.** Do not present read-only preferences as
   writable or copy emulator physical-key/hardware stubs into a remote device API.
   Keep library-entry removal separate from irreversible source-file removal.
   Never use empty-body system theme updates for the custom slot.

## Explicitly deferred / outside this checkpoint

- [#11](https://github.com/eudj1n/snowsky-disc-qemu/issues/11): FiiO account/cloud
  synchronization and Official wallpapers. Owner reports registration/sign-in is
  required; no cloud capture/login requested for the local task.
- [#9](https://github.com/eudj1n/snowsky-disc-qemu/issues/9): remaining PEQ editor,
  and Auto EQ flows without an account; Share/login is deferred to #11. Preset/BYPASS and device/local Save/Apply are
  captured; Local Apply's bulk-format mismatch is reproduced on V2.57, while
  the public JSON helper applies the intended bands correctly. See [PEQ](PEQ.md).
- [#8](https://github.com/eudj1n/snowsky-disc-qemu/issues/8): stereo ISO metadata,
  selection/favorites and same-path title replacement verified; committed in
  PR #20. Different track-layout replacement remains unchecked; seek/EOF,
  DST/multichannel and hardware output are separate extensions. See [scope and limits](SACD.md).
- [#7](https://github.com/eudj1n/snowsky-disc-qemu/issues/7): repository separation.
- Subsequent product work: local backend/frontend and Docker packaging, browser
  state service, production reconnect/conflict UI. Exact FiiO slider-formula
  cloning is unnecessary for an RGB editor; physical custom-opacity rendering,
  image picking/cropping and comprehensive hardware output remain unvalidated.
- Secondary deletion extensions: current-track/CUE/shared-path effects,
  favorite/queue source deletion, concurrent/failing requests and reboot
  persistence. These are documented limits, not supported public mutations.
- Physical iOS background/reconnect stays deferred unless an error appears.
  Legacy V2.40 cleanup and stable-release gates are separate work; completing
  protocol research is not a firmware release or hardware certification.

## Validation and continuation

See [test-selection policy](CI.md#test-selection-policy). The final helper passes
**297 Python / 23 JavaScript tests**, shell syntax/four shim builds and fresh
V2.57 `themes` direct/proxy acceptance, including 19 independent system edits per
path and restoration. Earlier
library and seven-scope deletion acceptance remains recorded in the domain docs;
no unrelated power/release gates are claimed rerun. Raw firmware, captures,
artwork and experimental logs remain ignored; sanitized fixtures are tracked.
The [research record](PROTOCOL_RESEARCH.md) preserves chronology and remaining
follow-up boundaries. This summary is the current entry point for a controller.
