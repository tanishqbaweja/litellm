import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path('/qa/litellm-35800')
phase = sys.argv[1]
assert phase in ('red', 'shard')
source = Path('/opt/litellm-34927-baseline' if phase == 'red' else '/opt/litellm-35800')
relative = Path('tests/unit/proxy/auth/test_user_api_key_auth.py')
target = source / relative
original = target.read_bytes()
candidate = (Path('/opt/litellm-35800') / relative).read_bytes()
command = [sys.executable, '-m', 'pytest', '-q', '--tb=short', '-o', 'faulthandler_timeout=60']
if phase == 'red':
    command += [str(relative) + '::test_soft_budget_alert']
else:
    command += [
        '-n', '4', '--dist', 'loadscope',
        'tests/unit/proxy/auth/test_auth_checks.py', str(relative),
        'tests/unit/proxy/test_credential_slot_registry.py',
        'tests/unit/proxy/test_deprecated_key_grace_period.py',
    ]
report = {
    'phase': phase,
    'command': command,
    'source_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip(),
    'test_sha256': hashlib.sha256(candidate).hexdigest(),
    'production_sha256': hashlib.sha256((source / 'litellm/proxy/auth/auth_checks.py').read_bytes()).hexdigest(),
    'started_at': datetime.now(timezone.utc).isoformat(),
    'reruns_enabled': False,
}
env = {**os.environ, 'PYTHONPATH': str(source), 'PYTHON_DOTENV_DISABLED': '1', 'LITELLM_LOCAL_MODEL_COST_MAP': 'True'}
if phase == 'red':
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=source, text=True).strip()
    target.write_bytes(candidate)
try:
    with (root / f'auth-followup-{phase}.log').open('w') as log:
        result = subprocess.run(command, cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=600)
    report['returncode'] = result.returncode
finally:
    if phase == 'red':
        target.write_bytes(original)
        report['baseline_restored_exactly'] = not subprocess.check_output(['git', 'status', '--porcelain'], cwd=source, text=True).strip()
    report['completed_at'] = datetime.now(timezone.utc).isoformat()
    (root / f'auth-followup-{phase}.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2), flush=True)
print((root / f'auth-followup-{phase}.log').read_text()[-6500:], flush=True)
sys.exit(result.returncode)
