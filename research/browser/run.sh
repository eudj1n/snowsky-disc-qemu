#!/usr/bin/env bash
# Standalone experimental workflow; never starts the regular interactive stack.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
case "${1:-help}" in
    build)
        OTA="${2:?usage: bash research/browser/run.sh build /path/to/main_os/ota_v257}"
        mkdir -p work/browser-disc
        python3 -m research.browser.fetch
        docker build -t snowsky-disc-qemu-ci docker
        docker build -t snowsky-disc-browser-build research/browser
        bash research/browser/prepare-firmware.sh "$OTA"
        docker run --rm --network none -v "$PWD:/repo" snowsky-disc-browser-build \
            bash /repo/research/browser/build-kernel.sh > work/browser-disc/kernel-build.log 2>&1 || {
                tail -60 work/browser-disc/kernel-build.log; exit 1;
            }
        docker run --rm --network none -v "$PWD:/repo" snowsky-disc-browser-build \
            python3 -B -m research.browser.bundle
        printf '\nStart the static server: bash research/browser/run.sh serve\n'
        ;;
    serve)
        test -f work/browser-disc/www/manifest.json || { echo 'Build the prototype first.' >&2; exit 1; }
        exec python3 -m http.server "${2:-8091}" --bind 127.0.0.1 --directory work/browser-disc/www
        ;;
    *)
        printf '%s\n' 'Usage:' \
            '  bash research/browser/run.sh build /path/to/main_os/ota_v257' \
            '  bash research/browser/run.sh serve [port, default 8091]'
        ;;
esac
