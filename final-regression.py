import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path('/qa/litellm-35459')
source = Path('/opt/litellm-35459')
initial = json.loads((root / 'backend-regression.json').read_text())
report = {'started_at': datetime.now(timezone.utc).isoformat(), 'files': initial['files']}
with (root.parent / 'logs' / 'litellm-35459-related-tests-final.log').open('w') as log:
    result = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-ra', *report['files']], cwd=source, stdout=log, stderr=subprocess.STDOUT)
report['returncode'] = result.returncode
report['completed_at'] = datetime.now(timezone.utc).isoformat()
(root / 'backend-regression-final.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report), flush=True)
print((root.parent / 'logs' / 'litellm-35459-related-tests-final.log').read_text()[-6000:], flush=True)
raise SystemExit(result.returncode)
