import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path('/qa/litellm-42689')
source = Path('/opt/litellm-42689')
name = sys.argv[1]
commands = {
    'format': ['make', 'format'],
    'lint': ['make', 'lint', 'BASE_REF=origin/main', 'LINT_JOBS=2'],
    'committed-format': ['make', 'lint-format-check-changed', 'BASE_REF=origin/main', 'LINT_DEP_INSTALL=', 'LINT_DEP_BASE='],
}
command = commands[name]
env = {
    **os.environ,
    'PATH': '/opt/uv-x86_64-unknown-linux-gnu:/opt/litellm-venv/bin:/opt/contri-node/bin:' + os.environ['PATH'],
    'CARGO_TARGET_DIR': '/opt/litellm-rust-target',
    'CARGO_BUILD_JOBS': '2',
    'CARGO_INCREMENTAL': '0',
    'UV_PROJECT_ENVIRONMENT': '/opt/litellm-venv',
    'PYTHONPATH': str(source),
    'PRISMA_BINARY_CACHE_DIR': '/opt/prisma-cache',
    'PYTHON_DOTENV_DISABLED': '1',
    'LITELLM_LOCAL_MODEL_COST_MAP': 'True',
}
report = {'name': name, 'command': command, 'started_at': datetime.now(timezone.utc).isoformat()}
with (root / f'{name}.log').open('w') as log:
    result = subprocess.run(command, cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT)
report.update(returncode=result.returncode, completed_at=datetime.now(timezone.utc).isoformat())
(root / f'{name}.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2), flush=True)
print((root / f'{name}.log').read_text()[-4000:], flush=True)
sys.exit(result.returncode)
