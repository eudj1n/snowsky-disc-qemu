# sherpa-onnx environment smoke check, 2026-09-21

The separate CPU evaluation environment was installed and exercised on macOS
ARM64 with Python 3.13.0 and sherpa-onnx 1.13.8. The candidate is
`sherpa-onnx-streaming-zipformer-small-ru-vosk-int8-2025-08-16` at revision
`31fa603e4f31279c6e1f7600fed13dc4312663ab`. The installer pins the SHA-256 of its
encoder, decoder, joiner, tokens and two upstream demonstration WAVs.

Both upstream WAVs (9.24 and 7.08 seconds) produced nonempty, repeatable Russian
transcripts with 2 and 4 CPU threads. Each thread profile ran one warmup pass and
two measured passes: 12 successful inference calls, including four warmups.
Warm calls took approximately 133–201 ms in this small uncontrolled run. This is
file throughput with a 300 ms context-flush tail, not microphone response latency.
No gold transcript or command-intent labels were supplied, so no accuracy score
is reported. The text interpreter rejected both non-command transcripts.

The private installation retains `installed-requirements.txt`,
`model-provenance.json`, and `smoke-2026-09-21/{manifest,run,report}.json` plus WAVs
and incremental rows under the operator's `~/disc-speech/sherpa-onnx` directory.
No model or audio is committed. The [evaluation guide](../evaluation/sherpa-onnx.md)
provides reproduction and paired fixed-audio Whisper commands.

This establishes local installation and inference only. No Whisper quality/speed
comparison, human command cohort, Orange Pi/NPU measurement, live-web migration,
TTS change or physical-device operation was performed. Existing software MVP
acceptance is unchanged.

## Browser lab follow-up

A separate loopback web lab was subsequently added at port 8091, with the shared
browser PCM recorder, WAV upload/listening/download and side-by-side transcript
results. A browser upload of the same upstream 7.08-second WAV returned both
Sherpa and native Whisper small transcripts. The UI displayed distinct timings,
first-request labels, execution order and a downloadable report. This was a
browser/inference integration check, not a comparative quality benchmark.

Twenty focused Python checks passed, covering existing benchmark behavior plus
HTTP host/origin/token gates, malformed/oversized WAV rejection, busy rejection,
identical provider inputs, alternating order, partial errors and result release.
Existing browser audio tests passed for encoding, channel mixing, duration limits
and capture stop. Actual human microphone quality remains unmeasured.

Ctrl-C was exercised on the real lab: its web process, Sherpa worker and owned
Whisper server all exited. The final lab was restarted for owner testing. No
existing Assistant service or physical DISC connection was used.

## Main Assistant web integration

The main web adapter now offers an explicit Whisper/Sherpa selector, with the
same application interpretation, journal and guarded Controller execution. Sherpa
runs in an owned resident subprocess from the separate optional environment.
The ordinary Assistant environment does not import ONNX or NumPy. Browser engine
changes restore Preview, and this model accepts Russian only without catalog hints.

Validation on 2026-09-21:

- `./experiments/disc_assistant/run.sh test`: 389 tests, OK, 4 skips for optional
  soxr/tomlkit dependencies. New checks cover process reuse across event loops,
  cancellation/timeout cleanup, invalid responses, locale/model failure without
  fallback, Preview/Execute, journal evidence and connection-generation guards.
- Both browser audio/reply JavaScript test scripts passed.
- Real pinned Sherpa through the main `/api/audio` endpoint recognized synthetic
  macOS Milena recordings of `Пауза` and `Продолжи`. Each passed Transcribe,
  Preview and Execute against the synthetic Controller peer: zero writes for
  the first two modes and exactly one write for Execute. The first load took
  about 1.07 seconds; subsequent recognition took 13–15 ms for these very short
  0.50/0.63-second synthetic utterances. This is not human-speech accuracy evidence.
- An exploratory `Поставь на паузу` recording was recognized correctly, but the
  existing interpreter returned `command.unrecognized` and sent zero writes.
  The speech adapter does not expand the current command dictionary.
- Browser checks confirmed the configured Sherpa selection, reset to Preview on
  engine change, and disabled Sherpa recording with an English command locale.
  Text controls remained usable; no browser console warnings/errors were observed.
- Disposable V2.57 firmware regression passed `ru-cyrillic`, `ru-pause`,
  `ru-resume`, `ru-next`, and `ru-negation` through `ci/assistant.sh --case ...`.
  This checks the common text/control pipeline; the real-audio check above used
  a synthetic peer, not firmware. Temporary evidence is under
  `/tmp/disc-sherpa-runtime-regression-20260921` and `/tmp/disc-sherpa-web-smoke.json`.

No physical-device acceptance or human-speech quality estimate was performed.
The accepted software MVP boundary remains unchanged.
