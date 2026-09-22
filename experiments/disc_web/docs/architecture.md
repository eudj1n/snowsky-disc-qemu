# Application architecture

`disc_web` is an independent experimental consumer of the public Controller API.
It can move with its backend, frontend, tests and documentation after acceptance.
No path mutation or Assistant storage is needed.

```text
Browser (HTML / CSS / JavaScript modules)
    | same-origin JSON requests, cached-state polling
Loopback HTTP server (backend/server.py)
    | token / request ID / operation admission
Device projection (backend/device.py)
    | one DiscSession + same-target HTTPClient
Controller
    | reviewed TCP and stock HTTP
Physical DISC or emulator

--demo selects backend/demo.py instead: no device construction or sockets.
```

## Ownership

The server starts a session lifetime without enabling its connection. An explicit
Connect enables it. Each backend operation takes a nonblocking application lock:
conflicting requests fail rather than waiting to execute later. Public session
methods retain their own serialization, mutation pacing, fresh preflight,
confirmation and observation-only recovery. Disconnect disables recovery.

All playback and playlist writes use facade methods. Library HTTP reads occur inside a session
operation with scan checks before/after, bounded `CatalogReader` pagination and
literal scopes. A playlist name must resolve uniquely; list rows are checked again
after its tracks are read. Artist-album navigation retains the artist filter in
both the URL and subsequent playback command. Action menus retain their opening
scope and original row token. Album navigation is enabled only when that source
actually supplies the album name; generic HTTP track rows do not. Unsupported
playlist-add sources remain disabled rather than being widened implicitly. The backend does not turn those
albums into generic whole albums.

Views currently load a bounded complete category (at most 10,000 records and 60
HTTP requests); browser search filters that view. This is not a persistent search
index. Large-library virtualization and paged presentation are future work.

Visible album cards optionally request `kind=album_info` through the same library
endpoint. This reads the scoped album rows and returns distinct literal credits,
count and connection generation, without allocating playback selection tokens.
The browser serializes these reads, discards old-view/connection results and keeps
at most 256 summaries for 60 seconds within the view. Refresh/navigation clears
them. Failures retain the known group count. No persistent Library snapshot,
Assistant import or guessed title/artist-to-album join is introduced. Empty
album/duration columns are hidden per view; the album detail retains its known
scope. A current-track duration is not applied to other catalog rows by name.

## HTTP surface

| Endpoint | Behavior |
| --- | --- |
| `GET /api/state` | Latest import/scan job, cached normalized state, application session token, demo/endpoint information; no device query |
| `GET /api/interfaces` | Local host IPv4 interfaces eligible for passive discovery; empty in demo |
| `POST /api/discover` | Token/request ID, selected current interface, six-second passive multicast listener; no TCP connection |
| `POST /api/connection` | Token/request ID/generation, local IPv4 and TCP/HTTP ports; replace the sole owner and enable connection |
| `GET /api/library?kind=...&name=...&artist=...` | Named category/detail projection; bounded live HTTP reads or fictional demo rows |
| `GET /api/queue` | Fresh public facade queue result |
| `GET /api/cover` | Current device JPEG/PNG; no arbitrary proxy URL |
| `POST /api/upload?name=relative/path.flac` | Raw bounded file body, token, request ID and generation headers; private staging then async facade upload |
| `POST /api/scan` | JSON request ID/generation, one async observed scan |
| `POST /api/action` | Explicit allowlisted command, request ID, connection generation and session token |

The process binds to loopback. Host and Origin checks reject cross-site and DNS
rebinding requests; POST also requires `X-Disc-Token`; action/scan JSON and raw upload bodies have separate bounds. No CORS is
enabled. Connection/discovery JSON uses the same 16 KiB bound. CSP restricts scripts, styles, images and connections to local assets;
live covers accept only JPEG/PNG. Error messages and names are inserted as text
or escaped HTML. Requests are not logged with private names or query strings.

The process remembers up to 4,096 request IDs and rejects further writes once
that budget is reached, rather than evicting IDs and allowing replay. This is not durable exactly-once delivery. Browsers never retry a
write or persist commands for reconnect. Unknown results remain uncertain.
JSON reads rejected as busy (HTTP 409) may retry up to six times with bounded
backoff, so cover/catalog overlap need not become a failed collection screen.
Transport failures, other HTTP errors and every POST fail without replay.

State polling every 1.5 seconds reads cached session state, not the device socket.
The browser disables control after a server/connection loss. Duration comes from
validated stock milliseconds; absent duration keeps seek disabled. Dragging or
keyboard adjustment previews a requested position and sends once on change. The
draft retains its original track/source/generation, so a track change during a
drag rejects the selection. A paused seek is explicitly pending observation;
it does not trigger resume, optimistic progress or retries.
Volume is the last value read back after this server's volume operation, or
unknown. Changes made using physical buttons are not yet tracked by this field.
The queue is a snapshot refreshed on opening or after this browser's commands;
continuous multi-browser queue invalidation is not implemented yet.

Displayed track/queue rows carry opaque source tokens. The server keeps up to
32 source snapshots for ten minutes, tied to the connection generation. Commands
resolve the original scope and position from that snapshot; browser filtering
cannot renumber a selection. Controller compares the expected immutable rows
against fresh source data before sending. There is still no atomic stock revision.

Playlist edits run under the same session lease/pacer, resolve fresh list
positions by unique names, recheck source/membership and verify readback. A lost
reply is uncertain and cannot be automatically resubmitted. Removal changes
membership only; source files are never deleted by this UI.

## Import ownership

`backend/imports.py` owns one foreground job and a nonblocking admission gate
shared with other API operations. Cached state and static assets remain readable
during staging, transfer and scanning. `frontend/imports.mjs` owns file/folder
selection, per-file batch progress and explicit scan presentation. It preserves
browser `webkitRelativePath`, filters the documented audio extensions and
shows the skipped-file count. Names are relative, traversal/control characters
and invalid FAT path characters are rejected, and sizes follow the stock 31-bit
limit. Only one private temporary file exists per active transfer.

Uploads and scans call `DiscSession.upload_audio()` and `scan_library()` with the
original connection generation translated to the current Controller session. The generation is checked under the session
lease as well as before staging/dispatch. A batch stops on any unconfirmed item;
there is no durable queue, overwrite, automatic scan or resume. Demo consumes
bytes without staging or device construction and only simulates job progress.

During scans the Controller reader consumes start/count/end events without
interleaved queries. Cached job progress is separate from playback. Starting a
scan invalidates displayed source tokens. An observed end triggers a fresh view
read; a timeout is uncertain, never an automatic restart. The completed job stays
readable after a page reload until another explicit job replaces it.

## Connection ownership and discovery

`backend/connections.py` validates local IPv4 targets and inventories eligible
macOS/Linux interfaces. Its bounded listener uses Controller's reviewed exact
DISC multicast recognizer. Sender addresses are candidates, not authenticated
identities; the UI requires explicit selection and connection. TCP/HTTP ports
are known defaults, not fields supplied by the beacon. Only one discovery job
runs at a time. Demo performs neither interface inspection nor discovery.

Target replacement shares foreground admission with library operations and
imports. The old session is stopped before the replacement starts; HTTP always
uses the same target. An application generation offset stays monotonic across
session replacements, clears source tokens and prevents old browser/import
generations from matching a new Controller session. The completed import job is
cleared on accepted configuration. No operation is replayed onto a new target.
`frontend/connection.mjs` persists only a validated connection draft, never a
connect command. Startup remains disconnected; browser reload retains the
server's existing enabled session.

## Frontend

The UI uses local system fonts, original SVG artwork and no frontend framework or
build step. `core.mjs` holds pure rendering/search/navigation helpers. `app.js`
owns routes, requests and DOM presentation; `style.css` owns layout and responsive
breakpoints. `locales/ru.json` and `locales/en.json` hold interface strings;
`i18n.mjs` handles placeholders, plural rules, static accessibility labels and
live language changes. Device metadata remains untouched. `theme.js` applies
saved/system appearance before CSS paints and observes system changes in auto
mode. Both preferences tolerate unavailable localStorage and sync between tabs.
These modules have no device side effects or build dependencies.

The responsive design includes a fixed desktop sidebar, mobile bottom
navigation, persistent mini-player and queue drawer. Album and artist links are
deep-linkable and retain Unicode names.

The visual direction is an original music-library interface: warm paper surfaces,
quiet green neutrals, coral primary actions, generous cover art and restrained
typography. It does not reuse assets or logos from commercial music services.

## Extension boundaries

Add missing persistent operations to Controller with their own typed results and
fresh identity checks before exposing them here. Settings and future file operations need their own verification, not success based on HTTP 200. Maintain the distinction between removing a list member and deleting a file.

Assistant can later use a shared application runtime/adapter. The current server
is not a generic Controller daemon and does not make independent Assistant and
Web processes simultaneous TCP owners. This integration and root-level promotion
are separate decisions.
