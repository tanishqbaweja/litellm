#!/usr/bin/env bash
set -euo pipefail
export PATH="/opt/uv-x86_64-unknown-linux-gnu:/opt/litellm-venv/bin:$PATH"
export CARGO_TARGET_DIR=/opt/litellm-rust-target
export CARGO_BUILD_JOBS=2
export UV_PROJECT_ENVIRONMENT=/opt/litellm-venv
export PYTHONPATH=/opt/litellm-35459
export PRISMA_BINARY_CACHE_DIR=/opt/prisma-cache
cd /opt/litellm-35459
make format
uv run --no-sync ruff format litellm/router_strategy/lowest_cost.py tests/unit/router_strategy/test_lowest_cost.py
