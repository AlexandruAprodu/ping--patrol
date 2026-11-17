#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SESSION="ping_patrol"

find_python() {
    local python
    for python in "$ROOT_DIR/venv/bin/python" "$ROOT_DIR/.venv/bin/python"; do
        if [[ -x "$python" ]]; then
            printf '%s\n' "$python"
            return 0
        fi
    done
    echo "[error] Missing virtual environment in $ROOT_DIR (venv/ or .venv/)" >&2
    return 1
}

# One shared virtual environment and one root requirements.txt.
if [[ "${1:-}" == "--serve-http" ]]; then
    name="${2:?Missing window name}"
    module="${3:?Missing FastAPI module}"
    port="${4:?Missing port}"
    cd "$ROOT_DIR"
    PYTHON="$(find_python)"
    export PYTHONPATH="$ROOT_DIR:$ROOT_DIR/generated${PYTHONPATH:+:$PYTHONPATH}"
    echo "[$name] http://127.0.0.1:$port"
    if PYTHONUNBUFFERED=1 "$PYTHON" -m uvicorn "$module:app" \
        --reload --host 127.0.0.1 --port "$port"; then
        echo "[$name] Server stopped normally."
    else
        code=$?
        echo "[$name] Uvicorn exited with status $code" >&2
    fi
    exec "${SHELL:-/bin/bash}" -i
fi

if [[ "${1:-}" == "--serve-grpc" ]]; then
    cd "$ROOT_DIR"
    PYTHON="$(find_python)"
    export PYTHONPATH="$ROOT_DIR:$ROOT_DIR/generated${PYTHONPATH:+:$PYTHONPATH}"
    # Generated modules are imported by services.rules.grpc_server.
    if [[ ! -f "$ROOT_DIR/generated/rules_pb2.py" || ! -f "$ROOT_DIR/generated/rules_pb2_grpc.py" ]]; then
        mkdir -p "$ROOT_DIR/generated"
        "$PYTHON" -m grpc_tools.protoc \
            -I "$ROOT_DIR/contracts" \
            --python_out="$ROOT_DIR/generated" \
            --grpc_python_out="$ROOT_DIR/generated" \
            "$ROOT_DIR/contracts/rules.proto"
    fi
    echo '[rules-grpc] 127.0.0.1:50051'
    # grpc_server.py exposes serve_grpc(), not a runnable CLI entrypoint.
    if PYTHONUNBUFFERED=1 "$PYTHON" -c \
        'import asyncio; from services.rules.grpc_server import serve_grpc; asyncio.run(serve_grpc())'; then
        echo '[rules-grpc] Server stopped normally.'
    else
        code=$?
        echo "[rules-grpc] gRPC exited with status $code" >&2
    fi
    exec "${SHELL:-/bin/bash}" -i
fi

start_http() {
    local name="$1" module="$2" port="$3" command
    printf -v command '%q ' /bin/bash "$ROOT_DIR/start_servers.sh" --serve-http "$name" "$module" "$port"
    if tmux has-session -t "$SESSION" 2>/dev/null; then
        tmux new-window -d -t "$SESSION:" -n "$name" -c "$ROOT_DIR" "$command"
    else
        tmux new-session -d -s "$SESSION" -n "$name" -c "$ROOT_DIR" "$command"
    fi
    tmux set-window-option -t "$SESSION:$name" automatic-rename off
    printf '[servers] %-12s http://127.0.0.1:%s\n' "$name" "$port"
}

start_grpc() {
    local command
    printf -v command '%q ' /bin/bash "$ROOT_DIR/start_servers.sh" --serve-grpc
    tmux new-window -d -t "$SESSION:" -n rules-grpc -c "$ROOT_DIR" "$command"
    tmux set-window-option -t "$SESSION:rules-grpc" automatic-rename off
    echo '[servers] rules-grpc   127.0.0.1:50051'
}

start_http monitoring  services.monitoring.main  8001
start_http rules       services.rules.main       8002
start_http incidents   services.incidents.main   8003
start_http alerts      services.alerts.main      8004
start_http fake-target services.fake_target.main 8090

#start_grpc

bash "$ROOT_DIR/start_dependencies.sh" --order-windows
