# Branches, CI and firmware inputs

## Version policy

`2.x` is the default development branch for firmware 2.x. Keep `main` as historical
context, not a second development target. A future incompatible major gets `3.x`.
Firmware V2.40 is the released default; V2.57 has an opt-in profile and clean baseline
checks. Its upstream-feature acceptance remains in [firmware/2.57.md](firmware/2.57.md).

The first validated V2.40 milestone is
[v2.40](https://github.com/eudj1n/snowsky-disc-qemu/releases/tag/v2.40). Emulator-only follow-up fixes
for that firmware use `v2.40-r1`, `v2.40-r2`, etc. Never move/reuse an existing tag.
This is a firmware-based naming convention, not npm/SemVer package versioning.
V2.57 will use `v2.57` after its own validation. Do not merely replace the rootfs hash:
binary patches, diagnostic addresses, UI coordinates and protocol behavior must be checked.
GitHub immutable releases are enabled: publish only once the release contents are final.

Before releasing, require both workflows below to have succeeded **on the exact
release commit**, review the declared limitations in STATUS.md, and publish only
source/release notes, never firmware. Tags/releases are not created automatically.
For example, inspect `gh run list --branch 2.x --commit <full-sha>` before publishing.

### GitHub protection limitation

On 2026-09-11 GitHub returned HTTP 403: this private repository needs GitHub Pro
(or public visibility) for branch protection. Its visibility is intentionally unchanged.
CI can report failures but is **not a server-enforced merge/push gate** under the current
plan. After upgrading, protect `2.x`: require `Firmware-free checks`, require branches
up to date, disallow force pushes/deletions, include administrators. Keep firmware
integration a separate exact-commit release gate, not a required check on fork PRs.

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
Actions use Node.js 24 (`checkout` v6, `setup-docker-action` v5 and
`setup-compose-action` v2). `.github/dependabot.yml` checks GitHub Actions weekly and
groups proposed updates into PRs; SHA pins are retained and tested by `test_ci_pins.py`.
No automatic merging is enabled. This updater does not change Docker Engine/Compose
input versions, the Debian snapshot, or firmware checksums; those require explicit updates.
Both workflows install **Docker Engine 28.5.2 and Compose 2.39.4** using official
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
gh secret set FIRMWARE_V240_URL --repo eudj1n/snowsky-disc-qemu
gh workflow run firmware.yml --ref 2.x -f version=2.40
# Set FIRMWARE_V257_URL at the hidden prompt before selecting the second profile:
gh workflow run firmware.yml --ref 2.x -f version=2.57
```

Paste the direct HTTPS ZIP download URL at the hidden prompt; do not pass it as a
command argument or put it in `.env`, YAML, docs or a chat. The downloader selects
`FIRMWARE_V240_URL` or `FIRMWARE_V257_URL` for the requested profile.
Version, rootfs size/hash, chunk count and exact binary/patch fingerprints are in
`firmware/v<version>.json`; no direct download URL is committed.

`tools/fetch_firmware.py` receives the secret only in its download step. It requires
HTTPS (including redirects), suppresses download exception details, bounds ZIP/chunk
sizes and extracts validated chunk basenames (85 for V2.40, 77 for V2.57). It never extracts archive paths,
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
5. Compares TCP/WS protocol/catalog/settings, checks volume restore, play/pause,
   exclusive connection and reconnect, then checks byte-exact periods of the
   generated waveform in the decoded 32-bit PCM (promoted from signed 16-bit WAV).
6. Checks physical-button events with TCP/sysfs readback and dynamic BusyBox `reboot`
   binding to `fbshim` without invoking a kernel reboot.
7. Stops its guest, unmounts/detaches its SD loop, removes only its own stack/work
   volume and generated media. The interactive `diskos-work`/`sdcard` remain untouched.

Local equivalent using already extracted chunks:

```sh
bash ci/integration.sh /absolute/path/to/main_os/ota_v240
# Optional local diagnostic PNGs; never uploaded by Actions:
CI_SHOTS="$PWD/shots/ci" bash ci/integration.sh /absolute/path/to/main_os/ota_v240
FW_VERSION=2.57 CI_SHOTS="$PWD/shots/v257" bash ci/integration.sh /absolute/path/to/main_os/ota_v257
```

The workflow does not upload/cache firmware, rootfs, guest logs, captures or derived
images. The hosted runner is discarded afterwards. Secret masking is not a guarantee
against careless logging; never add `set -x`, verbose download output, or raw network
exceptions. A secret also does not preserve an expired/disappeared upstream file.

## Next: V2.57 acceptance

Preserve the V2.40 tag/baseline and default profile. The second profile, download
secret and test target are now separate. The user-provided
changelog additionally calls for font sizes, Wi-Fi details, multilingual tags/lyrics,
configurable list gestures, FiiO Link Favorites, AUTO EQ, MP3 seeking, external covers,
USB AUDIO tag refresh and M3U/CD-number UI changes. Hardware-dependent BT/USB behavior
must not be marked validated solely from emulation.
