#!/bin/sh
set -e

# Start Ollama in background
ollama serve &

# Wait until Ollama is accepting requests
echo "[startup] Waiting for Ollama..."
until curl -sf http://localhost:11434/ > /dev/null 2>&1; do
  sleep 1
done
echo "[startup] Ollama ready — llama3.2:3b pre-loaded"

# Start FastAPI
exec uvicorn backend.main:app --host 0.0.0.0 --port 7860
