# Public release preparation

Visibility remains **private**. This checklist is preparation, not permission to
publish the repository, change immutable releases, or rewrite history.

## Prepared

- MIT license chosen by the owner for project code/documentation.
- Owner confirmed `assets/skin.png` is their original photo; provenance recorded in
  [assets/README.md](../assets/README.md). The skin is tracked, not ignored.
- Root README omits the OTA password and references to the owner's private projects.
  Tooling and technical preparation notes retain necessary decryption details.
- Shared agent instructions moved to `AGENTS.md`, without a duplicate legacy file.
- README distinguishes the independent emulator from vendor firmware and device flashing.
  Firmware, branding and depicted vendor UI are not relicensed as project code.
- Runtime defaults stay localhost-only, with a separate unprivileged WebSocket adapter.
- Firmware-free PR CI needs no secrets; privileged integration is manual on trusted
  `2.x` commits, uses disposable hosted runners and uploads no firmware artifacts.

## Before changing visibility

- Audit **all Git history, branches, tags, release notes and Actions logs**, not just
  the current checkout, for private references, local paths, credentials and assets.
  Removing text today does not remove it from old commits. The immutable `v2.40`
  snapshot predates these presentation cleanups; it has not been rewritten.
  If historical references must not be public, agree a separate publication strategy
  with the owner first. Do not silently force-push or move the tag.
- Confirm retained screenshots are appropriate research illustrations and contain no
  private media/network/device identifiers. Vendor UI screenshots are not project art.
- Public source pages are recorded in the runtime profiles, including the confirmed
  [FiiO V2.57 release page](https://forum.fiio.com/note/showNoteContent.do?id=202601311712087234434).
  Direct acquisition URLs stay secrets, never artifacts or release assets.
- Review fresh CI on the exact release commit for every advertised firmware; keep
  vendor announcements separate from observed emulator compatibility in the per-version reports.
- Configure branch protection/required checks when the plan/visibility permits.
- Have the owner explicitly approve public visibility and publication contents.

“Internal documentation” means contributor-oriented, **not access-controlled**: files
become readable with the repository when published. The retained OTA password is
intentionally not being treated as a secret; download URLs are.
