# Stock OTA check and CI feasibility

Investigated on 2026-09-15 using the pinned V2.57 rootfs, static MIPS
disassembly, and read-only HTTPS requests from the host. No guest OTA installer
was executed. GitHub-hosted access has not yet been tested.

## Result

The OTA service can supply both an update signal and firmware **files** without
a device, serial number, account, or authentication in the requests tested.
It supplies a directory of package files; no ZIP download was found in this flow.
A CI downloader could consume rootfs chunks directly, without building a ZIP.

The existing [firmware workflow](../.github/workflows/firmware.yml) still uses
fixed ZIP URL secrets through [fetch_firmware.py](../tools/fetch_firmware.py).
The separate [OTA check workflow](../.github/workflows/ota.yml) polls daily;
it does not change the firmware integration input.

## Check protocol

The stock `/etc/ota_info` contains local version `257`, OTA service
`https://discpick.fiio.net`, and type `user`. The player requests the service's
`/ota_patch_user.json` using an ordinary GET (`wget` in the firmware). The request
does not send the current version: selection happens locally.

Each record has these fields (package URL deliberately omitted):

```json
{"last_version": 240, "new_version": 257, "recovery": 18, "patch_url": "<package base>"}
```

The player selects the first record whose `last_version` equals the installed
version, then compares `new_version` with the installed version. This is a
source-version-to-target-version map, not just a single latest-version value.
Absence of a matching source version must not be reported as "up to date".

The observed response has 17 records for source versions
156, 160, 165, 176, 177, 186, 195, 196, 197, 203, 204, 209, 221, 228, 234, 240,
and 257. Every record targets **257 / recovery 18**, with the same package base.
Thus V2.40 is offered V2.57; V2.57 has no newer target in this snapshot.

**Parser detail:** the response has a trailing comma before the closing `]`.
Python's strict `json.loads()` rejects it. The firmware reads lines into a
512-byte buffer, skips array delimiters, and parses individual object lines,
which explains why this response works on the device. A host implementation
should accept this specific trailing-comma format while validating all fields;
do not evaluate the response as code or silently skip malformed records.

V2.57 static evidence (addresses apply only to the pinned `mq_player`):

| Location | Observation |
| --- | --- |
| `0x004c99f0` | Reads local OTA version/site |
| `0x004c9c6c` | Fetches and selects the server record |
| `0x004c9d10` | References the `wget` catalog request format |
| `0x004c9dc0`–`0x004c9e20` | Reads and parses individual object lines |
| `0x004c9ebc`–`0x004c9ec0` | Compares record source version with local version |
| `0x0042dfc4` | Tests whether selected target is greater than local version |
| String `0x006b0630` and downloader around `0x0042c300` | Uses `md5_file_info.txt` to obtain package files |

## What can be downloaded

`patch_url` is a base directory. The stock downloader requests
`md5_file_info.txt`, then files under that base. Package layout includes:

```text
ota_config.in
md5_file_info.txt
main_os/ota_v<V>/ota_v<V>.ok
main_os/ota_v<V>/ota_update.in.enc
main_os/ota_v<V>/manifest.sha256
main_os/ota_v<V>/manifest.sha256.sig
main_os/ota_v<V>/rootfs.squashfs.<index>.<hash>.enc
main_os/ota_v<V>/xImage.<...>.enc
recovery/ota_v<R>/...
```

Live checks returned HTTP 200 for the config, MD5 file list, main-OS manifest,
signature, encrypted update description, completion marker, and one rootfs
chunk. All seven matched the corresponding local V2.57 package files byte for
byte. The main-OS manifest contains **77 rootfs chunks**. Its ECDSA signature
verified using the public key from the pinned stock rootfs; the downloaded
1,048,608-byte chunk matched its signed SHA-256 entry.

This establishes file access and a representative integrity check, not a full
OTA package download. Recovery payloads and all remaining chunks were not
downloaded. A ZIP assembled from OTA files would be a newly created archive;
byte-for-byte identity with FiiO's published ZIP is not established.

## Daily GitHub Actions monitor

[ota.yml](../.github/workflows/ota.yml) runs at **04:17 UTC daily** (09:17 in
Asia/Aqtobe) and supports manual dispatch:

```sh
gh workflow run ota.yml --ref 2.x
python3 -B tools/check_ota.py
python3 -B tools/check_ota.py --version 2.40
```

The workflow runs the catalog tests, then queries the service from host Python.
No Docker, firmware binaries, secrets, downloads of package files, or uploaded
artifacts are needed. Each run produces a summary with the reviewed, offered,
and highest advertised main-OS/recovery pairs. A newer advertised pair emits a
GitHub warning; the check remains successful when valid metadata was obtained.
This is a workflow summary/annotation signal, not an email or issue notification.
The warning repeats daily until the reviewed profile catches up or the catalog
changes; no persistent last-seen state is maintained.

Job outputs include `update_available` for the reviewed version's route and
`newer_release_available` across all catalog routes, along with target/latest
main-OS and recovery versions. A recovery-only increase also counts. The local
CLI prints the same sanitized metadata. Missing routes, duplicate sources or
fields, malformed records, non-HTTPS URLs, oversized responses, and network
failures fail the check instead of reporting "no update". Network requests use
a 20-second timeout and up to three attempts; the job has a five-minute limit.

The parser accepts strict JSON arrays and the vendor's trailing array comma.
It discards package URLs after validation; exceptions are not printed because
they can contain server response text or URLs.

## Possible download/notification extensions

1. **Download:** implement an OTA input mode separately from the current ZIP
   input. Resolve the selected record, require the expected target version,
   validate HTTPS redirects, bounded responses and safe relative file names,
   then fetch only the required rootfs chunks. Verify per-file SHA-256 and the
   existing pinned assembled-rootfs SHA-256 before extraction/execution. The
   signed manifest can add vendor verification if a reviewed trust anchor is
   provisioned; MD5 alone is not an authenticity check.
2. **State/notifications:** store the last observed release tuple separately
   from supported runtime profiles to avoid repeated alerts. A workflow output
   or job summary is the minimal signal; an issue or another notification can
   be added explicitly. Catalog changes must not automatically make unreviewed
   firmware executable in integration CI; follow [PORTING.md](PORTING.md).

Keep package URLs and raw catalog responses out of logs/artifacts, following
[CI.md](CI.md). Retain fixed historical ZIP inputs: the observed catalog points
every source version to the latest package and does not guarantee access to
older releases or permanent availability of their files.

GitHub schedules run on the default branch, and may be delayed or dropped under
load. This monitor uses an off-hour minute, `17 4 * * *` (UTC).
Public-repository schedules can be disabled after 60 days without
repository activity. The repository's default branch was confirmed as `2.x`.
See [GitHub's schedule documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

The remaining deployment check is one read-only run on a GitHub-hosted runner:
host access succeeded here, but runner egress/CDN behavior has not been measured.
