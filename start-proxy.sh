#!/usr/bin/env bash
set -euo pipefail
revision="${1:?revision required}"
case "$revision" in
  baseline) source_path=/opt/litellm-34927-baseline ;;
  fixed) source_path=/opt/litellm-34681 ;;
  *) exit 2 ;;
esac
export PATH="/opt/litellm-venv/bin:$PATH"
export PYTHONPATH="$source_path"
export PRISMA_BINARY_CACHE_DIR=/opt/prisma-cache
export LITELLM_UI_PATH=/qa/litellm-ui-baseline-47520
export LITELLM_LOCAL_MODEL_COST_MAP=True
unset LITELLM_LICENSE
cd "$source_path"
python - "$revision" <<'PY'
import json, subprocess, sys
from pathlib import Path
import litellm
root = Path('/qa/litellm-34681')
revision = sys.argv[1]
source = Path(litellm.__file__).resolve().parent.parent
sha = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
expected = json.loads((root / ('runtime.json' if revision == 'baseline' else 'product.json')).read_text())['base' if revision == 'baseline' else 'head']
assert sha == expected
assert not subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True).strip()
(root / f'proxy-source-{revision}.json').write_text(json.dumps({'source': str(source), 'sha': sha}, indent=2) + '\n')
PY
printf '%s\n' "$$" > /qa/litellm-34681/proxy.pid
exec python -m litellm.proxy.proxy_cli --host 0.0.0.0 --port 41475 --telemetry false \
  --config /qa/litellm-34681/config.yml > "/qa/litellm-34681/proxy-${revision}.log" 2>&1
