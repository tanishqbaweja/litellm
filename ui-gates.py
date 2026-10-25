import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

qa = Path(__file__).resolve().parent
dashboard = Path('/opt/litellm-36095/ui/litellm-dashboard')
dependencies = qa / 'dashboard-deps-linux'
node = '/opt/contri-node/bin/node'
assert (dashboard / 'package-lock.json').read_bytes() == (dependencies / 'package-lock.json').read_bytes()
env = {**os.environ, 'PATH': '/opt/contri-node/bin:' + os.environ['PATH'], 'CI': 'true'}
locale = json.loads(subprocess.run([node, '-p', 'JSON.stringify({locale:new Intl.NumberFormat().resolvedOptions().locale,number:(1000000).toLocaleString()})'], capture_output=True, text=True, check=True).stdout)
assert locale == {'locale': 'en-US', 'number': '1,000,000'}
resume = '--resume' in sys.argv[1:]
report = json.loads((qa / 'ui-gates-linux.json').read_text()) if resume else {'started_at': datetime.now(timezone.utc).isoformat(), 'locale': locale, 'gates': []}
if resume:
    report['resumed_at'] = datetime.now(timezone.utc).isoformat()


def run(name, arguments, allowed=(0,)):
    log = qa.parent / 'logs' / f'litellm-36095-ui-linux-{name}.log'
    command = [node, *arguments]
    previous = next((gate for gate in report['gates'] if gate['name'] == name), None)
    if resume and previous is not None:
        assert previous['command'] == command and previous['returncode'] in allowed, previous
        print(name, 'already recorded', previous['returncode'], flush=True)
        return
    with log.open('w') as output:
        result = subprocess.run(command, cwd=dashboard, env=env, stdout=output, stderr=subprocess.STDOUT, text=True)
    report['gates'].append({'name': name, 'command': command, 'returncode': result.returncode})
    (qa / 'ui-gates-linux.json').write_text(json.dumps(report, indent=2) + '\n')
    print(name, result.returncode, flush=True)
    print(log.read_text(errors='replace')[-5000:], flush=True)
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
run('eslint-report', ['node_modules/eslint/bin/eslint.js', '.', '-f', 'json', '-o', str(qa / 'eslint-report-linux.json')], allowed=(0, 1, 2))
lint_results = json.loads((qa / 'eslint-report-linux.json').read_text())
assert lint_results and all(result['fatalErrorCount'] == 0 for result in lint_results)
report['eslint_report_files'] = len(lint_results)
report['eslint_fatal_errors'] = 0
report['raw_eslint_exit_reason'] = 'The CI workflow permits the raw report command to fail before checking budgets. This run reports existing stale suppressions, with a valid JSON report and no fatal lint errors.'
run('eslint-budgets', ['scripts/check-lint-budgets.mjs', str(qa / 'eslint-report-linux.json'), 'eslint-budgets.json'])
run('knip', ['node_modules/knip/bin/knip.js', '--exclude', 'exports,nsExports,types,nsTypes,enumMembers,classMembers,duplicates'])
report['completed_at'] = datetime.now(timezone.utc).isoformat()
(qa / 'ui-gates-linux.json').write_text(json.dumps(report, indent=2) + '\n')
