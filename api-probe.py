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
model = 'qa-cost-35459'
expected = json.loads((root / ('runtime.json' if args.revision == 'baseline' else 'product.json')).read_text())['base' if args.revision == 'baseline' else 'head']
report = {'revision': args.revision, 'source_sha': expected, 'started_at': datetime.now(timezone.utc).isoformat(), 'cases': []}


def save():
    (root / f'api-report-{args.revision}.json').write_text(json.dumps(report, indent=2) + '\n')


def rows(kind):
    path = root / f'{kind}-{args.revision}.jsonl'
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


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
    api.get('/health/readiness', timeout=5).raise_for_status()
    source = json.loads((root / f'proxy-source-{args.revision}.json').read_text())
    assert source['sha'] == expected
    assert source['pid'] == int((root / 'proxy.pid').read_text())
    assert Path(f'/proc/{source["pid"]}/cwd').resolve() == Path(source['source'])
    assert b'/qa/litellm-35459/config.yml' in Path(f'/proc/{source["pid"]}/cmdline').read_bytes().split(b'\0')
    model_info = api.get('/model/info')
    model_info.raise_for_status()
    deployment = next(item for item in model_info.json()['data'] if item['model_info']['id'] == model + '-deployment')
    report['model_configuration'] = {'group': deployment['model_name'], 'id': deployment['model_info']['id'], 'provider_model': deployment['litellm_params']['model']}
    with httpx.Client(base_url='http://127.0.0.1:11434', timeout=30) as provider:
        report['provider_version'] = provider.get('/api/version').json()
        report['provider_model'] = next(item for item in provider.get('/api/tags').json()['models'] if item['name'] == 'qa-qwen3.5-0.8b:latest')
    fixture_path = root / f'fixture-{args.revision}.private.json'
    assert not fixture_path.exists(), 'Clean up the previous owned fixture before repeating'
    alias = f'qa-35459-{args.revision}-{uuid.uuid4().hex[:6]}'
    created = api.post('/key/generate', json={'key_alias': alias, 'models': [model]})
    created.raise_for_status()
    key = created.json()['key']
    fixture_path.write_text(json.dumps({'alias': alias, 'key': key, 'token': hashlib.sha256(key.encode()).hexdigest()}, indent=2) + '\n')
    report['alias'] = alias
    headers = {'Authorization': 'Bearer ' + key, 'anthropic-version': '2023-06-01'}
    before_errors = len(rows('callback-errors'))
    before_callbacks = len(rows('callback-metadata'))
    for endpoint in ('/v1/chat/completions', '/v1/responses', '/v1/messages'):
        for streaming in (False, True):
            prompt = 'Reply with only: Routing works. Verification reference ' + uuid.uuid4().hex[:12]
            payload = {'model': model, 'stream': streaming}
            if endpoint == '/v1/responses':
                payload.update({'input': prompt, 'max_output_tokens': 48})
            else:
                payload.update({'messages': [{'role': 'user', 'content': prompt}], 'max_tokens': 48})
            response = api.post(endpoint, headers=headers, json=payload)
            body = response.text if streaming and response.status_code == 200 else response.json()
            item = {'endpoint': endpoint, 'stream': streaming, 'status': response.status_code, 'request_body': payload, 'response_body': body, 'headers': {name: value for name, value in response.headers.items() if name in ('x-litellm-model-id', 'x-litellm-model-name', 'x-litellm-model-api-base', 'x-litellm-call-id')}}
            report['cases'].append(item)
            save()
            response.raise_for_status()
            content = response_text(endpoint, body, streaming)
            assert content.strip()
            assert response.headers.get('x-litellm-model-id') == model + '-deployment', item
            item['generated_content'] = content
            print(json.dumps({'endpoint': endpoint, 'stream': streaming, 'status': response.status_code, 'model_id': response.headers.get('x-litellm-model-id')}), flush=True)
            save()
    for _ in range(100):
        if len(rows('callback-metadata')) >= before_callbacks + 6:
            break
        time.sleep(0.1)
    else:
        raise AssertionError('Successful routed callbacks were not observed')
    time.sleep(0.5)
    report['callbacks'] = rows('callback-metadata')[before_callbacks:]
    report['callback_errors'] = rows('callback-errors')[before_errors:]
    assert report['callback_errors'] == [], report['callback_errors']
    assert all(item['deployment_id'] == model + '-deployment' for item in report['callbacks']), report['callbacks']
    report['completed_at'] = datetime.now(timezone.utc).isoformat()
    save()
    print(json.dumps({'calls': len(report['cases']), 'successes': sum(case['status'] == 200 for case in report['cases']), 'callback_errors': len(report['callback_errors'])}))
