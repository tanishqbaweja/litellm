import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx


root = Path(__file__).resolve().parent
revision = sys.argv[1]
private_path = root / f'fixture-{revision}.private.json'
output = root / f'api-{revision}'
output.mkdir(exist_ok=True)
source_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
base_url = 'http://127.0.0.1:41475'
master = os.environ['LITELLM_MASTER_KEY']

with httpx.Client(base_url=base_url, headers={'Authorization': 'Bearer ' + master}, timeout=30) as api:
    for port, path in ((41475, '/health/readiness'), (51477, '/health'), (51478, '/health')):
        for _ in range(40):
            try:
                ready = api.get(f'http://127.0.0.1:{port}{path}')
                if ready.status_code == 200:
                    break
            except httpx.ConnectError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError(f'Service on port {port} did not become ready')

    assert not private_path.exists(), 'Use a fresh revision label or clean up its owned fixture first'
    alias = 'qa-vllm-33210-' + revision + '-' + uuid4().hex[:6]
    created = api.post('/key/generate', json={'key_alias': alias, 'models': ['qa-33210-embedding', 'qa-33210-ranking', 'qa-33210-regular-embedding']})
    created.raise_for_status()
    key = created.json()['key']
    token = hashlib.sha256(key.encode()).hexdigest()
    private_path.write_text(json.dumps({'alias': alias, 'key': key, 'token': token}, indent=2) + '\n')
    cases = (
        ('pooling', '/vllm/pooling', {'model': 'qa-33210-embedding', 'input': ['Hello world.'], 'task': 'embed'}),
        ('score', '/vllm/score', {'model': 'qa-33210-ranking', 'text_1': 'What color is the sky?', 'text_2': ['The sky is blue.', 'Pizza is a food.']}),
        ('rerank', '/vllm/rerank', {'model': 'qa-33210-ranking', 'query': 'What color is the sky?', 'documents': ['The sky is blue.', 'Pizza is a food.'], 'top_n': 2}),
        ('classify', '/vllm/classify', {'model': 'qa-33210-ranking', 'input': ['The sky is blue.', 'Pizza is a food.']}),
        ('relay-embeddings-control', '/vllm/v1/embeddings', {'model': 'qa-33210-embedding', 'input': ['The relay embedding control.']}),
        ('regular-embeddings-control', '/v1/embeddings', {'model': 'qa-33210-regular-embedding', 'input': ['The regular embedding control.']}),
    )
    results = []
    for name, path, body in cases:
        request_path = output / (name + '-request.json')
        response_path = output / (name + '-response.json')
        headers_path = output / (name + '-headers.txt')
        request_path.write_text(json.dumps(body, indent=2) + '\n')
        command = ['curl', '--silent', '--show-error', '--max-time', '45', '--config', '-', '--request', 'POST',
                   '--header', 'Content-Type: application/json', '--data-binary', '@' + str(request_path),
                   '--dump-header', str(headers_path), '--output', str(response_path), '--write-out', '%{http_code}', base_url + path]
        request = subprocess.run(command, input='header = "Authorization: Bearer ' + key + '"\n', text=True, capture_output=True, check=True)
        status = int(request.stdout)
        response = json.loads(response_path.read_text())
        response_headers = dict(line.split(': ', 1) for line in headers_path.read_text().splitlines() if ': ' in line)
        selected_headers = {name: value for name, value in response_headers.items() if name.lower() in {'x-litellm-call-id', 'x-litellm-model-id', 'x-litellm-response-cost', 'x-request-id'}}
        result = {'case': name, 'endpoint': path, 'http_status': status, 'response_id': response.get('id'),
                  'response_model': response.get('model'), 'usage': response.get('usage'),
                  'response_keys': list(response), 'headers': selected_headers}
        results.append(result)
        print(json.dumps(result), flush=True)
        assert status == 200, response
        assert response.get('data') or response.get('results'), response

    now = datetime.now(timezone.utc)
    params = {'api_key': token, 'start_date': (now - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S'),
              'end_date': (now + timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S'), 'page_size': 50}
    deadline = time.monotonic() + 20
    while True:
        response = api.get('/spend/logs/v2', params=params)
        response.raise_for_status()
        data = response.json()
        rows = data if isinstance(data, list) else data['data']
        if len(rows) >= len(cases) or time.monotonic() >= deadline:
            break
        time.sleep(1)
    fields = ('request_id', 'call_type', 'model', 'prompt_tokens', 'completion_tokens', 'total_tokens', 'spend', 'status', 'api_base')
    selected_rows = [{field: row.get(field) for field in fields} for row in rows]
    metrics = api.get('/metrics/')
    selected_metrics = [line for line in metrics.text.splitlines() if 'qa-33210-' in line]
    report = {'revision': revision, 'source_sha': source_sha, 'alias': alias, 'cases': results,
              'spend_rows': selected_rows, 'metrics_status': metrics.status_code, 'metrics': selected_metrics,
              'observed_at': datetime.now(timezone.utc).isoformat()}
    (root / f'api-report-{revision}.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'revision': revision, 'source_sha': source_sha, 'alias': alias,
                      'successful_requests': len(results), 'spend_rows': selected_rows,
                      'metrics_status': metrics.status_code, 'metric_lines': len(selected_metrics)}, indent=2), flush=True)
