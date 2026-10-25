import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path('/qa/litellm-42689')
repo = Path('/opt/litellm-42689')
dashboard = repo / 'ui/litellm-dashboard'
cache_source = Path('/opt/litellm-36095/ui/litellm-dashboard')
dependencies = Path('/qa/litellm-36095/dashboard-deps-linux/node_modules')
assert dependencies.is_dir()
for name in ('package.json', 'package-lock.json'):
    assert (dashboard / name).read_bytes() == (cache_source / name).read_bytes()
modules = dashboard / 'node_modules'
if not modules.exists():
    modules.symlink_to(dependencies, target_is_directory=True)
assert modules.resolve() == dependencies.resolve()
commands = {
    'frontend': [
        '/opt/contri-node/bin/node', 'node_modules/vitest/vitest.mjs', 'run',
        'src/components/logs/request/RequestLogsPanel.test.tsx',
        'src/components/logs/request/RequestLogsTableColumns.test.tsx',
        'src/app/(dashboard)/logs/page.integration.test.tsx',
        'src/app/(dashboard)/usage/_components/hooks/useAggregatedDailyActivity.test.ts',
        'src/app/(dashboard)/usage/_components/components/overview/UsageStatStrip.integration.test.tsx',
        'src/app/(dashboard)/usage/_components/components/errors/errorsData.test.ts',
    ],
    'ui-types': ['/opt/contri-node/bin/node', 'node_modules/typescript/bin/tsc', '--project', 'tsconfig.production.json'],
}
name = sys.argv[1]
command = commands[name]
report = {
    'name': name, 'command': command, 'started_at': datetime.now(timezone.utc).isoformat(),
    'lock_sha256': hashlib.sha256((dashboard / 'package-lock.json').read_bytes()).hexdigest(),
    'dependency_cache': str(dependencies), 'dependency_manifests_match': True,
}
env = {**os.environ, 'PATH': '/opt/contri-node/bin:/opt/litellm-venv/bin:' + os.environ['PATH'], 'CI': 'true'}
with (root / f'{name}.log').open('w') as log:
    result = subprocess.run(command, cwd=dashboard, env=env, stdout=log, stderr=subprocess.STDOUT)
report.update(returncode=result.returncode, completed_at=datetime.now(timezone.utc).isoformat())
(root / f'{name}.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report), flush=True)
print((root / f'{name}.log').read_text()[-3500:], flush=True)
sys.exit(result.returncode)
