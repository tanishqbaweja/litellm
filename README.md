# LiteLLM Redis batch-throttle refresh verification

Evidence for [issue #34681](https://github.com/BerriAI/litellm/issues/34681), captured on 2026-10-25 UTC

Before is upstream main `dddbaa803d6e9fcc862ea7a5412f771cb1ae040e`. After is `0242f0845e76d0045e196a87b2719074e9b2daec` on `litellm_fix_34681_throttle_refresh`

The product diff changes one condition in `LimitedSizeOrderedDict.__setitem__` and adds one parametrized regression in the existing DualCache test file. Updating an existing key no longer evicts another key when the dictionary is full. Inserting a new key still evicts the oldest entry

The real Redis trace below demonstrates the bug and fix. The real model API and headed dashboard runs are compatibility controls. They do not show a UI change or establish production performance impact

## Real Redis reproduction

Redis 7.4.11 ran in an owned container using `redis@sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499`, with persistence disabled and a loopback listener on port 6386 in the QA container's network namespace. No host port was exposed. The probe ran before any proxy requests, so no other requests contributed to its command counters

[`redis-probe.py`](redis-probe.py) uses the actual `DualCache`, `RedisCache` and Redis server. It checks the imported source path, Git SHA and clean tree, uses a fresh namespace for each case, and reads Redis `INFO commandstats` around each batch read. The clock and network are real. No timestamp map is seeded or edited

The throttle expiry is 10 seconds. Each case makes these eight batch reads, with one actual 10.1-second wait between the first and second steps

| Step | Read | What it checks |
| --- | --- | --- |
| 1 | `fresh, expired` | Establish both timestamps through public batch reads |
| 2 | `fresh` | Refresh the first timestamp after expiry |
| 3 | `filler` | Fill the three-entry map |
| 4 | `expired` | Refresh a different existing entry at capacity |
| 5 | `expired` | Its immediate repeat stays throttled |
| 6 | `fresh` | The unrelated recently refreshed entry stays throttled |
| 7 | `new` | A new entry still causes eviction at capacity |
| 8 | `fresh` | The genuinely evicted entry now reaches Redis |

Every read returns the expected missing values. The command counts expose the unnecessary Redis read, which does not change those returned values. The probe also checks that steps after refreshing `fresh` finish within five seconds, inside its ten-second expiry

The exact recorded commands used the source workdir as well as `PYTHONPATH`, avoiding accidental imports from the container's default workdir

```bash
docker exec -w /opt/litellm-34927-baseline \
  -e PYTHONPATH=/opt/litellm-34927-baseline contri-litellm-47520 \
  /opt/litellm-venv/bin/python /qa/litellm-34681/redis-probe.py baseline

docker exec -w /opt/litellm-34681 \
  -e PYTHONPATH=/opt/litellm-34681 contri-litellm-47520 \
  /opt/litellm-venv/bin/python /qa/litellm-34681/redis-probe.py fixed
```

| Mode | Capacity | Before MGET counts by step | After MGET counts by step |
| --- | --- | --- | --- |
| Sync | 3 | `1,1,1,1,0,1,1,0` | `1,1,1,1,0,0,1,1` |
| Async | 3 | `1,1,1,1,0,1,1,0` | `1,1,1,1,0,0,1,1` |
| Sync | 4 | `1,1,1,1,0,0,1,0` | `1,1,1,1,0,0,1,0` |
| Async | 4 | `1,1,1,1,0,0,1,0` | `1,1,1,1,0,0,1,0` |

Step 6 reproduces the bug in both full-capacity cases before the fix. Step 8 checks that a new insertion still evicts correctly. Both spare-capacity controls remain unchanged

The full observations, timestamps and source checks are in [before/redis-report.json](before/redis-report.json) and [after/redis-report.json](after/redis-report.json). Console output is in [redis-before.log](redis-before.log) and [redis-after.log](redis-after.log)

## Live proxy and model controls

Both revisions used the same local PostgreSQL 16.10 QA database, Redis 7.4.11 and Ollama 0.40.11, with actual CPU inference from Qwen3.5-0.8B Q4_0. The exact configuration is in [config.yml](config.yml). The chat model's SHA256 is `57d1997790d1744fba5b40a7317df71ea5e2acee28c47e78f0cce39c0703f8cf`, recorded in [chat-model-verification.json](chat-model-verification.json). Binary and model metadata are included, but binaries, weights and private environment files are not

The model is registered as `qa-cache-34681`. Response caching uses the owned Redis instance and a separate response namespace. Provider retries are disabled. Configured costs are local test pricing and are not provider invoices. No external paid provider call was made

[`start-proxy.sh`](start-proxy.sh) verifies the source SHA and clean tree, then serves port 41475. [`proxy-probe.py`](proxy-probe.py) generates one temporary restricted virtual key per revision and issues 12 real requests. Each of `/v1/chat/completions`, `/v1/responses` and `/v1/messages` receives a non-streaming pair and a streaming pair, with the exact same body within each pair and a unique prompt across pairs

```bash
docker exec -d contri-litellm-47520 bash /qa/litellm-34681/start-proxy.sh baseline
docker exec -w /opt/litellm-34927-baseline \
  -e PYTHONPATH=/opt/litellm-34927-baseline contri-litellm-47520 \
  /opt/litellm-venv/bin/python /qa/litellm-34681/proxy-probe.py baseline
```

The fixed run uses `start-proxy.sh fixed`, `/opt/litellm-34681` and `proxy-probe.py fixed`, after stopping the baseline proxy. The scripts record the actual commands' request bodies and response JSON or SSE, without Authorization headers

| Endpoint | Requests per revision | Before | After |
| --- | --- | --- | --- |
| `/v1/chat/completions` | 4 | Four 200 responses, valid text/SSE | Four 200 responses, valid text/SSE |
| `/v1/responses` | 4 | Four 200 responses, valid text/SSE | Four 200 responses, valid text/SSE |
| `/v1/messages` | 4 | Four 200 responses, valid text/SSE | Four 200 responses, valid text/SSE |

Every pair returns matching nonempty generated content. Each revision persists 12 spend rows, including two `cache_hit=True` rows per endpoint. The other rows contain three explicit `False` values and three `None` strings. The reports preserve that distinction instead of treating an unset value as a verified miss

The original baseline harness expected six explicit `False` values and failed after all 12 requests had returned 200. That expectation was corrected against the observed main behavior, the original key was deleted, and the full baseline run was repeated with a fresh key. The final before and after runs both pass. This was a harness correction, with no product edit

See [before/api-report.json](before/api-report.json), [after/api-report.json](after/api-report.json), [api-before.log](api-before.log) and [api-after.log](api-after.log)

## Headed dashboard checks

Both proxies served the same unchanged production dashboard export built from `dddbaa803d6e9fcc862ea7a5412f771cb1ae040e`. Chromium 145 and Playwright 1.58.1 exercised desktop 1440x900 and phone 390x844 with touch. A new browser context was used for each viewport, with video recording enabled

```bash
docker exec -e DISPLAY=:99 \
  -e PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers \
  contri-litellm-47520 node /qa/litellm-34681/qa.cjs baseline

docker exec -e DISPLAY=:99 \
  -e PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers \
  contri-litellm-47520 node /qa/litellm-34681/qa.cjs fixed
```

The actual workflow on each revision was

1. Sign in at `http://127.0.0.1:41475/ui/login` as the local QA admin using the masked password field
2. Open `http://127.0.0.1:41475/ui/?page=llm-playground`, choose New chat and select `qa-cache-34681`
3. Enter `Reply with only: Cache works. Verification reference <unique reference>` and submit with Send message on desktop or Enter on phone
4. Check the real HTTP 200 SSE response and the complete generated answer on screen
5. Choose New chat, select the same model and submit the identical prompt, then observe the same answer and the Cached response badge

All four workflows pass before and after. Screenshots and captured text confirm the cache badge appears only for the repeat. No JavaScript exception or HTTP 5xx occurred. Both revisions produce the same existing static-prefetch/runtime-config 404 paths, 41 desktop and seven phone responses per revision

The phone layout already clips the Send control and parts of the navigation, and the assistant overlaps the composer footer. Enter submission was tested directly. The generated answer and cache badge remain visible. These existing layout issues are documented rather than presented as fixed

| Viewport | Before | After |
| --- | --- | --- |
| Desktop first response | [Screenshot](before/desktop-first.png) | [Screenshot](after/desktop-first.png) |
| Desktop repeat | [Annotated screenshot](before/desktop-repeat-annotated.png) | [Annotated screenshot](after/desktop-repeat-annotated.png) |
| Phone first response | [Screenshot](before/phone-first.png) | [Screenshot](after/phone-first.png) |
| Phone repeat | [Annotated screenshot](before/phone-repeat-annotated.png) | [Annotated screenshot](after/phone-repeat-annotated.png) |
| Desktop recording | [WebM](before/desktop.webm) | [WebM](after/desktop.webm) |
| Phone recording | [WebM](before/phone.webm) | [WebM](after/phone.webm) |

All eight raw screenshots and eight annotations were visually inspected by Codex. Eight evenly sampled frames from each of the four recordings were also inspected, rather than every video frame. The recordings retain loading, model selection, streaming and temporary toasts. Final screenshots wait for the toast to clear. [visual-review.json](visual-review.json) records inspected artifacts and hashes, and [visual-review](visual-review) contains the sampled-frame contact sheets

## Regression tests and quality gates

The new test exercises the public synchronous and asynchronous batch APIs with controlled timestamps and a Redis boundary double. It checks the complete sequence of requested keys and returned values, including refresh suppression and new-key eviction. It never edits the timestamp map directly

Both new cases fail against unmodified production code, with `2 failed, 55 deselected`. The fixed DualCache file passes all 57 tests. The final broader run passes 770 tests across the nine files listed in [affected-test-files.json](affected-test-files.json), with 64 warnings in 35.29 seconds

```bash
uv run --no-sync pytest tests/unit/caching/test_dual_cache.py \
  tests/unit/caching/test_redis_batch.py \
  tests/unit/caching/test_in_memory_cache.py \
  tests/unit/caching/test_request_redis_batch_pre_call.py \
  tests/unit/caching/test_request_redis_batch_post_call.py \
  tests/unit/proxy/auth/test_auth_checks_object_access_and_lookup.py \
  tests/unit/proxy/auth/test_auth_hot_path_network_requests.py \
  tests/unit/proxy/auth/test_object_permission_loading.py \
  tests/unit/proxy/utils/proxy_logging/test_module_helpers.py -q

make format
make lint BASE_REF=origin/main LINT_JOBS=2
```

Five targeted mutations are rejected by both parametrized cases. They restore the original eviction, disable new-key eviction, evict the newest key, allow one extra entry, or stop refreshing existing timestamps. The exact source is restored afterwards, with its SHA256 recorded in [mutation-report.json](mutation-report.json)

`make format` leaves all 2932 production files unchanged. Targeted formatting also leaves both edited files unchanged. Full `make lint` exits zero, including strict Ruff, type discipline, test quality, OpenAPI docs, import and circular-import checks. Whole-tree type checking stays within main's existing per-rule ceilings, with 105900 existing diagnostics. Separate E2E type checking reports zero errors, warnings and notes

One existing real-time TTL test failed in the first broader run, giving 769 passes and one failure. Without any code changes, it then passed individually on both main and the fix. The complete nine-file run also passed on main, with 768 tests, and on the fix, with 770 tests. The initial failure and all comparison logs are retained. The failure was not reproduced on main, and is not claimed to be a confirmed baseline defect

The baseline regressions, final results and quality gates are in [tests-baseline.log](tests-baseline.log), [tests-fixed.log](tests-fixed.log), [format.log](format.log), [targeted-format.log](targeted-format.log) and [lint.log](lint.log). The first failure is in [first-wide-test-failure.log](first-wide-test-failure.log), with comparison runs in [wide-tests-baseline.log](wide-tests-baseline.log) and [wide-tests-fixed.log](wide-tests-fixed.log)

## Cleanup and scope

All three temporary virtual keys, including the initial harness exploration, were deleted with HTTP 200. The owned proxy was stopped after validating its exact command line, and the owned Redis container was stopped after verifying its container ID. The local provider server is shared with other contribution QA and was retained

Only explicit public evidence files are included. Private key fixtures, credentials, private proxy logs, model weights and tool binaries are excluded. The published files were scanned for the known QA secrets, key values, token hashes, JWTs and private-key headers before pushing

This is bounded local verification with a small CPU model and one Redis version. It does not establish production frequency, throughput, latency improvement, all-model support or the absence of every possible regression
