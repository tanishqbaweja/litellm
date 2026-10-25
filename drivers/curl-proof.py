import json
import os
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path("/qa/litellm-38352")
revision = sys.argv[1]
assert revision in ("baseline", "fixed")
assert shutil.which("curl") and shutil.which("jq")
source = json.loads((root / f"proxy-source-{revision}.json").read_text())
assert Path(f"/proc/{source['pid']}/cwd").resolve() == Path(source["source"])
private = json.loads((root / f"live-{revision}.private.json").read_text())
fixture = json.loads((root / f"fixture-{revision}.private.json").read_text())
tokens = {"admin": private["master_key"], **{item["label"]: item["key"] for item in fixture["keys"]}}
report = {"revision": revision, "source_sha": source["sha"], "started_at": datetime.now(timezone.utc).isoformat(), "cases": []}
projection = "if .data then {returned: (.data|length), first_three_ids: [.data[:3][].vector_store_id], total_count, current_page, total_pages} else . end"
for route in ("/vector_store/list", "/v1/vector_store/list"):
    for actor, page, size in (("admin", 1, 2), ("admin", 2, 2), ("admin", 53, 2), ("admin", 0, 2), ("admin", -1, 2), ("admin", 1, 0), ("restricted", 2, 2), ("empty", 1, 2)):
        command = f'curl -sS -w "%{{stderr}}HTTP %{{http_code}}\\n" -H "Authorization: Bearer $QA_TOKEN" "http://127.0.0.1:41477{route}?page={page}&page_size={size}" | jq {shlex.quote(projection)}'
        result = subprocess.run(["bash", "-o", "pipefail", "-c", command], env={**os.environ, "QA_TOKEN": tokens[actor]}, text=True, capture_output=True)
        assert result.returncode == 0, result.stderr
        assert not any(token in result.stdout + result.stderr for token in tokens.values())
        status = int(result.stderr.strip().split()[-1])
        assert status == (400 if size < 1 or revision == "fixed" and page < 1 else 200)
        report["cases"].append({"actor": actor, "route": route, "page": page, "page_size": size, "command": command, "status": status, "stdout": result.stdout, "stderr": result.stderr, "output": json.loads(result.stdout)})
report["completed_at"] = datetime.now(timezone.utc).isoformat()
(root / f"curl-report-{revision}.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({"revision": revision, "curl_commands": len(report["cases"]), "source_sha": source["sha"]}), flush=True)
