# Audio capture and browser playback

Local playback works through the stock firmware decoder → tinyalsa → `shim/tinyshim.c`.
No audio patches to `mq_player` are needed; the key-enable patch is unrelated.

```sh
./run.sh boot
./run.sh view                 # http://localhost:8080 → Enable sound
# Browse files → select a track in the device UI.
./run.sh audio                # snapshot → shots/audio.wav
```

**Enable sound** plays captured PCM through Web Audio as it arrives. **Mute sound** stops
browser playback; **Replay capture** starts the current recording again. These buttons do
not change firmware play/pause state. Browser playback buffers a little and can pause if
emulation cannot supply data fast enough. WAV export also works without a browser.
Each `pcm_open` starts a new recording, replacing `/audio.pcm`; export before switching
tracks if you want to keep it.

## The actual blocker

`get_i2s3_pcm_device` (`FUN_0047670c`) scans `/proc/asound/cards` for **x2000 - x2000**.
It extracts the card number from the second character of the matching line and uses device 3.
LinuxKit has no such card, so `set_out_device` (`FUN_00474f84`) left `ctx+0x58` at
**0 = NO_OUT_DEV**, instead of **6 = I2S3_OUT**.

The fix is `shim/asound.cards`, installed as `/etc/asound.cards`. The preload shim redirects
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
`asndshim.c` remains the separate USB/BT interposer; those routes and DSD are unvalidated.

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
python3 -m unittest discover -s tools -p 'test_*.py'
```

`tools/audio.py` exports a bounded WAV snapshot. `/audio.json` reports generation, format,
and available bytes; `/audio.pcm?generation=…&offset=…` returns bounded, frame-aligned chunks
and rejects stale generations. `tools/audio.js` converts PCM to float samples and schedules
them in Web Audio. Timing depends on decoder cost and host load; the earlier blanket claim
that qemu cannot play FLAC in real time was not established.

Future firmware analysis: [RE.md](RE.md), [Ghidra tooling](../ghidra/README.md).
