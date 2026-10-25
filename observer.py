import json
import logging
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path

import litellm
from litellm.integrations.custom_logger import CustomLogger

root = Path(__file__).resolve().parent
revision = os.environ['QA_35459_REVISION']


def append(kind, item):
    with (root / f'{kind}-{revision}.jsonl').open('a') as output:
        output.write(json.dumps({'at': datetime.now(timezone.utc).isoformat(), **item}, default=str) + '\n')


class ErrorCapture(logging.Handler):
    def emit(self, record):
        if record.filename == 'lowest_cost.py':
            append('callback-errors', {
                'function': record.funcName,
                'message': record.getMessage(),
                'exception_type': record.exc_info[0].__name__ if record.exc_info else None,
                'traceback': ''.join(traceback.format_exception(*record.exc_info)) if record.exc_info else None,
            })


class Observer(CustomLogger):
    def __init__(self):
        self.capture = ErrorCapture(logging.ERROR)
        litellm.verbose_logger.addHandler(self.capture)

    def record(self, mode, kwargs):
        params = kwargs.get('litellm_params') or {}
        info = params.get('model_info')
        append('callback-metadata', {
            'mode': mode,
            'call_type': kwargs.get('call_type'),
            'model': kwargs.get('model'),
            'model_info_type': type(info).__name__,
            'deployment_id': info.get('id') if isinstance(info, dict) else None,
            'metadata_model_group': (params.get('metadata') or {}).get('model_group'),
            'litellm_call_id': kwargs.get('litellm_call_id'),
        })

    def log_success_event(self, kwargs, response_obj, start_time, end_time):
        self.record('sync', kwargs)

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        self.record('async', kwargs)


observer = Observer()
