import json
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path('/qa/litellm-38759')
revision = sys.argv[1]
assert revision in ('baseline', 'fixed')
private = json.loads((root / f'live-{revision}.private.json').read_text())
source = json.loads((root / f'proxy-source-{revision}.json').read_text())
expected = json.loads((root / ('runtime.json' if revision == 'baseline' else 'product.json')).read_text())['base' if revision == 'baseline' else 'head']
assert source['sha'] == expected and Path(f'/proc/{source["pid"]}/cwd').resolve() == Path(source['source'])
base_url = 'http://127.0.0.1:41478'
budget_id = 'qa38759-api'
report = {
    'revision': revision, 'source_sha': source['sha'], 'started_at': datetime.now(timezone.utc).isoformat(),
    'enterprise_entitlement_override': False, 'provider_requests_performed': False, 'requests': [],
}

def request(label, path, body):
    arguments = [
        'curl', '--silent', '--show-error', '--max-time', '30', '-X', 'POST', base_url + path,
        '-H', 'Authorization: Bearer ' + private['master_key'], '-H', 'Content-Type: application/json',
        '--data-raw', json.dumps(body), '--write-out', '\nHTTP %{http_code}\n',
    ]
    result = subprocess.run(arguments, capture_output=True, text=True, check=True)
    response_text, status_text = result.stdout.rsplit('\nHTTP ', 1)
    status, parsed = int(status_text.strip()), json.loads(response_text)
    display = 'curl -sS -X POST ' + shlex.quote(base_url + path) + ' -H "Authorization: Bearer $MASTER_KEY" -H \'Content-Type: application/json\' --data-raw ' + shlex.quote(json.dumps(body)) + ' -w \'\\nHTTP %{http_code}\\n\''
    entry = {'label': label, 'path': path, 'method': 'POST', 'body': body, 'command': display, 'status': status, 'response': parsed, 'stdout': result.stdout, 'stderr': result.stderr}
    report['requests'].append(entry)
    (root / f'api-report-{revision}.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'revision': revision, 'step': label, 'status': status}), flush=True)
    return status, parsed

def info(label):
    status, rows = request(label, '/budget/info', {'budgets': [budget_id]})
    assert status == 200 and len(rows) == 1, rows
    return rows[0]

def stable(value):
    return {name: field for name, field in value.items() if name != 'updated_at'}

created = False
try:
    status, row = request('create', '/budget/new', {'budget_id': budget_id, 'max_budget': 20, 'soft_budget': 5, 'tpm_limit': 1000, 'rpm_limit': 60, 'budget_duration': '30d', 'model_max_budget': {}})
    assert status == 200 and row['model_max_budget'] == {}, row
    created = True
    before = info('read-before')
    null_status, null_response = request('explicit-null', '/budget/update', {'budget_id': budget_id, 'model_max_budget': None})
    assert null_status == (500 if revision == 'baseline' else 200), null_response
    after_null = info('read-after-null')
    assert stable(after_null) == stable(before), after_null
    if revision == 'baseline':
        assert after_null == before
    else:
        assert null_response == after_null
    status, repeated = request('repeat-null', '/budget/update', {'budget_id': budget_id, 'model_max_budget': None})
    assert status == null_status, repeated
    status, empty = request('empty-object-control', '/budget/update', {'budget_id': budget_id, 'model_max_budget': {}})
    assert status == 200 and stable(empty) == stable(before), empty
    status, omitted = request('omitted-control', '/budget/update', {'budget_id': budget_id, 'max_budget': 25})
    assert status == 200 and stable(omitted) == {**stable(before), 'max_budget': 25}, omitted
    status, scalar = request('scalar-null-control', '/budget/update', {'budget_id': budget_id, 'soft_budget': None})
    assert status == 200 and stable(scalar) == {**stable(omitted), 'soft_budget': None}, scalar
    status, malformed = request('malformed-control', '/budget/update', {'budget_id': budget_id, 'model_max_budget': {'qa-budget-a': {'max_budget': 'lots'}}})
    assert status == 422 and malformed['detail'][0]['loc'] == ['body', 'model_max_budget', 'qa-budget-a', 'max_budget'], malformed
    status, scalar_entry = request('legacy-scalar-control', '/budget/update', {'budget_id': budget_id, 'model_max_budget': {'qa-budget-a': 5}})
    assert status == 422, scalar_entry
    status, gated = request('license-gate-control', '/budget/update', {'budget_id': budget_id, 'model_max_budget': {'qa-budget-a': {'max_budget': 1}}})
    assert status == 400 and 'enterprise license' in str(gated), gated
    after_rejections = info('read-after-rejections')
    assert after_rejections == scalar, after_rejections
    report['result'] = 'pass'
    report['null_status'] = null_status
finally:
    if created:
        status, deleted = request('cleanup-budget', '/budget/delete', {'id': budget_id})
        report['budget_deleted'] = status == 200
    report['completed_at'] = datetime.now(timezone.utc).isoformat()
    (root / f'api-report-{revision}.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'revision': revision, 'result': report.get('result'), 'requests': len(report['requests']), 'null_status': report.get('null_status'), 'budget_deleted': report.get('budget_deleted')}), flush=True)
