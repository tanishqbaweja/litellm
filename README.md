# Custom favicon navigation fix

Evidence for [LiteLLM #34916](https://github.com/BerriAI/litellm/issues/34916), captured on 2026-10-25

Before source is `dddbaa803d6e9fcc862ea7a5412f771cb1ae040e`. After source is `7975e117e467daa99752f80ad3b0767657568dba`. This evidence branch is separate from the product branch

## Problem and change

On current main, saving a custom favicon and reloading displays the chosen image. Clicking Home restores the default browser-tab icon. Route metadata replaces the URL set by UI Theme, and the app-directory favicon adds a competing `/favicon.ico?...` URL that returns 404 behind the proxy

The fix keeps the default icon in public assets and renders its fallback link from the persistent root layout. The existing theme update can then keep its selected URL across navigation. React places that icon link in the document head, as described in its [link reference](https://react.dev/reference/react-dom/components/link)

## Environment

The actual proxy and PostgreSQL served before and after production dashboard exports at `http://127.0.0.1:41475`. The backend stayed at the before revision because this is a frontend change. A local HTTP server on port 51477 served the included orange and cyan PNG images. There was no browser request interception, and the configuration workflow required no LLM inference

Playwright 1.58.1 drove headed Chromium 145.0.7632.6 on Linux in an isolated Xvfb display. The page viewports were 1440x900 and 390x844, with mobile and touch emulation on the latter. The phone case is browser emulation, not a physical-device test. Both builds used the same database and image server

Window screenshots and screen recordings include the browser tab, so they show the icon the browser actually displays. The wider white margin beside the phone page comes from its desktop browser window. The red environment-login banner comes from the local proxy configuration

## Reproduce by hand

Run `python image-server.py` beside the two PNG files, in the browser's network namespace. Sign in to the proxy as an admin

1. Open `http://127.0.0.1:41475/ui/ui-theme/` and enter `http://127.0.0.1:51477/favicon.png` in Custom Favicon URL
2. Click Save Changes and reload. Confirm that the saved URL remains in the field and the orange F appears in the browser tab
3. Click Home in the sidebar. At phone width, open navigation first. Main restores the default blue icon, while the fixed revision keeps the orange F
4. Return to UI Theme and save `http://127.0.0.1:51477/favicon-alt.png`. Click Home again. Main restores the default again, while the fixed revision keeps the cyan F
5. Return to UI Theme, click Reset to Default and reload. The default icon returns, and `/ui/favicon.ico` still serves the original image

The driver additionally checks saved values through the real API, resolves each declared icon URL, records browser errors, and restores the original theme after each viewport. Its paths reflect the original workspace. Window captures use the locally installed screenshot helper, while FFmpeg records the isolated display

## Observed results

Both before runs show the custom icon being replaced after each navigation. Both after runs preserve the orange and cyan icons, use the configured image URLs directly, and restore a working default after reset and reload

All 28 browser-window screenshots and eight sampled frames from each of the four recordings were visually inspected, including enlarged tab crops. The raw folder also contains the corresponding viewport-only screenshots. There were no uncaught browser exceptions or HTTP 5xx responses. Existing runtime-config and static-prefetch 404s occur on both revisions

| Case | Before | After |
| --- | --- | --- |
| Desktop after Home navigation | [Screenshot](desktop-before.png) | [Screenshot](desktop-after.png) |
| Phone after Home navigation | [Screenshot](phone-before.png) | [Screenshot](phone-after.png) |
| Desktop workflow | [Recording](desktop-before.webm) | [Recording](desktop-after.webm) |
| Phone workflow | [Recording](phone-before.webm) | [Recording](phone-after.webm) |

Red rectangles identify the browser-tab icon. The [before report](before-report.json) and [after report](after-report.json) include source hashes, viewport settings, icon URLs, response statuses, errors and cleanup results. `raw/` contains the unannotated captures

## Tests and checks

The new Playwright case in `tests/e2e/ui/tests/migration/migratedPages.spec.ts` fails on the unchanged main production export because navigation replaces the selected icon URL. It passes on the final export, one test in 5.6 seconds. It checks saving, persisted reload, client navigation, the selected icon URLs and their actual image bytes, then restores the original settings

Five affected frontend files pass, 34 tests with no reported type errors. These cover UIThemeSettings, dashboard layout, its real-tree integration, chat layout and connect layout. The full frontend suite was left to CI as required by the dashboard contributor guide

The production build, production typecheck, changed-file Prettier, full CI ESLint, lint budgets, knip and `git diff --check` pass. ESLint reports zero errors and 3349 existing warnings with the repository's `--pass-on-unpruned-suppressions` flag. Three existing backend favicon tests also pass against the unchanged backend

The default E2E TypeScript command reports two existing `Promise.withResolvers` errors in `keyBudgetWindow.spec.ts` on both main and this branch. The same typecheck passes with `--lib ES2024,DOM,DOM.Iterable`. Node was 24.21.0, and backend tests used Python 3.12.13 on Linux
