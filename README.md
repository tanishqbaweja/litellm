# LiteLLM #26170: explicit Ollama API base precedence

An explicit Ollama URL was overridden by the global `litellm.api_base`. This evidence uses real local model servers, the real proxy with PostgreSQL, and headed Chromium against the production dashboard. No live upstream or browser responses were mocked

- Before: `dddbaa803d6e9fcc862ea7a5412f771cb1ae040e`
- After: `f548922490cbbd5d9d519671e858a8ddb127ed04`
- Same unchanged production dashboard export from main for both revisions
- Exact results and limits: [checks.json](checks.json)
- Complete three-file change: [product.diff](product.diff)

## Observed behavior

The explicit URL is `http://127.0.0.1:11434`, served by Ollama. The conflicting global URL is `http://127.0.0.1:51476/v1`, served by a real OpenAI-compatible llama.cpp server. Sending Ollama-native paths to that global server returns HTTP 404. Both server configurations are retained

| Case | Main | Fixed |
| --- | --- | --- |
| Six SDK calls with an explicit URL, across sync/async generate, chat and embedding | Six HTTP 404 errors | Six successful native model responses |
| 24 SDK controls using global, empty-explicit, environment and default configuration | All succeed | All succeed |
| `/v1/chat/completions`, both Ollama providers, streaming and non-streaming | Four HTTP 404 errors | Four HTTP 200 responses with generated text |
| `/v1/responses`, both providers, streaming and non-streaming | Four HTTP 404 errors | Four HTTP 200 responses with generated text |
| `/v1/messages`, both providers, streaming and non-streaming | Four HTTP 404 errors | Four HTTP 200 responses with generated text |
| `/v1/embeddings` with `hello` | HTTP 404 | HTTP 200, 1024 dimensions, exact match to direct Ollama control |
| Playground, both providers on desktop and phone | Four visible request-failed errors | Four visible `Routing works.` replies |

The unit regression covers the same five URL configurations at the HTTP boundary. Six cases fail on unmodified main and 24 controls pass. All 757 tests across eight affected files pass after the fix and after restoring each deliberate mutation

## Browser evidence

Sign in at `http://127.0.0.1:41475/ui/login`, open `/ui/?page=llm-playground`, start a new chat, select `qa-ollama-chat-26170`, and submit `Reply with only: Routing works.`. Repeat with `qa-ollama-generate-26170`. Desktop uses the Send message button. Phone uses Enter in the message field because the existing narrow layout clips the send button

| Viewport and provider | Before | After |
| --- | --- | --- |
| Desktop chat | [screenshot](before/desktop-chat-annotated.png) | [screenshot](after/desktop-chat-annotated.png) |
| Desktop generate | [screenshot](before/desktop-generate-annotated.png) | [screenshot](after/desktop-generate-annotated.png) |
| Phone chat | [screenshot](before/phone-chat-annotated.png) | [screenshot](after/phone-chat-annotated.png) |
| Phone generate | [screenshot](before/phone-generate-annotated.png) | [screenshot](after/phone-generate-annotated.png) |
| Desktop recording | [before](before/desktop.webm) | [after](after/desktop.webm) |
| Phone recording | [before](before/phone.webm) | [after](after/phone.webm) |

All eight raw screenshots, eight annotated screenshots and eight sampled frames from each of four recordings were visually inspected. This is sampled video review, not a claim to have reviewed every frame. [Visual review with file hashes](visual-review.json) and [sampled-frame contact sheets](visual-review/) preserve what was inspected

Desktop is 1440x900. Phone is 390x844 with touch enabled. Both models fail visibly before and generate a real reply after. The fixed desktop trace shows the explicit Ollama URL, correct native model, zero retries and zero fallbacks. Browser assertions check real response bodies, SSE contents and rendered text

No JavaScript exceptions or HTTP 5xx responses occurred. Existing static/runtime-config 404s remain. Desktop has 43 failures before, including the two expected inference errors, and 33 after. Phone has nine before, including the two expected inference errors, and seven after. There are no new failing paths. The pre-existing phone endpoint selector clipping and assistant overlap remain

The production dashboard source did not change. The same shared QA PostgreSQL database was used for both revisions. It contains unrelated fallback aliases from earlier work, named in the baseline error message, but no fallback exists for these three Ollama aliases. The tested requests use the real servers above and retries are disabled

## Runtime and model reproduction

- Ollama `0.40.11`, Linux amd64, CPU inference
- Chat: `ggml-org/Qwen3.5-0.8B-GGUF`, revision `807dfd9a6fadbf703207aac3bfb0b2b3040d077c`, file `Qwen3.5-0.8B-Q4_0.gguf`
- Chat SHA256: `57d1997790d1744fba5b40a7317df71ea5e2acee28c47e78f0cce39c0703f8cf`, 563036064 bytes
- Embedding: `qwen3-embedding:0.6b`, Q8_0, 1024 dimensions
- Embedding manifest digest: `ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d`
- Embedding model blob: `06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439`, 639150592 bytes
- PostgreSQL 16.10, Python 3.12.13, Playwright 1.58.1, Chromium 145.0.7632.6

[Ollama release verification](ollama-binary-verification.json), [chat model download and checksum](chat-model-verification.json), [embedding manifest](model-manifest-verification.json), and [actual `/api/tags` output](live-models.json) pin the downloaded runtime and weights. No binaries, model weights or credentials are included

Start Ollama using [start-ollama.sh](start-ollama.sh). Import the GGUF using [Modelfile](Modelfile) and pull the embedding model as in [setup-models.py](setup-models.py). That setup script checks the chat file SHA256 and saves direct native chat and embedding controls. The imported chat model is `qa-qwen3.5-0.8b`. Start the separate llama.cpp b11669 server using [start-global-server.sh](start-global-server.sh)

Start LiteLLM with [config.yml](config.yml), `DATABASE_URL` pointing at a local PostgreSQL database and a private `LITELLM_MASTER_KEY`. [start-proxy.sh](start-proxy.sh) selects the baseline or fixed product checkout through `PYTHONPATH` and serves the same dashboard export. The paths in these scripts describe the actual container layout and can be adapted for a fresh checkout

The dashboard's configured rate is `$0.000001/token` for input and output. The displayed costs are local test accounting, not provider invoices. This is routing verification, not a speed, model-quality or general platform-support benchmark

## SDK reproduction

Run the actual [sdk-probe.py](sdk-probe.py) against each clean source revision:

```sh
PYTHONPATH=/opt/litellm-34927-baseline python sdk-probe.py baseline
PYTHONPATH=/opt/litellm-26170 python sdk-probe.py fixed
```

The script asserts the imported source directory, exact Git SHA and clean tree, then executes 30 real calls per revision. It checks generated text, usage, 1024-dimensional embeddings and equality with a direct native embedding control

- [Before SDK results](before/sdk-report.json), [actual outbound HTTP URLs](before/sdk-http.log)
- [After SDK results](after/sdk-report.json), [actual outbound HTTP URLs](after/sdk-http.log)

## Proxy reproduction

[proxy-probe.py](proxy-probe.py) sends the 13 exact payloads recorded in the [before API report](before/api-report.json) and [after API report](after/api-report.json). It creates a temporary virtual key. Keep its generated private fixture file private and delete that key after verification. Both keys from this run were deleted successfully: [before cleanup](before/key-cleanup.json), [after cleanup](after/key-cleanup.json)

For example, with a temporary virtual key in `LITELLM_TEST_KEY`:

```sh
curl http://127.0.0.1:41475/v1/embeddings \
  -H "Authorization: Bearer $LITELLM_TEST_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"model":"qa-ollama-embed-26170","input":"hello"}'
```

Main returns HTTP 404 with an Ollama not-found error. The fixed revision returns HTTP 200 and a 1024-dimensional vector identical to the direct Ollama control, maximum absolute difference `0.0`

The three text endpoints each have their own four cases: two native Ollama providers, each with `stream: false` and `stream: true`. The fixed reports retain full native JSON or SSE, nonempty generated text and relevant proxy response headers

## Browser reproduction

[qa.cjs](qa.cjs) drives headed Chromium through the real login and Playground flows, including both provider aliases. It expects the repository's Playwright installation at `/repo/tests/e2e/ui/node_modules`, a running proxy at port 41475, and the test master key in the environment

```sh
DISPLAY=:99 PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers node qa.cjs baseline
DISPLAY=:99 PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers node qa.cjs fixed
```

The baseline capture must run against the baseline proxy and the fixed capture against the fixed proxy. Latest reports: [before](before/browser-report.json), [after](after/browser-report.json). The final baseline screenshot rerun happened after the fixed screenshot rerun to remove transient toasts from both sets. Each capture uses its recorded unchanged source revision

## Code validation

```sh
python -m pytest -q --tb=short tests/unit/test_main.py \
  -k test_ollama_requests_respect_api_base_precedence

python -m pytest -q --tb=short \
  tests/unit/test_main.py \
  tests/unit/litellm_core_utils/test_get_llm_provider_logic.py \
  tests/unit/llms/ollama

make format
make lint BASE_REF=origin/main LINT_JOBS=2
git diff --check origin/main...HEAD
```

- [Baseline new regression](tests-baseline.log): six fail, 24 pass, 535 deselected
- [Final affected tests](tests-fixed.log): **757 passed**, 73 warnings, 12.29 seconds
- [Four deliberate mutations](mutation-report.json): each rejected, exact source restored, then all 757 tests pass again
- [Production formatting](format.log): 2932 files unchanged
- [Full lint and quality gates](lint.log): exit zero, including strict rules, test quality, imports, OpenAPI documentation, type budgets and separate E2E types
- Whole-tree type checking remains within main's existing budget, 105900 diagnostics. Separate E2E types report zero errors

The initial broad test attempt lacked optional `tenacity`. Its locked version 8.5.0 was installed with the `uv.lock` SHA256 in [qa-extra-requirements.txt](qa-extra-requirements.txt), then all affected tests passed. [Dependency installation log](extra-test-dependency.log)

The format log also records an initial whole-file test reformat. Those unrelated existing formatting edits were discarded before the product commit. Only the new, formatted 64-line regression remains. Full final `make lint` and diff checks pass. No baseline lint/type budgets were raised

The separate Ollama `/api/show` URL forwarding issue tracked by PR #37062 is outside this fix. CI and review status are recorded on the product PR, separately from these local results
