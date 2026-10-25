import argparse
import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client

parser = argparse.ArgumentParser()
parser.add_argument('revision', choices=('baseline', 'fixed'))
args = parser.parse_args()
root = Path(__file__).resolve().parent
report = {'revision': args.revision, 'routing_strategy': 'cost-based-routing', 'started_at': datetime.now(timezone.utc).isoformat(), 'calls': []}


def rows(kind):
    path = root / f'{kind}-{args.revision}.jsonl'
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


async def main():
    async with httpx.AsyncClient(base_url='http://127.0.0.1:41475', headers={'Authorization': 'Bearer ' + os.environ['LITELLM_MASTER_KEY']}, timeout=5) as api:
        for _ in range(60):
            try:
                if (await api.get('/health/readiness')).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1)
        else:
            raise RuntimeError('Proxy did not become ready')
    source = json.loads((root / f'proxy-source-{args.revision}.json').read_text())
    expected = json.loads((root / ('runtime.json' if args.revision == 'baseline' else 'product.json')).read_text())['base' if args.revision == 'baseline' else 'head']
    assert source['sha'] == expected
    assert source['pid'] == int((root / 'proxy.pid').read_text())
    assert Path(f'/proc/{source["pid"]}/cwd').resolve() == Path(source['source'])
    report['source_sha'] = expected
    before_errors = len(rows('callback-errors'))
    before_callbacks = len(rows('callback-metadata'))
    async with create_mcp_http_client(headers={'Authorization': 'Bearer ' + os.environ['LITELLM_MASTER_KEY']}) as client:
        async with streamable_http_client('http://127.0.0.1:41475/mcp/', http_client=client) as (read, write, _):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                report['server_info'] = initialized.serverInfo.model_dump()
                tools = await session.list_tools()
                report['tool_names'] = [tool.name for tool in tools.tools]
                for method, values in [('add', {'a': 17, 'b': 25}), ('multiply', {'a': 6, 'b': 7})]:
                    name = next(tool.name for tool in tools.tools if 'math35459' in tool.name and tool.name.endswith(method))
                    result = await session.call_tool(name, values)
                    item = {'name': name, 'arguments': values, 'result': result.model_dump(mode='json')}
                    report['calls'].append(item)
                    assert not result.isError, item
                    assert any(getattr(content, 'text', None) == '42' for content in result.content), item
                    print(json.dumps(item), flush=True)
    for _ in range(150):
        if len(rows('callback-metadata')) >= before_callbacks + 2:
            break
        await asyncio.sleep(0.1)
    else:
        raise AssertionError('MCP success callbacks were not observed')
    await asyncio.sleep(0.5)
    report['callbacks'] = rows('callback-metadata')[before_callbacks:]
    report['callback_errors'] = rows('callback-errors')[before_errors:]
    assert all(item['model_info_type'] == 'NoneType' for item in report['callbacks']), report['callbacks']
    assert len(report['calls']) == 2
    if args.revision == 'baseline':
        assert len(report['callback_errors']) >= 2, report
        assert all(item['exception_type'] == 'AttributeError' for item in report['callback_errors'])
    else:
        assert report['callback_errors'] == [], report
    report['completed_at'] = datetime.now(timezone.utc).isoformat()


try:
    asyncio.run(main())
finally:
    (root / f'mcp-report-{args.revision}.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'revision': args.revision, 'tools_called': len(report['calls']), 'callback_errors': len(report['callback_errors'])}))
