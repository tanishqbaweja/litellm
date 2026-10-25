#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$$" > /qa/litellm-23743/model.pid
exec /opt/qa-llama-b11669/llama-b11669/llama-server \
  -m /opt/qa-models/Qwen3.5-0.8B-Q4_0.gguf \
  --host 127.0.0.1 --port 51476 --ctx-size 1024 --parallel 1 --threads 4 -n 32 \
  --alias Qwen3.5-0.8B --chat-template-kwargs '{"enable_thinking":false}' --reasoning-budget 0 \
  > /qa/logs/litellm-23743-real-model.log 2>&1
