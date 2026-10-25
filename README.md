# Unknown API keys and spend records

This evidence accompanies the fix for [LiteLLM #42689](https://github.com/BerriAI/litellm/issues/42689)

The baseline is `dddbaa803d6e9fcc862ea7a5412f771cb1ae040e`. The fixed commit is `ad971a738117785fe3ae1efb87287f6993490227`. Both live proxies ran from clean Linux worktrees with isolated databases on the same PostgreSQL server and separate, owned Redis instances

Eight requests used distinct unknown or malformed bearer tokens across `/v1/models`, `/v1/chat/completions`, `/v1/responses` and `/v1/messages`. All returned HTTP 401 on both revisions. Main wrote eight rows into each of the three spend tables. The fix wrote zero

Four recognized-key records remain on both revisions, one successful inference, two expired-key failures and one exhausted-budget failure. User and team spend aggregates therefore change from 12 requests, 11 failures and 11 distinct keys to four requests, three failures and three keys

The successful call used a real local Qwen3.5 0.8B model served by Ollama 0.40.11. Its 12 input tokens and 24 output tokens produce $0.06 at the deliberately assigned test prices of $0.001 and $0.002 per token. This is computed test spend, not a paid provider charge. The two single-call latency readings are not a performance comparison

[Baseline curl commands and responses](commands/baseline.md) and [fixed curl commands and responses](commands/fixed.md) contain the actual command arguments with credentials redacted. Full response records are in `reports/api-proof-baseline.json` and `reports/api-proof-fixed.json`

## Browser verification

Headed Chromium 145 was driven through Playwright CLI 0.1.22 at 1440x900 and 390x844 with touch emulation. Each revision was checked through login, request logs, the budget failure drawer and Usage. All 16 screenshots and 24 sampled frames from four recordings were visually inspected

The Usage headline retains nine gateway requests with one success and eight failures. That counter is separate from the spend tables and preserves rejected traffic as an operational signal. The spend-based average changes from $0.0050 to $0.0150, and the fixed key breakdown contains only the three recognized keys

[Baseline desktop recording](baseline/desktop.webm), [baseline phone recording](baseline/phone.webm), [fixed desktop recording](fixed/desktop.webm) and [fixed phone recording](fixed/phone.webm) show the actual interactions. Raw screenshots are alongside the recordings, with red-box annotations for the changed request rows and average spend

Both revisions have existing runtime-config and static-prefetch 404s, chart size warnings, a narrow phone request drawer, horizontal overflow and an Aria overlay. The phone check is Chromium emulation, not a physical-device claim. The report also records a 401 telemetry response when a fresh browser was opened without signing in, followed by a successful login

QA driver corrections are recorded in `reports/browser-comparison.json`, including the initial assumption that Usage headline counters would drop. Source inspection showed that `overviewTotals` uses the separate gateway counters, and the corrected assertion verifies their preservation

## Regression checks

The final unit selection passes 1,059 tests with 79 warnings recorded. All four real PostgreSQL and Redis integration cases pass, as do 106 frontend tests across six files and production TypeScript checking

The new 14-case unit regression fails four cases on main, while ten recognized-key controls pass. All six deliberate mutants are detected by assertions, and the exact production source is restored afterwards. The new integration cases fail on main with four unknown-key rows in each spend table and pass after the fix

`make format`, full `make lint` and the committed-diff format check pass. The lint gate compares type diagnostics to the main baseline, so passing does not mean that the entire repository has zero existing diagnostics. The final source report confirms that the committed patch matches the tested Linux and host files

The dashboard source is unchanged. Browser runs use the existing production export whose source provenance is recorded in `reports/baseline-ui-provenance.json`, and the frontend dependency manifests match the checked lock file

All three owned API keys were deleted after each live run. Both owned databases and Redis processes were removed, and the proxy port was closed
