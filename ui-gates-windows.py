import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

root = Path(__file__).resolve().parents[2]
qa = root / '.verification/litellm-36095'
dashboard = root / 'litellm-36095/ui/litellm-dashboard'
shared = root / 'litellm/ui/litellm-dashboard'
node_dir = root / '.tools/node-v24.21.0-win-x64'
node = str(node_dir / 'node.exe')
assert (dashboard / 'package-lock.json').read_bytes() == (shared / 'package-lock.json').read_bytes()
env = {**os.environ, 'PATH': str(node_dir) + os.pathsep + os.environ['PATH'], 'CI': 'true'}
report = {'started_at': datetime.now(timezone.utc).isoformat(), 'gates': []}


def run(name, arguments, allowed=(0,)):
    log = root / '.verification/logs' / f'litellm-36095-ui-{name}.log'
    command = [node, *arguments]
    with log.open('w', encoding='utf-8') as output:
        result = subprocess.run(command, cwd=dashboard, env=env, stdout=output, stderr=subprocess.STDOUT, text=True)
    report['gates'].append({'name': name, 'command': command, 'returncode': result.returncode})
    (qa / 'ui-gates.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(name, result.returncode, flush=True)
    print(log.read_text(encoding='utf-8', errors='replace')[-6000:], flush=True)
    assert result.returncode in allowed, name


run('targeted-tests', ['node_modules/vitest/vitest.mjs', 'run',
    'src/components/model_info_view.test.tsx',
    'src/components/add_model/AddModelForm.integration.test.tsx',
    'src/components/add_model/handle_add_model_submit.test.tsx',
    'src/lib/http/api.test.ts', '--maxWorkers=2'])
run('production-types', ['node_modules/typescript/bin/tsc', '--project', 'tsconfig.production.json'])
run('type-tests', ['node_modules/vitest/vitest.mjs', 'run', '--project', 'types', '--maxWorkers=2'])
run('prettier', ['node_modules/prettier/bin/prettier.cjs', '--check', 'src/lib/http/schema.d.ts'])
run('eslint-changed', ['node_modules/eslint/bin/eslint.js', '--no-warn-ignored', '--pass-on-unpruned-suppressions', 'src/lib/http/schema.d.ts'])
run('eslint-report', ['node_modules/eslint/bin/eslint.js', '.', '-f', 'json', '-o', str(qa / 'eslint-report.json')], allowed=(0, 1))
run('eslint-budgets', ['scripts/check-lint-budgets.mjs', str(qa / 'eslint-report.json'), 'eslint-budgets.json'])
run('knip', ['node_modules/knip/bin/knip.js', '--exclude', 'exports,nsExports,types,nsTypes,enumMembers,classMembers,duplicates'])
report['completed_at'] = datetime.now(timezone.utc).isoformat()
(qa / 'ui-gates.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
