# Repository refactoring validation, 2026-09-21

This records structural checks, not new firmware support or physical acceptance.
The three PRs have distinct scopes:

1. [Experiment boundaries, PR #30](https://github.com/eudj1n/snowsky-disc-qemu/pull/30),
   candidate `c642238`: move applications from research, relocate owned tests and
   update imports, launchers, build paths, CI discovery and Controller boundaries.
2. [Documentation ownership, PR #31](https://github.com/eudj1n/snowsky-disc-qemu/pull/31),
   candidate `9bfdbc4`: move 71 manuals/reports, add navigation and a local-link gate.
3. Editorial consolidation: replace accumulating status/roadmap pages with current
   guidance, preserve their full historical snapshots and record ownership rules.

## Structural regression

- Shared firmware-free container run: **393 Python / 37 JavaScript tests**, shell
  syntax and all four shim builds passed, with no skipped tests.
- Assistant: **370 Python tests** and both browser audio/reply checks passed.
  The first sandboxed attempt could not bind synthetic loopback sockets; the
  permitted local rerun passed. This was a sandbox restriction, not a device test.
- Ruff, strict mypy over 11 configured files, Controller sdist-to-wheel build,
  isolated core installation/synthetic session and optional extras passed.
- Disposable stock V2.57 `ru-voice-current` passed through the rebuilt acceptance
  image and moved imports. Result: **1/1**, read-only now-playing with verified
  output. Containers, network and volumes were removed by the runner.
- Frozen corpus/report/template payloads retained their pre-move SHA-256 values.
  Documentation within a dataset directory may receive command/link updates;
  JSON/JSONL/CSV payloads and accepted aggregate evidence remain unchanged.

Local logs are `/tmp/disc-refactor-ci.log`, `/tmp/disc-refactor-assistant.log`,
`/tmp/disc-refactor-web.log` and `/tmp/disc-refactor-quality.log`. Disposable
firmware evidence is `/tmp/disc-refactor-stage1-acceptance/results/report.json`.
These are local artifacts, not permanently hosted evidence or a speech cohort.

## Documentation checks and limits

Stage 2 checked **103 Markdown files** with no missing local targets; the checker
passed Ruff and Python compilation. Documentation-only changes require link/diff
checks, not another firmware run. Stage 3 checks **115 Markdown files** with no missing local targets or unresolved
Markdown fragments. Six full historical snapshot bodies match their predecessors
after normalizing link destinations and removing the archival notice; the extracted
emulator checkpoint history and frozen payloads are also preserved. Existing acceptance dates/counts remain attributed
to their original candidates; the structural run does not replace the accepted
64-case MVP or the earlier full/idle/USB evidence.

Controller extraction/publication and active firmware policy are unchanged.
Root `run.sh` and Docker ownership are a separate follow-up in
[issue #29](https://github.com/eudj1n/snowsky-disc-qemu/issues/29).
