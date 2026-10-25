import argparse
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

parser = argparse.ArgumentParser()
parser.add_argument('revision', choices=('baseline', 'fixed'))
args = parser.parse_args()
root = Path(__file__).resolve().parent
source_path = root / f'proxy-source-{args.revision}.json'
for _ in range(60):
    if source_path.exists():
        break
    time.sleep(1)
else:
    raise RuntimeError('Proxy did not write its source verification')
source = json.loads(source_path.read_text())
expected = json.loads((root / ('runtime.json' if args.revision == 'baseline' else 'product.json')).read_text())['base' if args.revision == 'baseline' else 'head']
assert source['sha'] == expected
cases = json.loads((root / 'cases.json').read_text())
report = {'revision': args.revision, 'source_sha': expected, 'started_at': datetime.now(timezone.utc).isoformat(), 'model_configuration': [], 'cases': []}


def save():
    (root / f'api-report-{args.revision}.json').write_text(json.dumps(report, indent=2) + '\n')


def response_text(endpoint, body, streaming):
    if not streaming:
        if endpoint == '/v1/chat/completions':
            return body['choices'][0]['message']['content']
        if endpoint == '/v1/responses':
            return ''.join(c.get('text', '') for item in body['output'] for c in item.get('content', []))
        return ''.join(c.get('text', '') for c in body['content'])
    events = [json.loads(line[6:]) for line in body.splitlines() if line.startswith('data: ') and line[6:] != '[DONE]']
    assert events and all(not event.get('error') for event in events)
    if endpoint == '/v1/chat/completions':
        return ''.join(event.get('choices', [{}])[0].get('delta', {}).get('content') or '' for event in events if event.get('choices'))
    if endpoint == '/v1/responses':
        return ''.join(event['delta'] for event in events if event.get('type') == 'response.output_text.delta')
    return ''.join(event.get('delta', {}).get('text', '') for event in events)


with httpx.Client(base_url='http://127.0.0.1:41475', headers={'Authorization': 'Bearer ' + os.environ['LITELLM_MASTER_KEY']}, timeout=120) as api:
    for _ in range(60):
        try:
            if api.get('/health/readiness', timeout=2).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(1)
    else:
        raise RuntimeError('Proxy did not become ready')
    source = json.loads(source_path.read_text())
    assert source['sha'] == expected
    assert source['pid'] == int((root / 'proxy.pid').read_text())
    assert Path(f'/proc/{source["pid"]}/cwd').resolve() == Path(source['source'])
    assert b'/qa/litellm-36095/config.yml' in Path(f'/proc/{source["pid"]}/cmdline').read_bytes().split(b'\0')
    with httpx.Client(base_url='http://127.0.0.1:11434', timeout=30) as provider:
        report['provider_version'] = provider.get('/api/version').json()
        model = next(m for m in provider.get('/api/tags').json()['models'] if m['name'] == 'qa-qwen3.5-0.8b:latest')
        report['provider_model'] = model
    model_info = api.get('/model/info')
    model_info.raise_for_status()
    models = model_info.json()['data']
    for case in cases:
        for position, suffix in enumerate(('-preferred', '-zero')):
            model = next(m for m in models if m['model_info']['id'] == case['name'] + suffix)
            params = model['litellm_params']
            value = params.get(case['metric'])
            report['model_configuration'].append({'group': case['name'], 'id': model['model_info']['id'], 'metric': case['metric'], 'value': value, 'value_type': type(value).__name__, 'weight': params.get('weight')})
            if args.revision == 'baseline' and case['fails_on_main']:
                assert isinstance(value, str) and float(value) == case['normalized'][position]
            else:
                assert isinstance(value, (int, float)) and value == case['normalized'][position]
    save()
    fixture_path = root / f'fixture-{args.revision}.private.json'
    assert not fixture_path.exists(), 'Clean up and archive any previous owned fixture before repeating this run'
    alias = f'qa-36095-{args.revision}-{uuid.uuid4().hex[:6]}'
    created = api.post('/key/generate', json={'key_alias': alias, 'models': [case['name'] for case in cases]})
    created.raise_for_status()
    key = created.json()['key']
    token = hashlib.sha256(key.encode()).hexdigest()
    fixture_path.write_text(json.dumps({'alias': alias, 'key': key, 'token': token}, indent=2) + '\n')
    report['alias'] = alias
    headers = {'Authorization': 'Bearer ' + key, 'anthropic-version': '2023-06-01'}
    for endpoint in ('/v1/chat/completions', '/v1/responses', '/v1/messages'):
        for streaming in (False, True):
            for case in cases:
                prompt = 'Reply with only: Weights work. Verification reference ' + uuid.uuid4().hex[:12]
                payload = {'model': case['name'], 'stream': streaming}
                if endpoint == '/v1/responses':
                    payload.update({'input': prompt, 'max_output_tokens': 48})
                else:
                    payload.update({'messages': [{'role': 'user', 'content': prompt}], 'max_tokens': 48})
                response = api.post(endpoint, headers=headers, json=payload)
                body = response.text if streaming and response.status_code == 200 else response.json()
                item = {'group': case['name'], 'endpoint': endpoint, 'stream': streaming, 'status': response.status_code, 'request_body': payload, 'response_body': body, 'headers': {name: value for name, value in response.headers.items() if name in ('x-litellm-model-id', 'x-litellm-model-name', 'x-litellm-model-api-base', 'x-litellm-call-id')}}
                report['cases'].append(item)
                save()
                if args.revision == 'baseline' and case['fails_on_main']:
                    assert response.status_code == 500
                    assert 'Deployment weight must be numeric' in json.dumps(body)
                    item['result'] = 'reported bug reproduced'
                else:
                    response.raise_for_status()
                    content = response_text(endpoint, body, streaming)
                    assert content.strip()
                    assert response.headers.get('x-litellm-model-id') == case['name'] + '-preferred', item
                    item['generated_content'] = content
                    item['result'] = 'preferred deployment selected'
                print(json.dumps({'group': case['name'], 'endpoint': endpoint, 'stream': streaming, 'status': response.status_code, 'model_id': response.headers.get('x-litellm-model-id')}), flush=True)
                save()
    report['successes'] = sum(item['status'] == 200 for item in report['cases'])
    report['expected_failures'] = sum(item['status'] == 500 for item in report['cases'])
    assert len(report['cases']) == 36
    assert (report['successes'], report['expected_failures']) == ((24, 12) if args.revision == 'baseline' else (36, 0))
    with httpx.Client(base_url='http://127.0.0.1:11434', timeout=30) as provider:
        report['provider_loaded_models'] = provider.get('/api/ps').json()
    report['completed_at'] = datetime.now(timezone.utc).isoformat()
    save()
    print(json.dumps({'calls': len(report['cases']), 'successes': report['successes'], 'expected_failures': report['expected_failures']}), flush=True)
