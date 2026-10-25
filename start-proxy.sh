#!/usr/bin/env bash
set -euo pipefail
revision="${1:?revision required}"
case "$revision" in
  baseline) source_path=/opt/litellm-34927-baseline ;;
  fixed) source_path=/opt/litellm-26170 ;;
  *) exit 2 ;;
esac
export PATH="/opt/litellm-venv/bin:$PATH"
export PYTHONPATH="$source_path"
export PRISMA_BINARY_CACHE_DIR=/opt/prisma-cache
export LITELLM_UI_PATH=/qa/litellm-ui-baseline-47520
export LITELLM_LOCAL_MODEL_COST_MAP=True
unset LITELLM_LICENSE
cd "$source_path"
printf '%s\n' "$$" > /qa/litellm-26170/proxy.pid
exec python -m litellm.proxy.proxy_cli --host 0.0.0.0 --port 41475 --telemetry false \
  --config /qa/litellm-26170/config.yml > "/qa/litellm-26170/proxy-${revision}.log" 2>&1
