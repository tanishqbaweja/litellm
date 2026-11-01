# Generic Guardrail API connection fields, proof files

Screenshots and the stand-in service behind the proof in BerriAI/litellm#48317, taken on 2026-11-01

- Before: `901b7f762f` (BerriAI/litellm main)
- After: `f38498305d` (the PR branch, main plus the fix)

Both legs ran the proxy on 127.0.0.1:4317 with PostgreSQL 16.2 and the dashboard build committed on main, and the screenshots come from headless Chrome at 1440x1400. The red boxes were drawn by the screenshot script

| File | What it shows |
|---|---|
| `before-form.png` | Main, Guardrails > Add New Guardrail > Add Provider Guardrail > Generic Guardrail API. Basic Info ends after "Skip tool messages in guardrail" with no URL or key input |
| `before-create-error.png` | Main, Create Guardrail fails with "api_base is required for Generic Guardrail API" |
| `after-form.png` | Branch, the same form now ends with the `api_base` and `api_key` inputs |
| `after-form-filled.png` | Branch, `api_base` set to the stand-in at http://127.0.0.1:18317 and `api_key` masked |
| `after-create-success.png` | Branch, "Guardrail created successfully" and the new guardrail row |
| `guardrail_standin.py` | The local guardrail service and chat model the proxy called, stdlib only |
