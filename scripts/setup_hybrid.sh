#!/usr/bin/env sh
# For Linux/macOS/CI: sh scripts/setup_hybrid.sh
set -eu
cd "$(dirname "$0")/.."
uv sync
uv run --no-sync python -m src.hybrid.prepare_models "$@"
