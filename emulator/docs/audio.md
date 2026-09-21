# Audio capture and browser playback

Local playback works through the stock firmware decoder → tinyalsa → `emulator/shims/tinyshim.c`.
No audio patches to `mq_player` are needed; the key-enable patch is unrelated.

```sh
./run.sh boot
./run.sh view                 # http://localhost:8080 → click the lower-left headphone jack
# Browse files → select a track in the device UI.
./run.sh audio                # snapshot → shots/audio.wav
```

The lower-left headphone jack (**Enable sound**) joins the current captured PCM
through Web Audio with a 150 ms look-back; it does not replay the recording from
its beginning. Click the jack again to mute. **Debug → Replay capture** starts
the current recording again. These viewer controls do
not change firmware play/pause state. Browser playback buffers a little and can pause if
emulation cannot supply data fast enough. If live playback falls more than two seconds
behind (for example after a background-tab stall), it drops queued history and rejoins
the current output. Replay mode deliberately preserves its position. PCM decoding and
DAC gains are unchanged. Debug labels the mode `live` / `replay`, and adds `silence`
when the decoded chunk contains only zero samples. The captured duration includes
stock service silence while paused; it is not proof of music playback.
WAV export also works without a browser.
Each `pcm_open` starts a new recording, replacing `/audio.pcm`; export before switching
tracks if you want to keep it.

## Physical volume and browser sound

The physical controls now honor the app's volume-gesture assignments ([KEYS.md](keys.md)).
`fbshim` mirrors the stock DAC attenuation writes (`0x80014d2d` / `0x80014d2f`) into
`emu/dac-left` / `emu/dac-right`; `/audio.json` reports the corresponding `output_gain`.
Web Audio applies these gains independently to the two output channels, with a short ramp.
CS43131 attenuation uses 0.5 dB steps and value 255 for digital mute, per the
[Cirrus Logic datasheet](https://statics.cirrus.com/pubs/proDatasheet/CS43131_DS1155F2.pdf).

Verified live while paused: volume 115 → 114 → 115 gives gains
0.37584 → 0.35481 → 0.37584. Browser graph wiring, gain updates and stopping queued audio
when the guest powers off are covered by `viewer/tests/test_audio_browser.js`.
Raw capture and WAV export remain pre-DAC samples: changing output gain does not rewrite
the recording. This models digital volume, not the analog amplifier/output circuitry.

## The actual blocker

`get_i2s3_pcm_device` (`FUN_0047670c`) scans `/proc/asound/cards` for **x2000 - x2000**.
It extracts the card number from the second character of the matching line and uses device 3.
LinuxKit has no such card, so `set_out_device` (`FUN_00474f84`) left `ctx+0x58` at
**0 = NO_OUT_DEV**, instead of **6 = I2S3_OUT**.

The fix is `emulator/shims/asound.cards`, installed as `/etc/asound.cards`. The preload shim redirects
only `fopen("/proc/asound/cards", ...)` to that file and forwards other paths to the guest
libc's `fopen64`. No host procfs changes or firmware instruction patches are involved.
The firmware discovers **hw:0,3** and selects its normal I2S3 route.
Its format table at `0x82e010` already supports 16/24/32 bits.

Corrections to the previous investigation:

- The caps table was not globally empty: the selected **NO_OUT_DEV** entry was empty.
  GDB confirmed populated entries for LOCAL_ANALOG (1) and I2S3_OUT (6).
- `0x10000000` is **PCM_IN**, not local playback. Output uses `flags=0`,
  `ctx+0x58`, and mask `0x5a`; `ctx+0x5c` / mask `0xc4` belong to input.
- Changing the route inside format lookup is too late: the caller has cached its old value.
  GDB observed rate=0 at PCM configuration in that experiment. Discovery must succeed first.

## Capture implementation

`pcm_params_get/min/max` emulate capabilities. `pcm_open` records channels, sample bytes,
and rate as three little-endian u32 values in `/audio.fmt`.
`pcm_write` takes a **byte count**, writes signed interleaved PCM to `/audio.pcm`, handles
short writes/EINTR, and returns failure on write errors.

`pcm_frames_to_bytes` and `pcm_bytes_to_frames` must also be intercepted: the real library
would dereference the fake handle. Buffer size is period size × period count.
The firmware's format enum differs from the initial assumption: playback uses **0 for
16-bit, 5 for packed 24-bit, 7 for 32-bit**.

Writes sleep for their audio duration, approximating a blocking DAC. Without pacing,
firmware-generated silence can grow the capture rapidly. Input is not implemented.
`asndshim.c` remains the separate USB/BT interposer; those routes and native
DSD/DoP output are unvalidated. DSD source metadata/selection is covered separately
in [FORMATS.md](../../docs/protocol/formats.md).

The shim uses `-nostdlib`, raw MIPS syscalls and the nan2008 ELF flag. Its only unresolved
dependency is `fopen64`, supplied by firmware libc. Do not link against the newer toolchain
glibc. Setup also creates `/dev/cs43131*` stubs. The absent mixer can log
`mixer_open failed`; this does not prevent capture.

## Verification and tools

On V2.40, stock audio code selected I2S3_OUT and opened 44,100 Hz stereo 32-bit PCM.
The two-second `01 - Tone A.wav` produced about 2.15 seconds including service silence.
A 1,000-frame region matched the source **byte for byte** after shifting its signed 16-bit
samples into 32-bit samples. Peak amplitude was about 0.300018.

Browser Enable sound / Replay capture / Mute sound were exercised without console errors.
Capture integrity tests cover signed stereo, frame boundaries, growing captures, stale
generations, and WAV's unsigned 8-bit convention:

```sh
python3 -m ci.unit
```

`emulator/runtime/audio.py` exports a bounded WAV snapshot. `/audio.json` reports generation, format,
and available bytes; `/audio.pcm?generation=…&offset=…` returns bounded, frame-aligned chunks
and rejects stale generations. `viewer/static/audio.js` converts PCM to float samples and schedules
them in Web Audio. Timing depends on decoder cost and host load; the earlier blanket claim
that qemu cannot play FLAC in real time was not established.

Future firmware analysis: [RE.md](../../research/docs/methods.md), [Ghidra tooling](../../research/ghidra/README.md).

## Format coverage (validated) and remaining caveats

**PCM, multiple formats — ✅ validated end-to-end** (play → firmware decode/resample → tinyalsa →
capture → WAV, tone faithful):

| source | captured `/audio.fmt` | tone |
|---|---|---|
| 16-bit / 44.1 kHz (`Tone A.wav`, 440 Hz) | 2ch · 32-bit · 44100 | 441 Hz ✓ (byte-exact after 16→32 shift) |
| 24-bit / 96 kHz (1 kHz) | 2ch · 32-bit · **96000** | ~1000 Hz ✓ |

The DAC (I2S3) runs 32-bit at the source rate; the firmware up-converts sample depth and keeps the
rate. Regenerate hi-res test tones with sox (in the container, into `/sdcard/...`):

```sh
sox -n -b 24 -r 96000 -c 2 "03 - HiRes 1kHz 24b96k.wav" synth 2 sine 1000 gain -6
```

**Remaining caveats (not done; scoped honestly):**
- **DSD output** — a separate route (`set_pcm_config` branches on DSD rates
  `0x2b110/0x56220/0xac440` and `is_dsd`). Generated DSD64 `.dsf/.dff` files now
  exercise indexing, source metadata and selection/pause; see [FORMATS.md](../../docs/protocol/formats.md).
  This does not validate native DSD/DoP, bit-exact conversion or hardware audio.
- **USB-DAC (device as USB audio sink)** — out of scope under qemu-user: there is no USB host to
  send audio to the emulated gadget. `asndshim.c` covers the libasound (USB/BT) *playback* path if
  those routes are ever driven, but the USB-input direction can't be emulated here.
- **Recording / input (`PCM_IN`, `pcm_read`)** — not implemented (`pcm_read` returns `-1`,
  not synthetic silence); niche for this project.
