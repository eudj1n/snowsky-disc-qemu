# SD card drop folder

Anything you put here shows up on the emulated player as its SD card at `/tmp/sdcard`
(the File Browser reads that path). Organize as you like, e.g.:

```
sdcard/
  Some Artist/
    Some Album/
      01 track.flac
```

`docker-compose.yml` bind-mounts this folder into the container as `/sdcard`, and
`scripts/10_setup_env.sh` binds it onto the guest's `/tmp/sdcard` after the rootfs unpack.
Drop files, then `./run.sh boot` to rescan and `./run.sh tap 180 160` to open the browser.

Media files here are git-ignored (only this README and `.gitkeep` are tracked).
Supported formats depend on the firmware's decoders (FLAC/MP3/WAV/DSD/…).
