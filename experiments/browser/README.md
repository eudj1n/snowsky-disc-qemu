# DISC browser experiment

Active experimental TinyEMU/WASM runtime and local bundle builder. This is a
separate execution path from the supported qemu-user emulator; see the
[verified results and limitations](../../docs/BROWSER.md).

From the repository root:

```sh
bash experiments/browser/run.sh build /absolute/path/to/main_os/ota_v257
bash experiments/browser/run.sh serve
```

The build uses pinned public TinyEMU/Linux/QEMU inputs and reviewed firmware
preparation. Downloads, generated images and served firmware stay in ignored
`work/browser-disc/`. Ordinary emulator/viewer startup never launches this project.

Unit tests live in `tests/` and run in the shared firmware-free CI suite. UI assets
reuse the viewer's device CSS; browser runtime and gestures are owned here.
