import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

root = Path("/qa/litellm-38352")
repo = Path("/opt/litellm-38352")
path = repo / "ui/litellm-dashboard/src/components/networking.tsx"
original = path.read_bytes()
base = json.loads((root / "runtime.json").read_text())["base"]
baseline = subprocess.check_output(["git", "show", f"{base}:ui/litellm-dashboard/src/components/networking.tsx"], cwd=repo)
report = {"runs": []}
try:
    for phase, source, expected in (("green-final", original, 0), ("red-final", baseline, 1)):
        path.write_bytes(source)
        with (root / f"frontend-{phase}.runner.log").open("w") as output:
            result = subprocess.run([sys.executable, str(root / "run-focused.py"), "frontend", phase], stdout=output, stderr=subprocess.STDOUT)
        text = re.sub(r"\x1b\[[0-9;]*m", "", (root / f"frontend-{phase}.log").read_text())
        summaries = [line.strip() for line in text.splitlines() if line.strip().startswith(("Test Files", "Tests ", "Duration"))]
        item = {"phase": phase, "returncode": result.returncode, "production_source_sha256": hashlib.sha256(source).hexdigest(), "summary": summaries}
        report["runs"].append(item)
        print(json.dumps(item), flush=True)
        assert result.returncode == expected, item
finally:
    path.write_bytes(original)
    report["fixed_source_restored_exactly"] = path.read_bytes() == original
    (root / "frontend-counterfactual.json").write_text(json.dumps(report, indent=2) + "\n")
