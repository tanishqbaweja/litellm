import argparse
import json
import math
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
product = json.loads((root / 'product.json').read_text())
report = {'revision': args.revision, 'source_sha': product['base'] if args.revision == 'baseline' else product['head'], 'started_at': datetime.now(timezone.utc).isoformat(), 'cases': []}
alias = f'qa-ollama-26170-{args.revision}-{uuid.uuid4().hex[:6]}'
models = ['qa-ollama-chat-26170', 'qa-ollama-generate-26170', 'qa-ollama-embed-26170']


def response_text(endpoint, body, streaming):
    if not streaming:
        if endpoint == '/v1/chat/completions': return body['choices'][0]['message']['content']
        if endpoint == '/v1/responses': return ''.join(c.get('text', '') for output in body['output'] for c in output.get('content', []))
        return ''.join(c.get('text', '') for c in body['content'])
    events = [json.loads(line[6:]) for line in body.splitlines() if line.startswith('data: ') and line[6:] != '[DONE]']
    assert events and all(not event.get('error') for event in events)
    if endpoint == '/v1/chat/completions': return ''.join(event.get('choices', [{}])[0].get('delta', {}).get('content') or '' for event in events if event.get('choices'))
    if endpoint == '/v1/responses': return ''.join(event['delta'] for event in events if event.get('type') == 'response.output_text.delta')
    return ''.join(event.get('delta', {}).get('text', '') for event in events)


with httpx.Client(base_url='http://127.0.0.1:41475', headers={'Authorization': 'Bearer ' + os.environ['LITELLM_MASTER_KEY']}, timeout=120) as api:
    for attempt in range(45):
        try:
            if api.get('/health/readiness', timeout=2).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(1)
    else:
        raise RuntimeError('Proxy did not become ready')
    assert not (root / f'fixture-{args.revision}.private.json').exists(), 'Clean up the previous owned fixture before repeating this run'
    key_response = api.post('/key/generate', json={'key_alias': alias, 'models': models})
    key_response.raise_for_status()
    key = key_response.json()['key']
    (root / f'fixture-{args.revision}.private.json').write_text(json.dumps({'alias': alias, 'key': key, 'models': models}, indent=2) + '\n')
    report['alias'] = alias
    headers = {'Authorization': 'Bearer ' + key, 'anthropic-version': '2023-06-01'}
    for model in models[:2]:
        for endpoint in ('/v1/chat/completions', '/v1/responses', '/v1/messages'):
            for streaming in (False, True):
                payload = {'model': model, 'stream': streaming}
                if endpoint == '/v1/responses':
                    payload.update({'input': 'Reply with only: Routing works.', 'max_output_tokens': 48})
                else:
                    payload.update({'messages': [{'role': 'user', 'content': 'Reply with only: Routing works.'}], 'max_tokens': 48})
                response = api.post(endpoint, headers=headers, json=payload)
                body = response.text if streaming and response.status_code == 200 else response.json()
                item = {'model': model, 'endpoint': endpoint, 'stream': streaming, 'status': response.status_code, 'request_body': payload, 'response_body': body, 'headers': {name: value for name, value in response.headers.items() if name in ('x-litellm-model-api-base', 'x-litellm-call-id', 'x-litellm-response-cost')}}
                report['cases'].append(item)
                (root / f'api-report-{args.revision}.json').write_text(json.dumps(report, indent=2) + '\n')
                print(json.dumps({name: item[name] for name in ('model', 'endpoint', 'stream', 'status')}), flush=True)
                if args.revision == 'fixed':
                    response.raise_for_status()
                    content = response_text(endpoint, body, streaming)
                    assert content and content.strip(), item
                    item['generated_content'] = content
    response = api.post('/v1/embeddings', headers=headers, json={'model': models[2], 'input': 'hello'})
    body = response.json()
    item = {'model': models[2], 'endpoint': '/v1/embeddings', 'stream': False, 'status': response.status_code, 'request_body': {'model': models[2], 'input': 'hello'}, 'response_body': body}
    report['cases'].append(item)
    (root / f'api-report-{args.revision}.json').write_text(json.dumps(report, indent=2) + '\n')
    if args.revision == 'fixed':
        response.raise_for_status()
        vector = body['data'][0]['embedding']
        direct = json.loads((root / 'direct-embed.json').read_text())['body']['embeddings'][0]
        assert len(vector) == len(direct) and all(math.isfinite(value) for value in vector)
        difference = max(abs(a - b) for a,b in zip(vector, direct, strict=True))
        assert difference < 1e-6, difference
        item['dimensions'] = len(vector)
        item['maximum_absolute_difference_from_direct'] = difference
    report['completed_at'] = datetime.now(timezone.utc).isoformat()
    (root / f'api-report-{args.revision}.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'alias': alias, 'cases': len(report['cases']), 'statuses': [c['status'] for c in report['cases']]}), flush=True)
