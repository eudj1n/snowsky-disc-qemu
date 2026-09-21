#!/usr/bin/env bash
# Run with the interpreter containing ci/requirements-quality.txt on PATH.
set -euo pipefail
cd "$(dirname "$0")/.."
python -m ruff check controller research/disc_assistant/assistant/controller_results.py
python -m mypy
python ci/controller_wheel.py
