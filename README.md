# LiteLLM issue 35459 verification

The change normalizes null deployment metadata before reading its ID in both cost-routing success handlers

Baseline `dddbaa803d6e9fcc862ea7a5412f771cb1ae040e`

Fixed `cf5082d8077212669b8cb91f2cc3c814007f02e8`

The complete product diff is [product.diff](product.diff), containing two production-line changes and eight regression cases in the existing mapped test file

## Results

| Check | Baseline | Fixed |
| --- | --- | --- |
| Eight new unit cases | Null sync and async cases fail, six controls pass | All eight pass, with all 11 existing mapped tests |
| Real SDK requests | Two null-metadata AttributeErrors, successful responses | Zero targeted errors, successful responses |
| Valid routed SDK control | Exactly one RPM and 27 TPM | Exactly one RPM and 27 TPM |
| Aggregate MCP tool listing and calls | Three null-metadata AttributeErrors, tools return 42 | Zero targeted errors, tools still return 42 |
| Three text endpoints, both streaming modes | Six successful real responses | Six successful real responses |
| Desktop and phone browser actions | Four successful actions, two MCP callback errors | Four successful actions, zero targeted errors |

The broader eight-file test run and complete quality-gate results are recorded in [checks.json](checks.json) with their full logs

## Runtime

Real Ollama 0.40.11, local CPU Qwen3.5-0.8B Q4_0, PostgreSQL 16.10, Python 3.12.13, official MCP SDK 2.3.0, headed Chromium 145.0.7632.6 and Playwright 1.58.1

The model and Ollama provenance files include the downloaded artifact hashes. The [Modelfile](Modelfile) sets a 1024-token context, and the request parameters disable reasoning. The exact routing and MCP configuration is [config.yml](config.yml)

Current main registers this handler for `cost-based-routing`, so that is the strategy used here. The issue title mentions `usage-based-routing-v2`, but this evidence does not claim that strategy currently registers the same handler

The observer records callback metadata and exceptions from `lowest_cost.py`. It does not replace the handler, intercept network requests or fabricate provider responses. Model calls run through real Ollama, and MCP calls run through the official HTTP client and a real local math server

## Reproduction

The scripts expect this QA directory at `/qa/litellm-35459`, the baseline checkout at `/opt/litellm-34927-baseline`, the fixed checkout at `/opt/litellm-35459`, and the Python environment at `/opt/litellm-venv`. Install the repository lockfile, proxy and E2E development groups, and its locked `semantic-router` extra. These absolute paths are verification-environment paths, not product configuration changes

Provide your own `LITELLM_MASTER_KEY` and `DATABASE_URL` in the environment. Set `UI_USERNAME=admin` and `UI_PASSWORD` to the same local test secret as the master key for this harness. Start the verified local Ollama model at port 11434 and the math server with `python math-server.py` on port 41476. The [startup helper](start-math.py) records the math server PID

For each revision, use the matching checkout as both the working directory and `PYTHONPATH`. `start-proxy.sh baseline` or `start-proxy.sh fixed` verifies the complete Git SHA and clean tree before starting the proxy on port 41475. Both revisions serve the exact same unchanged production dashboard export from the baseline

1. Run `python /qa/litellm-35459/sdk-probe.py baseline` or `fixed` for direct synchronous and asynchronous completions and the routed counter control
2. Start the matching proxy with `bash /qa/litellm-35459/start-proxy.sh baseline` or `fixed`
3. Run `python /qa/litellm-35459/mcp-probe.py baseline` or `fixed` to initialize the official client at `http://127.0.0.1:41475/mcp/`, list tools, add 17 and 25, and multiply 6 and 7
4. Run `python /qa/litellm-35459/api-probe.py baseline` or `fixed` for all three text endpoints, each with streaming disabled and enabled
5. With `DISPLAY=:99` and the installed Playwright Chromium path, run `node /qa/litellm-35459/qa.cjs baseline` or `fixed` for fresh browser logins, streamed Playground requests and the Admin MCP tool
6. Run `python /qa/litellm-35459/cleanup.py baseline` or `fixed`, then `python /qa/litellm-35459/stop-proxy.py` before switching revisions

The API probe creates an owned virtual key and stores it in a private local file. Those files, credentials, raw proxy logs and authentication storage are excluded from this evidence branch. Both keys were deleted with HTTP 200 after verification

The MCP test server exposes `add` and `multiply` via real HTTP. The proxy lists them as `math35459-add` and `math35459-multiply`. Both return structured and textual 42. Requests already succeed on baseline because the callback catches its exception. The fix removes that exception and intentionally skips deployment accounting when there is no deployment ID

The SDK control proves that a valid routed deployment still accumulates exactly one request and 27 tokens. Unit controls and four rejected mutations also cover valid deployments and prevent unknown calls from being attributed to a fabricated deployment

## Frontend verification

Open `http://127.0.0.1:41475/ui/login` and sign in with the local admin credentials. The password field is verified to be masked before filling it

1. Open `/ui/?page=llm-playground`, choose New chat and select `qa-cost-35459`
2. Submit a prompt with the desktop Send button or Enter on the phone, then wait for the real streamed answer and completed response
3. Open `/ui/?page=mcp-servers`, choose `math35459`, select MCP Tools and the `add` tool
4. Fill `a=17` and `b=25`, select Call Tool and verify the visible 42 result and real HTTP 200 response

The two viewport contexts are 1440x900 desktop and 390x844 touch phone. The unchanged phone portrait MCP list collapses to zero-width tool labels, so both revisions capture that limitation and rotate to 844x390 landscape before selecting the tool. Landscape still has header crowding and horizontal scrolling. Phone chat also has a clipped Send control, partially hidden user prompt and overlapping Aria control

All ten raw screenshots and eight sampled frames from each of four recordings were visually inspected. The [visual review](visual-review.json) identifies the images, videos, sample contact sheets and SHA256 hashes. The videos contain the actual browser flow, with no mocked network requests

Both revisions have zero JavaScript page exceptions. The same static-prefetch and runtime-config 404 paths remain, with 61 desktop and 17 phone responses per revision. [browser-comparison.json](browser-comparison.json) records each path and count. Successful screenshots are compatibility checks, while the report exception counts prove the logging fix

## Quality gates and setup corrections

Full `make format` leaves 2932 production files unchanged, and targeted formatting leaves both edited files unchanged. Full `make lint BASE_REF=origin/main LINT_JOBS=2` passes all repository gates, including Ruff, strict rules, type discipline, test quality, OpenAPI documentation, import checks and type-budget checks. E2E type checking reports zero errors. The production type gate remains within main's existing per-rule ceilings, with 105900 existing diagnostics, so this is not a claim of a diagnostic-free codebase

The new unit cases first ran against unchanged production code and failed only for explicit null metadata in both callback modes. The fixed mapped file passes 19 tests. Four deliberate mutations are rejected with 1, 1, 5 and 8 failing cases. The original fixed production bytes are restored exactly before final verification

The initial broader run had four failures because the optional `semantic_router` dependency was absent. The repository-locked extra, version 0.1.15, was installed without changing product dependencies or the lockfile, and the complete same eight-file selection was rerun. Final results are in [backend-regression-final.json](backend-regression-final.json) and [tests-fixed.log](tests-fixed.log)

The initial Windows-to-Linux copy carried an executable bit on the production file. Exact Git tree comparison and the EXE002 lint gate caught it. Its committed 100644 mode was restored, the exact committed tree was verified, and full lint was rerun without suppressions or budget changes

Local MCP harness setup was updated for the installed official 2.3.0 SDK, which returns two transport streams and snake_case result fields. The older repository math fixture imports a removed FastMCP entry point, so a local official-SDK math server replaced only that QA fixture. The failed setup attempts are preserved under harness-history and do not count as product verification

## Limits

These checks use a local CPU model, with no paid-provider, model-quality, performance, all-provider or additional-platform claim. Configured token costs are local test prices. The SDK logs retain unrelated custom-pricing cache-field warnings, so the result is zero targeted callback exceptions rather than globally clean logs

No frontend source changes or standalone frontend build are claimed for this backend fix. Both runs use the same existing production export and exercise the real browser workflow against the matching backend SHA

Owned proxy and math-server ports are closed after testing. The math server exited normally and remains a non-running zombie under the container init until reaped. The shared local model and database remain available for other contribution checks
