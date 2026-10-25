# LiteLLM object fallback verification

Issue [#26473](https://github.com/BerriAI/litellm/issues/26473), checked on 2026-10-25

Before `dddbaa803d6e9fcc862ea7a5412f771cb1ae040e`, after `1942148f89b566d47a24887a025eefc8fea376d7`

The production dashboard ran through a real Linux LiteLLM proxy and PostgreSQL 16.10, using the repository's UI fixture configuration and seeded admin account. Playwright 1.58.1 drove Chromium 145.0.7632.6 on Windows, with Node 24.21.0 and locked dashboard dependencies. The Linux backend was built from the baseline source, and only the dashboard export changed between runs

No browser requests were intercepted, no UI state was injected, and no CSS was overridden during these captures. Configuration changes went through the real proxy API and were checked by reading the saved configuration after each action. These tests exercise settings persistence and rendering, with no paid provider calls

## Browser results

Both builds used `http://127.0.0.1:41475/ui/router-settings/` and the same two fallback chains, including a mixed string/object chain with `reasoning_effort`, a synthetic credential and an extra header

| Viewport | Before | After |
| --- | --- | --- |
| Desktop, 1440x900 | [Crash screenshot](desktop-before.png), [recording](desktop-before.webm) | [Fallbacks screenshot](desktop-after.png), [Loadbalancing screenshot](desktop-loadbalancing-after.png), [recording](desktop-after.webm) |
| Phone, 390x844 with touch | [Crash screenshot](phone-before.png), [recording](phone-before.webm) | [Fallbacks screenshot](phone-after.png), [Loadbalancing screenshot](phone-loadbalancing-after.png), [recording](phone-after.webm) |

Main throws React error 31 immediately on opening Router Settings, before the Fallbacks tab can be used. After the fix, the default Loadbalancing tab and the Fallbacks tab both render. Mixed targets display their model names, with an Overrides label and no credential or header values displayed

The object chain cannot open the model-list editor. Its desktop tooltip explains that parameter overrides are edited through the API or config file. The ordinary sibling chain can be saved, deleted and added back through the UI, with a deep comparison of the saved object after each action confirming that every override remains unchanged. Reloading shows both persisted chains

Narrow tables scroll horizontally inside their container. A geometry assertion checks that model labels and the Overrides label remain inside the fallback column, clear of the action column. It failed at 390px before the layout adjustment and passes with the final production build. Neither tested viewport has page-level horizontal overflow, uncaught page errors or HTTP 5xx responses in the fixed workflow

The screenshots and eight sampled frames from each recording were visually inspected. Red boxes annotate copies of the affected area, and all original screenshots remain under `raw/`. Menus are closed and transient success notifications settle before screenshots are captured

## Reproduction setup

Use a disposable proxy with `tests/e2e/ui/fixtures/config.yml` and its seeded PostgreSQL database. The commands below replace that fixture's fallback settings. Set `BASE` to the local proxy URL and `LITELLM_MASTER_KEY` to its configured admin key

```sh
export BASE=http://127.0.0.1:41475
curl --fail-with-body "$BASE/model/new" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"model_name":"qa-fallback-26473","litellm_params":{"model":"openai/fake-gpt-4","api_base":"http://127.0.0.1:51475/v1","api_key":"fake-key"},"model_info":{}}'

curl --fail-with-body "$BASE/config/update" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"router_settings":{"fallbacks":[{"fake-openai-gpt-4":[{"model":"fake-anthropic-claude","reasoning_effort":"none","api_key":"qa-override-not-a-provider-secret","extra_headers":{"X-QA-Sentinel":"preserve-me"}},"qa-fallback-26473"]},{"qa-fallback-26473":["fake-anthropic-claude"]}]}}'
```

At each viewport, sign in through `/ui/login`, open `/ui/router-settings/`, then click Fallbacks. Save the ordinary `qa-fallback-26473` row without changing its models, delete it, and add it again with the same fallback. Reload and inspect both rows. After every save, read back the configuration and compare the complete `fake-openai-gpt-4` target list

```sh
curl --fail-with-body "$BASE/get/config/callbacks" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY"
```

The [browser driver](browser-driver.cjs) contains the executable assertions and fresh-login flow. It was run from a `.verification` directory beside a `litellm` checkout whose UI harness dependencies were installed. The [before report](before-report.json) and [after report](after-report.json) preserve viewport details, steps, page errors and HTTP error paths

## Checks actually run

| Check | Result |
| --- | --- |
| New component regressions on main | 3 expected React object-child failures, 19 existing tests pass |
| Focused component tests on final source | 6 files, 57 tests pass, 9.58 seconds |
| UI type tests | 4 files, 8 tests pass |
| Production typecheck | Pass |
| Baseline and final production exports | Pass |
| Changed-file Prettier and diff check | Pass |
| Full ESLint with CI suppression flag | Pass, zero errors and 3349 existing warnings |
| Lint budgets | Pass |
| `npm run knip:ci` | Pass |
| Coverage of the three changed production components | 88.2% lines, 75.94% branches, 92.3% functions |
| Final browser workflows | Desktop and phone pass |

The full UI unit suite was not run locally, following the contributor instructions. The focused command was

```sh
npm exec -- vitest run \
  src/components/Settings/RouterSettings/Fallbacks/Fallbacks.test.tsx \
  src/components/Settings/RouterSettings/Fallbacks/AddFallbacks.test.tsx \
  src/components/Settings/RouterSettings/Fallbacks/EditFallbacks.test.tsx \
  src/components/Settings/RouterSettings/Fallbacks/AddFallbacksModal.test.tsx \
  src/components/Settings/RouterSettings/Fallbacks/FallbackSelectionForm.test.tsx \
  src/components/common_components/RouterSettingsAccordion.test.tsx \
  --maxWorkers=2 --reporter=dot --coverage \
  '--coverage.include=src/components/Settings/RouterSettings/Fallbacks/{Fallbacks,AddFallbacks,EditFallbacks}.tsx'
```

The remaining local checks were `npm run typecheck`, `npm run build`, `npm run test:types`, changed-file `prettier --check`, `eslint . --pass-on-unpruned-suppressions -f json`, the repository's `check-lint-budgets.mjs`, `npm run knip:ci` and `git diff --check`. Exit-code records are included alongside this file

Both exports log existing optional runtime-config and static Next prefetch 404s. Those paths are retained in the reports. No claims about live provider inference, billing accuracy or untested browsers are made
