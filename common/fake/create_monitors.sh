#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

PYTHON=""
for candidate in "$ROOT_DIR/venv/bin/python" "$ROOT_DIR/.venv/bin/python"; do
    if [[ -x "$candidate" ]]; then
        PYTHON="$candidate"
        break
    fi
done
if [[ -z "$PYTHON" ]]; then
    echo '[error] Missing virtual environment: venv/ or .venv/.' >&2
    exit 1
fi

exec "$PYTHON" -m common.fake.create_monitors "$@"
