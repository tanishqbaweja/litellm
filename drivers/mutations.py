import hashlib
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

root = Path('/qa/litellm-42689')
repo = Path('/opt/litellm-42689')
target = repo / 'litellm/proxy/hooks/proxy_track_cost_callback.py'
original = target.read_bytes()
text = original.decode()
unknown = 'isinstance(original_exception, KeyNotFoundError)'
malformed = 'is_invalid_virtual_key_error(original_exception)'
assert text.count(unknown) == text.count(malformed) == 1
mutants = {
    'baseline-control': subprocess.check_output(['git', 'show', 'origin/main:litellm/proxy/hooks/proxy_track_cost_callback.py'], cwd=repo, text=True),
    'unknown-keys-admitted': text.replace(unknown, 'False'),
    'malformed-keys-admitted': text.replace(malformed, 'False'),
    'both-markers-required': text.replace('or ' + malformed, 'and ' + malformed),
    'all-failures-dropped': text.replace(unknown, 'True'),
    'all-401s-dropped': text.replace(malformed, 'str(getattr(original_exception, "status_code", getattr(original_exception, "code", None))) == "401"'),
    'message-text-trusted': text.replace(malformed, '"Malformed virtual key" in str(original_exception)'),
}
env = {**os.environ, 'PYTHONPATH': str(repo), 'PYTHON_DOTENV_DISABLED': '1', 'LITELLM_LOCAL_MODEL_COST_MAP': 'True'}
report = {'started_at': datetime.now(timezone.utc).isoformat(), 'original_sha256': hashlib.sha256(original).hexdigest(), 'mutations': []}
try:
    for name, mutated in mutants.items():
        target.write_text(mutated)
        xml = root / f'mutation-{name}.xml'
        command = [sys.executable, '-m', 'pytest', 'tests/unit/proxy/hooks/test_proxy_track_cost_callback.py', '-k', 'unrecognized_keys_write', '-q', '--tb=short', '--junitxml=' + str(xml)]
        with (root / f'mutation-{name}.log').open('w') as log:
            result = subprocess.run(command, cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT)
        suite = ET.parse(xml).getroot().find('testsuite')
        assert suite is not None
        failures = [case.attrib['name'] for case in suite.findall('testcase') if case.find('failure') is not None]
        item = {'name': name, 'baseline_control': name == 'baseline-control', 'returncode': result.returncode, 'tests': int(suite.attrib['tests']), 'errors': int(suite.attrib['errors']), 'failed_assertions': failures}
        report['mutations'].append(item)
        (root / 'mutations.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(item), flush=True)
        assert result.returncode == 1 and failures and not item['errors'], item
finally:
    target.write_bytes(original)
    report['exact_source_restored'] = target.read_bytes() == original
    report['completed_at'] = datetime.now(timezone.utc).isoformat()
    (root / 'mutations.json').write_text(json.dumps(report, indent=2) + '\n')
assert report['exact_source_restored'] and len(report['mutations']) == len(mutants)
