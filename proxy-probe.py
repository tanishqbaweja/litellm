import argparse
import collections
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
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
report = {'revision': args.revision, 'source_sha': expected, 'started_at': datetime.now(timezone.utc).isoformat(), 'cases': []}


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
    fixture_path = root / f'fixture-{args.revision}.private.json'
    assert not fixture_path.exists(), 'Clean up the previous owned fixture before repeating this run'
    alias = f'qa-cache-34681-{args.revision}-{uuid.uuid4().hex[:6]}'
    created = api.post('/key/generate', json={'key_alias': alias, 'models': ['qa-cache-34681']})
    created.raise_for_status()
    key = created.json()['key']
    token = hashlib.sha256(key.encode()).hexdigest()
    fixture_path.write_text(json.dumps({'alias': alias, 'key': key, 'token': token}, indent=2) + '\n')
    report['alias'] = alias
    headers = {'Authorization': 'Bearer ' + key, 'anthropic-version': '2023-06-01'}
    for endpoint in ('/v1/chat/completions', '/v1/responses', '/v1/messages'):
        for streaming in (False, True):
            prompt = 'Reply with only: Cache works. Verification reference ' + uuid.uuid4().hex[:12]
            payload = {'model': 'qa-cache-34681', 'stream': streaming}
            if endpoint == '/v1/responses':
                payload.update({'input': prompt, 'max_output_tokens': 48})
            else:
                payload.update({'messages': [{'role': 'user', 'content': prompt}], 'max_tokens': 48})
            contents = []
            for repeat in range(2):
                response = api.post(endpoint, headers=headers, json=payload)
                body = response.text if streaming and response.status_code == 200 else response.json()
                item = {'endpoint': endpoint, 'stream': streaming, 'repeat': repeat, 'status': response.status_code, 'request_body': payload, 'response_body': body, 'headers': {name: value for name, value in response.headers.items() if name in ('x-litellm-cache-key', 'x-litellm-call-id', 'x-litellm-response-cost')}}
                report['cases'].append(item)
                (root / f'api-report-{args.revision}.json').write_text(json.dumps(report, indent=2) + '\n')
                response.raise_for_status()
                content = response_text(endpoint, body, streaming)
                assert content.strip()
                contents.append(content)
                item['generated_content'] = content
                print(json.dumps({'endpoint': endpoint, 'stream': streaming, 'repeat': repeat, 'status': response.status_code, 'content': content}), flush=True)
            assert contents[0] == contents[1]
    now = datetime.now(timezone.utc)
    params = {'api_key': token, 'start_date': (now - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S'), 'end_date': (now + timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S'), 'page_size': 100}
    for _ in range(45):
        response = api.get('/spend/logs/v2', params=params)
        response.raise_for_status()
        body = response.json()
        rows = body if isinstance(body, list) else body['data']
        if len(rows) >= len(report['cases']):
            break
        time.sleep(1)
    else:
        raise RuntimeError(f'Only {len(rows)} spend rows arrived for {len(report["cases"])} calls')
    fields = ('request_id', 'call_type', 'cache_hit', 'cache_key', 'model', 'prompt_tokens', 'completion_tokens')
    report['spend_rows'] = [{field: row.get(field) for field in fields} for row in rows]
    report['cache_hits'] = sum(str(row.get('cache_hit')).lower() == 'true' for row in rows)
    report['explicit_cache_misses'] = sum(str(row.get('cache_hit')).lower() == 'false' for row in rows)
    report['unspecified_cache_status'] = sum(str(row.get('cache_hit')).lower() == 'none' for row in rows)
    report['cache_status_counts'] = dict(collections.Counter(str(row.get('cache_hit')) for row in rows))
    (root / f'api-report-{args.revision}.json').write_text(json.dumps(report, indent=2) + '\n')
    assert len(rows) == 12 and report['cache_hits'] == 6, report['spend_rows']
    assert report['explicit_cache_misses'] + report['unspecified_cache_status'] == 6, report['spend_rows']
    assert collections.Counter(row['call_type'] for row in rows if str(row.get('cache_hit')).lower() == 'true') == {'acompletion': 2, 'aresponses': 2, 'anthropic_messages': 2}
    report['completed_at'] = datetime.now(timezone.utc).isoformat()
    (root / f'api-report-{args.revision}.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'calls': len(report['cases']), 'cache_status_counts': report['cache_status_counts']}), flush=True)
