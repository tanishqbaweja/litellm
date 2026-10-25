import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

root = Path(__file__).resolve().parents[2]
qa = root / '.verification/litellm-36095'
repo = root / 'litellm-36095'
dashboard = repo / 'ui/litellm-dashboard'
base = json.loads((qa / 'runtime.json').read_text())['base']
schema_name = 'ui/litellm-dashboard/src/lib/http/schema.d.ts'
schema = repo / schema_name
fixed = schema.read_bytes()
(qa / 'schema-fixed.before-baseline.bin').write_bytes(fixed)
baseline = subprocess.run(['git', '-C', str(repo), 'show', f'{base}:{schema_name}'], capture_output=True, check=True).stdout
node_dir = root / '.tools/node-v24.21.0-win-x64'
env = {**os.environ, 'PATH': str(node_dir) + os.pathsep + os.environ['PATH'], 'CI': 'true'}
node = str(node_dir / 'node.exe')
report = {'base': base, 'started_at': datetime.now(timezone.utc).isoformat()}
try:
    schema.write_bytes(baseline)
    subprocess.run(['git', '-C', str(repo), 'diff', '--exit-code', base, '--', 'ui/litellm-dashboard'], check=True)
    report['dashboard_matches_main_exactly'] = True
    report['locale'] = json.loads(subprocess.run([node, '-p', 'JSON.stringify({locale:new Intl.NumberFormat().resolvedOptions().locale,number:(1000000).toLocaleString()})'], capture_output=True, text=True, check=True).stdout)
    command = [node, 'node_modules/vitest/vitest.mjs', 'run',
        'src/components/model_info_view.test.tsx',
        'src/components/add_model/AddModelForm.integration.test.tsx',
        'src/components/add_model/handle_add_model_submit.test.tsx',
        'src/lib/http/api.test.ts', '--maxWorkers=2']
    log = root / '.verification/logs/litellm-36095-ui-baseline-windows.log'
    with log.open('w', encoding='utf-8') as output:
        result = subprocess.run(command, cwd=dashboard, env=env, stdout=output, stderr=subprocess.STDOUT, text=True)
    report['returncode'] = result.returncode
    clean = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', log.read_text(encoding='utf-8'))
    report['failures'] = [line.strip() for line in clean.splitlines() if ' FAIL ' in line]
    report['summary'] = [line.strip() for line in clean.splitlines() if line.strip().startswith(('Test Files ', 'Tests ', 'Duration '))]
    print(json.dumps(report, indent=2), flush=True)
finally:
    schema.write_bytes(fixed)
    report['fixed_schema_restored_exactly'] = schema.read_bytes() == fixed
    report['fixed_schema_sha256'] = hashlib.sha256(fixed).hexdigest()
    report['completed_at'] = datetime.now(timezone.utc).isoformat()
    (qa / 'ui-baseline-comparison.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
