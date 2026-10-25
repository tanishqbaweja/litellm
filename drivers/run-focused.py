import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path("/qa/litellm-38352")
repo = Path("/opt/litellm-38352")
kind, phase = sys.argv[1:]
env = os.environ.copy()
env["PYTHONPATH"] = str(repo)
env["PATH"] = "/opt/contri-node/bin:/opt/litellm-venv/bin:" + env["PATH"]
if kind == "backend":
    command = [
        sys.executable, "-m", "pytest", "-q", "--tb=short",
        "tests/unit/proxy/vector_store_endpoints/test_vector_store_endpoints.py",
        "tests/unit/proxy/vector_store_endpoints/test_vector_store_rbac.py",
        "-k", "returns_the_requested_page_in_id_order or paginates_only_the_stores_granted_to_the_key or rejects_non_positive_page_with_400",
    ]
    cwd = repo
elif kind == "frontend":
    command = [
        "/opt/contri-node/bin/node", "node_modules/vitest/vitest.mjs", "run", "--project", "unit",
        "src/components/networking.test.ts", "-t", "vectorStoreListCall complete dashboard inventory|keeps vector store inventory on the management backend",
        "--reporter=verbose",
    ]
    cwd = repo / "ui/litellm-dashboard"
else:
    raise ValueError(kind)
report = {"phase": phase, "kind": kind, "command": command, "started_at": datetime.now(timezone.utc).isoformat()}
log_path = root / f"{kind}-{phase}.log"
with log_path.open("w") as log:
    result = subprocess.run(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
report["returncode"] = result.returncode
report["completed_at"] = datetime.now(timezone.utc).isoformat()
(root / f"{kind}-{phase}.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report), flush=True)
print(log_path.read_text()[-14000:], flush=True)
sys.exit(result.returncode)
