import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

revision, case = sys.argv[1:]
root = Path('/qa/litellm-26231')
repo = Path('/opt/litellm-34927-baseline' if revision == 'baseline' else '/opt/litellm-26231')
sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
expected_premium = case in ('plain', 'dotted', 'dotted-unpadded') and (revision == 'fixed' or case == 'plain')
target = 'http://127.0.0.1:41475'
assert set(address[4][0] for address in socket.getaddrinfo('license.litellm.ai', 443)) == {'127.0.0.1'}
for _ in range(90):
    ready = subprocess.run(['curl', '-sS', '--max-time', '2', '--fail', target + '/health/readiness'], capture_output=True)
    if ready.returncode == 0:
        break
    time.sleep(1)
else:
    raise RuntimeError('Proxy did not become ready')
command = ['curl', '-sS', '--max-time', '30', '--fail-with-body', '-H', 'Authorization: Bearer ' + os.environ['LITELLM_MASTER_KEY'], target + '/health/license']
response = subprocess.run(command, capture_output=True, text=True)
assert response.returncode == 0, response.stderr
data = json.loads(response.stdout)
expected = {
    'has_license': True, 'license_type': 'enterprise' if expected_premium else 'community',
    'expiration_date': '2099-12-31' if expected_premium else None,
    'allowed_features': ['*'] if expected_premium else [],
    'limits': {'max_users': 500 if expected_premium else None, 'max_teams': 50 if expected_premium else None},
}
assert data == expected, data
record = {
    'revision': revision, 'source_sha': sha, 'case': case,
    'public_key_sha256': hashlib.sha256((repo / 'litellm/proxy/auth/public_key.pem').read_bytes()).hexdigest(),
    'license_sha256': hashlib.sha256((root / f'license-{case}.txt').read_bytes()).hexdigest(),
    'test_trust_anchor_substituted': True, 'license_server_dns': '127.0.0.1',
    'http_status': 200, 'response': data,
    'command': 'curl --fail-with-body -H "Authorization: Bearer $LITELLM_MASTER_KEY" http://127.0.0.1:41475/health/license',
}
(root / f'api-{revision}-{case}.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
