import hashlib
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx


root = Path(__file__).resolve().parent
mode = sys.argv[1]
revision = sys.argv[2]
fixture_path = root / f"fixture-{revision}.private.json"
with httpx.Client(
    base_url="http://127.0.0.1:41475",
    headers={"Authorization": "Bearer " + os.environ["LITELLM_MASTER_KEY"]},
    timeout=45,
) as api:
    for _ in range(40):
        try:
            ready = api.get("/health/readiness")
            if ready.status_code == 200:
                break
        except httpx.ConnectError:
            pass
        time.sleep(1)
    else:
        raise RuntimeError("Proxy did not become ready")

    if mode == "off":
        assert not fixture_path.exists()
        alias = "qa-cache-23743-" + uuid4().hex[:8]
        created = api.post("/key/generate", json={"key_alias": alias})
        created.raise_for_status()
        key = created.json()["key"]
        fixture = {"alias": alias, "key": key, "token": hashlib.sha256(key.encode()).hexdigest(), "calls": []}
        fixture_path.write_text(json.dumps(fixture, indent=2) + "\n")
    else:
        fixture = json.loads(fixture_path.read_text())

    def complete(name, prompt, session_id=None):
        body = {
            "model": "qa-response-cache", "max_tokens": 32, "temperature": 0,
            "messages": [{"role": "user", "content": "Reply with exactly hello. Request reference " + prompt}],
        }
        if session_id:
            body["metadata"] = {"session_id": session_id}
        response = api.post("/v1/chat/completions", headers={"Authorization": "Bearer " + fixture["key"]}, json=body)
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        assert isinstance(content, str) and content.strip(), "The real model must generate text"
        fixture["calls"].append({"name": name, "id": data["id"], "content": content, "usage": data.get("usage")})
        fixture_path.write_text(json.dumps(fixture, indent=2) + "\n")

    if mode == "off":
        complete("cache-disabled", fixture["alias"] + " off")
    elif mode == "on":
        complete("single-miss", fixture["alias"] + " single")
        complete("single-hit", fixture["alias"] + " single")
        for index in range(3):
            complete("session-" + str(index), fixture["alias"] + " grouped", fixture["alias"] + "-session")
        assert fixture["calls"][1]["content"] == fixture["calls"][2]["content"]
        assert fixture["calls"][3]["content"] == fixture["calls"][4]["content"] == fixture["calls"][5]["content"]
    elif mode == "cleanup":
        response = api.post("/key/delete", json={"keys": [fixture["key"]]})
        response.raise_for_status()
        print(json.dumps({"alias": fixture["alias"], "delete_status": response.status_code}))
        sys.exit(0)

    now = datetime.now(timezone.utc)
    params = {
        "api_key": fixture["token"],
        "start_date": (now - timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S"),
        "end_date": (now + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S"),
        "page_size": 50,
    }
    for _ in range(35):
        response = api.get("/spend/logs/v2", params=params)
        response.raise_for_status()
        payload = response.json()
        rows = payload if isinstance(payload, list) else payload["data"]
        if len(rows) >= len(fixture["calls"]):
            break
        time.sleep(1)
    else:
        raise RuntimeError("Spend rows did not arrive")
    ui_response = api.get("/spend/logs/ui", params={**params, "page": 1, "group_by_session": "true"})
    ui_response.raise_for_status()
    ui_rows = ui_response.json()["data"]
    selected = ("request_id", "cache_hit", "cache_key", "session_id", "session_total_count", "session_cache_hit_count")
    report = {
        "revision": revision,
        "source": "dddbaa803d6e9fcc862ea7a5412f771cb1ae040e",
        "alias": fixture["alias"],
        "calls": fixture["calls"],
        "logs": [{field: row.get(field) for field in selected} for row in rows],
        "grouped_rows": [{field: row.get(field) for field in selected} for row in ui_rows],
    }
    (root / f"fixture-report-{revision}.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
