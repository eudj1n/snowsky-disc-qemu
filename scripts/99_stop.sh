#!/usr/bin/env bash
# Stop the running guest processes.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$HERE/lib.sh"
kill_guest
log "stopped."
