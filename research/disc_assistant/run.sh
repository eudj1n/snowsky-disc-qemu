#!/usr/bin/env bash
# Independent research launcher; never calls the root emulator run.sh.
set -euo pipefail
prototype_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd -- "$prototype_dir/../.." && pwd)"
venv_python="$prototype_dir/assistant/.venv/bin/python"

if [[ ${1:-help} == help || ${1:-} == --help || ${1:-} == -h ]]; then
    cat <<'HELP'
Usage: research/disc_assistant/run.sh [--config PATH] COMMAND [ARGS]

  setup          Install dependencies; create missing config and private search key
  up             Start local Typesense and wait for readiness
  down           Stop local Typesense, preserving its volume
  start          Start Typesense, connect, sync/index, then keep an interactive console
  listen         Persistent console using existing catalog/index; no Docker startup
  language [CODES|reset]  Show/set saved command languages (ru, en, or ru en)
  sync           Read the selected DISC catalog into SQLite
  status         Show local catalog/index status
  queue          Read actual device queue and play mode; no search/index needed
  index          Rebuild Typesense from SQLite
  search QUERY   Return candidates (optional --limit N); no playback
  rank TEXT      Explain the best matches for Включи … / Play …, without playback
  ask TEXT       Play the best match, or Pause / Resume / Stop / Next / Previous
  test           Run firmware-free prototype unit tests
  check          Run disposable Typesense acceptance (requires Docker image)

Default config: ~/disc-assistant.toml (or DISC_ASSISTANT_CONFIG).
No virtualenv activation required. setup never overwrites an existing config/key.
Set DISC_ASSISTANT_PYTHON to a Python 3.11+ executable if automatic selection fails.
HELP
    exit 0
fi

if [[ ${1:-} == --config && $# -lt 3 ]]; then
    echo 'Expected --config PATH COMMAND; see run.sh help' >&2
    exit 2
fi
command_name="${1:-}"
[[ "$command_name" != --config ]] || command_name="${3:-}"
if [[ "$command_name" == setup && ! -x "$venv_python" ]]; then
    bootstrap_python=""
    if [[ -n ${DISC_ASSISTANT_PYTHON:-} ]]; then
        candidates=("$DISC_ASSISTANT_PYTHON")
    else
        candidates=(python3 python3.14 python3.13 python3.12 python3.11 /opt/homebrew/bin/python3 /usr/local/bin/python3)
    fi
    for candidate in "${candidates[@]}"; do
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
            bootstrap_python="$candidate"
            break
        fi
    done
    if [[ -z "$bootstrap_python" ]]; then
        echo 'Python 3.11+ required. Set DISC_ASSISTANT_PYTHON to its executable.' >&2
        exit 1
    fi
    "$bootstrap_python" -m venv "$prototype_dir/assistant/.venv"
fi
if [[ ! -x "$venv_python" ]]; then
    echo 'Environment missing. Run this launcher with setup first.' >&2
    exit 1
fi
if ! "$venv_python" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) and sys.prefix != sys.base_prefix else 1)'; then
    echo 'Existing .venv is invalid or older than Python 3.11; move it aside and run setup again.' >&2
    exit 1
fi
export DISC_ASSISTANT_CALLER_DIR="$PWD"
cd -- "$repo_dir"
exec "$venv_python" -m research.disc_assistant.launcher "$@"
