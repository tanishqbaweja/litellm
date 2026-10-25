#!/usr/bin/env bash
set -euo pipefail
export PATH="/opt/contri-node/bin:/opt/litellm-venv/bin:$PATH"
export PYTHONPATH=/opt/litellm-36095
export LITELLM_PYTHON=/opt/litellm-venv/bin/python
export PRISMA_BINARY_CACHE_DIR=/opt/prisma-cache
export LITELLM_LOCAL_MODEL_COST_MAP=True
cd /opt/litellm-36095
python - <<'PY'
from pathlib import Path
import litellm
root = Path('/opt/litellm-36095')
assert Path(litellm.__file__).resolve().parent.parent == root
dependencies = root / 'ui/litellm-dashboard/node_modules'
shared = Path('/repo/ui/litellm-dashboard/node_modules')
assert shared.is_dir()
assert (root / 'ui/litellm-dashboard/package-lock.json').read_bytes() == Path('/repo/ui/litellm-dashboard/package-lock.json').read_bytes()
if not dependencies.exists():
    dependencies.symlink_to(shared, target_is_directory=True)
assert dependencies.resolve() in (shared.resolve(), Path('/qa/litellm-36095/dashboard-deps-linux/node_modules').resolve())
assert (root / 'ui/litellm-dashboard/package-lock.json').read_bytes() == (dependencies.resolve().parent / 'package-lock.json').read_bytes()
print('Verified source and shared dashboard dependency lock')
PY
python -m litellm.proxy._lazy_openapi_snapshot
cd ui/litellm-dashboard
npm run gen:api
