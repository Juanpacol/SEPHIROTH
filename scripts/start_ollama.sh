#!/usr/bin/env bash
# Start (or reuse) a local Ollama server for this project's chat + vision
# models, and keep both pinned in RAM forever (OLLAMA_KEEP_ALIVE=-1) — by
# default Ollama unloads an idle model after 5 minutes, which turns every
# first request after a break into a ~30s cold-load instead of a normal
# inference call. Scoped to this project only: run this script instead of
# a bare `ollama serve`, rather than exporting OLLAMA_KEEP_ALIVE globally.
set -euo pipefail

CHAT_MODEL="${OLLAMA_MODEL:-qwen2.5:3b-instruct}"
VISION_MODEL="${OLLAMA_VISION_MODEL:-qwen2.5vl:3b}"
HOST="${OLLAMA_BASE_URL:-http://localhost:11434}"
HOST="${HOST%/v1}"

if ! curl -s -m 2 -o /dev/null "$HOST/api/tags"; then
  echo "Starting ollama serve (OLLAMA_KEEP_ALIVE=-1)..."
  OLLAMA_KEEP_ALIVE=-1 nohup ollama serve > /tmp/ollama-serve.log 2>&1 &
  disown
  for _ in $(seq 1 15); do
    curl -s -m 2 -o /dev/null "$HOST/api/tags" && break
    sleep 1
  done
else
  echo "ollama serve already running at $HOST."
fi

echo "Warming $CHAT_MODEL and $VISION_MODEL (keep_alive=-1, never unload)..."
curl -s "$HOST/api/chat" -d "{\"model\":\"$CHAT_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"stream\":false,\"keep_alive\":-1}" -o /dev/null
curl -s "$HOST/api/chat" -d "{\"model\":\"$VISION_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"stream\":false,\"keep_alive\":-1}" -o /dev/null

echo "Ready:"
curl -s "$HOST/api/ps" | python3 -c "import sys,json; [print(f\"  {m['name']} (until {m['expires_at']})\") for m in json.load(sys.stdin)['models']]"
