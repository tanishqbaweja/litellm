# Invitation authentication header verification

Evidence for LiteLLM issue [#34659](https://github.com/BerriAI/litellm/issues/34659)

The production dashboard fails to claim an invitation when the proxy expects a custom authentication header. Signup and password reset both submit the onboarding token under Authorization. The fix applies the header from the invitation token before submitting, including restoring Authorization when the claim is absent

Before is `dddbaa803d6e9fcc862ea7a5412f771cb1ae040e` and after is `48592e3c49857032553896eacaad1488f78a8cbd`. Both use the unchanged backend from the before revision, a real PostgreSQL database and production dashboard exports. Chromium 145.0.7632.6 runs with 1440x900 and 390x844 viewports, with mobile and touch emulation on the latter

## Observed behavior

With `general_settings.litellm_key_header_name` set to `x-litellm-api-key`, both forms return HTTP 401 before the fix and display Missing onboarding session for invitation link. After the fix, both return HTTP 200, establish the intended internal-user session, open Virtual Keys and allow a fresh browser login with the saved password

With the setting omitted, signup and password reset work before and after. Each successful case also reads the signed-in user's own record through the real API and receives HTTP 200. Key-list requests return HTTP 200 after the invitation claim and the fresh login, and screenshots wait for the empty table to finish loading. A fresh context uses the same viewport and touch settings for the second login

No browser requests are intercepted. No LLM inference is needed for this account workflow. The model entries in the supplied configs are repository fixtures and are not called. The fixture users use example.test addresses, invitation email is disabled, and each created user is deleted through the API after its case

## Screenshots and recordings

The four images at the repository root only add red outlines to the original screenshots. Raw images, recordings and request-status reports are in `before-custom`, `after-custom`, `before-default` and `after-default`

Each directory covers desktop signup, desktop password reset, phone signup and phone password reset in that order. Recordings show the invitation form and its result. Separate new-login screenshots show the successful fresh-context login where applicable. Recording pauses keep the result visible for inspection

All 44 raw screenshots, four annotated screenshots and eight sampled frames from each of the 16 recordings were visually inspected

The driver uses the same synthetic email for each paired case, with fresh one-use invitations and new random passwords. Passwords stay masked. Reports record header presence and status codes, without the authentication values

## Reproduction

Use a dedicated local proxy and PostgreSQL database with the repository's normal setup, including its generated Prisma client. Build the dashboard at the before or after revision with `npm run build` and set `LITELLM_UI_PATH` to that checkout's absolute `ui/litellm-dashboard/out` directory

Set `LITELLM_MASTER_KEY`, `DATABASE_URL` and `MOCK_LLM_URL` in the proxy environment. Start the repository's local model fixture if using the supplied model entries, although this workflow does not call it. Start the proxy on port 41475 with the chosen `config-custom.yml` or `config-default.yml`

1. Create an internal user and a new invitation through the admin API, using the configured authentication header
2. Open `http://127.0.0.1:41475/ui/onboarding/?invitation_id=<new-id>` in a fresh browser profile
3. Enter a password and click Sign Up, observing the error before or dashboard access after
4. For password reset, first set an initial password, create a new invitation and repeat with `&action=reset_password`
5. After a successful submission, open a fresh profile, log in with the email and new password, and open Virtual Keys

The included `qa.cjs` automates these steps against the live proxy. Run it with the same `LITELLM_MASTER_KEY` environment variable. Install the repository's Playwright package and Chromium, set `LITELLM_REPO` to the checkout containing `tests/e2e/ui/node_modules`, and provide a display or Xvfb for the headed browser

```bash
export LITELLM_REPO=/path/to/litellm
export LITELLM_BASE_URL=http://127.0.0.1:41475
export QA_SOURCE_SHA=48592e3c49857032553896eacaad1488f78a8cbd
node qa.cjs baseline custom
# Restart the proxy with the fixed UI export before the next command
node qa.cjs fixed custom
# Repeat both revisions with config-default.yml and the default argument
```

## Local checks

All six new integration cases fail on unchanged main because the outgoing claim request lacks the expected header. After the fix, the six affected frontend files pass 92 tests. The final six-case regression rerun also passes. These cases use the real form, hooks and HTTP client, with only the network boundary stubbed, and cover signup and reset with custom, default and missing header claims, including stale client state

The production build and configured production typecheck pass. Prettier, full CI ESLint, lint budgets, knip and diff checks pass. ESLint has zero errors and 3349 existing warnings. A broader `tsc --noEmit` reports the same 802 diagnostic lines on unchanged main and this commit, with no differences. The production typecheck is `tsc --project tsconfig.production.json`

The affected files are OnboardingForm's unit and integration tests, OnboardingFormBody's unit and integration tests, useOnboarding tests and networking tests. The new integration file tests the header on the actual outgoing request and verifies that a successful response establishes the session

## Existing behavior seen during verification

The main dashboard makes admin-only background requests to `/api/plugins` and `/health/readiness/details` after an internal-user login. Those return HTTP 401 on both revisions. Existing static-prefetch and runtime-config requests also return 404. The invitation claim and own-user API checks have the expected statuses, and no uncaught page exceptions or HTTP 5xx responses occur in the recorded flows

Phone results use Chromium emulation, not a physical device
