import json
import os
import sys
from pathlib import Path

import httpx

root = Path(__file__).resolve().parent
revision = sys.argv[1]
assert revision in ('baseline', 'fixed')
fixture = json.loads((root / f'fixture-{revision}.private.json').read_text())
assert fixture['alias'].startswith(f'qa-36095-{revision}-')
with httpx.Client(base_url='http://127.0.0.1:41475', headers={'Authorization': 'Bearer ' + os.environ['LITELLM_MASTER_KEY']}, timeout=30) as api:
    response = api.post('/key/delete', json={'keys': [fixture['key']]})
    report = {'alias': fixture['alias'], 'status': response.status_code}
    (root / f'cleanup-{revision}.json').write_text(json.dumps(report, indent=2) + '\n')
    response.raise_for_status()
    print(json.dumps(report))
