import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path('/qa/litellm-35800')
repo = Path('/opt/litellm-35800')
phase = sys.argv[1]
files = [
    'tests/unit/proxy/auth/test_auth_checks.py',
    'tests/unit/proxy/auth/test_auth_checks_object_access_and_lookup.py',
    'tests/unit/proxy/proxy_server/test_spend_counters.py',
    'tests/unit/integrations/SlackAlerting/test_slack_alerting.py',
]
command = [sys.executable, '-m', 'pytest', '-q', '--tb=short', *files]
if phase == 'red':
    assert not subprocess.check_output(['git', 'diff', '--name-only', '--', 'litellm', 'enterprise'], cwd=repo, text=True).strip()
    command += ['-k', 'soft_budget_alert_uses_current_spend_without_blocking_requests or test_virtual_key_soft_budget_check']
elif phase.startswith('focused'):
    command += ['-k', 'soft_budget_alert_uses_current_spend_without_blocking_requests']
env = {**os.environ, 'PYTHONPATH': str(repo), 'LITELLM_LOCAL_MODEL_COST_MAP': 'True', 'PYTHON_DOTENV_DISABLED': '1'}
env['PATH'] = '/opt/litellm-venv/bin:/opt/contri-node/bin:' + env['PATH']
report = {'phase': phase, 'command': command, 'started_at': datetime.now(timezone.utc).isoformat(),
          'source_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip(),
          'source_sha256': hashlib.sha256((repo / 'litellm/proxy/auth/auth_checks.py').read_bytes()).hexdigest()}
with (root / f'unit-{phase}.log').open('w') as log:
    result = subprocess.run(command, cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT)
report.update(returncode=result.returncode, completed_at=datetime.now(timezone.utc).isoformat())
(root / f'unit-{phase}.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report), flush=True)
print((root / f'unit-{phase}.log').read_text()[-10000:], flush=True)
sys.exit(result.returncode)
