# DISC running inside a browser — experimental prototype

This is separate from the [normal browser viewer](VIEWER.md). Here the browser
executes Linux, QEMU and the stock DISC programs. The host serves static files;
there is no server-side firmware process or framebuffer API.

```
Browser Web Worker
  TinyEMU / WebAssembly → RISC-V Linux → qemu-mipsel → mq_ui + mq_player
       ↕ virtual 9P filesystem (in browser memory)
  Canvas framebuffer ← frame.bgrx     tap-N → MIPS input events
```

The first target is the V2.57 main menu and a working tap. This is a research
prototype, not a replacement for the validated Docker emulator. It does not
enable another firmware profile or change the normal startup scripts.

## Build and run locally

From the repository root, with Docker available and the stock OTA unpacked:

```sh
bash research/browser/run.sh build /absolute/path/to/main_os/ota_v257
bash research/browser/run.sh serve
```

Open [the local prototype](http://127.0.0.1:8091/) and click **Start player**.
The server binds to localhost only. **Stop** terminates the worker and clears
the display; starting again creates a fresh VM. **Save screen** exports the
actual Canvas pixels. The optional console sends commands into the emulated
RISC-V Linux, not the host.

Docker is required to build the bundle, not to run it. Once built, serving
`work/browser-disc/www` is sufficient. Do not rebuild that directory while a
VM is running: its disk blocks are fetched on demand. Stop the VM, rebuild,
reload the page, then start it again.

The build:

1. Downloads public dependencies pinned by SHA-256 in
   [sources.json](../research/browser/sources.json). No firmware is downloaded.
2. Runs the existing exact-build validation, shim compilation, device setup and
   configuration priming in a **fresh disposable Compose stack**, with no host
   ports or user media. Exports the stopped rootfs, then removes that stack and
   its volume. The interactive stack and work volume are not used.
3. Builds a RISC-V Linux kernel and a small native RISC-V framebuffer/input
   adapter. The adapter and QEMU live outside the MIPS chroot.
4. Makes a 256 MiB ext2 disk image and splits it into 256 KiB HTTP blocks.
   Copies the WASM engine and page into `work/browser-disc/www`.

All downloaded sources, firmware, intermediate rootfs trees, disk images and
captures stay under ignored `work/browser-disc/`. `www/manifest.json` records
the firmware version and kernel, QEMU and disk hashes. Do not publish the
generated directory: it contains proprietary firmware. The source implementation
and these notes can be committed independently.

## Implementation and boundaries

- TinyEMU RISC-V source/demo: 2019-12-21, MIT. Its license is copied into the
  bundle. The precompiled WASM is reused; its JS file-download callback is
  adapted to deliver virtual 9P exports to the page's worker messages.
- Linux: the exact `a3b1e7acc6a181e04e9a943942084395df4498dd` revision from
  Bellard's recipe. `BINFMT_MISC`, `POSIX_MQUEUE`, `SYSVIPC` and kernel-config
  inspection are enabled. Modern compiler compatibility changes are confined
  to RISC-V ISA flag spelling and VDSO linking. This is an old research kernel,
  not a maintained general-purpose browser OS.
- QEMU: Debian RISC-V static `qemu-mipsel` 10.0.13, outside the DISC rootfs.
  `binfmt_misc` registers only MIPS32 little-endian executables **inside the
  virtual kernel**. No RISC-V handler is registered in Docker's kernel.
- The browser provides 64 fresh bytes from Web Crypto to initialize the virtual
  kernel's entropy pool. No reusable random seed is baked into the disk.
- The standard MIPS `fbshim`, `asndshim` and `tinyshim` are retained. The normal
  guarded key patch comes from the existing preparation pipeline; the browser
  adapter adds no stock-binary patches.
- The adapter reads `emu/fb-live`, samples that sub-buffer, then checks the
  marker again. The page reverses pixel order and converts BGRX to RGBA. As in
  the existing viewer, this is not an atomic framebuffer fence.
- Touch uses explicit **16-byte MIPS input_event** records; the RISC-V host's
  native timeval layout must not be used. The adapter flips both coordinates
  and separates press/release by 300 ms of guest time. Only one tap may be
  pending. Missing acknowledgement never causes an automatic retry.
- TinyEMU's old path walker does not resolve `/` as an import directory; the
  guest sets the 9P import directory to `.`. Using `/` silently drops imported
  commands even though framebuffer exports continue working.
- All firmware, filesystem changes, console commands and input processing run
  inside WASM. The VM has no configured external network interface or relay.
  Disk and 9P backing files are fetched from the local static server.

## Current scope and evidence

The initial local browser run on 2026-09-17 reached both open input devices and
a fresh framebuffer in about 35.5 seconds, then the English main menu at about
99.7 seconds. The input/frame readiness signal is **not** proof that the menu
has finished loading; the stock splash appears first. Timings are observations
from this development machine, not performance guarantees.

After fixing the import-directory path, a fresh browser boot reached the menu
again. A real click on its central **Browse files** icon produced `tap 1 injected`
and a new frame showing the stock **Browse files /tmp/sdcard** screen. The card
is intentionally absent/empty in this prototype; this verifies UI navigation,
not SD mounting or media playback. The worker's Stop control was also exercised.
Fresh browser entropy initialized the virtual kernel's CRNG at about 0.9 seconds
of guest time; this does not establish a startup-speed improvement.

On this branch, firmware-free checks passed: **312 Python tests and 25 JavaScript
tests**, shell syntax and all four standard MIPS shim builds. The RISC-V adapter
also compiled with `-Wall -Wextra -Werror`. The generated bundle's dependency
hashes and local documentation links were checked. No shared emulator runtime
code was changed, and no full/idle acceptance claim is made for this prototype.

The same RISC-V kernel/disk also boots with native TinyEMU as a diagnostic
preflight. Native results alone are not browser acceptance. Firmware-free
checks include known-color/opposite-corner framebuffer conversion and rejection
of truncated or concatenated frames.

Implemented scope: startup, framebuffer delivery, click-to-tap transport,
worker stop/restart, screen export and a guest console. Sound delivery, SD/media
import, swipes, physical buttons, network control, persistence and mobile-browser
performance remain outside this prototype. Existing firmware sleep/idle settings
are not overridden; complete power/screen lifecycle behavior is not validated.
The page reserves 512 MiB of guest RAM; the browser needs additional memory for
the emulator, disk cache and display. Double CPU emulation makes startup and UI
operations substantially slower than the normal Docker emulator.

References: [TinyEMU](https://bellard.org/tinyemu/),
[JSLinux technical notes](https://bellard.org/jslinux/tech.html),
[TinyEMU kernel/buildroot recipe](https://bellard.org/tinyemu/buildroot.html).
