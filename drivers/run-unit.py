import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path('/qa/litellm-42689')
source = Path('/opt/litellm-42689')
phase = sys.argv[1]
env = {
    **os.environ,
    'PATH': '/opt/litellm-venv/bin:/opt/contri-node/bin:' + os.environ['PATH'],
    'PYTHONPATH': str(source),
    'PYTHON_DOTENV_DISABLED': '1',
    'LITELLM_LOCAL_MODEL_COST_MAP': 'True',
    'PRISMA_BINARY_CACHE_DIR': '/opt/prisma-cache',
}
command = [sys.executable, '-m', 'pytest', 'tests/unit/proxy/hooks/test_proxy_track_cost_callback.py', '-q', '--tb=short']
if phase != 'full':
    command += ['-k', 'unrecognized_keys_write']
else:
    command += [
        'tests/unit/proxy/auth/test_auth_utils.py',
        'tests/unit/proxy/auth/test_auth_exception_handler.py',
        'tests/unit/proxy/auth/test_resolvers_exceptions.py',
        'tests/unit/proxy/db/test_db_spend_update_writer.py',
        '-n', '4',
    ]
command += ['--junitxml=' + str(root / f'unit-{phase}.xml')]
report = {'phase': phase, 'command': command, 'started_at': datetime.now(timezone.utc).isoformat()}
report['head'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
if phase == 'red':
    assert not subprocess.check_output(['git', 'diff', '--name-only', '--', 'litellm'], cwd=source, text=True).strip()
with (root / f'unit-{phase}.log').open('w') as log:
    result = subprocess.run(command, cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT)
report.update(returncode=result.returncode, completed_at=datetime.now(timezone.utc).isoformat())
(root / f'unit-{phase}.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2), flush=True)
print((root / f'unit-{phase}.log').read_text()[-5500:], flush=True)
sys.exit(result.returncode)
