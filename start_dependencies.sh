#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SESSION="ping_patrol"

load_env() {
    if [[ -f "$ROOT_DIR/.env" ]]; then
        set -a
        # shellcheck disable=SC1091
        source "$ROOT_DIR/.env"
        set +a
    fi
}

find_python() {
    local python
    for python in "$ROOT_DIR/venv/bin/python" "$ROOT_DIR/.venv/bin/python"; do
        if [[ -x "$python" ]]; then
            printf '%s\n' "$python"
            return 0
        fi
    done
    echo '[error] Missing virtual environment: venv/ or .venv/.' >&2
    return 1
}

order_dependency_windows() {
    local name last_index
    tmux has-session -t "$SESSION" 2>/dev/null || return 0
    for name in celery rabbitmq redis postgresql; do
        if tmux list-windows -t "$SESSION" -F '#{window_name}' | grep -Fxq "$name"; then
            last_index="$(tmux list-windows -t "$SESSION" -F '#{window_index}' | sort -n | tail -n 1)"
            tmux move-window -d -s "$SESSION:=$name" -t "$SESSION:$((last_index + 1))"
        fi
    done
    tmux move-window -r -t "$SESSION:"
}

if [[ "${1:-}" == "--order-windows" ]]; then
    order_dependency_windows
    exit 0
fi

if [[ "${1:-}" == "--logs" ]]; then
    case "${2:-}" in
        rabbitmq) exec journalctl -u rabbitmq-server -n 50 -f --no-pager ;;
        redis) exec journalctl -u redis-server -n 50 -f --no-pager ;;
        postgresql) exec journalctl -u postgresql -u 'postgresql@*' -n 50 -f --no-pager ;;
        *) echo '[error] Unknown dependency.' >&2; exit 1 ;;
    esac
fi

# This entry point is run inside the dedicated tmux window.
if [[ "${1:-}" == "--celery" ]]; then
    cd "$ROOT_DIR"
    load_env
    PYTHON="$(find_python)"
    export CELERY_BROKER_URL="${CELERY_BROKER_URL:-amqp://${RABBITMQ_USER:-guest}:${RABBITMQ_PASSWORD:-guest}@127.0.0.1:${RABBITMQ_PORT:-5672}//}"
    export CELERY_RESULT_BACKEND="${CELERY_RESULT_BACKEND:-redis://127.0.0.1:${REDIS_PORT:-6379}/0}"

    if [[ -n "${CELERY_APP:-}" ]]; then
        exec "$PYTHON" -m celery -A "$CELERY_APP" worker --loglevel=info
    fi

    # A worker can start before application-specific tasks are implemented.
    # Keep the fallback worker on this project's queue.
    exec "$PYTHON" -c '
import os
from celery import Celery

app = Celery(
    "ping_patrol",
    broker=os.environ["CELERY_BROKER_URL"],
    backend=os.environ["CELERY_RESULT_BACKEND"],
)
app.worker_main(["worker", "--loglevel=info", "--concurrency=1", "--queues=ping_patrol"])
'
fi

cd "$ROOT_DIR"
load_env

command -v service >/dev/null 2>&1 || {
    echo '[error] The service command is missing.' >&2
    exit 1
}
command -v tmux >/dev/null 2>&1 || {
    echo '[error] tmux is not installed.' >&2
    exit 1
}

start_local_service() {
    local name="$1" label="$2"

    if service "$name" status >/dev/null 2>&1; then
        echo "[dependencies] $label already running."
        return 0
    fi

    echo "[dependencies] Starting $label..."
    if (( EUID == 0 )); then
        service "$name" start || {
            echo "[error] Cannot start $label (service: $name)." >&2
            return 1
        }
    else
        command -v sudo >/dev/null 2>&1 || {
            echo '[error] sudo is required to start local system services.' >&2
            return 1
        }
        sudo service "$name" start || {
            echo "[error] Cannot start $label (service: $name)." >&2
            return 1
        }
    fi
}

if [[ "${1:-}" != "--windows-only" ]]; then
    start_local_service postgresql PostgreSQL
    start_local_service rabbitmq-server RabbitMQ
    start_local_service redis-server Redis
fi

if [[ "${1:-}" == "--services-only" ]]; then
    exit 0
fi

PYTHON="$(find_python)"
"$PYTHON" -m celery --version >/dev/null || {
    echo '[error] Celery is not installed in the project virtual environment.' >&2
    exit 1
}

start_dependency_window() {
    local name="$1" command
    shift
    if tmux has-session -t "$SESSION" 2>/dev/null && \
       tmux list-windows -t "$SESSION" -F '#{window_name}' | grep -Fxq "$name"; then
        return 0
    fi
    printf -v command '%q ' /bin/bash "$ROOT_DIR/start_dependencies.sh" "$@"
    command+='; exec /bin/bash -i'
    if tmux has-session -t "$SESSION" 2>/dev/null; then
        tmux new-window -d -t "$SESSION:" -n "$name" -c "$ROOT_DIR" "$command"
    else
        tmux new-session -d -s "$SESSION" -n "$name" -c "$ROOT_DIR" "$command"
    fi
    tmux set-window-option -t "$SESSION:=$name" automatic-rename off
}

start_dependency_window celery --celery
start_dependency_window rabbitmq --logs rabbitmq
start_dependency_window redis --logs redis
start_dependency_window postgresql --logs postgresql
order_dependency_windows
printf '[dependencies] PostgreSQL, RabbitMQ, Redis and Celery started.\n'
