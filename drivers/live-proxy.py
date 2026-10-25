import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, urlunsplit

import httpx
import psycopg
import yaml
from dotenv import dotenv_values
from psycopg import sql

root = Path('/qa/litellm-35800')
revision = sys.argv[1]
assert revision in ('baseline', 'fixed')
source = Path('/opt/litellm-34927-baseline' if revision == 'baseline' else '/opt/litellm-35800')
metadata = json.loads((root / ('runtime.json' if revision == 'baseline' else 'product.json')).read_text())
expected = metadata['base' if revision == 'baseline' else 'head']
sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
assert sha == expected
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=source, text=True).strip()
assert not subprocess.check_output(['git', 'diff', metadata['base'], '--', 'ui/litellm-dashboard'], cwd=source, text=True).strip()
ui = Path('/qa/litellm-ui-baseline-47520')
assert (ui / 'index.html').exists()
port, receiver_port = 41479, 41480
for check_port in (port, receiver_port):
    with socket.socket() as connection:
        assert connection.connect_ex(('127.0.0.1', check_port)) != 0
stop_file = root / f'stop-{revision}'
assert not stop_file.exists()
sys.path.insert(0, str(source))
from tests.integration._support.redis_process import owned_redis

messages = []
message_lock = threading.Lock()


class Receiver(BaseHTTPRequestHandler):
    def do_POST(self):
        assert self.path == '/alerts'
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        with message_lock:
            messages.append({'received_at': datetime.now(timezone.utc).isoformat(), 'body': body})
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'ok')

    def do_GET(self):
        assert urlsplit(self.path).path == '/messages'
        alias = parse_qs(urlsplit(self.path).query).get('alias', [''])[0]
        with message_lock:
            values = [entry for entry in messages if alias in str(entry['body']) and 'Soft Budget' in str(entry['body'])]
        body = json.dumps({'count': len(values), 'messages': values}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


receiver = ThreadingHTTPServer(('127.0.0.1', receiver_port), Receiver)
receiver_thread = threading.Thread(target=receiver.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
receiver_thread.start()
database_name = f'qa35800_{revision}_{uuid.uuid4().hex[:10]}'
base_database = dotenv_values('/qa/litellm-linux.env')['DATABASE_URL']
database_url = urlunsplit(urlsplit(base_database)._replace(path='/' + database_name))
master_key = 'sk-' + secrets.token_hex(24)
config_path = root / 'alerting-config.yml'
config_path.write_text(yaml.safe_dump({
    'model_list': [{
        'model_name': 'qa-alert-model',
        'litellm_params': {
            'model': 'openai/qa-qwen3.5-0.8b:latest', 'api_base': 'http://127.0.0.1:11434/v1', 'api_key': 'sk-local-unused',
        },
        'model_info': {'id': 'qa35800-model', 'input_cost_per_token': 0.001, 'output_cost_per_token': 0.002},
    }],
    'general_settings': {
        'master_key': 'os.environ/LITELLM_MASTER_KEY', 'database_url': 'os.environ/DATABASE_URL',
        'proxy_batch_write_at': 1, 'proxy_batch_polling_interval': 1,
        'alerting': ['slack'], 'alert_types': ['budget_alerts'],
        'alert_to_webhook_url': {'budget_alerts': 'os.environ/SLACK_WEBHOOK_URL'},
        'alerting_args': {'budget_alert_ttl': 86400},
    },
    'litellm_settings': {
        'enable_redis_auth_cache': True, 'cache': True,
        'cache_params': {'type': 'redis', 'host': 'os.environ/REDIS_HOST', 'port': 'os.environ/REDIS_PORT'},
    },
}))
(root / f'live-{revision}.private.json').write_text(json.dumps({
    'master_key': master_key, 'database_url': database_url, 'database_name': database_name,
}, indent=2) + '\n')
env = {
    **os.environ, 'PATH': '/opt/litellm-venv/bin:/opt/contri-node/bin:' + os.environ['PATH'],
    'PYTHONPATH': str(source), 'PRISMA_BINARY_CACHE_DIR': '/opt/prisma-cache',
    'LITELLM_LOCAL_MODEL_COST_MAP': 'True', 'PYTHON_DOTENV_DISABLED': '1',
    'LITELLM_UI_PATH': str(ui), 'LITELLM_MASTER_KEY': master_key,
    'LITELLM_SALT_KEY': 'sk-' + secrets.token_hex(24), 'DATABASE_URL': database_url,
    'PROXY_BASE_URL': f'http://127.0.0.1:{port}', 'UI_USERNAME': 'admin', 'UI_PASSWORD': master_key,
    'SLACK_WEBHOOK_URL': f'http://127.0.0.1:{receiver_port}/alerts',
}
env.pop('LITELLM_LICENSE', None)
env.pop('DISABLE_SCHEMA_UPDATE', None)
report = {
    'revision': revision, 'source': str(source), 'sha': sha, 'source_clean': True,
    'ui': str(ui), 'ui_source_sha': metadata['base'], 'ui_source_unchanged': True,
    'port': port, 'receiver_port': receiver_port, 'database_name': database_name,
    'started_at': datetime.now(timezone.utc).isoformat(), 'enterprise_entitlement_override': False,
    'local_receiver_only': True, 'hosted_slack_not_tested': True,
    'provider': 'Ollama 0.40.11, local Qwen3.5 0.8B through the OpenAI-compatible endpoint',
    'custom_prices': {'input_cost_per_token': 0.001, 'output_cost_per_token': 0.002},
}
process = None
try:
    with psycopg.connect(base_database, autocommit=True) as admin, owned_redis(root / f'redis-{revision}') as redis:
        env.update(REDIS_HOST=redis.host, REDIS_PORT=str(redis.port))
        report['redis_port'] = redis.port
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database_name)))
        try:
            with (root / f'live-proxy-{revision}.private.log').open('w') as log:
                process = subprocess.Popen([
                    sys.executable, '-m', 'litellm.proxy.proxy_cli', '--host', '127.0.0.1', '--port', str(port),
                    '--telemetry', 'false', '--use_prisma_db_push', '--config', str(config_path),
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
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(database_name)))
            report['owned_database_dropped'] = True
    report['owned_redis_stopped'] = True
finally:
    receiver.shutdown()
    receiver.server_close()
    receiver_thread.join(timeout=2)
    for name, check_port in (('proxy_port_closed', port), ('receiver_port_closed', receiver_port)):
        with socket.socket() as connection:
            report[name] = connection.connect_ex(('127.0.0.1', check_port)) != 0
    report['stopped_at'] = datetime.now(timezone.utc).isoformat()
    (root / f'live-cleanup-{revision}.json').write_text(json.dumps(report, indent=2) + '\n')
    (root / f'webhook-payloads-{revision}.private.json').write_text(json.dumps(messages, indent=2) + '\n')
    print(json.dumps({'revision': revision, 'cleanup': report}), flush=True)
