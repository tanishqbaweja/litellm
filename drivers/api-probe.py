import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

root = Path("/qa/litellm-38352")
revision = sys.argv[1]
assert revision in ("baseline", "fixed")
private = json.loads((root / f"live-{revision}.private.json").read_text())
source = json.loads((root / f"proxy-source-{revision}.json").read_text())
assert Path(f"/proc/{source['pid']}/cwd").resolve() == Path(source["source"])
all_ids = [f"vs_qa38352_{index:03d}" for index in range(1, 104)]
granted_ids = [all_ids[2], all_ids[101], all_ids[102]]
report = {"revision": revision, "source_sha": source["sha"], "started_at": datetime.now(timezone.utc).isoformat(), "cases": [], "enumerations": []}
fixture = {"keys": [], "users": [], "database_stores": []}
fixture_path = root / f"fixture-{revision}.private.json"
assert not fixture_path.exists()
secret = "qa38352-catalog-only-provider-token"


def save():
    fixture_path.write_text(json.dumps(fixture, indent=2) + "\n")
    (root / f"api-report-{revision}.json").write_text(json.dumps(report, indent=2) + "\n")


def store_body(index):
    return {
        "vector_store_id": f"vs_qa38352_{index:03d}", "vector_store_name": f"Catalog {index:03d}",
        "vector_store_description": "Pagination QA database store", "custom_llm_provider": "openai",
        "litellm_params": {"api_key": secret}, "vector_store_metadata": {"qa_issue": "38352"},
    }


with httpx.Client(base_url="http://127.0.0.1:41477", headers={"Authorization": "Bearer " + private["master_key"]}, timeout=30, trust_env=False) as api:
    for index in (102, 103):
        body = store_body(index)
        response = api.post("/vector_store/new", json=body)
        response.raise_for_status()
        fixture["database_stores"].append(body)
        save()
    for label, grants in (("restricted", granted_ids), ("empty", [])):
        user_id = f"qa38352-{revision}-{label}"
        response = api.post("/user/new", json={"user_id": user_id, "user_role": "internal_user", "auto_create_key": False})
        response.raise_for_status()
        fixture["users"].append(user_id)
        save()
        response = api.post("/key/generate", json={"user_id": user_id, "key_alias": user_id, "models": ["qa-catalog-38352"], "object_permission": {"vector_stores": grants}})
        response.raise_for_status()
        fixture["keys"].append({"label": label, "key": response.json()["key"], "grants": grants})
        save()

    def request_page(route, page, size, actor, expected_ids):
        headers = {} if actor == "admin" else {"Authorization": "Bearer " + next(item["key"] for item in fixture["keys"] if item["label"] == actor)}
        response = api.get(route, params={"page": page, "page_size": size}, headers=headers)
        body = response.json()
        item = {"route": route, "actor": actor, "page": page, "page_size": size, "status": response.status_code}
        if response.status_code == 200:
            ids = [row["vector_store_id"] for row in body["data"]]
            item.update({"ids": ids, "total_count": body["total_count"], "current_page": body["current_page"], "total_pages": body["total_pages"]})
            assert body["object"] == "list" and body["current_page"] == page
            assert body["total_count"] == len(expected_ids)
            assert body["total_pages"] == math.ceil(len(expected_ids) / size)
            assert set(ids).issubset(expected_ids)
            for row in body["data"]:
                assert row["is_config"] == (int(row["vector_store_id"].rsplit("_", 1)[1]) <= 101)
                assert row["litellm_params"]["api_key"] != secret
            item["requested_slice_matches"] = ids == expected_ids[(page - 1) * size : page * size]
            if revision == "fixed":
                assert item["requested_slice_matches"], item
        else:
            item["error"] = body
        report["cases"].append(item)
        save()
        return item

    for route in ("/vector_store/list", "/v1/vector_store/list"):
        for page, size in ((1, 2), (2, 2), (52, 2), (53, 2), (1, 100), (2, 100)):
            assert request_page(route, page, size, "admin", all_ids)["status"] == 200
        for page, size in ((0, 2), (-1, 2), (1, 0), (1, -1)):
            response = api.get(route, params={"page": page, "page_size": size})
            expected_status = 400 if revision == "fixed" or size < 1 else 200
            assert response.status_code == expected_status, response.text
            report["cases"].append({"route": route, "actor": "admin", "page": page, "page_size": size, "status": response.status_code, "positive_bounds_enforced": response.status_code == 400})
            save()
        for page in (1, 2, 3):
            assert request_page(route, page, 2, "restricted", granted_ids)["status"] == 200
        assert request_page(route, 1, 2, "empty", [])["status"] == 200
        rounds = []
        for _ in range(2):
            pages = [request_page(route, page, 17, "admin", all_ids)["ids"] for page in range(1, 8)]
            rounds.append([identifier for page in pages for identifier in page])
        comparison = {"route": route, "rounds_equal": rounds[0] == rounds[1], "exactly_once_in_id_order": rounds[0] == all_ids, "enumerated_count": len(rounds[0]), "unique_count": len(set(rounds[0]))}
        assert comparison["rounds_equal"]
        assert comparison["exactly_once_in_id_order"] == (revision == "fixed")
        report["enumerations"].append(comparison)
        save()
    report["config_store_count"] = 101
    report["database_store_count"] = 2
    report["credentials_masked"] = True
    report["provider_requests_performed"] = False
    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    save()
    print(json.dumps({"revision": revision, "requests": len(report["cases"]), "enumerations": report["enumerations"], "credentials_masked": True}), flush=True)
