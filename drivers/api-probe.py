import hashlib
import json
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

root = Path('/qa/litellm-35800')
revision = sys.argv[1]
assert revision in ('baseline', 'fixed')
private = json.loads((root / f'live-{revision}.private.json').read_text())
source = json.loads((root / f'proxy-source-{revision}.json').read_text())
base = 'http://127.0.0.1:41479'
receiver = 'http://127.0.0.1:41480'
master = private['master_key']
secrets = {master: '$MASTER_KEY'}
keys = []
report = {'revision': revision, 'sha': source['sha'], 'started_at': datetime.now(timezone.utc).isoformat(),
          'local_real_inference': True, 'hosted_slack_not_tested': True, 'requests': [], 'cases': [], 'poll_curl_requests': 0}


def redact(value):
    if isinstance(value, dict):
        return {key: ('<QA_KEY>' if key in ('key', 'token', 'hashed_key', 'key_id') and isinstance(item, str) else redact(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        result = value
        for secret, replacement in secrets.items():
            result = result.replace(secret, replacement)
        return result
    return value


def request(label, method, path, body=None, key=None, query_key=None, record=True):
    credential = key or master
    command = ['curl', '-sS', '--max-time', '120', '-X', method, base + path,
               '-H', 'Authorization: Bearer ' + credential, '-H', 'Content-Type: application/json']
    if query_key:
        command += ['--get', '--data-urlencode', 'key=' + query_key]
    if body is not None:
        command += ['--data-raw', json.dumps(body)]
    command += ['-w', '\nCURL_HTTP_STATUS:%{http_code}\n']
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, 'curl transport failed'
    text, status = result.stdout.rsplit('\nCURL_HTTP_STATUS:', 1)
    status = int(status.strip())
    value = json.loads(text)
    if path == '/key/generate' and status == 200:
        keys.append(value['key'])
        secrets[value['key']] = '$VIRTUAL_KEY'
        secrets[hashlib.sha256(value['key'].encode()).hexdigest()] = '<QA_KEY_HASH>'
    if record:
        display = shlex.join([redact(argument) for argument in command])
        for variable in ('$MASTER_KEY', '$VIRTUAL_KEY'):
            display = display.replace(shlex.quote('Authorization: Bearer ' + variable), '"Authorization: Bearer ' + variable + '"')
            display = display.replace(shlex.quote('key=' + variable), '"key=' + variable + '"')
        report['requests'].append({'label': label, 'command': display, 'status': status, 'response': redact(value)})
    else:
        report['poll_curl_requests'] += 1
    return status, value


def info(key, *, record=False):
    status, body = request('key-info', 'GET', '/key/info', query_key=key, record=record)
    assert status == 200, status
    value = body['info']
    budget = value.get('litellm_budget_table') or {}
    return {'spend': value['spend'], 'soft_budget': value.get('soft_budget', budget.get('soft_budget')),
            'team_id': value.get('team_id'), 'max_budget': value.get('max_budget')}


try:
    for label, initial, soft, calls in [('crossed-by-request', 0.0, 0.01, 3), ('already-crossed', 1.0, 0.01, 2), ('below-budget', 0.0, 1000.0, 3), ('no-soft-budget', 0.0, None, 2)]:
        alias = 'qa35800-api-' + label
        status, body = request('create-' + label, 'POST', '/key/generate', {'key_alias': alias, 'models': ['qa-alert-model'], 'soft_budget': soft, 'spend': initial})
        assert status == 200, status
        key = body['key']
        case = {'label': label, 'alias': alias, 'before': info(key, record=True), 'calls': []}
        report['cases'].append(case)
        assert case['before']['soft_budget'] == soft and case['before']['team_id'] is None
        for index in range(calls):
            payload = {'model': 'qa-alert-model', 'messages': [{'role': 'user', 'content': f'Say hi. {label} call {index + 1}'}], 'max_tokens': 8, 'cache': {'no-cache': True}}
            status, body = request(f'{label}-chat-{index + 1}', 'POST', '/v1/chat/completions', payload, key=key)
            assert status == 200 and body['usage']['total_tokens'] > 0 and body['choices'], status
            case['calls'].append({'status': status, 'usage': body['usage']})
            if label == 'crossed-by-request' and index == 0:
                deadline = time.monotonic() + 40
                while True:
                    current = info(key)
                    if current['spend'] >= soft:
                        break
                    assert time.monotonic() < deadline, current
                    time.sleep(0.2)
                case['after_first_persisted'] = info(key, record=True)
        case['key'] = key
    time.sleep(16)
    with httpx.Client(timeout=5, trust_env=False) as client:
        for case in report['cases']:
            case['after'] = info(case.pop('key'), record=True)
            response = client.get(receiver + '/messages', params={'alias': case['alias']})
            response.raise_for_status()
            case['alerts'] = response.json()
            expected = 1 if case['label'] == 'already-crossed' or (case['label'] == 'crossed-by-request' and revision == 'fixed') else 0
            assert case['alerts']['count'] == expected, {'case': case['label'], 'observed': case['alerts']['count'], 'expected': expected}
    report['result'] = 'passed'
finally:
    report['cleanup'] = []
    for key in keys:
        status, body = request('delete-owned-key', 'POST', '/key/delete', {'keys': [key]})
        report['cleanup'].append(status)
        assert status == 200, status
    report['completed_at'] = datetime.now(timezone.utc).isoformat()
    (root / f'api-secrets-{revision}.private.json').write_text(json.dumps(list(secrets)) + '\n')
    (root / f'api-report-{revision}.json').write_text(json.dumps(redact(report), indent=2) + '\n')
    print(json.dumps({'revision': revision, 'result': report.get('result'), 'cases': [{k: value for k, value in case.items() if k in ('label', 'before', 'after', 'alerts')} for case in report['cases']], 'cleanup': report['cleanup']}), flush=True)
