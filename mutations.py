import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path('/qa/litellm-36095')
source = Path('/opt/litellm-36095')
path = source / 'litellm/types/router.py'
original = path.read_bytes()
text = original.decode()
field = '    weight: float | None = None\n'
assert text.count(field) == 1
changes = (
    ('missing-weight-field', ''),
    ('integer-only-weight', '    weight: int | None = None\n'),
    ('allow-unconverted-strings', '    weight: float | str | None = None\n'),
    ('reject-zero-weight', '    weight: float | None = Field(default=None, gt=0)\n'),
    ('reject-explicit-none-weight', '    weight: float = None\n'),
)
report = {'started_at': datetime.now(timezone.utc).isoformat(), 'mutations': []}
try:
    for name, replacement in changes:
        path.write_text(text.replace(field, replacement))
        result = subprocess.run(
            [sys.executable, '-m', 'pytest', '-q', '--tb=short', 'tests/unit/types/test_router.py',
             '-k', 'numeric_string_routing_params or none_weight or invalid_deployment_weight'],
            cwd=source, capture_output=True, text=True,
        )
        output = result.stdout + result.stderr
        (root.parent / 'logs' / f'litellm-36095-mutation-{name}.log').write_text(output)
        match = re.search(r'(\d+) failed', output)
        report['mutations'].append({'name': name, 'returncode': result.returncode, 'failed_cases': int(match.group(1)) if match else 0})
        assert result.returncode == 1 and match, (name, output)
        print(json.dumps(report['mutations'][-1]), flush=True)
finally:
    path.write_bytes(original)
    report['source_restored_exactly'] = path.read_bytes() == original
    report['restored_sha256'] = hashlib.sha256(original).hexdigest()
    report['completed_at'] = datetime.now(timezone.utc).isoformat()
    (root / 'mutation-report.json').write_text(json.dumps(report, indent=2) + '\n')
