#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
if [[ -x "$ROOT_DIR/venv/bin/python" ]]; then
    PYTHON="$ROOT_DIR/venv/bin/python"
elif [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
    PYTHON="$ROOT_DIR/.venv/bin/python"
else
    echo '[error] Missing venv/bin/python or .venv/bin/python' >&2
    exit 1
fi
exec "$PYTHON" -m services.common.db_init alerts
