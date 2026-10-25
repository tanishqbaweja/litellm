import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path('/qa/litellm-38759')
repo = Path('/opt/litellm-38759')
target = repo / 'litellm/proxy/management_endpoints/budget_management_endpoints.py'
original = target.read_bytes()
text = original.decode()
expression = 'field: {} if field == "model_max_budget" and value is None else value'
patch = 'budget_patch: Final[Mapping[str, object]] = budget_obj.model_dump(exclude_unset=True)'
mutations = [
    ('leave-null-unserialized', expression, 'field: value'),
    ('clear-nonempty-model-limits', expression, 'field: {} if field == "model_max_budget" else value'),
    ('convert-scalar-nulls-to-objects', expression, 'field: {} if value is None else value'),
    ('drop-explicit-nulls', patch, 'budget_patch: Final[Mapping[str, object]] = budget_obj.model_dump(exclude_none=True)'),
    ('overwrite-omitted-fields', patch, 'budget_patch: Final[Mapping[str, object]] = budget_obj.model_dump(exclude_unset=False)'),
]
command = [
    sys.executable, '-m', 'pytest', '-q', '--tb=short',
    'tests/unit/proxy/management_endpoints/test_budget_endpoints.py', '-k',
    'preserves_omitted_model_budgets_and_clears_explicit_empty_values or serializes_model_max_budget_for_prisma',
]
env = {**os.environ, 'PYTHONPATH': str(repo), 'LITELLM_LOCAL_MODEL_COST_MAP': 'True', 'PYTHON_DOTENV_DISABLED': '1'}
report = {'started_at': datetime.now(timezone.utc).isoformat(), 'source_sha256': hashlib.sha256(original).hexdigest(), 'command': command, 'mutations': []}
if '--resume' in sys.argv:
    report = json.loads((root / 'mutation-report.json').read_text())
    assert report['source_sha256'] == hashlib.sha256(original).hexdigest() and report['exactly_restored']
    incomplete_log = root / 'mutation-overwrite-omitted-fields.log'
    archived_log = root / 'initial-summary-parser-mutation-overwrite-omitted-fields.log'
    assert not archived_log.exists()
    archived_log.write_bytes(incomplete_log.read_bytes())
try:
    for name, old, new in mutations:
        if any(entry['name'] == name for entry in report['mutations']):
            continue
        assert text.count(old) == 1, name
        target.write_text(text.replace(old, new))
        with (root / f'mutation-{name}.log').open('w') as log:
            result = subprocess.run(command, cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT)
        output = (root / f'mutation-{name}.log').read_text()
        failed = re.search(r'(\d+) failed', output)
        passed = re.search(r'(\d+) passed', output)
        assert result.returncode == 1 and failed and 'ERROR collecting' not in output, name
        entry = {'name': name, 'old': old, 'new': new, 'returncode': result.returncode, 'failures': int(failed.group(1)), 'controls_passed': int(passed.group(1)) if passed else 0, 'killed': True}
        assert entry['failures'] + entry['controls_passed'] == 4
        report['mutations'].append(entry)
        target.write_bytes(original)
        assert target.read_bytes() == original
        (root / 'mutation-report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(entry), flush=True)
finally:
    target.write_bytes(original)
    report['restored_source_sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
    report['exactly_restored'] = target.read_bytes() == original
    report['completed_at'] = datetime.now(timezone.utc).isoformat()
    (root / 'mutation-report.json').write_text(json.dumps(report, indent=2) + '\n')
assert len(report['mutations']) == len(mutations) and report['exactly_restored']
subprocess.run([sys.executable, str(root / 'run-unit.py'), 'post-mutations'], check=True)
