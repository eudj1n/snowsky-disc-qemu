#!/usr/bin/env bash
# Stop the running guest processes.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$HERE/lib.sh"
pkill -f 'tools/stream.py' 2>/dev/null || true   # live viewer, if running (./run.sh view)
kill_guest
log "stopped."
