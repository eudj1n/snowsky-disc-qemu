# Audio (work in progress)

Goal: play a track under emulation and capture the decoded PCM (offline — qemu-user can't decode
in real time). The pieces are in place at the bottom of the stack, but local playback is gated by
a **chain of hardware-format-negotiation layers** that each validate against the absent CS43131
DAC / ALSA card and fail. This documents what's built, the exact gate chain (from Ghidra), and
what remains — so it can be finished (or re-derived on a new firmware version).

## What's built and ready

- **`shim/asndshim.c`** — a freestanding libasound **interposer** (preloaded via
  `/etc/ld.so.preload`, ahead of `libasound.so.2`). It fakes the PCM handle
  (`snd_pcm_open` → non-null), makes every hw/sw-params call succeed, records the negotiated
  format to `/audio.fmt` (channels, sample-bytes, rate as 3× u32 LE), and appends every
  `snd_pcm_writei` buffer to `/audio.pcm`. The device opens `hw:%d,%d` (kernel-direct — an
  `asound.conf` `file` plugin can't redirect it) and the LinuxKit VM has no snd modules, so
  interposing libasound is the only capture route. Built by `build_shims.sh`, installed by
  `10_setup_env.sh`. **Correct and inert until playback reaches `snd_pcm_writei`.**
- **CS43131 DAC stubs** — `/dev/cs43131[,b,c,d]` (0-byte), so `dac_control.c` opens succeed.

## The gate chain (why no PCM yet), local playback (LOCALPLAYER)

Tap a track → `mq_player` runs `audio_track_create` (`player_output.c:1026`, `FUN_0044f2d4`):

1. **Format lookup** — `FUN_00475348` (audio_router_manager) maps the requested bit-depth to a
   format code using a **per-route capability table** `DAT_0082dfb0[route*0x10]`, which is empty
   under emulation (no card caps read at init) → returns "unsupported" → `player_output.c:1057
   error update pcm_out stream format`. **Patched** (manually, in the `/work` copy — not yet
   scripted): entry rewritten to `*param_2 = fmt; *param_3 = 0; return 0` (bytes at file off
   `0x75348`), i.e. "supported as-is". That clears this gate.
2. **PCM param config** — the next gate: `pcm_control.c:538 error config pcm params`
   (`FUN_004715fc`), reached from `player_output.c:1079 pcm device config failed`. It validates
   the rate/format against DAC register tables and rejects the values (partly because gate 1's
   patch returns the raw requested bit-depth rather than a route-validated one). **Not yet
   solved.**
3. … then the ALSA open/writei (`asndshim`) — **not yet reached.**

Also present but likely **not** the local-playback blocker: `audio_router_manager.c:411 open
/proc/asound/cards failed` spam — that's USB-Audio detection (`get_usb_pcm_device`,
`FUN_00475868`), a background poll, not the local route.

## What remains

Finish the gate chain so execution reaches `snd_pcm_writei`:
- Make gate 1 (`FUN_00475348`) return a format the `pcm_control` tables accept (a specific
  validated value, not the raw request), or populate the route capability table `DAT_0082dfb0`.
- Clear gate 2 (`pcm_control.c FUN_004715fc`) — either supply the rate/format it expects or patch
  its validation, and stub any CS43131 ioctls it issues (add cs43131-fd tracking to `fbshim` and
  return 0 for their ioctls).
- Then `asndshim` captures `/audio.pcm` + `/audio.fmt`; wrap to WAV on the host (header from the
  recorded channels/sample-bytes/rate) and play. **Live real-time audio is not a goal** — qemu-user
  MIPS can't decode FLAC in real time; this is capture-then-play.

Reverse-engineering method + the Ghidra setup used to trace all of the above: [RE.md](RE.md).
