import argparse
import asyncio
import json
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import litellm
import redis
from litellm.caching.dual_cache import DualCache
from litellm.caching.redis_cache import RedisCache

parser = argparse.ArgumentParser()
parser.add_argument('revision', choices=('baseline', 'fixed'))
args = parser.parse_args()
root = Path(__file__).resolve().parent
runtime = json.loads((root / 'runtime.json').read_text())
source = Path(litellm.__file__).resolve().parent.parent
sha = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
expected = runtime['base'] if args.revision == 'baseline' else json.loads((root / 'product.json').read_text())['head']
assert sha == expected, (str(source), sha, expected)
assert not subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True).strip()
report = {'revision': args.revision, 'source_path': str(source), 'source_sha': sha, 'started_at': datetime.now(timezone.utc).isoformat(), 'cases': []}
observer = redis.Redis(host='127.0.0.1', port=6386, decode_responses=True)
report['redis_version'] = observer.info('server')['redis_version']


def mget_count():
    return observer.info('commandstats').get('cmdstat_mget', {}).get('calls', 0)


async def main():
    for asynchronous in (False, True):
        for capacity in (3, 4):
            namespace = 'qa-34681-' + uuid.uuid4().hex
            storage = RedisCache(host='127.0.0.1', port=6386, namespace=namespace)
            cache = DualCache(redis_cache=storage, default_max_redis_batch_cache_size=capacity, default_redis_batch_cache_expiry=10)
            case = {'asynchronous': asynchronous, 'capacity': capacity, 'namespace': namespace, 'expiry_seconds': 10, 'steps': []}
            report['cases'].append(case)
            started = time.monotonic()
            try:
                for index, keys in enumerate((['fresh', 'expired'], ['fresh'], ['filler'], ['expired'], ['expired'], ['fresh'], ['new'], ['fresh'])):
                    if index == 1:
                        await asyncio.sleep(10.1)
                    before = mget_count()
                    result = await cache.async_batch_get_cache(keys) if asynchronous else cache.batch_get_cache(keys)
                    after = mget_count()
                    assert result == [None] * len(keys), result
                    case['steps'].append({'keys': keys, 'result': result, 'redis_mget_commands': after - before, 'elapsed_seconds': round(time.monotonic() - started, 4)})
                expected = [1, 1, 1, 1, 0, 0, 1, 0] if capacity == 4 else ([1, 1, 1, 1, 0, 1, 1, 0] if args.revision == 'baseline' else [1, 1, 1, 1, 0, 0, 1, 1])
                observed = [step['redis_mget_commands'] for step in case['steps']]
                assert observed == expected, (case, expected)
                assert case['steps'][-1]['elapsed_seconds'] - case['steps'][1]['elapsed_seconds'] < 5
                case['outcome'] = 'pass'
                print(json.dumps({'asynchronous': asynchronous, 'capacity': capacity, 'redis_mget_commands_by_step': observed}), flush=True)
            finally:
                if storage.redis_async_client is not None:
                    await storage.redis_async_client.aclose()
                await storage.async_redis_conn_pool.disconnect()
                storage.redis_client.close()
                (root / f'redis-report-{args.revision}.json').write_text(json.dumps(report, indent=2) + '\n')
    report['completed_at'] = datetime.now(timezone.utc).isoformat()
    (root / f'redis-report-{args.revision}.json').write_text(json.dumps(report, indent=2) + '\n')


try:
    asyncio.run(main())
finally:
    observer.close()
