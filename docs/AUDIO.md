# Audio capture (work in progress)

Goal: play a track under emulation and capture the decoded PCM (offline — qemu-user can't decode
in real time). The capture mechanism is built and correct; local playback is blocked by a
DAC-route **state machine** in `mq_player` that expects the (absent) hardware's initialised output
state. This documents what's built, the exact gate chain (from Ghidra), and the honest blocker —
so it can be finished methodically or re-derived on a new firmware version.

## Key discovery: local playback is tinyalsa, not libasound

`mq_player` links **both** `libasound.so.2` and **`libtinyalsa.so.1`**. The **LOCAL DAC** path
(internal CS43131) goes through **tinyalsa** (`pcm_params_get` → `pcm_open` → `pcm_write`), not
`snd_pcm_*`. The device opens `hw:%d,%d` (kernel-direct; an `asound.conf` `file` plugin can't
redirect it) and the LinuxKit VM has no snd modules — so the only capture route is a
**symbol-level interposer**.

## What's built and ready

- **`shim/tinyshim.c`** — freestanding **tinyalsa interposer** (preloaded via `/etc/ld.so.preload`
  ahead of `libtinyalsa.so.1`): `pcm_params_get`/`_get_min`/`_get_max` report a permissive card,
  `pcm_open` returns a fake handle + records the config (`config->channels/rate/format`) to
  `/audio.fmt`, and `pcm_write` appends the raw PCM (tinyalsa's `pcm_write` takes a **byte count**,
  so capture is exact) to `/audio.pcm`. **Verified**: with it, tinyalsa's param check
  `FUN_00470c6c` passes (no "device only supports" errors).
- **`shim/asndshim.c`** — libasound interposer, same idea, for the USB/BT paths (not local).
- **CS43131 DAC stubs** — `/dev/cs43131[,b,c,d]`.
- All built by `build_shims.sh`, installed + preloaded by `10_setup_env.sh`. Inert until playback
  reaches `pcm_write`.

## The gate chain (why no PCM yet)

Tap a track → `mq_player` runs `audio_track_create` (`player_output.c:1026`, `FUN_0044f2d4`), which
must configure the PCM device before writing. Traced gate-by-gate with the Ghidra scripts:

1. **Format lookup** — `FUN_00475348` (audio_router_manager) maps bit-depth→format via an **empty
   per-route caps table** (`DAT_0082dfb0`, not populated under emulation) → `player_output.c:1057
   error update pcm_out stream format`. Clears with a small patch (`*param_2=fmt; *param_3=0;
   return 0`, file off `0x75348`).
2. **PCM param config** — `pcm_control.c:538 error config pcm params` (`set_pcm_config`,
   `FUN_004715fc`; via `player_output.c:1079`). This is the **blocker**. It is a **DAC-route state
   machine**: it branches on the output-route mode `*(ctx+0x5c)` / `*(ctx+0x58)` (`ctx =
   DAT_00832214`), which under emulation is **not the value a real initialised DAC would hold**, so
   the config is rejected before `pcm_open`. The route mode drives several interdependent checks:
   - the `param_4 == 0x10000000` PCM path vs. a `switch(*(ctx+0x58))` (case 3 = DSD, etc.);
   - two `(1 << route) & 0xC4` masks requiring route ∈ {2,6,7} (at `0x4717ac` and `0x471d14`);
   - `pcm_params` validation `FUN_00470c6c` (**passes** with tinyshim);
   - then `pcm_open` at `0x471df0`.
   Forcing the route masks (`li v0,2` @`0x7179c`, `li s3,2` @`0x71d08`) and the PCM path (`beq`→`b`
   @`0x71708`) **individually did not converge** — the route state feeds branches whose correct
   values depend on the DAC init that never ran. Blind static patching whack-a-moles.
3. … then `pcm_open`/`pcm_write` (tinyshim) — **not yet reached**.

`audio_router_manager.c:411 open /proc/asound/cards failed` spam is USB-Audio detection
(`get_usb_pcm_device`), a background poll — not the local blocker.

## What remains (the right way to finish)

The blind-patch approach is the wrong tool for a state machine. Instead:
- **Find what initialises the route mode** (`*(ctx+0x5c)`/`*(ctx+0x58)`) for local headphone
  output — the output-route selection / DAC init — and set it to the value real hardware holds
  (so the existing config logic simply passes), or
- **instrument the value at runtime** (a shim that logs/pokes `ctx+0x5c/0x58`) to learn the
  correct route, then set it, or
- replace `set_pcm_config` wholesale with a stub that fills the config struct and calls
  `pcm_open` directly.

Once execution reaches `pcm_write`, `tinyshim` captures `/audio.pcm` (+ `/audio.fmt`); wrap to WAV
on the host (header from the recorded channels/sample-bytes/rate) and play. Then stream it to the
viewer alongside the UI. **Real-time live audio is out** (qemu-user can't decode FLAC in real time)
— this is capture-then-play by design.

RE method + Ghidra setup used to trace all of the above: [RE.md](RE.md).
