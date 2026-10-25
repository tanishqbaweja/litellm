import json
import os
import secrets
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx
import psycopg
import yaml
from dotenv import dotenv_values
from psycopg import sql

root = Path('/qa/litellm-38759')
revision = sys.argv[1]
assert revision in ('baseline', 'fixed')
source = Path('/opt/litellm-34927-baseline' if revision == 'baseline' else '/opt/litellm-38759')
metadata = json.loads((root / ('runtime.json' if revision == 'baseline' else 'product.json')).read_text())
expected = metadata['base' if revision == 'baseline' else 'head']
sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
assert sha == expected
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=source, text=True).strip()
ui = Path('/qa/litellm-ui-baseline-47520' if revision == 'baseline' else '/opt/qa-ui-build-38759/out')
assert (ui / 'index.html').exists()
if revision == 'fixed':
    build = json.loads((root / 'ui-build.json').read_text())
    assert build['source_sha'] == sha and build['returncode'] == 0
    assert build['product_tree_clean'] and not build['build_changed_tracked_files']
port = 41478
with socket.socket() as connection:
    assert connection.connect_ex(('127.0.0.1', port)) != 0
stop_file = root / f'stop-{revision}'
assert not stop_file.exists()
database_name = f'qa38759_{revision}_{uuid.uuid4().hex[:10]}'
base_database = dotenv_values('/qa/litellm-linux.env')['DATABASE_URL']
database_url = urlunsplit(urlsplit(base_database)._replace(path='/' + database_name))
master_key = 'sk-' + secrets.token_hex(24)
config_path = root / 'budget-config.yml'
config_path.write_text(yaml.safe_dump({
    'model_list': [],
    'general_settings': {
        'master_key': 'os.environ/LITELLM_MASTER_KEY',
        'database_url': 'os.environ/DATABASE_URL',
    },
}))
(root / f'live-{revision}.private.json').write_text(json.dumps({
    'master_key': master_key, 'database_url': database_url, 'database_name': database_name,
}, indent=2) + '\n')
env = {
    **os.environ,
    'PATH': '/opt/litellm-venv/bin:/opt/contri-node/bin:' + os.environ['PATH'],
    'PYTHONPATH': str(source), 'PRISMA_BINARY_CACHE_DIR': '/opt/prisma-cache',
    'LITELLM_LOCAL_MODEL_COST_MAP': 'True', 'PYTHON_DOTENV_DISABLED': '1',
    'LITELLM_UI_PATH': str(ui), 'LITELLM_MASTER_KEY': master_key,
    'LITELLM_SALT_KEY': 'sk-' + secrets.token_hex(24), 'DATABASE_URL': database_url,
    'PROXY_BASE_URL': f'http://127.0.0.1:{port}', 'UI_USERNAME': 'admin', 'UI_PASSWORD': master_key,
}
env.pop('LITELLM_LICENSE', None)
env.pop('DISABLE_SCHEMA_UPDATE', None)
report = {
    'revision': revision, 'source': str(source), 'sha': sha, 'source_clean': True,
    'ui': str(ui), 'ui_source_sha': sha,
    'port': port, 'database_name': database_name, 'started_at': datetime.now(timezone.utc).isoformat(),
    'enterprise_entitlement_override': False,
}
process = None
with psycopg.connect(base_database, autocommit=True) as admin:
    admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database_name)))
    try:
        with (root / f'live-proxy-{revision}.private.log').open('w') as log:
            process = subprocess.Popen([
                sys.executable, '-m', 'litellm.proxy.proxy_cli', '--host', '127.0.0.1',
                '--port', str(port), '--telemetry', 'false', '--use_prisma_db_push',
                '--config', str(config_path),
            ], cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT)
        report['pid'] = process.pid
        (root / f'proxy-source-{revision}.json').write_text(json.dumps(report, indent=2) + '\n')
        deadline = time.monotonic() + 180
        with httpx.Client(base_url=f'http://127.0.0.1:{port}', headers={'Authorization': 'Bearer ' + master_key}, timeout=2, trust_env=False) as api:
            while True:
                assert process.poll() is None, 'QA proxy exited before readiness'
                try:
                    if api.get('/health/readiness').status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                assert time.monotonic() < deadline, 'QA readiness deadline expired'
                time.sleep(0.2)
        report['ready_at'] = datetime.now(timezone.utc).isoformat()
        (root / f'proxy-source-{revision}.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({'revision': revision, 'ready': True, 'source_sha': sha, 'port': port, 'pid': process.pid}), flush=True)
        while not stop_file.exists():
            assert process.poll() is None
            time.sleep(0.2)
    finally:
        if process is not None:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=30)
                report['forced_stop'] = False
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
                report['forced_stop'] = True
            report['process_reaped'] = True
            report['exit_code'] = process.returncode
        admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(database_name)))
        report['owned_database_dropped'] = True
        with socket.socket() as connection:
            report['port_closed'] = connection.connect_ex(('127.0.0.1', port)) != 0
        report['stopped_at'] = datetime.now(timezone.utc).isoformat()
        (root / f'live-cleanup-{revision}.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({name: report[name] for name in ['revision', 'process_reaped', 'owned_database_dropped', 'port_closed']}), flush=True)
