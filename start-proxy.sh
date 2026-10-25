#!/usr/bin/env bash
set -euo pipefail
revision="${1:?revision required}"
case "$revision" in
  baseline) source_path=/opt/litellm-34927-baseline ;;
  fixed) source_path=/opt/litellm-36095 ;;
  *) exit 2 ;;
esac
export PATH="/opt/litellm-venv/bin:$PATH"
export PYTHONPATH="$source_path"
export PRISMA_BINARY_CACHE_DIR=/opt/prisma-cache
export LITELLM_UI_PATH=/qa/litellm-ui-baseline-47520
export LITELLM_LOCAL_MODEL_COST_MAP=True
export QA_36095_INTEGER_WEIGHT=100
export QA_36095_FRACTIONAL_WEIGHT=1.5
export QA_36095_ZERO_WEIGHT=0
export QA_36095_RATE=1000000
export QA_36095_ZERO_RATE=0
unset LITELLM_LICENSE
cd "$source_path"
python - "$revision" <<'PY'
import json, os, socket, subprocess, sys
from pathlib import Path
import litellm
root = Path('/qa/litellm-36095')
revision = sys.argv[1]
source = Path(litellm.__file__).resolve().parent.parent
sha = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
expected = json.loads((root / ('runtime.json' if revision == 'baseline' else 'product.json')).read_text())['base' if revision == 'baseline' else 'head']
assert sha == expected
assert not subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True).strip()
with socket.socket() as connection:
    assert connection.connect_ex(('127.0.0.1', 41475)) != 0, 'QA proxy port is occupied'
pid = os.getppid()
(root / 'proxy.pid').write_text(str(pid) + '\n')
temporary = root / f'proxy-source-{revision}.tmp'
temporary.write_text(json.dumps({'source': str(source), 'sha': sha, 'pid': pid}, indent=2) + '\n')
temporary.replace(root / f'proxy-source-{revision}.json')
PY
exec python -m litellm.proxy.proxy_cli --host 0.0.0.0 --port 41475 --telemetry false \
  --config /qa/litellm-36095/config.yml > "/qa/litellm-36095/proxy-${revision}.log" 2>&1
