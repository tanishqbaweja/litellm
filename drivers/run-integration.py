import json
import os
import subprocess
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values

root = Path('/qa/litellm-42689')
repo = Path('/opt/litellm-42689')
phase = sys.argv[1]
results = root / f'integration-{phase}'
results.mkdir(exist_ok=True)
os.chdir(repo)
sys.path.insert(0, str(repo))
os.environ.update({
    'DATABASE_URL': dotenv_values('/qa/litellm-linux.env')['DATABASE_URL'],
    'PYTHONPATH': os.pathsep.join((str(repo), str(repo / 'tests'), str(repo / 'tests/e2e'))),
    'INTEGRATION_PROXY_ROOT': str(repo),
    'LITELLM_LOCAL_MODEL_COST_MAP': 'True',
    'PYTHON_DOTENV_DISABLED': '1',
    'PRISMA_BINARY_CACHE_DIR': '/opt/prisma-cache',
    'PATH': '/opt/litellm-venv/bin:/opt/contri-node/bin:' + os.environ['PATH'],
})
os.environ.pop('DISABLE_SCHEMA_UPDATE', None)
filename = 'tests/integration/spend/test_expired_ui_session_failure_rows.py'
nodes = [filename + '::test_unrecognized_keys_do_not_fill_spend_tables'] if phase == 'red' else [filename]
report = {'phase': phase, 'started_at': datetime.now(timezone.utc).isoformat(), 'nodes': nodes}
report['source_head'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
if phase == 'red':
    assert report['source_head'] == json.loads((root / 'runtime.json').read_text())['base']
    assert not subprocess.check_output(['git', 'diff', '--name-only', '--', 'litellm', 'enterprise'], text=True).strip()
print(json.dumps({'phase': phase, 'stage': 'Starting repository-owned Postgres, Redis, upstream and proxy services'}), flush=True)
with (root / f'integration-{phase}.private.log').open('w') as log, redirect_stdout(log), redirect_stderr(log):
    try:
        from tests.integration._support.workers import GatewayProfile, worker_stack

        stack = worker_stack(results, GatewayProfile(peer=False, replica=False, cost_map=False, coverage_file=None))
        with stack.resources:
            report['services_ready'] = True
            result = subprocess.run(
                [sys.executable, 'tests/integration/run.py', 'accounting', '--results', str(results), *nodes],
                env={**os.environ, **stack.environment}, stdout=log, stderr=subprocess.STDOUT,
            )
            report['returncode'] = result.returncode
        report['owned_services_cleaned_up'] = True
    except BaseException as error:
        traceback.print_exc()
        report['error_type'] = type(error).__name__
        report['returncode'] = 2
report['completed_at'] = datetime.now(timezone.utc).isoformat()
(root / f'integration-{phase}.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report), flush=True)
sys.exit(report['returncode'])
