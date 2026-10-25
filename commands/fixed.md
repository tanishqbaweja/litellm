# Captured curl requests, fixed

Source `ad971a738117785fe3ae1efb87287f6993490227`, captured 2026-10-25T23:11:53.881211+00:00

These are the actual curl arguments. Each `<QA_KEY>` replaces a private credential or a deliberately invalid bearer. Substitute the corresponding key when replaying. Response excerpts are identified below, and the report JSON preserves the full redacted responses

## create-qa42689-valid

```sh
curl \
  --silent \
  --show-error \
  --connect-timeout 3 \
  --max-time 120 \
  --request POST http://127.0.0.1:41481/key/generate \
  --header 'Authorization: Bearer <QA_KEY>' \
  --header 'Content-Type: application/json' \
  --data-binary '{"key_alias":"qa42689-valid","models":["qa-ledger-model"]}' \
  --write-out '\n__HTTP_STATUS__:%{http_code}'
```

HTTP 200

Response excerpt

```json
{
  "key": "<QA_KEY>",
  "key_alias": "qa42689-valid",
  "expires": null,
  "spend": 0.0,
  "max_budget": null
}
```

## create-qa42689-expired

```sh
curl \
  --silent \
  --show-error \
  --connect-timeout 3 \
  --max-time 120 \
  --request POST http://127.0.0.1:41481/key/generate \
  --header 'Authorization: Bearer <QA_KEY>' \
  --header 'Content-Type: application/json' \
  --data-binary '{"key_alias":"qa42689-expired","models":["qa-ledger-model"],"duration":"1s"}' \
  --write-out '\n__HTTP_STATUS__:%{http_code}'
```

HTTP 200

Response excerpt

```json
{
  "key": "<QA_KEY>",
  "key_alias": "qa42689-expired",
  "expires": "2026-10-25T23:11:55.030568Z",
  "spend": 0.0,
  "max_budget": null
}
```

## create-qa42689-budget

```sh
curl \
  --silent \
  --show-error \
  --connect-timeout 3 \
  --max-time 120 \
  --request POST http://127.0.0.1:41481/key/generate \
  --header 'Authorization: Bearer <QA_KEY>' \
  --header 'Content-Type: application/json' \
  --data-binary '{"key_alias":"qa42689-budget","models":["qa-ledger-model"],"spend":1.0,"max_budget":0.01}' \
  --write-out '\n__HTTP_STATUS__:%{http_code}'
```

HTTP 200

Response excerpt

```json
{
  "key": "<QA_KEY>",
  "key_alias": "qa42689-budget",
  "expires": null,
  "spend": 1.0,
  "max_budget": 0.01
}
```

## unknown-models

```sh
curl \
  --silent \
  --show-error \
  --connect-timeout 3 \
  --max-time 120 \
  --request GET http://127.0.0.1:41481/v1/models \
  --header 'Authorization: Bearer <QA_KEY>' \
  --write-out '\n__HTTP_STATUS__:%{http_code}'
```

HTTP 401

Response excerpt

```json
{
  "error": {
    "message": "Authentication Error, Invalid API key provided.",
    "type": "token_not_found_in_db",
    "param": "key",
    "code": "401"
  }
}
```

## unknown-chat

```sh
curl \
  --silent \
  --show-error \
  --connect-timeout 3 \
  --max-time 120 \
  --request POST http://127.0.0.1:41481/v1/chat/completions \
  --header 'Authorization: Bearer <QA_KEY>' \
  --header 'Content-Type: application/json' \
  --data-binary '{"model":"qa-ledger-model","messages":[{"role":"user","content":"Reply OK"}],"max_tokens":24}' \
  --write-out '\n__HTTP_STATUS__:%{http_code}'
```

HTTP 401

Response excerpt

```json
{
  "error": {
    "message": "Authentication Error, Invalid API key provided.",
    "type": "token_not_found_in_db",
    "param": "key",
    "code": "401"
  }
}
```

## unknown-responses

```sh
curl \
  --silent \
  --show-error \
  --connect-timeout 3 \
  --max-time 120 \
  --request POST http://127.0.0.1:41481/v1/responses \
  --header 'Authorization: Bearer <QA_KEY>' \
  --header 'Content-Type: application/json' \
  --data-binary '{"model":"qa-ledger-model","input":"Reply OK","max_output_tokens":24}' \
  --write-out '\n__HTTP_STATUS__:%{http_code}'
```

HTTP 401

Response excerpt

```json
{
  "error": {
    "message": "Authentication Error, Invalid API key provided.",
    "type": "token_not_found_in_db",
    "param": "key",
    "code": "401"
  }
}
```

## unknown-messages

```sh
curl \
  --silent \
  --show-error \
  --connect-timeout 3 \
  --max-time 120 \
  --request POST http://127.0.0.1:41481/v1/messages \
  --header 'Authorization: Bearer <QA_KEY>' \
  --header 'Content-Type: application/json' \
  --data-binary '{"model":"qa-ledger-model","messages":[{"role":"user","content":"Reply OK"}],"max_tokens":24}' \
  --write-out '\n__HTTP_STATUS__:%{http_code}'
```

HTTP 401

Response excerpt

```json
{
  "error": {
    "message": "Authentication Error, Invalid API key provided.",
    "type": "token_not_found_in_db",
    "param": "key",
    "code": "401"
  }
}
```

## malformed-models

```sh
curl \
  --silent \
  --show-error \
  --connect-timeout 3 \
  --max-time 120 \
  --request GET http://127.0.0.1:41481/v1/models \
  --header 'Authorization: Bearer <QA_KEY>' \
  --write-out '\n__HTTP_STATUS__:%{http_code}'
```

HTTP 401

Response excerpt

```json
{
  "error": {
    "message": "LiteLLM Virtual Key expected. Received=word****de1d, expected to start with 'sk-'.",
    "type": "auth_error",
    "param": "None",
    "code": "401"
  }
}
```

## malformed-chat

```sh
curl \
  --silent \
  --show-error \
  --connect-timeout 3 \
  --max-time 120 \
  --request POST http://127.0.0.1:41481/v1/chat/completions \
  --header 'Authorization: Bearer <QA_KEY>' \
  --header 'Content-Type: application/json' \
  --data-binary '{"model":"qa-ledger-model","messages":[{"role":"user","content":"Reply OK"}],"max_tokens":24}' \
  --write-out '\n__HTTP_STATUS__:%{http_code}'
```

HTTP 401

Response excerpt

```json
{
  "error": {
    "message": "LiteLLM Virtual Key expected. Received=word****1b87, expected to start with 'sk-'.",
    "type": "auth_error",
    "param": "None",
    "code": "401"
  }
}
```

## malformed-responses

```sh
curl \
  --silent \
  --show-error \
  --connect-timeout 3 \
  --max-time 120 \
  --request POST http://127.0.0.1:41481/v1/responses \
  --header 'Authorization: Bearer <QA_KEY>' \
  --header 'Content-Type: application/json' \
  --data-binary '{"model":"qa-ledger-model","input":"Reply OK","max_output_tokens":24}' \
  --write-out '\n__HTTP_STATUS__:%{http_code}'
```

HTTP 401

Response excerpt

```json
{
  "error": {
    "message": "LiteLLM Virtual Key expected. Received=word****fd9f, expected to start with 'sk-'.",
    "type": "auth_error",
    "param": "None",
    "code": "401"
  }
}
```

## malformed-messages

```sh
curl \
  --silent \
  --show-error \
  --connect-timeout 3 \
  --max-time 120 \
  --request POST http://127.0.0.1:41481/v1/messages \
  --header 'Authorization: Bearer <QA_KEY>' \
  --header 'Content-Type: application/json' \
  --data-binary '{"model":"qa-ledger-model","messages":[{"role":"user","content":"Reply OK"}],"max_tokens":24}' \
  --write-out '\n__HTTP_STATUS__:%{http_code}'
```

HTTP 401

Response excerpt

```json
{
  "error": {
    "message": "LiteLLM Virtual Key expected. Received=word****b107, expected to start with 'sk-'.",
    "type": "auth_error",
    "param": "None",
    "code": "401"
  }
}
```

## valid-inference

```sh
curl \
  --silent \
  --show-error \
  --connect-timeout 3 \
  --max-time 120 \
  --request POST http://127.0.0.1:41481/v1/chat/completions \
  --header 'Authorization: Bearer <QA_KEY>' \
  --header 'Content-Type: application/json' \
  --data-binary '{"model":"qa-ledger-model","messages":[{"role":"user","content":"Reply OK"}],"max_tokens":24}' \
  --write-out '\n__HTTP_STATUS__:%{http_code}'
```

HTTP 200

Response excerpt

```json
{
  "id": "chatcmpl-29e0ba7c-b0a0-4439-9728-04be65ae95c7",
  "model": "qa-ledger-model",
  "usage": {
    "completion_tokens": 24,
    "prompt_tokens": 12,
    "total_tokens": 36,
    "prompt_tokens_details": {
      "cached_tokens": 0
    }
  }
}
```

## expired-models

```sh
curl \
  --silent \
  --show-error \
  --connect-timeout 3 \
  --max-time 120 \
  --request GET http://127.0.0.1:41481/v1/models \
  --header 'Authorization: Bearer <QA_KEY>' \
  --write-out '\n__HTTP_STATUS__:%{http_code}'
```

HTTP 401

Response excerpt

```json
{
  "error": {
    "message": "Authentication Error - Expired Key. Key Expiry time 2026-10-25 23:11:55.030000+00:00 and current time 2026-10-25 23:12:12.641551+00:00",
    "type": "expired_key",
    "param": "sk-...f6f3",
    "code": "401"
  }
}
```

## expired-chat

```sh
curl \
  --silent \
  --show-error \
  --connect-timeout 3 \
  --max-time 120 \
  --request POST http://127.0.0.1:41481/v1/chat/completions \
  --header 'Authorization: Bearer <QA_KEY>' \
  --header 'Content-Type: application/json' \
  --data-binary '{"model":"qa-ledger-model","messages":[{"role":"user","content":"Reply OK"}],"max_tokens":24}' \
  --write-out '\n__HTTP_STATUS__:%{http_code}'
```

HTTP 401

Response excerpt

```json
{
  "error": {
    "message": "Authentication Error - Expired Key. Key Expiry time 2026-10-25 23:11:55.030000+00:00 and current time 2026-10-25 23:12:12.656406+00:00",
    "type": "expired_key",
    "param": "sk-...IE8w",
    "code": "401"
  }
}
```

## budget-chat

```sh
curl \
  --silent \
  --show-error \
  --connect-timeout 3 \
  --max-time 120 \
  --request POST http://127.0.0.1:41481/v1/chat/completions \
  --header 'Authorization: Bearer <QA_KEY>' \
  --header 'Content-Type: application/json' \
  --data-binary '{"model":"qa-ledger-model","messages":[{"role":"user","content":"Reply OK"}],"max_tokens":24}' \
  --write-out '\n__HTTP_STATUS__:%{http_code}'
```

HTTP 422

Response excerpt

```json
{
  "error": {
    "message": "Budget has been exceeded! Key=qa42689-budget (sk-...Qovw) Current cost: 1.0, Max budget: 0.01",
    "type": "budget_exceeded",
    "param": null,
    "code": "422"
  }
}
```

## user-usage-report

```sh
curl \
  --silent \
  --show-error \
  --connect-timeout 3 \
  --max-time 120 \
  --request GET 'http://127.0.0.1:41481/user/daily/activity/aggregated?start_date=2026-10-25&end_date=2026-10-25' \
  --header 'Authorization: Bearer <QA_KEY>' \
  --write-out '\n__HTTP_STATUS__:%{http_code}'
```

HTTP 200

Response excerpt

```json
{
  "metadata": {
    "total_spend": 0.06,
    "total_flat_cost": 0.0,
    "total_ptu_hours": 0.0,
    "total_prompt_tokens": 12,
    "total_completion_tokens": 24,
    "total_tokens": 36,
    "total_api_requests": 4,
    "total_successful_requests": 1,
    "total_failed_requests": 3,
    "total_cache_read_input_tokens": 0,
    "total_cache_creation_input_tokens": 0,
    "total_compression_saved_tokens": 0,
    "total_compression_savings_spend": 0.0,
    "total_prompt_caching_savings_spend": 0.0,
    "total_gateway_injected_caching_savings_spend": 0.0,
    "total_autorouter_savings_spend": 0.0,
    "total_response_time_ms": 18148,
    "total_timed_requests": 1,
    "page": 1,
    "total_pages": 1,
    "has_more": false,
    "api_key_limit": 100,
    "total_api_keys": 3,
    "entity_total_api_keys": null
  }
}
```

## team-usage-report

```sh
curl \
  --silent \
  --show-error \
  --connect-timeout 3 \
  --max-time 120 \
  --request GET 'http://127.0.0.1:41481/team/daily/activity/aggregated?start_date=2026-10-25&end_date=2026-10-25' \
  --header 'Authorization: Bearer <QA_KEY>' \
  --write-out '\n__HTTP_STATUS__:%{http_code}'
```

HTTP 200

Response excerpt

```json
{
  "metadata": {
    "total_spend": 0.06,
    "total_flat_cost": 0.0,
    "total_ptu_hours": 0.0,
    "total_prompt_tokens": 12,
    "total_completion_tokens": 24,
    "total_tokens": 36,
    "total_api_requests": 4,
    "total_successful_requests": 1,
    "total_failed_requests": 3,
    "total_cache_read_input_tokens": 0,
    "total_cache_creation_input_tokens": 0,
    "total_compression_saved_tokens": 0,
    "total_compression_savings_spend": 0.0,
    "total_prompt_caching_savings_spend": 0.0,
    "total_gateway_injected_caching_savings_spend": 0.0,
    "total_autorouter_savings_spend": 0.0,
    "total_response_time_ms": 18148,
    "total_timed_requests": 1,
    "page": 1,
    "total_pages": 1,
    "has_more": false,
    "api_key_limit": 100,
    "total_api_keys": 3,
    "entity_total_api_keys": {
      "Unassigned": 3
    }
  }
}
```

## operator-request-logs

```sh
curl \
  --silent \
  --show-error \
  --connect-timeout 3 \
  --max-time 120 \
  --request GET 'http://127.0.0.1:41481/spend/logs/ui?start_date=2026-10-25+00%3A00%3A00&end_date=2026-10-25+23%3A59%3A59&page=1&page_size=50' \
  --header 'Authorization: Bearer <QA_KEY>' \
  --write-out '\n__HTTP_STATUS__:%{http_code}'
```

HTTP 200

Response excerpt

```json
{
  "total": 4,
  "page": 1,
  "page_size": 50,
  "total_pages": 1
}
```
