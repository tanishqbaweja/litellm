import os
import signal
import time
from pathlib import Path

pid = int(Path('/qa/litellm-34681/proxy.pid').read_text())
command = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
assert b'litellm.proxy.proxy_cli' in command
assert b'/qa/litellm-34681/config.yml' in command
os.kill(pid, signal.SIGTERM)
for _ in range(100):
    if not Path(f'/proc/{pid}').exists():
        print(f'Stopped owned proxy {pid}')
        break
    time.sleep(0.1)
else:
    raise RuntimeError('Proxy did not stop within 10 seconds')
