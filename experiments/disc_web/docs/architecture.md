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
both the URL and subsequent playback command. The backend does not turn those
albums into generic whole albums.

Views currently load a bounded complete category (at most 10,000 records and 60
HTTP requests); browser search filters that view. This is not a persistent search
index. Large-library virtualization and paged presentation are future work.

## HTTP surface

| Endpoint | Behavior |
| --- | --- |
| `GET /api/state` | Cached normalized state, application session token, demo/endpoint information; no device query |
| `GET /api/library?kind=...&name=...&artist=...` | Named category/detail projection; bounded live HTTP reads or fictional demo rows |
| `GET /api/queue` | Fresh public facade queue result |
| `GET /api/cover` | Current device JPEG/PNG; no arbitrary proxy URL |
| `POST /api/action` | Explicit allowlisted command, request ID, connection generation and session token |

The process binds to loopback. Host and Origin checks reject cross-site and DNS
rebinding requests; POST also requires `X-Disc-Token` and bounded JSON. No CORS is
enabled. CSP restricts scripts, styles, images and connections to local assets;
live covers accept only JPEG/PNG. Error messages and names are inserted as text
or escaped HTML. Requests are not logged with private names or query strings.

The process remembers the last 4,096 request IDs to reject immediate duplicate
submissions. This is not durable exactly-once delivery. Browsers never retry a
write or persist commands for reconnect. Unknown results remain uncertain.

State polling every 1.5 seconds reads cached session state, not the device socket.
The browser disables control after a server/connection loss. Timing is observed
only: absent duration stays unknown, and the progress bar is not a seek control.
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
fresh identity checks before exposing them here. Upload, scan and settings need operation-specific verification, not success based on HTTP
200. Maintain the distinction between removing a list member and deleting a file.

Assistant can later use a shared application runtime/adapter. The current server
is not a generic Controller daemon and does not make independent Assistant and
Web processes simultaneous TCP owners. This integration and root-level promotion
are separate decisions.
