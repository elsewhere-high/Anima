#!/usr/bin/env sh
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$PROJECT_DIR"
export PYTHONPATH="$PROJECT_DIR/v4"
export SOCIAL_DEVICE="${SOCIAL_DEVICE:-cuda}"
exec "${SOCIAL_PYTHON:-python}" -m uvicorn social_v4.server:app --host 127.0.0.1 --port "${SOCIAL_PORT:-8767}"
