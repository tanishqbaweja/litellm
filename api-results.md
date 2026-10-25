# Live offline license results

Every request used curl against the actual proxy and returned HTTP 200

```bash
curl --fail-with-body -H "Authorization: Bearer $LITELLM_MASTER_KEY" http://127.0.0.1:41475/health/license
```

| Generated signed input | Before | After |
| --- | --- | --- |
| plain | enterprise | enterprise |
| dotted | community | enterprise |
| dotted-unpadded | community | enterprise |
| expired | community | community |
| tampered | community | community |

The same RSA public key and exact signed inputs were used on both revisions. Their SHA-256 fingerprints and full JSON replies are recorded under `before/api-*.json` and `after/api-*.json`. The test public key was substituted only in the private verification worktrees. The remote license server resolved to a closed loopback endpoint

The successful replies retain the signed expiration date, features and user/team limits. Rejected replies have empty features and null limits
