#!/usr/bin/env bash
set -euo pipefail
export PATH="/opt/uv-x86_64-unknown-linux-gnu:/opt/litellm-venv/bin:$PATH"
export CARGO_TARGET_DIR=/opt/litellm-rust-target
export CARGO_BUILD_JOBS=2
export UV_PROJECT_ENVIRONMENT=/opt/litellm-venv
export PYTHONPATH=/opt/litellm-35459
export PRISMA_BINARY_CACHE_DIR=/opt/prisma-cache
cd /opt/litellm-35459
set +e
make lint BASE_REF=origin/main LINT_JOBS=2 > /qa/logs/litellm-35459-lint.log 2>&1
result=$?
printf '%s\n' "$result" > /qa/litellm-35459/lint.exit
exit "$result"
