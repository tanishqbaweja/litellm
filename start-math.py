import json
import socket
import subprocess
import sys
import time
from pathlib import Path

root = Path('/qa/litellm-35459')
source = Path('/opt/litellm-34927-baseline')
with socket.socket() as connection:
    assert connection.connect_ex(('127.0.0.1', 41476)) != 0, 'MCP QA port is occupied'
with (root / 'math-server.log').open('w') as log:
    process = subprocess.Popen(
        [sys.executable, str(root / 'math-server.py')],
        cwd=source, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
    )
(root / 'math-server.pid').write_text(str(process.pid) + '\n')
for _ in range(100):
    assert process.poll() is None, (root / 'math-server.log').read_text()
    with socket.socket() as connection:
        if connection.connect_ex(('127.0.0.1', 41476)) == 0:
            break
    time.sleep(0.1)
else:
    raise AssertionError('MCP server did not listen within ten seconds')
print(json.dumps({'math_server_pid': process.pid, 'port': 41476}))
