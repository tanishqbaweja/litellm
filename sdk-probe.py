import argparse
import asyncio
import hashlib
import json
import logging
import math
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import httpx
import litellm

parser = argparse.ArgumentParser()
parser.add_argument('revision', choices=('baseline', 'fixed'))
args = parser.parse_args()
root = Path(__file__).resolve().parent
source = Path(litellm.__file__).resolve().parent.parent
sha = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
expected_sha = 'dddbaa803d6e9fcc862ea7a5412f771cb1ae040e' if args.revision == 'baseline' else json.loads((root / 'product.json').read_text())['head']
assert sha == expected_sha
assert not subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True).strip()
local = 'http://127.0.0.1:11434'
other = 'http://127.0.0.1:51476/v1'
chat_model = 'qa-qwen3.5-0.8b'
embedding_model = 'qwen3-embedding:0.6b'
report = {'revision': args.revision, 'source_sha': sha, 'source_path': str(source), 'started_at': datetime.now(timezone.utc).isoformat(), 'cases': []}
logging.basicConfig(filename=root / f'sdk-http-{args.revision}.log', level=logging.WARNING, format='%(asctime)s %(name)s %(message)s')
logging.getLogger('httpx').setLevel(logging.INFO)

with httpx.Client(timeout=120) as client:
    version = client.get(local + '/api/version')
    version.raise_for_status()
    report['ollama'] = version.json()
    assert client.get(other + '/models').status_code == 200
    direct = client.post(local + '/api/embed', json={'model': embedding_model, 'input': 'hello', 'options': {'num_ctx': 1024, 'num_thread': 4}})
    direct.raise_for_status()
    direct_vector = direct.json()['embeddings'][0]
    assert direct_vector and all(math.isfinite(value) for value in direct_vector)
    report['direct_embedding'] = {'dimensions': len(direct_vector), 'sha256': hashlib.sha256(json.dumps(direct_vector).encode()).hexdigest(), 'prompt_tokens': direct.json().get('prompt_eval_count')}

async def main():
    for config, explicit, global_base, env_base in (
        ('explicit', local, other, other),
        ('global', None, local, other),
        ('empty-explicit', '', local, other),
        ('environment', None, None, local),
        ('default', None, None, None),
    ):
        litellm.api_base = global_base
        if env_base is None:
            os.environ.pop('OLLAMA_API_BASE', None)
        else:
            os.environ['OLLAMA_API_BASE'] = env_base
        for provider, endpoint in (('ollama', 'generate'), ('ollama_chat', 'chat'), ('ollama', 'embed')):
            for asynchronous in (False, True):
                item = {'configuration': config, 'provider': provider, 'endpoint': endpoint, 'asynchronous': asynchronous, 'explicit_base': explicit, 'global_base': global_base, 'env_base': env_base}
                expected_failure = args.revision == 'baseline' and config == 'explicit'
                try:
                    model = embedding_model if endpoint == 'embed' else chat_model
                    params = {'model': f'{provider}/{model}', 'api_base': explicit, 'num_retries': 0}
                    if endpoint == 'embed':
                        response = await litellm.aembedding(**params, input='hello') if asynchronous else litellm.embedding(**params, input='hello')
                        vector = response.data[0]['embedding']
                        assert len(vector) == len(direct_vector)
                        difference = max(abs(a-b) for a,b in zip(vector, direct_vector, strict=True))
                        assert difference < 1e-6, difference
                        item.update({'dimensions': len(vector), 'maximum_absolute_difference_from_direct': difference, 'usage': response.usage.model_dump()})
                    else:
                        generation = {'messages': [{'role': 'user', 'content': 'Reply with only: Routing works.'}], 'max_tokens': 48, 'num_ctx': 1024, 'num_thread': 4, 'temperature': 0, 'reasoning_effort': 'none'}
                        response = await litellm.acompletion(**params, **generation) if asynchronous else litellm.completion(**params, **generation)
                        content = response.choices[0].message.content
                        assert content and content.strip(), response.model_dump()
                        assert response.usage.prompt_tokens > 0 and response.usage.completion_tokens > 0
                        item.update({'content': content, 'usage': response.usage.model_dump(), 'finish_reason': response.choices[0].finish_reason})
                    item['outcome'] = 'success'
                    assert not expected_failure, 'Baseline unexpectedly succeeded'
                except Exception as error:
                    item.update({'outcome': 'error', 'exception': type(error).__name__, 'message': str(error), 'status_code': getattr(error, 'status_code', None)})
                    if not expected_failure:
                        report['cases'].append(item)
                        (root / f'sdk-report-{args.revision}.json').write_text(json.dumps(report, indent=2) + '\n')
                        raise
                    assert getattr(error, 'status_code', None) == 404, str(error)
                report['cases'].append(item)
                (root / f'sdk-report-{args.revision}.json').write_text(json.dumps(report, indent=2) + '\n')
                print(json.dumps({key: item[key] for key in ('configuration', 'endpoint', 'asynchronous', 'outcome')}), flush=True)

asyncio.run(main())
assert len(report['cases']) == 30
assert sum(c['outcome'] == 'error' for c in report['cases']) == (6 if args.revision == 'baseline' else 0)
report['completed_at'] = datetime.now(timezone.utc).isoformat()
(root / f'sdk-report-{args.revision}.json').write_text(json.dumps(report, indent=2) + '\n')
