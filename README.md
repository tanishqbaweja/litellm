# Request Logs cache-hit column verification

Evidence for [LiteLLM #23743](https://github.com/BerriAI/litellm/issues/23743), recorded on 2026-10-25 with Codex

| Component | Revision or version |
| --- | --- |
| Before dashboard and both backend runs | `dddbaa803d6e9fcc862ea7a5412f771cb1ae040e` |
| After dashboard | `aa8cc11379b190c5b9260e73b684d8711dc362d5` |
| Dashboard build | Next.js 16.4.1, default Turbopack production export, Node 24.21.0 |
| Browser | Headed Chromium 145.0.7632.6 through Playwright 1.58.1 and Xvfb |
| Viewports | Desktop 1440x900; phone 390x844 with mobile and touch emulation |
| Backend | Python 3.12.13, real LiteLLM proxy, PostgreSQL 16.10 |
| Model | Qwen3.5-0.8B Q4_0, executed locally by llama.cpp b11669 |

The before and after browser runs use the same six persisted requests, not regenerated fixtures. Only the dashboard export changes. There is no browser route interception or mock model response

## Observed behavior

| Request | Actual stored values | Before table | After table |
| --- | --- | --- | --- |
| Caching disabled | `cache_hit: "None"`, `cache_key: "Cache OFF"` | No column | `-` |
| Cache miss | `cache_hit: "None"`, nonempty cache key | No column | `No` |
| Cache hit | `cache_hit: "True"` | No column | `Yes` |
| Three-request session | `session_total_count: 3`, `session_cache_hit_count: 2` | No column | `2 hits` |

Six proxy requests cause three real model generations and three response-cache hits. Every generated response is `hello`; every request records 36 prompt tokens and 2 completion tokens. [requests.json](requests.json) contains the selected API results, and [model-generation.log](model-generation.log) records three model tasks

These observations verify cache behavior and its display. They are not a latency, throughput, cost-savings or hosted-provider benchmark

## Screenshots and recordings

| Viewport | Before | After |
| --- | --- | --- |
| Desktop screenshot | [Before](desktop-before.png) | [After](desktop-after.png) |
| Phone screenshot | [Before](phone-before.png) | [After](phone-after.png) |
| Desktop recording | [Before](before/desktop.webm) | [After](after/desktop.webm) |
| Phone recording | [Before](before/phone.webm) | [After](after/phone.webm) |

Red boxes highlight the existing Status column before and the new Cache Hit column after. Unannotated screenshots and browser reports are in [before](before) and [after](after)

All 20 raw screenshots, all four annotated screenshots and eight sampled frames from each of the four recordings were visually inspected. The browser driver also checks individual hit/miss details, hit filtering, filter reset, cache values and table-page width. Phone row and filter actions use touch taps. For phone details, the existing Collapse trace sidebar button is tapped, then the Hit or Miss badge is checked to be fully inside the viewport

## Reproduction

1. Prepare an isolated PostgreSQL database and a LiteLLM proxy environment at the backend revision above. Set `DATABASE_URL` and a local-only `LITELLM_MASTER_KEY`. Apply the repository's normal database setup
2. Build the dashboard at each listed revision with `npm ci` and `npm run build` in `ui/litellm-dashboard`. Keep each `out` directory separately. Point `LITELLM_UI_PATH` at the appropriate export when starting the proxy
3. Download [llama.cpp b11669 for Ubuntu x64](https://github.com/ggml-org/llama.cpp/releases/download/b11669/llama-b11669-bin-ubuntu-x64.tar.gz). The archive SHA-256 verified for this run is `cf07c1c112d709bd67e522017471de57ed0ec8bea031d732c5422351c07f65ac`
4. Download [the pinned model](https://huggingface.co/ggml-org/Qwen3.5-0.8B-GGUF/resolve/807dfd9a6fadbf703207aac3bfb0b2b3040d077c/Qwen3.5-0.8B-Q4_0.gguf). Its 563036064 bytes have verified SHA-256 `57d1997790d1744fba5b40a7317df71ea5e2acee28c47e78f0cce39c0703f8cf`, also recorded in [model-verification.json](model-verification.json)
5. Start `llama-server -m /path/to/Qwen3.5-0.8B-Q4_0.gguf --host 127.0.0.1 --port 51476 --ctx-size 1024 --parallel 1 --threads 4 -n 32 --alias Qwen3.5-0.8B --chat-template-kwargs '{"enable_thinking":false}' --reasoning-budget 0`
6. From the unchanged backend, start `python -m litellm.proxy.proxy_cli --host 127.0.0.1 --port 41475 --telemetry false --config /path/to/config-off.yml` with the before dashboard export
7. Run `python fixtures.py off baseline`. This creates a disposable virtual key and makes the uncached request. The generated `*.private.json` contains that key and must stay local
8. Restart the same backend with [config-on.yml](config-on.yml), keeping the same database, and run `python fixtures.py on baseline`. This sends the five cache-enabled requests and writes `fixture-report-baseline.json`
9. Install the repository's `tests/e2e/ui` Playwright dependencies and Chromium. With a graphical display or Xvfb available, set `LITELLM_REPO` to that repository checkout and run `node qa.cjs baseline` from this evidence directory
10. Restart only the proxy with `LITELLM_UI_PATH` set to the after export, using the same backend, database and cache-enabled config. Copy `fixture-report-baseline.json` to `fixture-report-fixed.json`, then set `QA_SOURCE_SHA=aa8cc11379b190c5b9260e73b684d8711dc362d5` and run `node qa.cjs fixed`
11. To check manually, sign in as `admin` with the local master key, open `http://127.0.0.1:41475/ui/?page=logs`, filter by the generated key alias and compare the four rows. Open the individual hit and miss rows, apply Cache Hit under Filters, then restore All Requests
12. After verification, run `python fixtures.py cleanup baseline` to delete the disposable virtual key

The supplied configs expect the proxy and model server to share the same loopback network. All commands above use the verification ports, not public services

## Automated checks

- Three new table integration tests fail on unchanged main because the Cache Hit column is absent
- Seven affected frontend files pass, 243 tests, including the existing request panel, filters and details integration tests
- Mutating away cache-key handling produces three failures; substituting a representative request's cache flag for the session total produces one failure. The restored source passes all 243 tests
- Production build and production TypeScript check pass
- Prettier for all five changed files, full CI ESLint, lint budgets, knip and `git diff --check` pass. ESLint reports zero errors and 3349 existing warnings
- Both browser cases pass on each revision with no JavaScript exceptions or HTTP 5xx responses

[checks.json](checks.json) records the results. This is targeted frontend validation; no full local frontend-suite or cross-browser claim is made

## Existing limitations observed on both revisions

The phone details drawer remains narrow and clips or overlaps some unrelated metric values even with its trace sidebar collapsed. The cache badge is visible and agrees with the table. The existing floating assistant also overlaps part of the pagination area. This column change does not alter either layout

The same runtime-config and static RSC-prefetch URLs return HTTP 404 before and after: 41 console 404 messages in each desktop run and seven in each phone run. There are no additional missing-resource paths after the change. These are retained in the browser reports
