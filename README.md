# LiteLLM pagination verification

Issue [#47520](https://github.com/BerriAI/litellm/issues/47520), checked on 2026-10-25

Before `dddbaa803d6e9fcc862ea7a5412f771cb1ae040e`, after `f926fd593a319dc355e28c163df70b459c040a11`

The real production dashboard was served by a local Linux LiteLLM proxy backed by PostgreSQL 16.10. The repository's `tests/e2e/ui/fixtures/config.yml`, seed data and mock LLM upstream supplied reproducible log rows, as described in `tests/e2e/AGENTS.md`. The browser and proxy requests were not intercepted or mocked. This verifies UI pagination, not paid provider behavior or billing

The two dashboard exports were built with Node 24.21.0 and the locked dependencies. Playwright 1.58.1 drove Chromium 145.0.7632.6 from Windows. The Linux backend was built from the unchanged baseline source. Only the dashboard export changed between the before and after runs

## Browser result

Both runs used the same URL, `http://127.0.0.1:41475/ui/?page=logs`, and the same 26 recorded requests filtered by key alias `qa-pagination-1792934983174`

| Viewport | Before | After |
| --- | --- | --- |
| Desktop, 1440x900 | [Screenshot](desktop-before.png), [recording](desktop-before.webm) | [Screenshot](desktop-after.png), [recording](desktop-after.webm) |
| Phone, 390x844 with touch | [Screenshot](phone-before.png), [recording](phone-before.webm) | [Screenshot](phone-after.png), [recording](phone-after.webm) |
| Short desktop, 1280x600 | [Screenshot](short-desktop-before.png), [recording](short-desktop-before.webm) | [Screenshot](short-desktop-after.png), [recording](short-desktop-after.webm) |

On main, ordinary next-page clicks were blocked by the Aria Agent launcher at all three sizes. The committed regression independently reproduced the interception at both 1440px and 390px widths

After the fix, next, previous, last and first controls displayed the expected ranges. Choosing 50 rows displayed all 26 records and disabled next/last. Returning to 25 rows, opening and closing Aria, and paginating again all passed. Desktop dismissal used Escape and phone dismissal used the close button, with focus returning to the launcher. Virtual Keys navigation and alias search also passed, settling on exactly one matching key

The page had no horizontal overflow at the tested sizes. Wide tables still have their own horizontal scrolling. No uncaught page errors or HTTP 5xx responses occurred during the fixed workflow

Screenshots were inspected visually, including the assistant dialog, last-page state and filtered Virtual Keys page. Eight sampled frames from each of the six recordings were also inspected. Red boxes were added to copies of the before/after screenshots around the next-page control and launcher. The original captures are retained under `raw/`

## Checks actually run

| Check | Result |
| --- | --- |
| New Playwright cases against main | Both fail for launcher pointer interception |
| Same Playwright cases against fixed production export | 2 passed, 21.0 seconds |
| Affected component/layout tests on main | 4 files, 101 passed |
| Affected component/layout tests with fix | 4 files, 101 passed, 71.83 seconds |
| UI production typecheck | Passed |
| Production build before and after | Both passed |
| Changed-file Prettier and CI ESLint command | Passed |
| Full ESLint with CI's `--pass-on-unpruned-suppressions` flag | Passed, zero errors and 3349 existing warnings |
| Repository lint budgets | Passed |
| `npm run knip:ci` | Passed |
| `git diff --check` | Passed |
| E2E TypeScript with `--lib ES2024,DOM` | Passed |

Focused component/layout command, run from `ui/litellm-dashboard`

```sh
npm exec -- vitest run \
  src/components/liteadmin/LiteAdmin.integration.test.tsx \
  'src/app/(dashboard)/layout.test.tsx' \
  'src/app/(dashboard)/layout.integration.test.tsx' \
  'src/app/(dashboard)/home/_components/HomePage.integration.test.tsx' \
  --maxWorkers=2 --reporter=dot
```

The browser regression used `logsPagination.spec.ts` and the grep `Logs pagination with the assistant visible`. A local config ran those self-contained fresh-login tests against the seeded proxy without the shared global setup's unrelated enterprise settings or saved role sessions. It used one Chromium worker, zero retries, 15-second action timeouts and a three-minute test timeout

The paired recording driver is included as `visual-check.cjs`. Set `LITELLM_REPO_ROOT`, `LITELLM_MASTER_KEY` and `E2E_UI_BASE_URL` for an isolated proxy with the repository UI fixtures, then run it with `baseline` and `fixed` after switching the served exports. Set `QA_HEAD_SHA` to the tested commit for the fixed run. It creates its shared key and request fixture once, so both runs use identical records. Its private fixture file is intentionally excluded from these artifacts

## Existing local limitations

The unmodified `npm run lint` exits 2 because of stale suppressions on both main and the branch, with identical counts of zero errors and 3349 warnings. The CI lint command explicitly passes `--pass-on-unpruned-suppressions`, and that command plus the lint budgets pass

The E2E package's default TypeScript command reports two TS2550 errors for `Promise.withResolvers` in `tests/proxy-admin/keyBudgetWindow.spec.ts` at lines 47 and 48. The same two errors were reproduced from unchanged main. The E2E typecheck passes with `--lib ES2024,DOM`, without changing the repository configuration

Both served exports logged 404s for optional runtime configuration and static route-prefetch assets. The workflows still completed without uncaught page errors or server failures. The build also reports an AVIF support warning

The assistant's inference behavior was not exercised. The fix reserves 4rem below the dashboard when the launcher is available, which reduces the content's visible height by that amount
