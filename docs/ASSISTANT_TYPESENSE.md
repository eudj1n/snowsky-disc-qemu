# Assistant Typesense on kernels without process I/O accounting

The default search service is the unmodified `typesense/typesense:30.2` image.
Some vendor kernels omit `CONFIG_TASK_IO_ACCOUNTING` and `/proc/self/io`.
[Upstream issue #2998](https://github.com/typesense/typesense/issues/2998), reported
by this project's owner on the same Orange Pi with an earlier Armbian version,
describes a brpc static-initializer crash before `main()`: Typesense exits 139
without logs. The owner confirmed the file is also absent on the current kernel;
this is the matching trigger. After enabling the wrapper, the owner reported a
working flow and supplied a trace with successful search on the updated board.
Playback confirmation and voice latency remain separate open items in
[current status](ASSISTANT_STATUS.md).

## Diagnose

On the Linux machine running Docker:

```sh
uname -r
cat /proc/self/io
docker run --rm typesense/typesense:30.2 --version
echo $?
```

For a remote Docker daemon, inspect its kernel, not the CLI machine's kernel.
Missing `/proc/self/io` plus exit 139 matches the reported startup failure.
The Assistant otherwise times out after 45 seconds and opens the interface with
playback controls. Increasing that timeout does not fix a crashed process.

## Enable the compatibility image

Stop the foreground Assistant with Ctrl-C. Update the checkout, then edit the
existing `[typesense]` section in `~/disc-assistant.toml` (or your `--config` file):

```toml
[typesense]
host = "127.0.0.1"
port = 8108
protocol = "http"
api_key_env = "TYPESENSE_API_KEY"
io_accounting_compat = true
```

From `experiments/disc_assistant`:

```sh
./run.sh up
./run.sh web --bootstrap
```

`up` builds a small native wrapper image, recreates only the Typesense service,
and checks `/health`. The Compose project, search key, port and data volume stay
the same; no library deletion or re-download of speech models is needed. The
first build needs Docker build support and network access to Ubuntu packages.
Subsequent starts reuse cached build layers. `setup --all` also honors the flag.
Setting it back to `false` and running `up` restores the stock image; it does not
fix the missing kernel feature. `down` preserves the data volume in either mode.

This option applies only to the managed local HTTP search service. It is off by
default; no host-kernel inference silently changes the image. Search, Whisper and
Piper ports remain loopback-only.

## Scope of the shim

The wrapper retains Typesense 30.2 and adds an `LD_PRELOAD` library, compiled
against Ubuntu 22.04 glibc for the build platform. It intercepts `fopen` and
`fopen64` only when a read-only open of exactly `/proc/self/io` fails with `ENOENT`.
It returns a memory stream with the seven standard I/O counters set to zero.
Existing file contents, permission errors, writes and all other paths retain
their original behavior. There is no logging or constructor in the shim.

**Process I/O metrics are synthetic zeros when the fallback is used.** The shim
does not enable kernel accounting or patch search/ranking behavior. A proper
upstream fix or a kernel providing the file can replace this temporary workaround.

## Validation

The Docker build runs a C probe before `main()` for missing, present and
permission-denied proc I/O, both fopen variants, independent stream positions,
ordinary files and unsupported write modes. Fault injection exists only in a
separate test image, never in the default runtime image. To exercise the actual
Typesense binary with the missing-file fixture, from the repository root:

```sh
docker build --target verification -t disc-assistant-typesense:io-verification \
  experiments/disc_assistant/assistant/typesense_compat
docker build -t disc-assistant-typesense:30.2-io-v1 \
  experiments/disc_assistant/assistant/typesense_compat
python3 experiments/disc_assistant/assistant/typesense_compat/tests/check_http.py
```

The verification target reproduces stock exit 139, then checks that the shim
reaches normal configuration validation. The HTTP check creates two isolated
containers with temporary data and ephemeral loopback ports, verifies health,
indexing and search, then removes them. On 2026-09-19 these checks passed on
native Linux arm64 in Docker Desktop, both with ordinary procfs and injected
missing proc I/O. No interactive Typesense volume was used.

Python regressions cover explicit opt-in, strict configuration, installer image
selection and actionable timeout diagnostics while playback controls stay
available. These checks do not constitute Orange Pi or physical-player acceptance.
