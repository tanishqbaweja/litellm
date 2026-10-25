# LiteLLM environment-based deployment weight verification

Evidence for [issue #36095](https://github.com/BerriAI/litellm/issues/36095), captured on 2026-10-25 UTC

Before is upstream main `dddbaa803d6e9fcc862ea7a5412f771cb1ae040e`. After is `828228e0d2894d2b3f2091dc00d9aab9cf9fe9ee` on `litellm_fix_36095_numeric_weights`

The fix declares `weight` as an optional float in `GenericLiteLLMParams`. Environment substitution already happens before model validation, but an undeclared weight survives as an unvalidated extra string. Current main rejects that value at request time with `Deployment weight must be numeric`

The declaration uses the existing validation boundary to accept integer and fractional numeric strings, zero and explicit null. A malformed value such as `heavy` fails validation before routing. RPM and TPM are already declared numeric on current main and already work. They are compatibility controls, not additional fixes claimed by this PR

The complete [product diff](product.diff) contains that one production declaration, regression tests in the existing mapped test file, and four generated dashboard schema lines. Regenerating the OpenAPI snapshot leaves it unchanged

## Real proxy reproduction

Both revisions use the same local PostgreSQL 16.10 database and Ollama 0.40.11 provider, with actual CPU inference from Qwen3.5-0.8B Q4_0. The GGUF SHA256 is `57d1997790d1744fba5b40a7317df71ea5e2acee28c47e78f0cce39c0703f8cf`, recorded in [chat-model-verification.json](chat-model-verification.json). Binary and model metadata are included, but weights, binaries and private environment files are excluded

Each group in [config.yml](config.yml) has two valid deployments of the same real provider model. The first has a positive weight or rate and an ID ending in `-preferred`. The second has zero weight or rate and an ID ending in `-zero`. Each successful response must identify the preferred deployment in `x-litellm-model-id`, so an arbitrary successful response is insufficient

| Group | Input values | Before | After |
| --- | --- | --- | --- |
| `qa-weight-int-36095` | Environment weights `100` and `0` | Strings, requests fail | Floats `100.0` and `0.0`, preferred deployment selected |
| `qa-weight-frac-36095` | Environment weights `1.5` and `0` | Strings, requests fail | Floats `1.5` and `0.0`, preferred deployment selected |
| `qa-weight-numeric-36095` | Literal weights `1.5` and `0` | Preferred deployment selected | Preferred deployment selected |
| `qa-weight-none-36095` | Null weights, literal RPM `1000000` and `0` | RPM routing works | RPM routing works |
| `qa-rpm-env-36095` | Environment RPM `1000000` and `0` | Integers, preferred deployment selected | Integers, preferred deployment selected |
| `qa-tpm-env-36095` | Environment TPM `1000000` and `0` | Integers, preferred deployment selected | Integers, preferred deployment selected |

[`start-proxy.sh`](start-proxy.sh) checks the imported source path, exact Git SHA and clean tree before starting port 41475. It sets the environment values and disables retries. [`api-probe.py`](api-probe.py) checks the running proxy's PID, working directory and command line after readiness, creates one restricted temporary virtual key, and records the normalized model configuration

The probe sends six groups through each of three text endpoints, with streaming both disabled and enabled. There are 36 actual requests per revision, with no mocked requests or model responses

```bash
docker exec -d contri-litellm-47520 \
  bash /qa/litellm-36095/start-proxy.sh baseline

docker exec -w /opt/litellm-34927-baseline \
  -e PYTHONPATH=/opt/litellm-34927-baseline contri-litellm-47520 \
  /opt/litellm-venv/bin/python /qa/litellm-36095/api-probe.py baseline
```

The fixed run uses `start-proxy.sh fixed`, `/opt/litellm-36095` and `api-probe.py fixed`, after stopping the baseline proxy. The private QA environment supplies the database and master key. It is not part of this evidence branch

| Endpoint | Requests per revision | Before | After |
| --- | --- | --- | --- |
| `/v1/chat/completions` | 12 | Four expected 500s, eight 200s | Twelve 200s |
| `/v1/responses` | 12 | Four expected 500s, eight 200s | Twelve 200s |
| `/v1/messages` | 12 | Four expected 500s, eight 200s | Twelve 200s |

Before, every environment-weight request returns 500 with `Deployment weight must be numeric`. All 24 controls return 200. After, all 36 requests return 200, contain real nonempty generated text or valid SSE, and identify the intended positive-weight deployment

Exact request bodies, JSON or SSE responses, selected deployment headers, model parameter types and provider metadata are in [before/api-report.json](before/api-report.json) and [after/api-report.json](after/api-report.json). Authorization headers and key material are excluded. Console results are in [api-before.log](api-before.log) and [api-after.log](api-after.log)

An initial fixed-run source guard compared the new source manifest with the old PID file before startup finished. It stopped before creating a key or sending requests. The harness now writes the PID before atomically publishing the source manifest and checks the live PID after readiness. The final fixed run above completed normally. The original guard and failure log are retained in [harness-history](harness-history)

## Headed dashboard checks

Both proxies serve the same unchanged production dashboard export built from `dddbaa803d6e9fcc862ea7a5412f771cb1ae040e`. The generated declaration file has no runtime JavaScript changes. Chromium 145 and Playwright 1.58.1 exercise desktop 1440x900 and phone 390x844 with touch, using a new browser context and video recording for each viewport

```bash
docker exec -e DISPLAY=:99 \
  -e PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers \
  contri-litellm-47520 /opt/contri-node/bin/node \
  /qa/litellm-36095/qa.cjs baseline

docker exec -e DISPLAY=:99 \
  -e PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers \
  contri-litellm-47520 /opt/contri-node/bin/node \
  /qa/litellm-36095/qa.cjs fixed
```

The actual workflow on each viewport and revision was

1. Sign in at `http://127.0.0.1:41475/ui/login` as the local QA admin using the masked password field
2. Open `http://127.0.0.1:41475/ui/?page=llm-playground`, choose New chat and select `qa-weight-frac-36095`
3. Enter `Reply with only: Weights work. Verification reference <unique reference>` and submit with Send message on desktop or Enter on phone
4. Observe the error on main or the real generated answer after the fix
5. Choose New chat, select `qa-weight-numeric-36095`, submit another prompt and confirm that the numeric control still succeeds

On main, both environment-weight actions show the 500 error card. Each action sends three HTTP requests because the dashboard client retries twice, independently of the proxy's disabled provider retries. The numeric control succeeds once per viewport. That is four user actions and eight HTTP responses, comprising six 500s and two 200s

After the fix, all four actions succeed on their first request. Each response identifies the preferred deployment, has valid nonempty SSE content, and the complete generated text appears on screen. No error card or JavaScript exception occurs

The same static-prefetch and runtime-config 404 paths appear before and after. Desktop counts are 26 before and 41 after, while phone counts are seven on each revision. These are recorded rather than described as a clean browser console. There are no new failing paths and no unexpected HTTP 5xx

The phone layout already clips navigation and composer controls, partly hides the user prompt under the sticky toolbar, and overlaps the footer with the Aria launcher. Enter submission is tested directly. The generated answer and selected group remain visible. This PR does not change that layout

| Viewport | Before | After |
| --- | --- | --- |
| Desktop environment weight | [Annotated screenshot](before/desktop-environment-annotated.png) | [Annotated screenshot](after/desktop-environment-annotated.png) |
| Desktop numeric control | [Screenshot](before/desktop-numeric-control.png) | [Screenshot](after/desktop-numeric-control.png) |
| Phone environment weight | [Annotated screenshot](before/phone-environment-annotated.png) | [Annotated screenshot](after/phone-environment-annotated.png) |
| Phone numeric control | [Screenshot](before/phone-numeric-control.png) | [Screenshot](after/phone-numeric-control.png) |
| Desktop recording | [WebM](before/desktop.webm) | [WebM](after/desktop.webm) |
| Phone recording | [WebM](before/phone.webm) | [WebM](after/phone.webm) |

All eight raw screenshots and eight annotations were visually inspected by Codex. Eight evenly sampled frames from each of the four recordings were also inspected, rather than every video frame. The recordings retain loading, streaming and temporary toasts. Final screenshots wait for the toast to clear. [visual-review.json](visual-review.json) records inspected artifacts and hashes, and [visual-review](visual-review) contains the sampled-frame contact sheets

The first baseline browser harness stalled while awaiting the retried 500 response body even though the page had rendered the error. An actual display screenshot confirmed the visible state. The owned worker was stopped, and the final harness was rerun fully on both viewports. It checks the visible error and all retry statuses without reading the failed browser response bodies. The separate API probe verifies those error bodies. Successful browser SSE bodies are read with a bounded timeout. The original harness and diagnostic are retained in [harness-history](harness-history)

## Regression tests and quality gates

The added tests construct the actual parameter model and call `simple_shuffle`, with no network, clock or collaborator doubles. A positive value paired with zero makes the selected deployment deterministic. Cases include fractional strings, mixed strings and numeric values, zero, null-weight fallback to RPM, RPM and TPM string controls, and malformed-weight validation

Against unmodified production code, the new cases report four failures and four passes. The fixed focused run passes all 110 tests in the types and simple-shuffle files. The broader ten-file run passes 888 tests with 24 warnings in 24.03 seconds. The full file list is in [backend-regression.json](backend-regression.json)

```bash
uv run --no-sync pytest tests/unit/types/test_router.py \
  tests/unit/router_strategy/test_simple_shuffle.py \
  tests/unit/test_router_weighted_failover.py \
  tests/unit/test_router_order_fallback.py \
  tests/unit/test_router_model_cost_isolation.py \
  tests/unit/test_router_get_settings.py \
  tests/unit/test_litellm_params_reserved_keys.py \
  tests/unit/test_router/test_enforce_model_rate_limits.py \
  tests/unit/test_router/test_io_token_rate_limits.py \
  tests/unit/test_router/test_router_get_deployments.py -q

make format
make lint BASE_REF=origin/main LINT_JOBS=2
```

Five targeted mutations remove the field, allow only integers, preserve unconverted strings, reject zero or reject explicit null. The regression tests reject them with 4, 2, 4, 4 and 1 failed cases respectively. The exact production source is restored afterward, with its SHA256 recorded in [mutation-report.json](mutation-report.json)

`make format` leaves all 2932 production files unchanged. Targeted formatting leaves both Python files unchanged. Full `make lint` exits zero, including strict Ruff, type discipline, test quality, OpenAPI docs, imports and circular imports. Whole-tree type checking stays within main's per-rule ceilings, with 105900 existing diagnostics. Separate E2E type checking reports zero errors, warnings and notes

The dashboard's generated API declarations were regenerated from the fixed proxy schema and regenerated again after the product commit. The second generation leaves the committed tree unchanged. The four-file affected UI run passes 190 tests with four expected failures on Linux, and eight type tests pass. Production TypeScript, changed-file formatting, the CI lint-budget gate and the dead-code gate pass

Two PTU error-message tests fail on this Windows machine's existing `en-IN` number formatting, which renders `10,00,000` where the tests expect `1,000,000`. Both failures were reproduced against the exact unchanged-main dashboard source, with 188 passes and four expected failures. The fixed schema was restored byte for byte afterward. The same four files pass on Linux with `en-US`. No general Windows pass is claimed

Raw ESLint exits 2 because of existing stale suppressions, while producing a valid report over 2442 files with zero fatal errors. The repository's CI treats that command as a report producer and enforces the separate budget check. Every budget passes without changing suppressions or budgets. The generated declaration file is ignored by the formatter and ESLint, and is verified through regeneration and TypeScript instead

The exact fixed dashboard source is also copied into an isolated Linux build directory with its locked dependencies, so the dependency symlink does not cross Turbopack's root. All 2662 tracked files are verified against the source. `npm run build` exits zero, including production TypeScript and generation of all 58 static pages, without changing any tracked file. Turbopack reports one warning that the existing AVIF logo is emitted without optimization. [ui-build.json](ui-build.json) and [ui-build.log](ui-build.log) record the result and source hashes

Test logs, mutation logs, frontend platform comparisons and all gate reports are included alongside this README. The complete unit suite is left to CI, following the repository's instruction to run only affected files locally

## Cleanup and scope

Both temporary virtual keys were deleted with HTTP 200. The owned proxy was stopped after checking its exact command line. The shared local provider server was retained for subsequent contribution QA

Only explicit evidence files are published. Private key fixtures, credentials, raw proxy logs, model weights, dependency directories and tool binaries are excluded. Published files are checked for the known QA secrets, temporary keys and hashes, JWTs and private-key headers before pushing

This verification uses a small local CPU model. No external paid provider request was made, and displayed costs use local test pricing. It does not establish production throughput, latency improvement, statistical routing proportions, all-provider support or the absence of every possible regression
