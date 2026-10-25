import json
import os
import subprocess
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values

root = Path("/qa/litellm-38759")
repo = Path("/opt/litellm-38759")
phase = sys.argv[1]
results = root / f"integration-{phase}"
results.mkdir(exist_ok=True)
os.chdir(repo)
sys.path.insert(0, str(repo))
os.environ["DATABASE_URL"] = dotenv_values("/qa/litellm-linux.env")["DATABASE_URL"]
os.environ["PYTHONPATH"] = os.pathsep.join((str(repo), str(repo / "tests"), str(repo / "tests/e2e")))
os.environ["INTEGRATION_PROXY_ROOT"] = str(repo)
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ["PRISMA_BINARY_CACHE_DIR"] = "/opt/prisma-cache"
os.environ.pop("DISABLE_SCHEMA_UPDATE", None)
os.environ["PATH"] = "/opt/litellm-venv/bin:/opt/contri-node/bin:" + os.environ["PATH"]
file = "tests/integration/management/test_budget_updates.py"
nodes = [file + "::test_clearing_model_budgets_preserves_other_limits"]
if phase == "green":
    nodes.append(file + "::test_shortening_budget_duration_moves_reset_at_onto_the_new_schedule")
elif phase == "full":
    nodes = [file]
report = {"phase": phase, "started_at": datetime.now(timezone.utc).isoformat(), "nodes": nodes}
report["source_head"] = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
if phase == "red":
    assert report["source_head"] == json.loads((root / "runtime.json").read_text())["base"]
    assert subprocess.check_output(["git", "diff", "--name-only", "--", "litellm", "enterprise"], text=True) == ""
print(json.dumps({"phase": phase, "stage": "Starting repository-owned isolated Postgres, Redis, upstream and two proxies"}), flush=True)
with (root / f"integration-{phase}.private.log").open("w") as log, redirect_stdout(log), redirect_stderr(log):
    try:
        from tests.integration._support.workers import GatewayProfile, worker_stack

        stack = worker_stack(results, GatewayProfile(peer=True, replica=False, cost_map=False, coverage_file=None))
        with stack.resources:
            report["services_ready"] = True
            result = subprocess.run(
                [sys.executable, "tests/integration/run.py", "management", "--results", str(results), *nodes],
                env={**os.environ, **stack.environment}, stdout=log, stderr=subprocess.STDOUT,
            )
            report["returncode"] = result.returncode
        report["owned_services_cleaned_up"] = True
    except BaseException as error:
        traceback.print_exc()
        report["error_type"] = type(error).__name__
        report["returncode"] = 2
report["completed_at"] = datetime.now(timezone.utc).isoformat()
(root / f"integration-{phase}.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report), flush=True)
sys.exit(report["returncode"])
