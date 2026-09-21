# Natural end of track and list (DISC V2.57)

Verified with the stock decoder, generated six-second WAV/FLAC files and a
three-track custom queue, over TCP and the WS bridge. No seek, next/previous,
injected EOF or playback-speed patch is used. Gapless and folder jump are both
read back as **off**. This is emulator evidence, not a physical-device capture
or a measurement of audible continuity.

## Five local modes

The test reads the actual HTTP queue order, denoted A, B, C below; network queue
positions are zero-based, while `a202.song.pos_id` / `playing_num` are one-based.

| Mode | Starting track | Observed natural behavior |
| --- | --- | --- |
| 0 — list once | B | B → C → stop; no wrap to A |
| 1 — random | B | Automatic selections continue within the queue, including beyond three completions; no fixed permutation asserted |
| 2 — repeat one | B | B → B → B, with progress restarting on each cycle |
| 3 — repeat list | C | C → A → B, proving last-to-first wrap |
| 4 — single once | B | B → stop; C is not selected |

Random is not a statistical distribution/non-repetition guarantee. Observed
orders included B → A → C → A and B → A → C → B. Do not calculate the next queue
position locally, especially in random mode; read the supplied metadata/mark.

## Events and final state

Each selected/repeated track starts with full `a202` metadata reporting
`state: 2`, followed by state-only `{"state":0}` notifications, often duplicated.
Ticks arrive as `a103` hexadecimal milliseconds: 1000, 2000, …, 6000 in this
fixture. At EOF the player often briefly sends `{"state":1}`; a later full-run
trace omitted it between two automatically selected tracks. The final-stop
sequence below remained intact. See [the discovery-checkpoint failure analysis](../../research/docs/status.md#lan-discovery-investigation-2026-09-16).

- For automatic continuation, a new full snapshot follows, including for
  repeat-one with the **same** filename. Progress starts again at 1000 ms.
- For final stop (modes 0/4), `a103` resets to **0**, then a metadata-free
  `a202` reports **`{"state":2}`**. The current queue and its final HTTP `mark`
  remain intact. Fingerprinted read-only runtime inspection reports internal
  player state **3** (internal 1=playing, 2=paused; wire 0/1/2 is different).

**Fresh `0202` is silent after this final stop** in both transports. It is not an
empty `a202` response. `0105` still returns the selected mode via `a102`, and
HTTP `curlist/song` still returns the three entries and last selected mark.
Selecting another valid track restores normal playback and query replies.
The local metadata handler suppresses its reply when the stop flag is set;
the static path below explains this silence without blaming the WS bridge.

Consequences for a future remote:

- Keep consuming pushes with one reader. The diagnostic clients' query methods
  discard pending notifications; this scenario uses only `event()` during EOF.
- Retain track metadata across state-only deltas. A full loading snapshot's
  state 2 is not sufficient to conclude that playback has finally stopped.
- Do not count duplicate playing deltas as repeated tracks. Track identity alone
  cannot detect repeat-one either: observe the full snapshot and progress restart.
- A transient state 1 at EOF is not evidence of a user pause, and can be absent
  between automatically selected tracks (observed in V2.57 decoder-only transition).
  Do not require that delta as proof of each track's completion. Allow the subsequent
  stop/selection sequence to resolve it; do not send a compensating toggle.
- Use the observed stop sequence, not a query timeout, to report final stop.
  After a reconnect without that history, missing `0202` leaves current playback
  unknown; an intact queue or its mark alone does not prove playing/stopped.
- Do not retry playback mutations or invent a fallback stop/play command when a
  read times out. This investigation does not establish a stopped-state resume
  contract or a separate absolute play/pause command.

## Static evidence

These addresses apply only to the fingerprinted V2.57 `mq_player`:

- `4524a4` is `playlist_server`, waiting on EOF/work flags around `839640` and
  dispatching mode `839638`. Its switch at `4525d4` uses table `6c13f8`:
  modes 0/1/2/3/4 target `452784`/`452750`/`45271c`/`45269c`/`4525dc`.
  Ghidra does not reconstruct this switch fully; inspect the table and MIPS
  branches, not just the decompiler's indirect-call output.
- `4522cc` handles the separate folder-jump preference before modes 0/1/3.
  The tested disabled preference leaves the normal mode dispatch in control.
- Mode 0 compares the current index with the list count before stopping;
  mode 4 takes the stop path directly. Modes 1/2/3 call `4249fc`
  (`comm_play_ctrl`) for automatic next/same/next behavior.
- Random selection is resolved through `451f84` and its `LIST_SONG_3` mapping,
  not simple increment/decrement of the visible queue index.
- Stop helper `458e1c` calls `456200` (`audio_track_stop`, internal state 3),
  resets progress through `452f58`, then invokes `42a720(0)` and
  `42489c(0,2)`, matching the observed zero progress / state-2 notifications.
- `0202` routes through dispatch row `838d88` → `41fc70` → callback slot
  `83a3d8` (`4ed618`) → local metadata handler `4252ac`. That handler replies
  only when `453684()==1` and `4537b0()==0`. The latter reads
  `*(DAT_0083dfc4 + 0x50)`; `456200` sets that flag to **1** at final stop.
  Thus the local stopped path returns without sending `a202`, rather than
  synthesizing empty or stopped metadata. The independent status at offset
  `+0x48` is read by `4536c0`; it is not the flag used by this reply gate.

Reproduce with `research/ghidra/DecAt.java` at function entries and an ELF disassembly
for the switch; see [Ghidra instructions](../../research/ghidra/README.md). Keep binaries,
projects and raw output under ignored `work/`. No firmware modification is needed.

## Reproducible acceptance and limits

```sh
CI_SCENARIO=track-end FW_VERSION=2.57 CI_LOGS="$PWD/work/track-end-check" \
  bash ci/integration.sh /absolute/path/to/main_os/ota_v257
```

`tests/integration/track_end_check.py` requires the disposable V2.57 stack and exact original
generated source files. It creates three short files and one custom playlist,
indexes through stock scanning, then tests all modes on TCP and WS. A bounded
event-only observation checks completed six-second cycles, fresh metadata,
progress restart, stop events and a quiet stop tail. Fresh mode/HTTP reads and
read-only runtime state corroborate the result; a timeout alone cannot pass.
It restores the original mode, selects/pauses a valid original album, deletes
only its own fixtures/list, and scans back to the original three tracks.
Full integration runs this before scan-cancel/reset/SD/preference checks.

The pure trace oracle has firmware-free tests rejecting missing completion,
loading-as-stop, duplicates-as-repeat, wrong positions/order, missing progress
reset, a selection after stop and implausibly immediate completion.

Scope is ordinary local WAV/FLAC in a three-track custom queue, gapless/folder
jump off. Empty/single-entry queues, folder-jump enabled, gapless enabled,
CUE/SACD/DSD, stopped-state resume/reconnect and actual hardware timing/audio
remain separate work. Validation history is in
[the research checkpoint](../../research/docs/status.md#natural-eof-investigation-2026-09-16).
