# Generic Guardrail API connection fields, proof files

Screenshots and the stand-in service behind the proof in BerriAI/litellm#48317, taken on 2026-11-01

- Before: `60fc121ce8` (BerriAI/litellm main)
- After: `7d1a275f2b` (the PR branch, main plus the fix)

Both legs ran the proxy on 127.0.0.1:4317 against a fresh PostgreSQL 16.2 database, with the dashboard build committed on main. The screenshots come from headless Chrome at 1440x1400, driven by a Playwright script, and the red boxes were drawn by that script

| File | What it shows |
|---|---|
| `before-form.png` | Main, Guardrails > Add New Guardrail > Add Provider Guardrail > Generic Guardrail API. Basic Info ends after "Skip tool messages in guardrail" with no URL or key input |
| `after-form.png` | Branch, the same form now ends with the `api_base` and `api_key` inputs |
| `after-form-filled.png` | Branch, `api_base` set to the stand-in at http://127.0.0.1:18317 and `api_key` masked |
| `before-create-toast.png` | Main, Create Guardrail fails with "api_base is required for Generic Guardrail API" |
| `after-create-toast.png` | Branch, "Guardrail created successfully" |
| `before-guardrail-list.png` | Main, the Guardrails table is still empty after the failed create |
| `after-guardrail-list.png` | Branch, the Guardrails table lists the new guardrail |
| `before-edit-form.png` | Main, Settings > Edit Settings of a Generic Guardrail API guardrail created through `POST /guardrails`. Provider Settings is empty |
| `after-edit-form.png` | Branch, the same view shows the stored `api_base` and a masked `api_key` |
| `guardrail_standin.py` | The local guardrail service and chat model the proxy called, stdlib only |
