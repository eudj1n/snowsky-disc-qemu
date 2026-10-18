/* The /audio.pcm recording that both audio shims (tinyshim.c, asndshim.c) append to.
 *
 * Stock keeps its output open while paused and writes zeros, so a recording grows at the
 * full byte rate for as long as the player is on. A write that would take the file past
 * CAPTURE_MAX empties it first and rewrites /audio.fmt, whose new mtime gives readers a new
 * generation. Emptying is ftruncate on the open descriptor, not a reopen: a reopen that failed
 * would leave the output with no file until the next pcm_open.
 * Durations and the effect on the viewer: emulator/docs/audio.md.
 * Tests build the shims with a small -DCAPTURE_MAX. */
#ifndef CAPTURE_MAX
#define CAPTURE_MAX (1u << 30)
#endif
/* MIPS O_WRONLY|O_CREAT|O_TRUNC|O_APPEND: appending keeps the other shim's writes at the
 * end after this one empties the file. */
#define O_CAPTURE 0x309
#define __NR_ftruncate 4093
