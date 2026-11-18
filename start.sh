#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SESSION="ping_patrol"

command -v tmux >/dev/null 2>&1 || {
    echo '[error] tmux is missing. Install it with: sudo apt install tmux' >&2
    exit 1
}

if [[ -n "${TMUX:-}" ]]; then
    echo '[error] First detach from tmux (Ctrl+B, then D), then run ./start.sh.' >&2
    exit 1
fi

# Re-running restarts only this project's tmux session.
if tmux has-session -t "$SESSION" 2>/dev/null; then
    tmux kill-session -t "$SESSION"
fi

bash "$ROOT_DIR/start_dependencies.sh" --services-only
bash "$ROOT_DIR/start_servers.sh"
bash "$ROOT_DIR/start_dependencies.sh" --windows-only

# Mouse/copy bindings preserved from the original launcher.
tmux set-option -t "$SESSION" mouse on
tmux set-window-option -g mode-keys vi
tmux set-window-option -g history-limit 50000

if [[ -n "${WAYLAND_DISPLAY:-}" ]] && command -v wl-copy >/dev/null 2>&1; then
    clipboard_command='wl-copy'
elif [[ -n "${DISPLAY:-}" ]] && command -v xclip >/dev/null 2>&1; then
    clipboard_command='xclip -selection clipboard -in >/dev/null'
else
    echo '[error] Copying tmux selections to the desktop clipboard requires' >&2
    echo '        wl-copy (Wayland) or xclip (X11/XWayland).' >&2
    echo '        Install: sudo apt install xclip wl-clipboard' >&2
    echo '        Run from a graphical terminal.' >&2
    tmux kill-session -t "$SESSION"
    exit 1
fi

for env_var in DISPLAY WAYLAND_DISPLAY XDG_RUNTIME_DIR XAUTHORITY; do
    if [[ -v "$env_var" ]]; then
        tmux set-environment -g "$env_var" "${!env_var}"
    fi
done

tmux set-option -s set-clipboard off
for table in copy-mode-vi copy-mode; do
    tmux bind-key -T "$table" MouseDragEnd1Pane send-keys -X copy-pipe-and-cancel "$clipboard_command"
    tmux bind-key -T "$table" Enter send-keys -X copy-pipe-and-cancel "$clipboard_command"
done
tmux bind-key -T copy-mode-vi y send-keys -X copy-pipe-and-cancel "$clipboard_command"

tmux select-window -t "$SESSION:monitoring"

printf '\n[ready] Independently selectable tmux windows:\n'
printf '  monitoring | rules | incidents | alerts | fake-target | users | celery | rabbitmq | redis | postgresql\n'
printf '  Ctrl+B, then W: select a window from a list\n'
printf '  Ctrl+B, then its window number: jump to a window directly\n'
printf '  Or click its name in the bottom tmux bar\n'
printf '  Left-click drag and release: copy selected text to system clipboard\n'
printf '  Ctrl+B, then D: detach (services keep running)\n'
printf '  Stop everything here: tmux kill-session -t %s\n\n' "$SESSION"

exec tmux attach-session -t "$SESSION"
