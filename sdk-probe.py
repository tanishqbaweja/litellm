import argparse
import asyncio
import json
import logging
import subprocess
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import httpx
import litellm
from litellm.integrations.custom_logger import CustomLogger
from litellm.litellm_core_utils.logging_worker import GLOBAL_LOGGING_WORKER
from litellm.router_strategy.lowest_cost import LowestCostLoggingHandler

parser = argparse.ArgumentParser()
parser.add_argument('revision', choices=('baseline', 'fixed'))
args = parser.parse_args()
root = Path(__file__).resolve().parent
source = Path(litellm.__file__).resolve().parent.parent
expected = json.loads((root / ('runtime.json' if args.revision == 'baseline' else 'product.json')).read_text())['base' if args.revision == 'baseline' else 'head']
sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
assert source == Path('/opt/litellm-34927-baseline' if args.revision == 'baseline' else '/opt/litellm-35459')
assert sha == expected
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=source, text=True).strip()
report = {'revision': args.revision, 'source': str(source), 'sha': sha, 'started_at': datetime.now(timezone.utc).isoformat(), 'calls': [], 'errors': [], 'callback_metadata': []}


class Observer(CustomLogger):
    def capture(self, mode, kwargs):
        params = kwargs.get('litellm_params') or {}
        info = params.get('model_info')
        report['callback_metadata'].append({
            'mode': mode, 'model': kwargs.get('model'),
            'model_info_type': type(info).__name__,
            'deployment_id': info.get('id') if isinstance(info, dict) else None,
            'metadata_model_group': (params.get('metadata') or {}).get('model_group'),
        })

    def log_success_event(self, kwargs, response_obj, start_time, end_time):
        self.capture('sync', kwargs)

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        self.capture('async', kwargs)


class Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.ERROR)

    def emit(self, record):
        if record.filename == 'lowest_cost.py':
            report['errors'].append({
                'function': record.funcName, 'message': record.getMessage(),
                'exception_type': record.exc_info[0].__name__ if record.exc_info else None,
                'traceback': ''.join(traceback.format_exception(*record.exc_info)) if record.exc_info else None,
            })


litellm.verbose_logger.addHandler(Capture())
params = json.loads((root / 'provider-params.json').read_text())
router = litellm.Router(
    model_list=[{'model_name': 'qa-cost-35459', 'litellm_params': params, 'model_info': {'id': 'qa-cost-35459-deployment'}}],
    routing_strategy='cost-based-routing', num_retries=0,
)
assert isinstance(router.lowestcost_logger, LowestCostLoggingHandler)
assert router.lowestcost_logger in litellm.callbacks
litellm.callbacks.append(Observer())
with httpx.Client(timeout=10) as provider:
    report['provider_version'] = provider.get('http://127.0.0.1:11434/api/version').json()


def record_response(kind, response):
    content = response.choices[0].message.content
    assert content and content.strip()
    report['calls'].append({'kind': kind, 'content': content, 'usage': response.usage.model_dump()})
    print(json.dumps(report['calls'][-1]), flush=True)


async def main():
    response = await litellm.acompletion(**params, messages=[{'role': 'user', 'content': 'Reply with only: Async routing works.'}])
    record_response('direct-async-completion', response)
    await asyncio.wait_for(GLOBAL_LOGGING_WORKER.flush(), timeout=20)
    for _ in range(150):
        if any(item['mode'] == 'async' and item['deployment_id'] is None for item in report['callback_metadata']):
            break
        await asyncio.sleep(0.1)
    else:
        raise AssertionError('The async success callback was not observed')
    await asyncio.sleep(0.1)
    response = await router.acompletion(model='qa-cost-35459', messages=[{'role': 'user', 'content': 'Reply with only: Routed control works.'}])
    record_response('router-async-control', response)
    await asyncio.wait_for(GLOBAL_LOGGING_WORKER.flush(), timeout=20)
    for _ in range(150):
        counters = await router.cache.async_get_cache(key='cost_map:qa-cost-35459')
        if counters is not None:
            break
        await asyncio.sleep(0.1)
    else:
        raise AssertionError('The routed cost counter was not recorded')
    assert set(counters) == {'qa-cost-35459-deployment'}, counters
    buckets = counters['qa-cost-35459-deployment']
    assert len(buckets) == 1
    assert next(iter(buckets.values())) == {'tpm': response.usage.total_tokens, 'rpm': 1}, buckets
    report['routed_counters'] = counters


try:
    response = litellm.completion(**params, messages=[{'role': 'user', 'content': 'Reply with only: Routing works.'}])
    record_response('direct-sync-completion', response)
    for _ in range(150):
        if any(item['mode'] == 'sync' for item in report['callback_metadata']):
            break
        time.sleep(0.1)
    else:
        raise AssertionError('The sync success callback was not observed')
    asyncio.run(main())
    if args.revision == 'baseline':
        assert [item['function'] for item in report['errors']] == ['log_success_event', 'async_log_success_event']
        assert all(item['exception_type'] == 'AttributeError' for item in report['errors'])
    else:
        assert report['errors'] == [], report['errors']
    report['completed_at'] = datetime.now(timezone.utc).isoformat()
finally:
    (root / f'sdk-report-{args.revision}.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'calls': len(report['calls']), 'callback_errors': len(report['errors']), 'routed_counters': report['routed_counters']}))
