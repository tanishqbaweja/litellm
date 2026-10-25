import hashlib
import json
import secrets
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import psycopg
from psycopg.rows import dict_row

root = Path('/qa/litellm-42689')
revision = sys.argv[1]
assert revision in ('baseline', 'fixed')
private_path = root / f'live-{revision}.private.json'
private = json.loads(private_path.read_text())
source = json.loads((root / f'proxy-source-{revision}.json').read_text())
base_url = 'http://127.0.0.1:41481'
master = private['master_key']
owned_keys = private.setdefault('owned_keys', {})
secret_values = {master, *owned_keys.values()}
secret_values.update(hashlib.sha256(value.encode()).hexdigest() for value in tuple(secret_values))
mode = 'cleanup' if len(sys.argv) > 2 and sys.argv[2] == 'cleanup' else 'proof'
report = {'revision': revision, 'source_sha': source['sha'], 'started_at': datetime.now(timezone.utc).isoformat(), 'requests': []}


def redact(value):
    if isinstance(value, dict):
        return {
            name: '<QA_KEY>' if name in ('key', 'token', 'hashed_key', 'api_key', 'master_key') and isinstance(item, str) else redact(item)
            for name, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        result = value
        for secret in sorted(secret_values, key=len, reverse=True):
            result = result.replace(secret, '<QA_KEY>')
        return result
    return value


def save():
    (root / f'api-{mode}-{revision}.json').write_text(json.dumps(redact(report), indent=2, default=str) + '\n')
    private_path.write_text(json.dumps(private, indent=2) + '\n')


def curl(name, method, route, key, body=None, expected=200):
    command = [
        'curl', '--silent', '--show-error', '--connect-timeout', '3', '--max-time', '120',
        '--request', method, base_url + route, '--header', 'Authorization: Bearer ' + key,
    ]
    if body is not None:
        command += ['--header', 'Content-Type: application/json', '--data-binary', json.dumps(body, separators=(',', ':'))]
    command += ['--write-out', '\n__HTTP_STATUS__:%{http_code}']
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    raw, status = result.stdout.rsplit('\n__HTTP_STATUS__:', 1)
    data = json.loads(raw)
    if route == '/key/generate' and int(status) == 200:
        secret_values.add(data['key'])
        secret_values.add(key_hash(data['key']))
    record = {'name': name, 'method': method, 'route': route, 'command': shlex.join(command), 'status': int(status), 'response': data}
    report['requests'].append(record)
    save()
    assert int(status) == expected, redact({'name': name, 'status': status, 'response': data})
    return data


def rows(sql, parameters=()):
    with psycopg.connect(private['database_url'], row_factory=dict_row) as db:
        return db.execute(sql, parameters).fetchall()


def eventually(read, predicate, seconds=40):
    deadline = time.monotonic() + seconds
    while True:
        value = read()
        if predicate(value):
            return value
        assert time.monotonic() < deadline, redact(value)
        time.sleep(0.1)


def key_hash(key):
    return hashlib.sha256(key.encode()).hexdigest()


if mode == 'cleanup':
    for alias, key in owned_keys.items():
        curl('delete-' + alias, 'POST', '/key/delete', master, {'keys': [key]})
    remaining = rows('SELECT count(*)::int AS count FROM "LiteLLM_VerificationToken" WHERE token = ANY(%s)', ([key_hash(key) for key in owned_keys.values()],))
    assert remaining == [{'count': 0}], remaining
    report.update(deleted_keys=list(owned_keys), remaining=remaining, completed_at=datetime.now(timezone.utc).isoformat())
    save()
    print(json.dumps({'revision': revision, 'cleanup': True, 'deleted_keys': list(owned_keys)}), flush=True)
    sys.exit(0)

assert not owned_keys, 'Seed each owned database once'
for alias, extra in (
    ('qa42689-valid', {}),
    ('qa42689-expired', {'duration': '1s'}),
    ('qa42689-budget', {'spend': 1.0, 'max_budget': 0.01}),
):
    data = curl('create-' + alias, 'POST', '/key/generate', master, {'key_alias': alias, 'models': ['qa-ledger-model'], **extra})
    owned_keys[alias] = data['key']
    save()

cases = (
    ('models', 'GET', '/v1/models', None),
    ('chat', 'POST', '/v1/chat/completions', {'model': 'qa-ledger-model', 'messages': [{'role': 'user', 'content': 'Reply OK'}], 'max_tokens': 24}),
    ('responses', 'POST', '/v1/responses', {'model': 'qa-ledger-model', 'input': 'Reply OK', 'max_output_tokens': 24}),
    ('messages', 'POST', '/v1/messages', {'model': 'qa-ledger-model', 'messages': [{'role': 'user', 'content': 'Reply OK'}], 'max_tokens': 24}),
)
invalid_keys = []
for prefix, category in (('sk-', 'unknown'), ('wordlist-', 'malformed')):
    for name, method, route, body in cases:
        invalid_key = prefix + secrets.token_hex(16)
        invalid_keys.append(invalid_key)
        secret_values.add(invalid_key)
        secret_values.add(key_hash(invalid_key))
        curl(category + '-' + name, method, route, invalid_key, body, expected=401)
private['invalid_keys'] = invalid_keys
save()

completion = curl('valid-inference', 'POST', '/v1/chat/completions', owned_keys['qa42689-valid'], cases[1][3])
assert completion['usage']['prompt_tokens'] > 0 and completion['usage']['completion_tokens'] > 0
expected_spend = completion['usage']['prompt_tokens'] * 0.001 + completion['usage']['completion_tokens'] * 0.002
curl('expired-models', 'GET', '/v1/models', owned_keys['qa42689-expired'], expected=401)
curl('expired-chat', 'POST', '/v1/chat/completions', owned_keys['qa42689-expired'], cases[1][3], expected=401)
budget = curl('budget-chat', 'POST', '/v1/chat/completions', owned_keys['qa42689-budget'], cases[1][3], expected=422)
assert budget['error']['type'] == 'budget_exceeded'

identities = invalid_keys + [key_hash(key) for key in invalid_keys]
expected_unknown = 8 if revision == 'baseline' else 0


def invalid_counts():
    return rows(
        'SELECT (SELECT count(*)::int FROM "LiteLLM_SpendLogs" WHERE api_key = ANY(%s)) AS spend_logs, '
        '(SELECT count(*)::int FROM "LiteLLM_DailyUserSpend" WHERE api_key = ANY(%s)) AS daily_user, '
        '(SELECT count(*)::int FROM "LiteLLM_DailyTeamSpend" WHERE api_key = ANY(%s)) AS daily_team',
        (identities, identities, identities),
    )[0]


aliases_by_hash = {key_hash(key): alias for alias, key in owned_keys.items()}
known_rows = eventually(
    lambda: rows(
        'SELECT api_key, status, spend, total_tokens, prompt_tokens, completion_tokens, call_type, request_id, model '
        'FROM "LiteLLM_SpendLogs" WHERE api_key = ANY(%s) ORDER BY api_key, call_type',
        (list(aliases_by_hash),),
    ),
    lambda values: len(values) == 4,
)
normalized = [{**row, 'alias': aliases_by_hash[row['api_key']]} for row in known_rows]
assert sorted((row['alias'], row['status']) for row in normalized) == [
    ('qa42689-budget', 'failure'), ('qa42689-expired', 'failure'), ('qa42689-expired', 'failure'), ('qa42689-valid', 'success'),
]
success = next(row for row in normalized if row['status'] == 'success')
assert abs(float(success['spend']) - expected_spend) < 1e-10
assert all(float(row['spend']) == 0 for row in normalized if row['status'] == 'failure')
report['unknown_key_rows'] = eventually(invalid_counts, lambda value: all(n == expected_unknown for n in value.values()))
if revision == 'fixed':
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        assert invalid_counts() == report['unknown_key_rows']
        time.sleep(0.1)
report['recognized_key_rows'] = normalized
report['expected_inference_spend_from_usage'] = expected_spend
report['actual_inference_spend'] = success['spend']
date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
query = urlencode({'start_date': date, 'end_date': date})
curl('user-usage-report', 'GET', '/user/daily/activity/aggregated?' + query, master)
curl('team-usage-report', 'GET', '/team/daily/activity/aggregated?' + query, master)
log_query = urlencode({'start_date': date + ' 00:00:00', 'end_date': date + ' 23:59:59', 'page': 1, 'page_size': 50})
curl('operator-request-logs', 'GET', '/spend/logs/ui?' + log_query, master)
report['completed_at'] = datetime.now(timezone.utc).isoformat()
save()
print(json.dumps({'revision': revision, 'source_sha': source['sha'], 'unknown_key_rows': report['unknown_key_rows'], 'recognized_rows': len(known_rows), 'real_inference_spend': success['spend'], 'requests': len(report['requests'])}), flush=True)
