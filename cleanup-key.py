import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx

parser = argparse.ArgumentParser()
parser.add_argument('revision', choices=('baseline', 'fixed'))
args = parser.parse_args()
root = Path(__file__).resolve().parent
path = root / f'fixture-{args.revision}.private.json'
fixture = json.loads(path.read_text())
assert fixture['alias'].startswith(f'qa-cache-34681-{args.revision}-')
with httpx.Client(base_url='http://127.0.0.1:41475', headers={'Authorization': 'Bearer ' + os.environ['LITELLM_MASTER_KEY']}, timeout=30) as api:
    response = api.post('/key/delete', json={'keys': [fixture['key']]})
    response.raise_for_status()
    assert response.status_code == 200
report = {'alias': fixture['alias'], 'delete_status': response.status_code, 'deleted_at': datetime.now(timezone.utc).isoformat()}
(root / f'cleanup-{args.revision}.json').write_text(json.dumps(report, indent=2) + '\n')
path.rename(root / f"fixture-{args.revision}-deleted-{fixture['alias'].rsplit('-', 1)[-1]}.private.json")
print(json.dumps(report))
