# Disc Assistant documentation

Start with [current status](status.md), [setup](guides/setup.md) and the
[command quick guide](guides/quick-guide.md). The [roadmap](roadmap.md) links
deferred work; reports below preserve earlier evidence, not current instructions.

## Architecture

- [Independent interpretation sources and shadow comparison](architecture/interpretation-sources.md)
- [Assistant interpretation, language and speech boundaries](architecture/pipeline.md)
- [Assistant playback controls and queue](architecture/playback.md)

## Evaluation

- [Assistant scenarios against the emulator](evaluation/emulator-acceptance.md)
- [Command data, annotation and reproducible training](evaluation/nlu-data.md)
- [Language understanding and music reference research](evaluation/nlu-research.md)
- [Physical-player baseline: preparation and operator worksheet](evaluation/physical-baseline.md)
- [Shadow reports and review queues](evaluation/shadow-reports.md)
- [Fixed-audio Whisper comparison](evaluation/speech-benchmark.md)
- [Optional sherpa-onnx comparison environment](evaluation/sherpa-onnx.md)

## Guides

- [Speech adapter contracts, deployment profiles and extensions](guides/voice-adapters.md)

- [Disc Assistant commands](guides/commands.md)
- [Assistant request and decision journal](guides/history.md)
- [Queue confirmation diagnostics](guides/queue-diagnostics.md)
- [Disc Assistant command quick guide](guides/quick-guide.md)
- [Assistant setup and lifecycle](guides/setup.md)
- [Local speech services and Piper replies](guides/tts.md)
- [Assistant Typesense on kernels without process I/O accounting](guides/typesense.md)
- [Speech input and file-based experiments](guides/voice.md)
- [Disc Assistant Web](guides/web.md)

## Reference

- [Command catalog and explanation preview](reference/command-catalog.md)
- [Assistant configuration and data](reference/configuration.md)
- [Contributing Assistant locales](reference/locales.md)
- [Disc Assistant software MVP: accepted scope](reference/mvp.md)
- [Assistant user responses](reference/responses.md)

## Reports

- [Speech adapter/profile migration](reports/2026-09-21-voice-adapters.md)

- [Preserved native GigaAM pilot](reports/2026-09-19-gigaam-native.md)

- [Review follow-up comparisons, 2026-09-18](reports/2026-09-18-review-evaluation.md)
- [Emulator acceptance development checkpoints](reports/2026-09-19-emulator-checkpoints.md)
- [Disc Assistant software MVP acceptance](reports/2026-09-19-mvp-acceptance.md)
- [Historical design and implementation plan](reports/2026-09-21-design-history.md)
- [Development checkpoints through 2026-09-21](reports/2026-09-21-development-checkpoints.md)
- [Preserved earlier prototype guide](reports/2026-09-21-prototype-guide.md)
