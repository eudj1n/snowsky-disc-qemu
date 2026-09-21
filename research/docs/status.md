# DISC research status

Current on 2026-09-21. The agreed local-protocol checkpoint is complete;
[umbrella issue #10](https://github.com/eudj1n/snowsky-disc-qemu/issues/10) remains
closed. The [capability reference](../../docs/protocol/disc-capabilities.md) owns
supported behavior. V2.57 is active; historical V2.40 findings do not enable a new
firmware or define continuing support.

The owner accepted the limited PEQ/SACD work for PR #20 on 2026-09-19. Remaining
investigations are optional backlog in #8/#9, not blockers for that checkpoint.
No new firmware tag, stable release, physical capture or media run is implied.

## PEQ remains paused

[Issue #9](https://github.com/eudj1n/snowsky-disc-qemu/issues/9) is paused by the
owner after capture `225312` on 2026-09-17. Do not start captures, reconnects,
device writes or scheduled follow-ups until the owner explicitly resumes it.

**Current physical Custom 10 state and restoration are unknown.** Screenshot
6851 shows nonzero bands and master −4.6 dB after Auto EQ Save, followed by an
owner-reported disconnect. The capture contains unanswered handshakes/TCP resets,
not Save, readback or cleanup. Earlier successful resets do not prove restoration
of this latest state, and the disconnect does not establish a firmware crash.

When explicitly resumed:

1. Capture reconnect and fresh Custom 10 reads **before Reset**, without repeating
   Save, Random or Auto EQ selection.
2. Reset only the approved Custom 10 slot, verify through Off → Custom 10, and
   finish Off. If reconnect fails, retain evidence and diagnose without replaying
   writes or silently rebooting.
3. Resume save/application analysis only after resolving that state. Do not repeat
   the preset sweep, Local Apply capture or catalog enumeration. Share/login stays
   deferred to #11.

Completed preset, edit/Save/Reset and Local Save/Apply findings remain in the
[PEQ report](reports/peq.md). BYPASS code 240 remains rejected by public setters;
its echo/reload behavior is not evidence of DSP bypass. The JSON helper is the
reviewed write path; the malformed captured Local Apply payload must not be copied.

## Other follow-ups

| Topic | Completed scope | Remaining boundary |
| --- | --- | --- |
| [SACD #8](https://github.com/eudj1n/snowsky-disc-qemu/issues/8) | Stereo metadata/identity, positional selection and same-path title replacement with restoration. | Different track-layout replacement, seek/EOF, DST/multichannel, a redistributable playable fixture and hardware DSD/DoP. [Evidence](reports/sacd.md). |
| [Account/cloud #11](https://github.com/eudj1n/snowsky-disc-qemu/issues/11) | Local theme metadata and separately captured app behavior. | Login, Share, official wallpaper/account sync remain deferred; no new login/capture. |
| Library edges | Reviewed artist/album/genre/folder selection, bulk addition and scoped deletion have separate emulator/physical evidence. | Root-tab Play all wire semantics and current-track/CUE deletion remain unverified; do not invent empty selectors or repeat ineffective captures. [Contracts](../../docs/protocol/README.md). |
| Phone lifecycle and hardware | Bounded LAN discovery/bridge and emulator idle/USB behavior have their own acceptance. | Physical iOS background/reconnect remains deferred unless an error appears; emulator results do not establish hardware audio fidelity. |
| Repository infrastructure | Experiments, documentation and [emulator launch/build infrastructure](../../emulator/docs/running.md) follow their component owners. | Controller extraction remains a separate decision. |

Keep issue checklists as the actionable backlog. Android M21/FiiO Music is a
separate implementation and reference only. New mutable investigations use
explicitly scoped disposable resources; never replay an uncertain mutation.

## Evidence and methods

The [dated protocol checkpoints](reports/2026-09-19-protocol-checkpoints.md)
preserve earlier priorities, failures, source revisions, captures and test counts.
Their historical “next” instructions do not supersede the pause above. Some old
ignored logs are absent locally; do not present recorded results as a fresh rerun.
Use the [analysis workflow](methods.md), [diagnostics](diagnostics.md) and
[report index](README.md) for provenance and reproduction.
