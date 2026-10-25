import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path('/qa/litellm-42689')
revision, viewport = sys.argv[1:3]
assert revision in ('baseline', 'fixed') and viewport in ('desktop', 'phone')
arguments = sys.argv[3:]
assert arguments
private = json.loads((root / f'live-{revision}.private.json').read_text())
secrets = {private['master_key'], *private.get('owned_keys', {}).values(), *private.get('invalid_keys', [])}
secrets.update(hashlib.sha256(value.encode()).hexdigest() for value in tuple(secrets))
output = root / 'output/playwright' / f'{revision}-{viewport}'
output.mkdir(parents=True, exist_ok=True)
config = output / 'cli.config.json'
config.write_text(json.dumps({
    'browser': {
        'browserName': 'chromium',
        'launchOptions': {
            'headless': False,
            'executablePath': '/opt/playwright-browsers/chromium-1208/chrome-linux64/chrome',
            'args': ['--no-sandbox', '--disable-dev-shm-usage'],
        },
        'contextOptions': {
            'viewport': {'width': 1440 if viewport == 'desktop' else 390, 'height': 900 if viewport == 'desktop' else 844},
            'isMobile': viewport == 'phone', 'hasTouch': viewport == 'phone',
            'colorScheme': 'light', 'timezoneId': 'UTC',
        },
    },
    'outputDir': str(output),
}, indent=2) + '\n')
if arguments[0] == 'open':
    arguments += ['--headed', '--config', str(config)]
if arguments[0] == 'fill-master':
    assert len(arguments) == 2
    arguments = ['fill', arguments[1], private['master_key']]
if arguments[0] == 'main-text':
    arguments = ['eval', "document.querySelector('main')?.innerText"]
if arguments[0] == 'run-file':
    assert len(arguments) == 2
    script = Path(arguments[1]).resolve()
    assert script.is_relative_to(root.resolve())
    arguments = ['run-code', script.read_text()]
command = [
    '/opt/contri-node/bin/npx', '--yes', '--package=@playwright/cli@0.1.22', 'playwright-cli',
    '-s=qa42689-' + revision + '-' + viewport, *arguments,
]
env = {**os.environ, 'PATH': '/opt/contri-node/bin:' + os.environ['PATH'], 'DISPLAY': ':99', 'PLAYWRIGHT_BROWSERS_PATH': '/opt/playwright-browsers'}
result = subprocess.run(command, cwd=output, env=env, capture_output=True, text=True)


def redact(value):
    for secret in sorted(secrets, key=len, reverse=True):
        value = value.replace(secret, '<QA_KEY>')
    return value


def compact_snapshot(value):
    lines = value.splitlines()
    dialog = next((i for i, line in enumerate(lines) if re.match(r'\s*- (?:alert)?dialog\b', line)), None)
    main = next((i for i, line in enumerate(lines) if re.match(r'\s*- main\b', line)), None)
    start = dialog if dialog is not None else main
    selected = lines[start:] if start is not None else lines
    return '\n'.join(line if len(line) < 900 else line[:500] + ' ... [long value in saved snapshot]' for line in selected)[:18000]


record = {'at': datetime.now(timezone.utc).isoformat(), 'arguments': [redact(arg) for arg in arguments], 'returncode': result.returncode, 'stdout': redact(result.stdout), 'stderr': redact(result.stderr)}
with (output / 'cli-actions.jsonl').open('a') as log:
    log.write(json.dumps(record) + '\n')
shown = record['stdout']
if '```yaml\n' in shown:
    prefix, rest = shown.split('```yaml\n', 1)
    snapshot_text, suffix = rest.split('```', 1)
    shown = prefix + '```yaml\n' + compact_snapshot(snapshot_text) + '\n```' + suffix
print(shown, end='')
print(record['stderr'], end='', file=sys.stderr)
if arguments[0] in ('open', 'snapshot', 'goto', 'click', 'reload'):
    match = re.search(r'\[Snapshot\]\(([^)]+)\)', result.stdout)
    if match:
        snapshot = (output / match.group(1)).resolve()
        assert snapshot.is_relative_to(output.resolve())
        print(compact_snapshot(redact(snapshot.read_text())))
sys.exit(result.returncode)
