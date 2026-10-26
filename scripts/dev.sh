#!/usr/bin/env bash
# One entry point for the local stack (AB#67/AB#70): Postgres, the API, the
# frontend, and — for the `local` profile — a native Ollama server this
# project owns outright, on its own port, never sharing one with whatever
# else on this machine happens to run Ollama (another project's container,
# a bare `ollama serve`). That port collision, and the three-terminal manual
# dance it used to take to start everything in the right order, are exactly
# what AB#67 opened to fix.
#
# Usage:
#   scripts/dev.sh up [local|cloud]   # default: local
#   scripts/dev.sh down
#   scripts/dev.sh status
#   scripts/dev.sh doctor             # same as `status`, plus a real
#                                      # chat+vision call (slower, one API
#                                      # round-trip) — see /health/ready?deep=1
#
# Env knobs (all optional): API_PORT (default 8000), FRONTEND_PORT (3100),
# OLLAMA_PORT (11435 — deliberately not Ollama's default 11434; see
# config/profiles/local.env's comment on why).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

STATE_DIR="$ROOT_DIR/.dev"
OLLAMA_PID_FILE="$STATE_DIR/ollama.pid"
OLLAMA_LOG_FILE="$STATE_DIR/ollama.log"
OLLAMA_PORT="${OLLAMA_PORT:-11435}"
API_PORT="${API_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3100}"

# Loads a profile (non-secret provider/model/timeout defaults), then `.env`
# (secrets + any deliberate override) on top of it, into THIS shell's
# environment — so everything launched below (docker compose, the native
# ollama warm-up) sees the same, single resolved configuration. `.env`
# loading is optional: a fresh checkout with no `.env` yet still runs the
# `cloud` profile's shape (just without a GEMINI_API_KEY, which `/health`
# already reports as "unconfigured" rather than crashing).
load_env() {
  local profile="$1"
  local profile_file="$ROOT_DIR/config/profiles/${profile}.env"
  if [[ ! -f "$profile_file" ]]; then
    echo "No such profile: $profile (expected $profile_file)" >&2
    exit 1
  fi
  set -a
  # shellcheck disable=SC1090
  source "$profile_file"
  if [[ -f "$ROOT_DIR/.env" ]]; then
    # shellcheck disable=SC1091
    source "$ROOT_DIR/.env"
  fi
  set +a
  export OLLAMA_PORT API_PORT FRONTEND_PORT
}

wait_for_http() {
  local url="$1" tries="${2:-30}"
  for _ in $(seq 1 "$tries"); do
    curl -s -m 2 -o /dev/null "$url" && return 0
    sleep 1
  done
  return 1
}

# Starts (if not already reachable) and warms this project's OWN native
# Ollama on $OLLAMA_PORT, pinning the chat+vision models in RAM
# (OLLAMA_KEEP_ALIVE=-1) so the first real request isn't a ~30s cold-load.
# Writes a pidfile only when THIS call is the one that started the process —
# `down` kills by that pidfile, never by port, so it can never kill a
# server some other tool on this port happens to be running (that would
# require OLLAMA_PORT colliding with something else, which defeats the
# point of giving this project its own port in the first place, but the
# pidfile check costs nothing and removes the assumption entirely).
start_ollama() {
  mkdir -p "$STATE_DIR"
  local host="http://localhost:${OLLAMA_PORT}"
  local chat_model="${OLLAMA_MODEL:-qwen3:8b}"
  local vision_model="${OLLAMA_VISION_MODEL:-qwen2.5vl:3b}"
  # Must match `OllamaEmbeddingProvider`'s default model id
  # (data/embeddings/ollama.py) — a cache-miss query otherwise gets a 404
  # from `/api/embeddings` and silently degrades to keyword-only retrieval
  # (RAG results come back with `dense_similarity: None`, and fast_path's
  # dense-similarity floor can then never clear). Nothing surfaces an error
  # for this; it just looks like weaker answers and fast_path never firing.
  local embedding_model="${OLLAMA_EMBEDDING_MODEL:-nomic-embed-text}"

  if curl -s -m 2 -o /dev/null "$host/api/tags"; then
    echo "ollama already reachable at $host (reusing it, not tracked for 'down')"
  else
    if ! command -v ollama >/dev/null 2>&1; then
      echo "ollama CLI not found — install it: https://ollama.com/download" >&2
      exit 1
    fi
    echo "Starting this project's own ollama serve on port $OLLAMA_PORT (OLLAMA_KEEP_ALIVE=-1)..."
    OLLAMA_HOST="127.0.0.1:${OLLAMA_PORT}" OLLAMA_KEEP_ALIVE=-1 \
      nohup ollama serve >"$OLLAMA_LOG_FILE" 2>&1 &
    echo $! >"$OLLAMA_PID_FILE"
    disown
    if ! wait_for_http "$host/api/tags" 15; then
      echo "ollama serve did not come up — check $OLLAMA_LOG_FILE" >&2
      exit 1
    fi
  fi

  if ! OLLAMA_HOST="127.0.0.1:${OLLAMA_PORT}" ollama list 2>/dev/null | grep -q "^${embedding_model}"; then
    echo "Pulling $embedding_model (not found locally — RAG retrieval degrades to keyword-only without it)..."
    OLLAMA_HOST="127.0.0.1:${OLLAMA_PORT}" ollama pull "$embedding_model"
  fi

  echo "Warming $chat_model, $vision_model and $embedding_model (keep_alive=-1, never unload)..."
  curl -s "$host/api/chat" \
    -d "{\"model\":\"$chat_model\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"stream\":false,\"keep_alive\":-1}" \
    -o /dev/null
  curl -s "$host/api/chat" \
    -d "{\"model\":\"$vision_model\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"stream\":false,\"keep_alive\":-1}" \
    -o /dev/null
  curl -s "$host/api/embeddings" \
    -d "{\"model\":\"$embedding_model\",\"prompt\":\"hi\",\"keep_alive\":-1}" \
    -o /dev/null
  echo "Ready: $(curl -s "$host/api/ps" | python3 -c 'import sys,json; print([m["name"] for m in json.load(sys.stdin)["models"]])' 2>/dev/null || echo "(could not list loaded models)")"
}

stop_ollama() {
  if [[ -f "$OLLAMA_PID_FILE" ]]; then
    local pid
    pid="$(cat "$OLLAMA_PID_FILE")"
    if kill -0 "$pid" 2>/dev/null; then
      echo "Stopping this project's ollama serve (pid $pid)..."
      kill "$pid"
    fi
    rm -f "$OLLAMA_PID_FILE"
  else
    echo "No ollama serve tracked by dev.sh (either not started, or reused one already running) — leaving it alone."
  fi
}

cmd_up() {
  local profile="${1:-local}"
  load_env "$profile"
  echo "Profile: $profile  (LLM_PROVIDER=${LLM_PROVIDER:-unset})"

  docker compose up -d postgres
  if [[ "$profile" == "local" ]]; then
    start_ollama
    # host.docker.internal, not localhost (which from inside the API
    # container means the container itself) — overridden only for this one
    # command, so `local.env`'s OLLAMA_BASE_URL (correct for the bare-metal
    # uvicorn flow in setup.md, where "localhost" really is this machine)
    # stays intact for every other consumer in this script and shell.
    OLLAMA_BASE_URL="http://host.docker.internal:${OLLAMA_PORT}/v1" \
      docker compose up -d --build api frontend
  else
    docker compose up -d --build api frontend
  fi

  echo
  echo "Up. API: http://127.0.0.1:${API_PORT}  Frontend: http://localhost:${FRONTEND_PORT}"
  echo "Check it actually works: scripts/dev.sh doctor"
}

cmd_down() {
  docker compose down
  stop_ollama
}

cmd_status() {
  local deep="${1:-}"
  docker compose ps
  echo
  if [[ -f "$OLLAMA_PID_FILE" ]]; then
    local host="http://localhost:${OLLAMA_PORT}"
    if curl -s -m 2 -o /dev/null "$host/api/tags"; then
      echo "ollama (dev.sh-managed, port $OLLAMA_PORT): reachable"
      curl -s "$host/api/ps" | python3 -c 'import sys,json; [print(f"  {m["name"]} (until {m["expires_at"]})") for m in json.load(sys.stdin)["models"]]' 2>/dev/null || true
    else
      echo "ollama (dev.sh-managed, port $OLLAMA_PORT): pidfile present but unreachable"
    fi
  else
    echo "ollama: not started by dev.sh this session"
  fi
  echo
  local ready_url="http://127.0.0.1:${API_PORT}/health/ready"
  [[ "$deep" == "deep" ]] && ready_url="${ready_url}?deep=1"
  echo "GET $ready_url"
  curl -s "$ready_url" | python3 -m json.tool 2>/dev/null || echo "(API not reachable)"
}

case "${1:-}" in
  up) cmd_up "${2:-local}" ;;
  down) cmd_down ;;
  status) cmd_status ;;
  doctor) cmd_status deep ;;
  *)
    echo "Usage: $0 {up [local|cloud]|down|status|doctor}" >&2
    exit 1
    ;;
esac
