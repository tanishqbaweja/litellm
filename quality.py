import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path('/qa/litellm-35459')
source = Path('/opt/litellm-35459')
logs = root.parent / 'logs'
path = source / 'litellm/router_strategy/lowest_cost.py'
original = path.read_bytes()
text = original.decode()
fixed = 'id = (kwargs["litellm_params"].get("model_info") or {}).get("id", None)'
broken = 'id = kwargs["litellm_params"].get("model_info", {}).get("id", None)'
guard = 'if model_group is None or id is None:'
assert text.count(fixed) == 2
assert text.count(guard) == 2
first, rest = text.split(fixed, 1)
middle, last = rest.split(fixed, 1)
changes = (
    ('null-sync-metadata', first + broken + middle + fixed + last),
    ('null-async-metadata', first + fixed + middle + broken + last),
    ('skip-valid-deployments', text.replace(guard, 'if True:')),
    ('attribute-unidentified-calls', text.replace(fixed, 'id = (kwargs["litellm_params"].get("model_info") or {}).get("id") or "unidentified"')),
)
report = {'started_at': datetime.now(timezone.utc).isoformat(), 'mutations': []}
try:
    for name, mutant in changes:
        path.write_text(mutant)
        result = subprocess.run(
            [sys.executable, '-m', 'pytest', '-q', '--tb=short', 'tests/unit/router_strategy/test_lowest_cost.py'],
            cwd=source, capture_output=True, text=True,
        )
        output = result.stdout + result.stderr
        (logs / f'litellm-35459-mutation-{name}.log').write_text(output)
        match = re.search(r'(\d+) failed', output)
        report['mutations'].append({'name': name, 'returncode': result.returncode, 'failed_cases': int(match.group(1)) if match else 0})
        print(json.dumps(report['mutations'][-1]), flush=True)
        assert result.returncode == 1 and match, (name, output[-12000:])
finally:
    path.write_bytes(original)
    report['source_restored_exactly'] = path.read_bytes() == original
    report['restored_sha256'] = hashlib.sha256(original).hexdigest()
    report['completed_at'] = datetime.now(timezone.utc).isoformat()
    (root / 'mutation-report.json').write_text(json.dumps(report, indent=2) + '\n')

files = [
    'tests/unit/proxy/pass_through_endpoints/test_pass_through_endpoints.py',
    'tests/unit/router_strategy/test_lowest_cost.py',
    'tests/unit/router_strategy/test_router_routing_groups.py',
    'tests/unit/router_strategy/test_router_routing_plugins.py',
    'tests/unit/router_utils/test_cooldown_handlers.py',
    'tests/unit/test_router/test_router.py',
    'tests/unit/test_router/test_router_helper_utils.py',
    'tests/unit/types/test_litellm_params.py',
]
regression = {'started_at': datetime.now(timezone.utc).isoformat(), 'files': files}
with (logs / 'litellm-35459-related-tests.log').open('w') as log:
    result = subprocess.run([sys.executable, '-m', 'pytest', '-q', *files], cwd=source, stdout=log, stderr=subprocess.STDOUT)
regression['returncode'] = result.returncode
regression['completed_at'] = datetime.now(timezone.utc).isoformat()
(root / 'backend-regression.json').write_text(json.dumps(regression, indent=2) + '\n')
print(json.dumps(regression), flush=True)
print((logs / 'litellm-35459-related-tests.log').read_text()[-5000:], flush=True)
assert result.returncode == 0

with (logs / 'litellm-35459-format.log').open('w') as log:
    result = subprocess.run(['bash', str(root / 'format.sh')], cwd=source, stdout=log, stderr=subprocess.STDOUT)
(root / 'format.exit').write_text(str(result.returncode) + '\n')
print((logs / 'litellm-35459-format.log').read_text()[-3000:], flush=True)
assert result.returncode == 0
changed = subprocess.check_output(['git', 'diff', '--name-only'], cwd=source, text=True).splitlines()
assert changed == ['litellm/router_strategy/lowest_cost.py', 'tests/unit/router_strategy/test_lowest_cost.py'], changed
subprocess.run(['git', 'diff', '--check'], cwd=source, check=True)
