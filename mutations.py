import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path('/qa/litellm-34681')
source = Path('/opt/litellm-34681')
path = source / 'litellm/caching/dual_cache.py'
original = path.read_bytes()
text = original.decode()
guard = 'if key not in self and len(self) >= self.max_size:'
assert text.count(guard) == 1
changes = (
    ('evict-on-refresh', guard, 'if len(self) >= self.max_size:'),
    ('never-evict-new-keys', guard, 'if False:'),
    ('evict-newest', 'self.popitem(last=False)', 'self.popitem(last=True)'),
    ('allow-one-entry-over-capacity', guard, 'if key not in self and len(self) > self.max_size:'),
    ('do-not-refresh-existing-timestamps', '    def __setitem__(self, key, value):\n', '    def __setitem__(self, key, value):\n        if key in self:\n            return\n'),
)
report = {'started_at': datetime.now(timezone.utc).isoformat(), 'mutations': []}
try:
    for name, old, new in changes:
        assert text.count(old) == 1
        path.write_text(text.replace(old, new))
        result = subprocess.run([sys.executable, '-m', 'pytest', '-q', '--tb=short', 'tests/unit/caching/test_dual_cache.py', '-k', 'refreshing_a_full_batch_throttle'], cwd=source, capture_output=True, text=True)
        output = result.stdout + result.stderr
        (root.parent / 'logs' / f'litellm-34681-mutation-{name}.log').write_text(output)
        match = re.search(r'(\d+) failed', output)
        report['mutations'].append({'name': name, 'returncode': result.returncode, 'failed_cases': int(match.group(1)) if match else 0})
        assert result.returncode == 1 and match, (name, output)
        print(json.dumps(report['mutations'][-1]), flush=True)
finally:
    path.write_bytes(original)
    report['source_restored_exactly'] = path.read_bytes() == original
    report['restored_sha256'] = hashlib.sha256(original).hexdigest()
    (root / 'mutation-report.json').write_text(json.dumps(report, indent=2) + '\n')
