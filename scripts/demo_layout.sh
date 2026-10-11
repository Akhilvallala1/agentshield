#!/usr/bin/env bash
# Four panes: gateway | demo runner / approval / evals (addendum 15.9)
set -euo pipefail
cd "$(dirname "$0")/.."
tmux kill-session -t shield 2>/dev/null || true
tmux new-session -d -s shield -n demo "uv run uvicorn agentshield.gateway:app --port 8765"
tmux split-window -h -t shield "zsh"
tmux split-window -v -t shield:0.1 "zsh"
tmux split-window -v -t shield:0.0 "zsh"
tmux send-keys -t shield:0.1 "uv run python -m agentshield.cli.demo send" ""
tmux send-keys -t shield:0.2 "uv run python -m agentshield.cli.approve" ""
tmux send-keys -t shield:0.3 "uv run python scripts/run_evals.py" ""
tmux attach -t shield
