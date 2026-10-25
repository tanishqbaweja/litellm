# Generic Guardrail API connection fields

Evidence for [LiteLLM #34927](https://github.com/BerriAI/litellm/issues/34927), captured on 2026-10-25

Before source is `dddbaa803d6e9fcc862ea7a5412f771cb1ae040e`, the current upstream main when reproduced. After source is `81a5dc0ae2e18cb19e9f9f29a8a92d8e723bd533`. The upstream change contains only the configuration fields and an endpoint regression test. This evidence branch is separate from the product branch

## Environment and scope

Chromium drove the production dashboard at `http://127.0.0.1:41475/ui/guardrails/` against the actual Python proxy and PostgreSQL. Both source revisions served the same unmodified production dashboard export built from the before commit. Viewports were 1440x900 desktop and 390x844 with mobile and touch emulation

The guardrail service was the included local HTTP fixture on port 51476. It checks `x-api-key`, returns the supplied text for an allowed request, and blocks text containing `qa-blocked-34927`. This exercises the configuration UI, persistence and real HTTP dispatch without an external guardrail vendor or LLM inference call. No browser requests were intercepted, and no application state or styles were injected

All names and keys in the recordings are local QA fixtures. The red environment-login banner is produced by the repository's local proxy configuration

## Reproduce by hand

Run `python generic-guardrail-service.py` in the same network namespace as the proxy, with an empty `service-events.jsonl` beside it. The included browser driver records the exact assertions and original workspace paths used for the capture. It expects the local admin credential through `LITELLM_MASTER_KEY`

1. Sign in and open `/ui/guardrails/`, then choose Add New Guardrail and Add Provider Guardrail
2. Enter `qa-generic-34927-desktop` or `qa-generic-34927-phone` and choose Generic Guardrail API
3. On the before revision, scroll through Basic Info and observe that URL and API-key inputs are absent. Next opens the existing Provider Configuration step, where optional parameters already render
4. On the after revision, enter `http://127.0.0.1:51476` in `api_base` and `qa-generic-local-key` in `api_key`. The key remains masked. Click Next and Create Guardrail
5. In Test Playground, select the new guardrail. Test ordinary text and text containing `qa-blocked-34927`. The first succeeds and the second displays the fixture's blocked reason
6. Open the guardrail's Settings and Edit Settings. Change the URL to `http://127.0.0.1:51476/updated` and the key to `qa-generic-updated-key`, then Save Changes
7. Repeat both Playground requests. They reach the updated endpoint with its matching key and produce the same allowed and blocked results

## Observed results

Both before runs confirm the missing inputs. Both after runs pass creation, saved-value readback, edit, saved-value readback and four Playground requests. The after reports contain eight authenticated service events in total, four using the initial URL and four using the updated URL. The temporary guardrails were deleted after each run

The new connection inputs fit inside both viewports and the key stays masked in create and edit forms. All 22 raw screenshots and eight evenly sampled frames from each of the four recordings were visually inspected

There were no uncaught browser exceptions or HTTP 5xx responses. The blocked checks intentionally return HTTP 400 and log the blocked reason. Both revisions log existing static-prefetch/runtime-config HTTP 404s. The separate optional-parameters step has existing horizontal overflow at phone width, visible before and after. These captures do not claim that unrelated layout is fixed

## Media and reports

| Case | Before | After |
| --- | --- | --- |
| Desktop connection fields | [Screenshot](desktop-before.png) | [Screenshot](desktop-after.png) |
| Phone connection fields | [Screenshot](phone-before.png) | [Screenshot](phone-after.png) |
| Desktop workflow | [Recording](desktop-before.webm) | [Recording](desktop-after.webm) |
| Phone workflow | [Recording](phone-before.webm) | [Recording](phone-after.webm) |

The red rectangles highlight the before form and the added inputs. Unannotated originals are in `raw/`. The [before report](before-report.json) and [after report](after-report.json) include source hashes, viewport settings, observed errors, steps and service events. Their recording names refer to the original capture folders, copied here under the readable names above

## Tests and quality gates

The two new cases in `test_provider_specific_params_exposes_generic_guardrail_connection_fields` failed on unchanged main with missing `api_base` and `api_key`. After the fix, the following affected backend files pass, 251 tests with 33 warnings

```sh
python -m pytest -q tests/unit/proxy/guardrails/test_guardrail_endpoints.py tests/unit/proxy/guardrails/guardrail_hooks/test_generic_guardrail_api.py
```

Six affected frontend test files pass, 93 tests and no type errors, covering `add_guardrail_form`, `guardrail_info`, `guardrail_provider_fields` and `guardrail_info_helpers`, including the two characterization files. The full frontend suite was left to CI, following the contributor guide

`make lint BASE_REF=origin/main LINT_JOBS=2` passes. This includes formatting, Ruff, type discipline, test quality, OpenAPI documentation, E2E and harness type checks, circular imports, import safety and the repository's basedpyright budget gate. The latter accepts existing diagnostics within its ceilings and does not mean the whole codebase has zero type errors. Changed-file formatting and `git diff --check` also pass

Python was 3.12.13 on Linux, uv was 0.10.9 and the browser driver used Node 24.21.0 on Windows. No UI source changed in this PR, and the dashboard export was reused rather than rebuilt for this backend-only change

The initial upstream CI run failed an existing tokenizer event-loop timing assertion in `test_token_counter_loads_a_custom_tokenizer_off_the_event_loop`, with 4328 other tests passing in that shard. Running that exact test locally also fails on unchanged main and on the PR. Neither the test, its timing helper nor its proxy implementation changes here. The after revision adds an empty commit to retry CI, and this browser evidence was refreshed for that revision. OSV also reports the same three dependency advisories as unchanged main, tracked separately in upstream PR #48302
