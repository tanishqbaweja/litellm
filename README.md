# Explicit null model-budget update verification

Issue [BerriAI/litellm#38759](https://github.com/BerriAI/litellm/issues/38759), covering the remaining explicit-null failure identified in the reporter's October 6 retest

Before `dddbaa803d6e9fcc862ea7a5412f771cb1ae040e`, after `52f7654be9ee2a86a88ecc5db0f2eb81962da9d9`

The live proxy uses PostgreSQL and normal master-key authentication, with no enterprise entitlement override. There are no model deployments or provider requests in this budget-management workflow. Each revision runs against its own temporary database, which is dropped after its budgets are deleted

## Live API proof

Both revisions execute the same 13 curl requests. The explicit-null update and its repeat return 500 before and 200 after. The fixed response stores an empty model-budget object while preserving the other fields. Empty-object, omitted-field and scalar-null controls return 200 on both revisions. Invalid nested and legacy scalar model entries return 422, and a valid nonempty model cap without an enterprise license still returns 400

The exact response bodies, statuses, request payloads and commands with authentication replaced by an environment placeholder are in [before](reports/api-report-baseline.json) and [after](reports/api-report-fixed.json). The [driver](drivers/api-probe.py) invokes curl against the real proxy

## Automated regression checks

The focused unit counterfactual fails the explicit-null case and passes three controls. The real PostgreSQL counterfactual fails the explicit-null clear and passes the empty-object clear. The final code passes all 26 tests in the mapped unit file and three selected real-service integration cases

The two new integration cases seed two populated model caps directly through the repository's SQL fixture, call the real update endpoint, and compare the stored row, response and info readback. This exercises clearing existing limits without overriding license validation. Two other pre-existing cases in this file require an enterprise license and were not included in the passing selection. These integration cases run in CircleCI on main, not in GitHub pull-request CI

All five targeted mutations were caught, with the exact production source restored and all 26 unit tests passing afterward. The 59 tests across the six relevant dashboard files also pass. The reports distinguish precommit working-tree checks from the final committed source, and record the production-file hash

Full make format and make lint pass, including the existing type ceilings. The committed-diff format check, API regeneration, production TypeScript, changed-file Prettier and ESLint, unchanged lint budgets, knip and production dashboard build pass. Raw whole-dashboard ESLint exits 2 for existing unpruned suppressions, with zero errors in its report. No suppression or budget file was changed. The production build generates all 58 pages and reports one existing AVIF image optimization warning

## Browser verification

Headed Chromium 145.0.7632.6 was driven at 1440 by 900 and at 390 by 844 with touch. Each revision creates a budget with spend limit 20, TPM 1000, RPM 60 and a monthly reset, edits the spend limit to 99, clears it to Unlimited, reloads and deletes the budget. The API readbacks compare all remaining fields after each edit, and every UI mutation returns 200

This is a dashboard regression check. The dashboard does not expose the model-budget JSON field whose explicit null is tested through the API

All 36 screenshots and eight sampled frames from each of the four recordings were visually inspected. The full recordings were not watched end to end. The phone forms remain usable, while the existing horizontal table scroll, clipped content, wrapped pagination and Aria overlay are documented in the [visual notes](reports/visual-inspection.json). Both revisions have zero page exceptions and zero HTTP 5xx responses in the browser, with existing runtime-config and static-prefetch 404s recorded in [the comparison](reports/browser-comparison.json)

Before [desktop recording](baseline/desktop.webm) and [phone recording](baseline/phone.webm), after [desktop recording](fixed/desktop.webm) and [phone recording](fixed/phone.webm)

The before dashboard reuses the verified main build described in [its provenance record](reports/baseline-ui-provenance.json). The after dashboard is freshly built from the submitted commit, with every tracked source file copied and checked. Both source checkouts are clean

## Reproduction drivers

The drivers record the local Linux paths and service setup used for this run. Supply local database credentials and adjust these paths to reproduce the same requests. Runtime secrets, private proxy logs and full integration service logs are excluded. Selected test summaries, mutation logs, public reports, screenshots and recordings are retained
