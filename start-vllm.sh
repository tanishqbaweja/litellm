#!/usr/bin/env bash
set -euo pipefail
model_kind="${1:?model kind required}"
case "$model_kind" in
  embedding)
    model_path=/qa/models/sentence-transformers
    served_name=sentence-transformers/all-MiniLM-L6-v2
    model_port=51477
    ;;
  ranking)
    model_path=/qa/models/cross-encoder
    served_name=cross-encoder/ms-marco-MiniLM-L6-v2
    model_port=51478
    ;;
  *) exit 2 ;;
esac
printf '%s\n' "$$" > "/qa/vllm-${model_kind}.pid"
exec vllm serve "$model_path" \
  --served-model-name "$served_name" --host 127.0.0.1 --port "$model_port" \
  --runner pooling --dtype float32 --max-model-len 128 \
  --max-num-seqs 4 --max-num-batched-tokens 512 --enforce-eager \
  > "/qa/vllm-${model_kind}.log" 2>&1
