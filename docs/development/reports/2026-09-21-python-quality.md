# Python quality and Controller extraction review

Reviewed 2026-09-21 on `codex/assistant-contextual-voice`, based on `a0633e0` plus
this task's changes. This is a targeted architecture/type/API review, not a full
security audit or a certification of every device operation.

The Controller already has a useful extraction boundary: production imports do
not depend on Assistant, emulator, viewer or firmware. Its isolation test copies
only Controller into a separate process and imports every production module.
The main remaining work is a stable, typed library contract and distributable
packaging, rather than moving device logic out of the application again.

## Original findings, resolved in the follow-up below

| Priority | Finding and evidence | Recommended change |
| --- | --- | --- |
| P2: correctness | `PlaybackSnapshot.from_wire()` accepts `state: true` as paused because Python booleans compare equal to integers. `controls.observe()` uses the same numeric membership convention. A synthetic JSON payload reproduced this without a device. See [wire parsing](../../../controller/fiio_link.py), [snapshot conversion](../../../controller/models.py), [control observation](../../../controller/controls.py). | Validate exact scalar types and enum membership once at the wire boundary. Preserve absent/unknown/loading distinctly; do not coerce malformed fields to a valid state. Add malformed-payload regression cases. |
| P2: public API | The facade returns `CommandResult`, while lower-level guarded operations, including the new current-state helper, return dictionaries. `CommandResult.from_result()` drops `volume`/`previous_volume`; its status enum cannot represent the new read-only `unavailable` outcome. Current Assistant calls use dictionaries directly, so this is an API consolidation gap, not a demonstrated lost-volume result in the application. See [result conversion](../../../controller/models.py), [current-state envelope](../../../controller/current.py). | Define typed results for observation, volume, favorites and playback, expose them through `DiscSession`, and serialize only at adapters. Make unknown/unavailable/uncertain separate, documented outcomes. |
| P2: static guarantees | No Ruff/type-checking gate or project type-check configuration was found. AST inventory counted fully annotated signatures (including nested helpers) in 4 of 257 Controller functions and 10 of 251 Assistant runtime functions. Dataclass field annotations are excluded from this narrow count; these numbers are not correctness scores. [CI](../../../ci/test.sh) currently checks shell syntax, tests and shim builds. | Add a pinned lint gate and incremental Pyright or mypy checks, starting with public models, wire parsers, capability checks and session APIs. Keep dynamic decoding at a small boundary instead of propagating `dict[str, Any]`. |
| P2: library surface | `LiveClient` inherits the complete raw `Client` API, but `LiveSocket` rejects methods outside its reviewed surface at runtime. Type annotations cannot tell consumers which inherited methods are valid. New volume/favorite writes additionally require the proper mutation phase. See [runtime allowlist](../../../controller/session.py). | Prefer a narrow public session facade and explicit reader/control `Protocol`s. Keep raw transport clients visibly separate; share encoders/validators without advertising unsupported operations by inheritance. |
| P2: extraction packaging | There is no standalone Controller `pyproject.toml`, versioned export surface, `py.typed`, extras declaration or wheel-install test. `controller/__init__.py` is empty. The existing [isolation test](../../../controller/tests/test_isolation.py) proves source-import independence, not that an installed distribution includes the bridge HTML or optional dependencies correctly. | Package the existing component first, with TCP/HTTP standard-library use and optional WebSocket/bridge extras. Build/install a wheel into a clean environment; test imports, public operations against synthetic peers and packaged resources. Choose the public package name before a repository split. |
| P3: maintainability | Wire values and small transport encoders remain repeated across older modules. The long positional `Config(...)` assembly is fragile when fields are inserted. See [TCP setters](../../../controller/fiio_link.py), [WS setters](../../../controller/fiio_ws.py), [config construction](../../../experiments/disc_assistant/assistant/config.py). | Gradually adopt named enums/shared encoders and keyword configuration construction. Do not mechanically replace historical capture values or rewrite every transport around a new abstraction at once. |

## Improvements completed in this task

- Named `PlaybackSource`, `WirePlaybackState` and `Capability` values replace the
  newly introduced magic-value checks. Assistant session, catalog and control
  paths now use reviewed capability checks instead of scattered `== 257` gates.
  Unknown versions receive no capabilities; a synthetic 260 test changes only
  a temporary test registry entry.
- New current-state operations mark attempts before I/O, preserve pacing, verify
  fresh state and never replay uncertain writes. Context changes block selection.
- NLU is an explicit Assistant component. Working rules, optional diagnostics,
  contributor-facing locale resources and training/evaluation data have separate
  locations. Learned execution remains disabled; frozen corpora are unchanged.
- The journal records the same rule revision as the interpreter; the previous
  hard-coded historical revision is removed from new request records.

## Resolution checkpoint, 2026-09-21

All six findings are addressed in the current working tree. The scope is an
incremental typed contract and extraction-ready packaging, not a mechanical
annotation of every historical diagnostic or a repository split.

| Finding | Resolution | Regression evidence |
| --- | --- | --- |
| Strict wire decoding | `controller/wire.py` validates playback/settings for both TCP and WS. Wrong scalar types and malformed song objects fail; absent and unknown states are preserved. `PlaybackSnapshot` and guarded control observation apply the same validation. | New malformed-payload cases cover bool/float/string/null states, source/favorite types, nested song JSON, settings and unknown/loading/stopped distinctions. |
| Typed results | `CommandResult` retains volume/previous volume, favorite/source observations, recording path, error type and `unavailable`. `DiscSession` exposes fresh current-track reads, favorite setters and absolute/relative volume. `controller.operations` supplies typed borrowed-client operations; Assistant serializes at its adapter boundary. | Public-session tests cover reads, no-ops, readback, limits, unavailable observations and uncertain writes with preserved result fields. |
| Static gate | Pinned Ruff checks all Controller Python; strict mypy checks nine public/core modules, the Assistant result adapter and a consumer contract. Three modules permit calls into legacy untyped helpers, while their own signatures and bodies are checked. The gate runs in hosted firmware-free CI. | `ci/python-quality.sh` passes; `ci/controller_types.py` asserts consumer-visible types, including optional result fields. |
| Narrow client surface | `LiveClient` inherits `ReviewedCommands` and `MutationGuard`, with no raw `Client` inheritance. Reader/control/selection protocols describe required capabilities; unsupported reset/scan/settings writes are absent. | Surface regression, synthetic session tests and static structural-protocol assignment. Existing receiver, pacing, cancellation and no-replay behavior are preserved. |
| Standalone packaging | The component builds as `snowsky-disc-controller` 0.1.0 with explicit public exports, MIT license, `py.typed`, bridge HTML and WebSocket/bridge extras. Python imports remain `controller`. | Build sdist, build wheel from sdist, install outside the checkout, perform synthetic commands without aiohttp, then install/import optional extras. |
| Maintainability | Guarded TCP clients share reviewed command implementations; TCP/WS share volume/favorite encoders. Core control/queue/confirmation paths use named playback/source enums. Assistant configuration construction uses field names. | Existing transport/controller/config suites plus byte-level command checks. Historical captures and frozen corpora are unchanged. |

Validation: 212 Controller tests; 370 Assistant tests; 393 shared Python / 37
JavaScript tests and shim builds; Ruff, mypy, clean core wheel installation and
optional extras; 30/30 disposable V2.57 voice-extension scenarios (ten no-write).
The full shared V2.57 integration scenario also passed (exit 0), with disposable
resource cleanup verified.
See [the current status](../../../experiments/disc_assistant/docs/status.md) for the retained initial failures,
corrected report and shared integration results.

## Remaining repository-split decisions

The original blockers are closed. A future split still needs an explicit owner
decision on repository location and package publication, copying component tests
and the license, and wiring the consuming integration repository to an installed
version. The local package name/version is ready but no registry publication or
new repository has occurred. Continue extending strict typing as legacy modules
are changed; the current gate deliberately does not promise full static coverage
of every raw diagnostic API. Firmware acceptance remains in this repository.
