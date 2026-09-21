# ADR 0002: emulator launch and build infrastructure

Accepted by the owner for [issue #29](https://github.com/eudj1n/snowsky-disc-qemu/issues/29)
after the component/documentation PRs were merged into `2.x`.
This completes the infrastructure follow-up deferred by [ADR 0001](0001-component-and-documentation-ownership.md).

## Decision

- Move the host launcher, base Compose stack, env template and Docker build context
  into `emulator/`. The local config is `emulator/.env`; the owner explicitly waived
  automatic migration. There is no root wrapper or fallback to a root env file.
- Rename the Compose service and internal Docker DNS hostname from `emu` to
  `emulator`, including overlays, WS upstreams, diagnostics and Assistant acceptance.
  Guest-internal `/emu` paths and existing Docker resource names are separate and
  retain their identity.
- Address services through Compose instead of a hard-coded container name. Resolve
  project/file/env paths explicitly so execution works from any caller directory.
  Compose paths remain repository-relative; explicit user OTA paths are caller-relative.
- Keep one pinned emulator/build image in `emulator/docker/`. CI and browser
  preparation consume it. Cross-component acceptance overlays/images stay in `ci/`;
  project-specific experiment builders stay with those experiments.

## Consequences

Existing installations configure the new env location explicitly and retire the
old-service container with the old checkout while preserving their chosen volume.
No automatic container adoption, data migration or firmware promotion occurs.
Default resource names, loopback bindings, optional WS profile and private data
locations are unchanged. Use the [launcher guide](../../emulator/docs/running.md).

Validate shell argument boundaries, config preservation, caller/project paths,
service overrides and volume-preserving shutdown. Compare rendered Compose with
the old stack, build the moved image, run firmware-free checks and disposable
full V2.57 integration. Verify Assistant-to-device DNS through its separate
focused acceptance scenario. No physical-device work is part of this change.
