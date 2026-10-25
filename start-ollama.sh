#!/usr/bin/env bash
set -euo pipefail
export OLLAMA_HOST=127.0.0.1:11434
export OLLAMA_MODELS=/qa/litellm-26170/ollama-models
export OLLAMA_CONTEXT_LENGTH=1024
export OLLAMA_NUM_PARALLEL=1
export OLLAMA_MAX_LOADED_MODELS=2
export OLLAMA_NO_CLOUD=1
printf '%s\n' "$$" > /qa/litellm-26170/ollama.pid
exec /opt/qa-ollama-0.40.11/bin/ollama serve > /qa/litellm-26170/ollama.log 2>&1
