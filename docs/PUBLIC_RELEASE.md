# Public release preparation

The owner approved publishing this repository and the `v2.57` source release on
2026-09-13, retaining all existing history, branches, tags and author metadata.
The audit snapshot below records the state before publication. Future history
rewrites or changes to immutable releases require separate authorization.

On 2026-09-16 the owner chose to keep `v2.57` as a **Pre-release** snapshot and
`v2.40` as the latest stable historical release. Both tags/commits remain intact;
the next stable V2.57 release needs a new name such as `v2.57-r1`. Active support
and hosted firmware CI now target only V2.57; release immutability remains enabled.

## Prepared

- MIT license chosen by the owner for project code/documentation.
- Owner confirmed `viewer/assets/skin.png` is their original photo; provenance recorded in
  [viewer/assets/README.md](../viewer/assets/README.md). The skin is tracked, not ignored.
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

## Audit snapshot — 2026-09-13

Reviewed the 62 commits / 741 reachable Git objects through `bb4de8c` (both remote
branches and `v2.40`), the published release metadata, all 39 available Actions logs
at audit time, and the 20 current photo/documentation images.

- **Current checkout:** no matches for the known private-project references. The
  local path in `docs/firmware/2.40.md` is a vendor build path recovered from firmware,
  not the owner's home directory. No firmware executable/archive blobs were found;
  binary assets are the photo and documentation images.
- **History accepted by the owner on 2026-09-13:** `origin/main`, `v2.40` and earlier commits
  retain private-project names/links in historical README, Compose, protocol and
  agent/status documentation. There is also one non-noreply author email in Git
  metadata. A cleanup commit does not remove any of this from public history.
- **Credential/URL checks:** pattern scans found no direct firmware package URLs,
  GitHub/AWS token patterns or private-key headers in reachable text blobs; the
  available Actions logs had no matching firmware URLs, token/key patterns or known
  private-project references. This was a targeted scan, not proof that every possible
  credential format is absent. Firmware decryption details are intentionally documented.
- **Images:** reviewed current images, including the full protocol-inspector capture;
  they show generated test tracks, emulator state and vendor UI. No personal library,
  Wi-Fi credentials or owner-specific device identifiers were observed. The vendor
  OTA service hostname in the inspector is not a direct package URL. Retain the
  existing distinction between MIT project/photo assets and vendor UI illustrations.
- **GitHub:** private; default branch `2.x`; both branches unprotected; Pages and Wiki
  disabled; zero Actions artifacts and zero uploaded release assets. `v2.40` is
  immutable. No visibility, history, release or protection settings were changed.

Before making the existing repository public, explicitly accept the historical
references and author metadata, or choose a separate clean public repository while
preserving the private history. Do not move the immutable tag to hide old content.
Then review the final candidate CI, enable branch protection/required checks and
available secret scanning/push protection, and approve the visibility change itself.
GitHub documents that Actions history/logs also become public:
[visibility consequences](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility).
