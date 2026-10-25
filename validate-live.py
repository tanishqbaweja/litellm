import json
import math
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

root = Path(__file__).resolve().parent
fixed_label = sys.argv[1]
source_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
assert not subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip()
reports = {mode: json.loads((root / f'api-report-{label}.json').read_text()) for mode, label in [('baseline', 'baseline'), ('fixed', fixed_label)]}
assert reports['baseline']['source_sha'] == 'dddbaa803d6e9fcc862ea7a5412f771cb1ae040e'
assert reports['fixed']['source_sha'] == source_sha
summary = {'verified_at': datetime.now(timezone.utc).isoformat(), 'base_sha': reports['baseline']['source_sha'], 'fixed_sha': source_sha, 'cases': [], 'prometheus': {}, 'between_run_float_tolerance': {'relative': 1e-6, 'absolute': 1e-6}}
stored_responses = {}

def compare_model_outputs(before, after, location, numeric_differences):
    if isinstance(before, dict):
        assert isinstance(after, dict) and before.keys() == after.keys(), location
        for key in before:
            if location == '' and key in ('id', 'created'):
                continue
            compare_model_outputs(before[key], after[key], location + '.' + key, numeric_differences)
    elif isinstance(before, list):
        assert isinstance(after, list) and len(before) == len(after), location
        for index, (left, right) in enumerate(zip(before, after, strict=True)):
            compare_model_outputs(left, right, location + f'[{index}]', numeric_differences)
    elif isinstance(before, float):
        assert isinstance(after, float) and math.isclose(before, after, rel_tol=1e-6, abs_tol=1e-6), location
        if before != after:
            numeric_differences.append({'path': location, 'before': before, 'after': after, 'absolute_difference': abs(before - after)})
    else:
        assert before == after, location

with httpx.Client(base_url='http://127.0.0.1:41475', headers={'Authorization': 'Bearer ' + os.environ['LITELLM_MASTER_KEY']}, timeout=30) as api:
    for before, after in zip(reports['baseline']['cases'], reports['fixed']['cases'], strict=True):
        assert before['case'] == after['case']
        assert before['http_status'] == after['http_status'] == 200
        name = before['case']
        before_body = json.loads((root / 'api-baseline' / f'{name}-response.json').read_text())
        after_body = json.loads((root / f'api-{fixed_label}' / f'{name}-response.json').read_text())
        numeric_differences = []
        compare_model_outputs(before_body, after_body, '', numeric_differences)
        assert json.loads((root / 'api-baseline' / f'{name}-request.json').read_text()) == json.loads((root / f'api-{fixed_label}' / f'{name}-request.json').read_text())
        selected = {}
        for mode in ['baseline', 'fixed']:
            rows = [row for row in reports[mode]['spend_rows'] if (row['call_type'] == 'aembedding' if name == 'regular-embeddings-control' else row['call_type'] == 'allm_passthrough_route' and urlparse(row['api_base']).path == before['endpoint'].removeprefix('/vllm'))]
            expected_count = 0 if mode == 'baseline' and not name.endswith('-control') else 1
            assert len(rows) == expected_count, (mode, name, rows)
            if rows:
                row = rows[0]
                assert row['status'] == 'success'
                assert row['prompt_tokens'] == after['usage']['prompt_tokens']
                assert row['total_tokens'] == after['usage']['total_tokens']
                assert row['completion_tokens'] == 0
                assert math.isclose(row['spend'], after['usage']['prompt_tokens'] / 1_000_000, abs_tol=1e-15)
                selected[mode] = {key: row[key] for key in ['request_id', 'prompt_tokens', 'completion_tokens', 'total_tokens', 'spend']}
            else:
                selected[mode] = None
        if not name.endswith('-control'):
            assert selected['fixed']['request_id'] == after_body['id']
            response = api.get('/spend/logs/ui/' + after_body['id'])
            response.raise_for_status()
            payload = response.json()
            stored = payload['response']
            if isinstance(stored, str):
                stored = json.loads(stored)
            assert stored == after_body, name
            stored_responses[name] = {'http_status': response.status_code, 'response': stored}
        summary['cases'].append({'case': name, 'endpoint': after['endpoint'], 'http_status': 200, 'same_request': True, 'same_response_except_id_created_and_recorded_float_differences': True, 'between_run_numeric_differences': numeric_differences, 'rows': selected, 'full_native_response_persisted': True if not name.endswith('-control') else None})

for mode, report in reports.items():
    assert report['metrics_status'] == 200
    totals = {}
    metrics = []
    for line in report['metrics']:
        name = line.split('{', 1)[0]
        if name not in ('litellm_requests_metric_total', 'litellm_input_tokens_metric_total', 'litellm_total_tokens_metric_total', 'litellm_spend_metric_total') or f'api_key_alias="{report["alias"]}"' not in line:
            continue
        value = float(line.rsplit(' ', 1)[-1])
        totals[name] = totals.get(name, 0.0) + value
        labels = dict(re.findall(r'(\w+)="([^"]*)"', line))
        safe_labels = {key: value for key, value in labels.items() if key in ('model', 'model_group', 'requested_model', 'api_provider', 'status', 'api_key_alias')}
        metrics.append({'metric': name, 'labels': safe_labels, 'value': value})
    expected_count = 2 if mode == 'baseline' else 6
    expected_tokens = 18 if mode == 'baseline' else 93
    assert totals['litellm_requests_metric_total'] == expected_count
    assert totals['litellm_input_tokens_metric_total'] == totals['litellm_total_tokens_metric_total'] == expected_tokens
    assert math.isclose(totals['litellm_spend_metric_total'], expected_tokens / 1_000_000, abs_tol=1e-15)
    summary['prometheus'][mode] = {'totals': totals, 'metrics': metrics}
    source_log = (root / f'proxy-{mode}.log').read_text(errors='replace')
    errors = [re.sub(r'\x1b\[[0-9;]*m', '', line) for line in source_log.splitlines() if 'standard_logging_object not found' in line or 'standard_logging_object is required, got=None' in line]
    assert bool(errors) == (mode == 'baseline')
    summary.setdefault('missing_standard_logging_errors', {})[mode] = len(errors)
    (root / f'proxy-{mode}-logging-errors.txt').write_text('\n'.join(errors) + ('\n' if errors else 'No missing-standard-logging errors in this run.\n'))

(root / 'live-validation.json').write_text(json.dumps(summary, indent=2) + '\n')
(root / 'stored-native-responses.json').write_text(json.dumps(stored_responses, indent=2) + '\n')
print(json.dumps({'base_sha': summary['base_sha'], 'fixed_sha': source_sha, 'cases': len(summary['cases']), 'native_responses_persisted_unchanged': len(stored_responses), 'prometheus_totals': {mode: value['totals'] for mode, value in summary['prometheus'].items()}, 'missing_standard_logging_errors': summary['missing_standard_logging_errors']}, indent=2))
