import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path('/qa/litellm-35800')
repo = Path('/opt/litellm-35800')
path = repo / 'litellm/proxy/auth/auth_checks.py'
original = path.read_bytes()
source = original.decode()
start = source.index('async def virtual_key_soft_budget_check(')
end = source.index('\n_virtual_key_soft_budget_check:', start)
prefix, function, suffix = source[:start], source[start:end], source[end:]
reader = '''    spend: Final = await get_current_spend(
        counter_key=f"spend:key:{valid_token.token}",
        fallback_spend=valid_token.spend or 0.0,
    )'''
mutations = (
    ('stale_auth_spend', reader, '    spend: Final = valid_token.spend'),
    ('stale_alert_payload', '            spend=spend,', '            spend=valid_token.spend,'),
    ('strictly_above_threshold', 'if spend >= valid_token.soft_budget:', 'if spend > valid_token.soft_budget:'),
    ('wrong_counter_prefix', 'counter_key=f"spend:key:{valid_token.token}"', 'counter_key=f"spend:user:{valid_token.token}"'),
    ('discard_cold_fallback', 'fallback_spend=valid_token.spend or 0.0,', 'fallback_spend=0.0,'),
    ('enforce_warning_as_limit', 'fallback_spend=valid_token.spend or 0.0,', 'fallback_spend=valid_token.spend or 0.0,\n        max_budget=valid_token.soft_budget,'),
    ('enable_zero_threshold', 'if not valid_token.soft_budget:', 'if valid_token.soft_budget is None:'),
)
env = {**os.environ, 'PYTHONPATH': str(repo), 'PYTHON_DOTENV_DISABLED': '1', 'LITELLM_LOCAL_MODEL_COST_MAP': 'True'}
command = [sys.executable, '-m', 'pytest', '-q', '--tb=short', 'tests/unit/proxy/auth/test_auth_checks.py', '-k', 'soft_budget_alert_uses_current_spend_without_blocking_requests']
report = {'started_at': datetime.now(timezone.utc).isoformat(), 'original_sha256': hashlib.sha256(original).hexdigest(), 'command': command, 'mutations': []}
try:
    for name, old, new in mutations:
        assert function.count(old) == 1, name
        path.write_text(prefix + function.replace(old, new) + suffix)
        log = root / f'mutation-{name}.log'
        with log.open('w') as output:
            result = subprocess.run(command, cwd=repo, env=env, stdout=output, stderr=subprocess.STDOUT)
        text = log.read_text()
        count = re.search(r'(\d+) failed', text)
        item = {'name': name, 'returncode': result.returncode, 'failed_tests': int(count.group(1)) if count else None,
                'mutant_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        report['mutations'].append(item)
        (root / 'mutations.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(item), flush=True)
        assert result.returncode == 1 and count is not None and 'ERROR collecting' not in text, name
finally:
    path.write_bytes(original)
    report['restored_exactly'] = hashlib.sha256(path.read_bytes()).hexdigest() == report['original_sha256']
    report['completed_at'] = datetime.now(timezone.utc).isoformat()
    (root / 'mutations.json').write_text(json.dumps(report, indent=2) + '\n')
assert report['restored_exactly']
with (root / 'unit-restored.log').open('w') as output:
    restored = subprocess.run(command, cwd=repo, env=env, stdout=output, stderr=subprocess.STDOUT)
report['restored_returncode'] = restored.returncode
(root / 'mutations.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'mutants_killed': len(report['mutations']), 'restored_returncode': restored.returncode}), flush=True)
assert restored.returncode == 0
