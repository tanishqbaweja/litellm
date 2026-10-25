import json
import sys
from pathlib import Path

import httpx

root = Path("/qa/litellm-38352")
revision = sys.argv[1]
private = json.loads((root / f"live-{revision}.private.json").read_text())
fixture = json.loads((root / f"fixture-{revision}.private.json").read_text())
results = []
with httpx.Client(base_url="http://127.0.0.1:41477", headers={"Authorization": "Bearer " + private["master_key"]}, timeout=30, trust_env=False) as api:
    for item in fixture["keys"]:
        response = api.post("/key/delete", json={"keys": [item["key"]]})
        results.append({"kind": "key", "label": item["label"], "status": response.status_code})
        response.raise_for_status()
    for user_id in fixture["users"]:
        response = api.post("/user/delete", json={"user_ids": [user_id]})
        results.append({"kind": "user", "user_id": user_id, "status": response.status_code})
        response.raise_for_status()
    for store in fixture["database_stores"]:
        response = api.post("/vector_store/delete", json={"vector_store_id": store["vector_store_id"]})
        results.append({"kind": "vector_store", "id": store["vector_store_id"], "status": response.status_code})
        response.raise_for_status()
(root / f"fixture-cleanup-{revision}.json").write_text(json.dumps(results, indent=2) + "\n")
(root / f"stop-{revision}").write_text("Finished API and browser verification\n")
print(json.dumps(results), flush=True)
