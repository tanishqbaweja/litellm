import json
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path('/qa/litellm-35800')
revision = sys.argv[1]
assert revision in ('baseline', 'fixed')
source = json.loads((root / f'proxy-source-{revision}.json').read_text())
reports = []
for label in ('api-crossed-by-request', 'api-already-crossed', 'api-below-budget', 'api-no-soft-budget', 'desktop', 'phone'):
    command = ['curl', '-sS', '--max-time', '10', 'http://127.0.0.1:41480/messages?alias=qa35800-' + label]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    response = json.loads(result.stdout)
    expected = 1 if label == 'api-already-crossed' or (revision == 'fixed' and label in ('api-crossed-by-request', 'desktop', 'phone')) else 0
    assert response['count'] == expected, label
    reports.append({'case': label, 'command': shlex.join(command), 'response': response})
report = {'revision': revision, 'sha': source['sha'], 'checked_at': datetime.now(timezone.utc).isoformat(), 'requests': reports}
(root / f'receiver-curl-{revision}.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'revision': revision, 'alert_counts': {item['case']: item['response']['count'] for item in reports}}))
