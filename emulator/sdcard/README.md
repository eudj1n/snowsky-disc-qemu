# SD card drop folder

Anything you put here shows up on the emulated player as its SD card at `/tmp/sdcard`
(the File Browser reads that path). Organize as you like, e.g.:

```
emulator/sdcard/
  Some Artist/
    Some Album/
      01 track.flac
```

`emulator/compose.yaml` bind-mounts this folder into the container as `/sdcard`, and
`emulator/scripts/10_setup_env.sh` builds a FAT image from it and mounts that image at the guest's `/tmp/sdcard`.
Run `./emulator/run.sh boot` from the repository root after changing files. This rebuilds
the SD image; use Update media lib separately to index new music.

Media files here are git-ignored (only this README and `.gitkeep` are tracked).
Supported formats depend on the firmware's decoders (FLAC/MP3/WAV/DSD/…).
