# Branches, CI and firmware inputs

## Version policy

`2.x` is the default development branch for firmware 2.x. The obsolete `main`
branch has been removed; its commits remain in `2.x`. A future incompatible major
gets `3.x`.
Firmware V2.57 is the active/default version and the only hosted integration target.
V2.40's legacy runtime profile remains temporarily, pending a separate cleanup task.
Its presence is not a promise of continuing support or backports.

We actively support **one validated firmware** and retain older releases as
historical snapshots. Switch only after validating the candidate and preserving
the previous version's final validated snapshot; OTA detection alone does not
trigger the transition. See [the support policy](PORTING.md#support-policy--one-active-firmware).

The first validated V2.40 milestone is
[v2.40](https://github.com/eudj1n/snowsky-disc-qemu/releases/tag/v2.40). Emulator-only follow-up fixes
for that firmware use `v2.40-r1`, `v2.40-r2`, etc. Never move/reuse an existing tag.
This is a firmware-based naming convention, not npm/SemVer package versioning.
Choose an unused firmware-based tag after validation. Do not merely replace the rootfs hash:
binary patches, diagnostic addresses, UI coordinates and protocol behavior must be checked.
GitHub immutable releases are enabled: publish only once the release contents are final.
The existing `v2.57` is retained as a pre-release snapshot; `v2.40` remains the latest
stable historical release. The next stable V2.57 release uses a new unused name,
currently `v2.57-r1`. Neither tag has been moved or deleted.
Deleting an immutable release/tag does not free its name for later reuse, even
if the repository setting is subsequently disabled. Use an unused `-rN` name;
do not delete a published tag merely to republish different code under that name.
See [GitHub's immutable-release rules](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases).

Before releasing, require firmware-free CI and full integration for **the firmware
being released** to have succeeded **on the exact release commit**, review the
declared limitations in STATUS.md, and publish only
source/release notes, never firmware. Tags/releases are not created automatically.
For example, inspect `gh run list --branch 2.x --commit <full-sha>` before publishing.
Retired versions leave required integration coverage; remove their current workflow
choices and compatibility code in the corresponding cleanup task.
Their immutable tags and analysis reports remain available as historical snapshots.
The daily OTA metadata check does not replace these release gates.

### Branch policy after public publication

- `2.x`: changes through pull requests, mandatory **Firmware-free checks** from
  GitHub Actions, branch up to date before merging and resolved review conversations.
  No mandatory second-person approval for this owner-maintained project.
- Protection for `2.x` includes administrators; force pushes and branch deletion
  are disabled.
- GitHub automatically deletes PR head branches after merge when permitted by
  branch protection. Keep development in short-lived branches targeting `2.x`.
  Local branches are not deleted automatically; use `git fetch --prune` to remove
  stale remote-tracking references and `git branch -d <branch>` for merged local
  branches after switching to an updated `2.x`.
- Firmware integrations remain exact-commit release gates, not required checks on
  fork PRs. Secrets are only used in trusted manual integration runs on `2.x`.

On 2026-09-11 the private repository's plan returned HTTP 403 for protection.
The owner approved public publication and configuring this policy on 2026-09-13.

## Firmware-free CI

`.github/workflows/ci.yml`: every push/PR plus manual dispatch; hosted Ubuntu 24.04.
No secrets, firmware, privileged containers, cache upload or image publishing.

- Validate the regular Compose definition.
- Build `docker/Dockerfile`: multi-architecture Debian image pinned by index digest,
  Debian and security packages pinned via the 2026-09-10 snapshot.
- Run all Python tests (including synthetic WebSocket integration tests), JavaScript
  tests, shell syntax checks and cross-compile all four MIPS shims. **Any Python skip fails CI.**
- Test container uses a read-only source mount and `--network none`.

Local equivalent:

```sh
docker build -t diskos-qemu-ci docker
docker run --rm --network none -v "$PWD:/repo:ro" diskos-qemu-ci bash /repo/ci/test.sh
OTA_DIR=/tmp/unused docker compose config --quiet
```

Checkout is pinned to a full action commit SHA and does not persist credentials.
Actions use Node.js 24 (`checkout` v7, `setup-docker-action` v5 and
`setup-compose-action` v2). `.github/dependabot.yml` checks GitHub Actions weekly and
groups proposed updates into PRs; SHA pins are retained and tested by `test_ci_pins.py`.
No automatic merging is enabled. This updater does not change Docker Engine/Compose
input versions, the Debian snapshot, or firmware checksums; those require explicit updates.
The firmware-free and firmware-integration workflows install **Docker Engine
28.5.2 and Compose 2.39.4** using official
Docker actions pinned to full SHAs. Compose's binary cache is disabled. The first
hosted integration attempt exposed an older preinstalled Engine: `interface_name`
requires Engine >=28.1 as well as Compose >=2.36. Do not rely on runner defaults.
Node/Python/aiohttp/toolchain versions come from the same dated package indexes.
The hosted runner/kernel/build backend can still change; this is a pinned userland
and repeatable functional test, **not a claim of bit-identical Docker image builds**.
Updating the image digest or snapshot is an explicit dependency change requiring tests.
Old snapshots also freeze security fixes; update them deliberately, not never.

## Private firmware integration

`.github/workflows/firmware.yml`: manual dispatch **on `2.x` only**, hosted disposable
runner; no fork PR trigger, no `pull_request_target`, no self-hosted runner. Only
trusted maintainers may change/run this workflow: a ref condition does not protect
secrets from someone who can edit trusted workflow code.

```sh
gh secret set FIRMWARE_V257_URL --repo eudj1n/snowsky-disc-qemu
gh workflow run firmware.yml --ref 2.x
```

Paste the direct HTTPS ZIP download URL at the hidden prompt; do not pass it as a
command argument or put it in `.env`, YAML, docs or a chat. The workflow has no
version selector and exposes only the active profile's `FIRMWARE_V257_URL`.
The unused historical secret may remain stored for archival work, but is not
passed to current CI jobs. The workflow's version and secret are checked against
the default runtime profile by `tools/test_ci_pins.py`.
Version, rootfs size/hash, chunk count and exact binary/patch fingerprints are in
`firmware/v<version>.json`; no direct download URL is committed.

For the daily OTA monitor and verified OTA file access, see [OTA.md](OTA.md).
Firmware integration still uses fixed ZIP inputs.

`tools/fetch_firmware.py` receives the secret only in its download step. It requires
HTTPS (including redirects), suppresses download exception details, bounds ZIP/chunk
sizes and extracts validated chunk basenames (77 for active V2.57). The legacy local
V2.40 downloader still validates its 85 chunks until cleanup. It never extracts archive paths,
kernel or recovery images. The ZIP wrapper itself has no pinned checksum; the actual
consumed rootfs **is SHA-256 verified before unsquashfs or firmware execution** by
`00_extract_rootfs.sh`. A changed wrapper is acceptable only if that payload is identical.

The workflow first runs the firmware-free suite on the same commit, then:

1. Downloads/extracts chunks to runner temporary storage.
2. Starts the regular Compose services with `ci/compose.yml` overlay: no published ports,
   randomly named container/work volume and a separate generated SD directory.
3. Decrypts/verifies/extracts the selected firmware, checks six binary fingerprints,
   applies its guarded key patch, primes a new config DB, and boots normally.
4. Confirms an initially empty TCP catalog, slowly drags to Settings, scrolls to
   Update media lib, taps Update now, and checks the generated WAV is indexed.
5. Restarts before any track selection, verifies repeated viewer SD eject/insert,
   busy-card rejection, media preservation and the USB charging stub.
6. Compares TCP/WS protocol/catalog/settings, checks volume restore, play/pause,
   exclusive connection and reconnect, then checks byte-exact periods of the
   generated waveform in the decoded 32-bit PCM (promoted from signed 16-bit WAV).
7. Checks physical-button events with TCP/sysfs readback and dynamic BusyBox `reboot`
   binding to `fbshim` without invoking a kernel reboot.
8. On V2.57, checks repeated automatic SD scanning and Cyrillic add/rename/delete.
9. Stops its guest, unmounts/detaches its SD loop, removes only its own stack/work
   volume and generated media. The interactive `diskos-work`/`sdcard` remain untouched.

Local equivalent using already extracted chunks:

```sh
bash ci/integration.sh /absolute/path/to/main_os/ota_v257
# Optional local diagnostic PNGs; never uploaded by Actions:
FW_VERSION=2.57 CI_SHOTS="$PWD/shots/v257" bash ci/integration.sh /absolute/path/to/main_os/ota_v257
```

The workflow does not upload/cache firmware, rootfs, guest logs, captures or derived
images. The hosted runner is discarded afterwards. Secret masking is not a guarantee
against careless logging; never add `set -x`, verbose download output, or raw network
exceptions. A secret also does not preserve an expired/disappeared upstream file.

## V2.57 emulator release scope

V2.57 integration additionally runs `ci/storage_check.py --disposable`: cold-cache
SD discovery, stock remove/add, repeated Auto update with result dismissal, screen
lock/unlock, and exact Cyrillic add/rename/delete comparisons across SD/SQLite/TCP.
It uses V2.57-only fingerprinted UI reads. The legacy V2.40 local scenario remains
available until cleanup, but is not run by hosted CI. See [MEDIA_LIBRARY.md](MEDIA_LIBRARY.md).

Preserve the historical V2.40 tag/baseline. Its legacy local profile/test target
remain until cleanup, and are no longer mandatory release gates. The hosted workflow
neither offers V2.40 nor receives its historical download secret.
Release gates cover the parts implemented or
affected by emulation: guarded boot/patches, framebuffer and input, storage/hotplug,
network adapters, PCM/browser audio and guest power confinement. The active firmware
must pass integration on the exact release commit, alongside firmware-free CI.

Vendor feature changes are reference information, not a mandatory acceptance suite
for this project. Add a targeted check when a change affects an emulator interface,
shim or patch, or reproduces an emulator regression. Unverified vendor fixes are not
advertised as verified emulator features. Hardware-dependent BT/USB behavior remains
outside this release's validated scope.
