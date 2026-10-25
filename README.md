# Standalone-key soft-budget alert verification

This branch holds verification artifacts for [LiteLLM #35800](https://github.com/BerriAI/litellm/issues/35800). The product PR changes four files, the evidence stays on this separate fork branch

The baseline is `dddbaa803d6e9fcc862ea7a5412f771cb1ae040e` and the fixed commit is `8c0fe877b9bbfa0a6934d8ec9373fcaf029a2082`

The stale auth object can retain zero spend after the spend counter advances. The fix reads the current key counter, uses the existing cold-cache fallback, and sends the current spend in the soft-budget warning

## Live proof

Both revisions run a normal authenticated proxy with real PostgreSQL and Redis, a real local Qwen3.5 0.8B model through Ollama 0.40.11, and a local HTTP receiver for Slack-format messages. There is no enterprise-entitlement override. Hosted Slack and paid provider calls were not tested

The proxy serves port 41479 and the local collector serves port 41480. The model alias is `qa-alert-model`, with test prices of $0.001 per input token and $0.002 per output token. The configured alert cooldown is 86400 seconds, and the normal batching interval is five seconds

The final run makes ten curl inference requests on each revision. Exact commands and redacted response bodies are in [baseline API results](reports/api-report-baseline.json) and [fixed API results](reports/api-report-fixed.json). Collector curl commands and outputs are in [baseline receiver results](reports/receiver-curl-baseline.json) and [fixed receiver results](reports/receiver-curl-fixed.json)

| Case | Initial spend | Soft budget | Final spend | Alerts before | Alerts after |
| --- | --- | --- | --- | --- | --- |
| Crossed by a request | 0 | 0.01 | 0.105 | 0 | 1 |
| Already crossed | 1 | 0.01 | 1.07 | 1 | 1 |
| Below budget | 0 | 1000 | 0.102 | 0 | 0 |
| No soft budget | 0 | unset | approximately 0.072 | 0 | 0 |

Every inference request returns HTTP 200. The crossing case waits for the first request's spend to persist before sending two more requests. The collector is checked after a 16-second batching wait. All four API-created keys are deleted

## Browser workflow

Headed Chromium 145.0.7632.6 runs through Playwright 1.58.1 at desktop 1440 × 900 and touch-phone 390 × 844. Both source revisions serve the same existing production dashboard export, verified against all 2662 tracked UI source files at the baseline. This change does not edit UI source files or claim a fresh dashboard build

1. Sign in at `http://127.0.0.1:41479/ui/login`, then open `/ui/?page=api-keys`
2. Choose **Create New Key**, name the key, and leave its team and hard budget unset
3. Open the key, select **Settings**, choose **Edit Settings**, enter `0.01` in **Soft Budget (USD)**, and save
4. Reload and verify the saved value, then send three real inference requests with the key
5. Reload **Overview** and confirm `0.117` spend. The baseline receiver gets no alert, the fixed receiver gets one
6. Change the soft budget to `1000`, save, and reload to verify persistence and preserved sibling fields
7. Choose **More key actions**, **Delete Key**, type the key alias, and confirm deletion. The row disappears and the deleted key returns HTTP 401

There are seven screenshots per viewport per revision and four recordings. All 28 screenshots and eight evenly spaced frames from each recording were visually inspected. The one-time credential reveal panel is masked, and every test key is deleted before publication

The phone workflow completes with existing header wrapping, horizontal overflow/clipping and the floating Aria control visible on both revisions. Static/runtime-config 404s remain, 98/13 desktop/phone before and 81/13 after. There are no recorded page exceptions or HTTP 5xx responses. See [visual notes](reports/visual-inspection.json) and [browser comparison](reports/browser-comparison.json)

## Regression and quality checks

The counterfactual unit run on unchanged production code has four expected failures and thirteen passes. The new real-service two-proxy integration fails at the missing alert assertion, after successful inference and persisted spend

The fixed code passes 892 selected backend unit tests, with 76 recorded warnings, and three PostgreSQL/Redis integration cases. Seven targeted mutations are detected, the exact production file is restored, and all seven focused regression cases pass again

Six selected frontend files pass 292 tests with three existing expected failures. Production TypeScript passes. Full `make format`, `make lint`, and committed-diff formatting pass. Test formatting outside the added regression was restored with AST equality verified

The integration harness scripts the external upstream response, as required by its repository instructions. The separate live API and browser proof uses actual model inference. New integration coverage runs in CircleCI on main

The [source check](reports/final-source-check.json) ties the tests and artifacts to the clean committed product tree. The [eligibility check](reports/eligibility-final.json) records the open issue, current default branch and adjacent PR review

## Artifact layout

`baseline/` and `fixed/` contain the original screenshots and recordings. `reports/` contains redacted request results, source provenance, check results and cleanup records. `logs/` contains unit, mutation, frontend and lint output, plus sanitized integration summaries. `drivers/` contains the exact local QA harnesses, which use the test environment paths recorded in their source

Both owned databases were dropped, Redis processes stopped and proxy/receiver ports closed. Earlier setup failures, harness corrections and screenshot-framing runs remain archived locally, the published live evidence is the latest complete run at each stated revision

## Authentication regression follow-up

The current product tip is `f8afcdc27d0ba7f9e2aef46521d1b7eca45d54bc`. Its only addition to the live-tested `8c0fe877b9bbfa0a6934d8ec9373fcaf029a2082` is the existing authentication regression test. Production and dashboard files match the recorded live runs byte for byte

The regression now supplies an isolated real spend counter, uses the real authentication and alerting paths, and captures the complete outbound webhook through an external HTTP transport. It checks stale and current cached spend while confirming the request remains authorized, with a controlled clock and explicit background-task cleanup

On unchanged main, the stale-spend case fails at the missing alert and the existing-current-spend case passes. The exact baseline was restored afterward. The full four-file authentication CI group passes 291 tests with 54 recorded warnings and no reruns. Full formatting, lint/type gates and committed-diff formatting pass again

See the [follow-up source and results](reports/auth-ci-followup.json), [fixture diagnosis](reports/auth-fixture-diagnosis.json), [main regression](logs/auth-followup-red.log), [full auth group](logs/auth-followup-shard.log), and [quality gates](logs/auth-followup-lint.log)
