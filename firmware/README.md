# Firmware (not included)

The firmware is **not** stored in this repository. Download it yourself from FiiO.

GitHub integration downloads use only the active version's secret
(`FIRMWARE_V257_URL`), never a committed direct URL. Legacy V2.40 local tooling
still understands `FIRMWARE_V240_URL`, but hosted CI does not receive it. Runtime profiles:
[v2.40.json](v2.40.json), [v2.57.json](v2.57.json). See [CI policy](../docs/CI.md).

The daily [OTA monitor](../docs/OTA.md) opens a tracking Issue for a new vendor
version. It does not download the full archive or enable that firmware for runtime
use. Active support follows the [single-firmware policy](../docs/PORTING.md#support-policy--one-active-firmware).
V2.57 is active; the V2.40 profile remains temporarily pending legacy cleanup.

## Where to get it

FiiO Snowsky Disc firmware **V2.57** (default, local-upgrade package):

- FiiO forum release note: <https://forum.fiio.com/note/showNoteContent.do?id=202601311712087234434>

Download the local-upgrade ZIP and unzip it. You get this layout:

```
SNOWSKY_DISC_update_.../
├── ota_config.in                 # current_version=257  recovery_version=18
├── md5_file_info.txt             # md5 of every .enc chunk
├── main_os/
│   └── ota_v257/                 # <-- point run.sh at THIS directory
│       ├── manifest.sha256(.sig) # ECDSA P-256 signature (the real flashing barrier)
│       ├── ota_update.in.enc
│       ├── rootfs.squashfs.0000.<sha>.enc … .0076.<sha>.enc   (77 chunks)
│       └── xImage.*.enc          # kernel (not needed for user-mode emulation)
└── recovery/ota_v18/             # recovery image (not needed here)
```

## Distribution format (how the OTA is packed)

Each `*.enc` file is an independent OpenSSL "salted" blob:

- Cipher: **AES-256-CBC**
- Key derivation: **PBKDF2-HMAC-SHA256, 10000 iterations**
- Password: **`fo123`** (public; same across FiiO/Snowsky players)
- Header: `Salted__` + 8-byte salt

Decrypt one chunk:

```sh
openssl enc -d -aes-256-cbc -pbkdf2 -iter 10000 -k fo123 -in <chunk>.enc -out <chunk>.dec
```

For the historical **V2.40** package, the `rootfs.squashfs.NNNN.*.enc` chunks, decrypted and **concatenated in numeric
index order (0000…0084)**, reassemble `rootfs.squashfs`:

- size: 88 420 352 bytes
- sha256: `b479e159db5134325819b5f6e5a54388f3adefae373a4ee60680f02d5dcf0bb8`
- compression: LZO squashfs

`scripts/00_extract_rootfs.sh` does exactly this and verifies the sha256, then
`unsquashfs` unpacks it to `/work/rootfs`.

## Device facts

- SoC: **Ingenic X2000**, MIPS32r2 little-endian, o32 ABI, **nan2008** (`ld-linux-mipsn8.so.1`), glibc 2.29
- Screen: 360×360 round, 32bpp; quad **CS43131** DACs; **cst816t** capacitive touch; **x2000_key** GPIO keys
- Fuel gauge: **cw2215** (`/sys/class/power_supply/cw221X-bat`)
- FiiO MCU over UART; AP6212 Wi-Fi/BT
- UI split into `mq_player` (audio/backend) + `mq_ui` (LVGL GUI), talking over POSIX mqueues

## Flashing note

Re-flashing a modified image to real hardware requires a valid `manifest.sha256.sig`
(ECDSA P-256). That signature is the actual barrier to custom firmware — emulation
here sidesteps it entirely (we run the unpacked binaries directly under qemu).
