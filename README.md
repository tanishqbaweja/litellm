# LiteLLM #33210: native vLLM passthrough logging

Actual requests against two CPU vLLM model servers, LiteLLM and PostgreSQL, followed by headed Chromium checks of the real dashboard. No upstream or browser mocking.

- Before: `dddbaa803d6e9fcc862ea7a5412f771cb1ae040e`
- After: `ce6d5f6e9edaf11599c6a19e949b5d8392af1ece`
- Same unchanged production dashboard export from main for both revisions
- Full assertions and limitations: [checks.json](checks.json), [live-validation.json](live-validation.json)

## Observed behavior

All six requests return HTTP 200 in both revisions. Main records only the two embedding controls. The fix records all six; the four newly logged native requests preserve their IDs, usage and complete native response bodies. Missing-standard-logging errors occur before and are absent after.

| Route | Before spend row | After spend row | After configured cost |
| --- | --- | --- | --- |
| `/vllm/pooling` | missing | 5 tokens | $0.000005 |
| `/vllm/score` | missing | 28 tokens | $0.000028 |
| `/vllm/rerank` | missing | 28 tokens | $0.000028 |
| `/vllm/classify` | missing | 14 tokens | $0.000014 |
| `/vllm/v1/embeddings` | 9 tokens | 9 tokens | $0.000009 |
| `/v1/embeddings` | 9 tokens | 9 tokens | $0.000009 |

Prometheus changes from two requests / 18 input tokens / $0.000018 to six requests / 93 input tokens / $0.000093. All completion counts are zero. The configured rate is $0.000001 per prompt token; these are accounting checks, not provider invoices.

Every persisted native response equals its own client response in full. The two separate score calls have two floating point differences of 9.5367431640625e-7; the complete before/after responses and comparison tolerances are retained. This is not a numerical accuracy benchmark.

## Browser evidence

The same six request bodies are sent in each revision using separate temporary key aliases. Sign in at `http://127.0.0.1:41475/ui/login`, open `/ui/?page=logs`, filter by the test key alias, inspect metrics and the JSON response, then reopen Logs and apply the filter again. Desktop is 1440x900; phone is 390x844 with touch enabled.

| Viewport | Before | After |
| --- | --- | --- |
| Desktop | [annotated screenshot](desktop-baseline-annotated.png), [recording](before/desktop.webm) | [annotated screenshot](desktop-fixed-annotated.png), [recording](after/desktop.webm) |
| Phone | [annotated screenshot](phone-baseline-annotated.png), [recording](before/phone.webm) | [annotated screenshot](phone-fixed-annotated.png), [recording](after/phone.webm) |

All 32 raw screenshots and four annotated screenshots were visually inspected, along with eight sampled frames from each recording. Recordings show the short automated workflows; the screenshots preserve every checked detail state. Browser reports list every screenshot and assertion: [before](before/browser-report.json), [after](after/browser-report.json).

The existing phone drawer is narrow and clips headers, and the floating assistant overlaps pagination on both revisions. Native results are visible in JSON view; Pretty view does not render these non-chat responses. No JavaScript exceptions or HTTP 5xx responses occurred. Static/runtime-config 404s remain on both revisions with no new paths.

## Runtime and request reproduction

The actual model files, pinned revisions and SHA256 hashes are listed in [verified-model-files.json](verified-model-files.json). No model weights or credentials are included.

- `sentence-transformers/all-MiniLM-L6-v2`, revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`
- `cross-encoder/ms-marco-MiniLM-L6-v2`, revision `233902d25c440f23af6f7d6e94d2946bac0bee0a`
- vLLM `0.32.0+cpu`: `vllm/vllm-openai-cpu@sha256:827ef38187f9b52f2bb838695ef815ec5b65f4bf3e4c061b002b2b0a19cb0701`
- Linux amd64, AVX2 CPU, float32, PostgreSQL 16.10, Python 3.12.13, Playwright 1.58.1 / Chromium 145.0.7632.6

The servers used the exact flags in [start-vllm.sh](start-vllm.sh), with their pinned model directories mounted under `/qa/models`. The vLLM container shared the proxy container's network namespace; its model ports 51477 and 51478 were loopback-only. Environment: `VLLM_CPU_OMP_THREADS_BIND=nobind`, `OMP_NUM_THREADS=2`, `VLLM_CPU_KVCACHE_SPACE=1`, `VLLM_NO_USAGE_STATS=1`, `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`. Inference used safetensors and no remote model code.

Start the proxy with [config.yml](config.yml), a local PostgreSQL connection in `DATABASE_URL`, and a test master key in `LITELLM_MASTER_KEY`. Enable the Prometheus callback and store prompts as shown. The two native aliases use base URLs without `/v1`; the regular embedding control uses `/v1`.

The exact request and response JSON files are under [before](before/) and [after](after/). For example, with a temporary virtual key in `LITELLM_TEST_KEY`:

```sh
curl -X POST http://127.0.0.1:41475/vllm/pooling \
  -H "Authorization: Bearer $LITELLM_TEST_KEY" \
  -H 'Content-Type: application/json' \
  --data-binary @after/pooling-request.json
```

[probe.py](probe.py) is the actual six-request curl driver. Run it from the checked-out product revision so it records the correct source SHA. It creates a temporary key and writes a private fixture file; keep that file private and delete the key after verification. [validate-live.py](validate-live.py) checks persisted native responses and Prometheus totals. [qa.cjs](qa.cjs) drives the real browser; it expects the repository's Playwright package at `/repo/tests/e2e/ui/node_modules` and the test master key in the environment. The frozen published reports are separate from any fresh local run these scripts generate.

Live pooling used task `embed`. Two-dimensional `token_classify` data is covered by the unit regression, but no live BAAI/bge-m3 or token-classification model is claimed.

## Code validation

- Four parametrized regressions fail against unchanged main: [baseline test log](tests-baseline.log)
- Five relevant files pass after the fix: **45 passed**, 25 warnings: [fixed test log](tests-fixed.log)
- All five targeted mutations fail, followed by exact restoration and passing tests: [mutation report](mutation-report.json)
- `make format` and targeted test formatting pass: [format log](format.log)
- `make lint BASE_REF=origin/main LINT_JOBS=2` passes: [lint log](lint.log)
- Whole-tree type budget: 105900 existing diagnostics, every rule within the merge-base ceiling; separate E2E types report zero errors
- Complete three-file product diff reviewed; no unrelated source changes

CI results are tracked on the PR, separately from these local results.
