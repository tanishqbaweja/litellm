import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path('/qa/litellm-38759')
repo = Path('/opt/litellm-38759')
phase = sys.argv[1]
files = ['tests/unit/proxy/management_endpoints/test_budget_endpoints.py']
command = [sys.executable, '-m', 'pytest', '-q', '--tb=short', *files]
if phase == 'red':
    assert not subprocess.check_output(['git', 'diff', '--name-only', '--', 'litellm', 'enterprise'], cwd=repo, text=True).strip()
    command += ['-k', 'preserves_omitted_model_budgets_and_clears_explicit_empty_values or serializes_model_max_budget_for_prisma']
env = {**os.environ, 'PYTHONPATH': str(repo), 'LITELLM_LOCAL_MODEL_COST_MAP': 'True', 'PYTHON_DOTENV_DISABLED': '1'}
env['PATH'] = '/opt/litellm-venv/bin:/opt/contri-node/bin:' + env['PATH']
report = {
    'phase': phase, 'command': command, 'started_at': datetime.now(timezone.utc).isoformat(),
    'source_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip(),
    'source_sha256': hashlib.sha256((repo / 'litellm/proxy/management_endpoints/budget_management_endpoints.py').read_bytes()).hexdigest(),
}
with (root / f'unit-{phase}.log').open('w') as log:
    result = subprocess.run(command, cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT)
report.update(returncode=result.returncode, completed_at=datetime.now(timezone.utc).isoformat())
(root / f'unit-{phase}.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report), flush=True)
print((root / f'unit-{phase}.log').read_text()[-9000:], flush=True)
sys.exit(result.returncode)
