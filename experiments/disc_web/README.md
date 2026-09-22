# DISC Web

An experimental music remote with its own application server, interface and
launcher. It uses the public [Controller](../../controller/README.md) and has no
Assistant, viewer, emulator or speech dependencies. It stays under `experiments/`
until a separately agreed promotion.

## Run

Python 3.11+ is sufficient; there are no Python packages, Node dependencies,
external fonts, CDNs or frontend build steps to install.

```sh
# Fictional interactive collection. Never opens a connection to a device.
./experiments/disc_web/run.sh --demo

# Emulator: starts disconnected; click Connect in the device dialog.
./experiments/disc_web/run.sh

# Physical DISC: supply its address and stock HTTP port explicitly.
./experiments/disc_web/run.sh --device 192.168.1.50 --http-port 12103
```

Open [127.0.0.1:8091](http://127.0.0.1:8091). Stop the process with Ctrl+C.
Use `--port` for another local application port. The server binds only to
127.0.0.1. Mobile layouts can be inspected in browser device emulation; this is
not a LAN-exposed phone service.

Disconnect Assistant or FiiO Control before connecting DISC Web. There is one
stock TCP owner. Closing a browser tab does not disconnect the server or stop
device playback. The application does not connect on startup, boot an emulator,
download firmware or open a physical device during tests.

## Available now

- Responsive home, album grid/detail, artist-scoped albums, tracks, favorites
  and custom playlist browsing; search within the current view.
- Persistent bottom player, expanded Now Playing with mobile-accessible controls,
  and an explicitly refreshed queue drawer.
- Light, dark and system appearance; RU/EN interface with saved browser preferences.
- Live whole-album/artist/playlist playback, indexed tracks from albums, the
  catalog, favorites, playlists and queue; pause/resume, previous/next, current-track
  favorite, absolute volume and random/repeat-list controls through `DiscSession`.
- Seek with time preview in both players, exact displayed-track protection and
  explicit pending/uncertain status for paused or unconfirmed device seeks.
- Track action menus with playback, supported playlist edits and navigation to
  known albums/artists; keyboard navigation and mobile bottom-sheet layout.
- Create/rename custom playlists; add tracks from all tracks or an unscoped
  album and remove playlist members, with fresh identity checks and readback.
- Current-track cover from stock HTTP; other live covers use honest placeholders.
  The stock API here only supplies the currently playing cover.
- An isolated demo with eight original SVG covers and fictional names, genre
  filtering, track/queue selections, simulated playback and favorites. It has no
  music files, audible output, persistence or real-device mutations.

The interface labels demo mode, including on mobile. Demo actions simulate presentation and do not prove firmware behavior.
Files/upload, scan and device settings remain future implementation stages. They must use reviewed public
Controller operations, not raw command forwarding. Browser audio streaming is
outside this implementation; live audio stays on DISC.

## Validation and documentation

```sh
./experiments/disc_web/run.sh test
```

Tests use loopback synthetic peers and curated data. They are also discovered by
the repository's firmware-free runner. Node is only needed for the frontend
utility and preference tests, not to run the application.

- [Architecture and API](docs/architecture.md)
- [Current status and next stages](docs/status.md)
- [Contributor instructions](AGENTS.md)
