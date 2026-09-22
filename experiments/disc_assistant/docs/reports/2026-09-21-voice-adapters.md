# Speech adapter/profile migration, 2026-09-21

This increment adds version-1 STT/TTS adapter contracts, explicit lazy factories,
application-owned lifecycle on a stable event loop, deployment profiles, custom
package factories, an HTTP extension example and a device-free model matrix.
Legacy configuration and public adapter imports remain compatible. Web choices
come from configured instances; actual provider/model and prepare/inference times
are displayed with each result, and the browser remembers its selected instance.

GigaAM code and its curated historical JSON were selectively ported from commit
`40a9bb7` on `codex/gigaam-stt`. The old provider-specific factory/Web/config changes
were not merged. The JSON is byte-identical to the source commit. The preserved
[2026-09-19 pilot](2026-09-19-gigaam-native.md) is historical evidence, not a new
quality claim after this migration. The current setup and extension contract are
in the [adapter guide](../guides/voice-adapters.md).

## Verification

- Final `./experiments/disc_assistant/run.sh test`: **409 tests, OK, 4 skips** for
  optional soxr/tomlkit dependencies. Earlier focused and full runs are not additive.
- Both browser audio/reply JavaScript suites passed. Browser inspection on the
  temporary synthetic-peer service confirmed the actual Sherpa/model/timings,
  selection persistence through reload, Preview after reload, and preservation
  of the original result identity after selecting a different engine. No console
  warning/error was observed.
- Shared contracts cover custom factory registration, profile validation and
  precedence, two adapters served by a custom HTTP service, a persistent client
  session across calls, event-loop ownership, cancellation/timeout cleanup, busy
  rejection, wrong locale/hints, malformed results, disabled TTS, cache scoping,
  Web routing and matrix failure isolation without retries.
- Real installed Sherpa, Whisper HTTP, GigaAM v3 CTC HTTP and Piper each processed
  two synthetic requests through the common runtime. STT used one macOS Milena
  `Пауза` WAV; TTS synthesized `Пауза.` without playing it. Evidence is private in
  `/tmp/disc-voice-matrix.json` and `/tmp/disc-voice-gigaam-fixed.json`. Those are
  integration checks, not comparable quality/performance measurements.
- The first real GigaAM attempt failed because the old optional environment lacked
  `ffmpeg`. That failure remains in the original matrix JSON. The isolated venv
  received `imageio-ffmpeg==0.6.0` and a local executable symlink; the worker was
  explicitly restarted with that venv's bin directory on PATH. A separate check
  then recognized both utterances and verified checkpoint hash/upstream revision.
  Worker startup now rejects a missing decoder before model loading/readiness.
- Disposable stock V2.57 regression passed `ru-cyrillic`, `ru-pause`, `ru-resume`,
  `ru-next` and `ru-negation`; output is
  `/tmp/disc-voice-adapters-firmware-20260921`. This checks the common text/control
  pipeline. Real-audio Web mutation checks used a synthetic peer, not a physical
  device. No physical playback command was sent during this migration.
- Documentation relative links and `git diff --check` passed.

No model weights, private recordings or raw user journals were added to Git.
Orange Pi/Raspberry Pi, hardware acceleration, multilingual GigaAM/RNNT and
human-speech quality remain unvalidated. Profiles are configuration/deployment
inputs, not certified platform builds or automatic dependency installers.
