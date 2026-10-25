import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path("/qa/litellm-38352")
repo = Path("/opt/litellm-38352")
backend_path = repo / "litellm/proxy/vector_store_endpoints/management_endpoints.py"
frontend_path = repo / "ui/litellm-dashboard/src/components/networking.tsx"
originals = {path: path.read_bytes() for path in (backend_path, frontend_path)}
report = {"started_at": datetime.now(timezone.utc).isoformat(), "mutations": []}
only_kind = sys.argv[1] if len(sys.argv) > 1 else None
assert only_kind in (None, "frontend", "backend")
if only_kind:
    previous = json.loads((root / "mutation-report.json").read_text())
    archive = root / f"mutation-report-before-{only_kind}-refresh-{datetime.now(timezone.utc).strftime('%H%M%S')}.json"
    assert not archive.exists()
    archive.write_text(json.dumps(previous, indent=2) + "\n")
    assert previous["source_restored_exactly"]
    preserved = frontend_path if only_kind == "backend" else backend_path
    assert previous["restored_sha256"][str(preserved.relative_to(repo))] == hashlib.sha256(originals[preserved]).hexdigest()
    report["mutations"] = [item for item in previous["mutations"] if item["kind"] != only_kind]
    report["preserved_mutations_started_at"] = previous["started_at"]
    report["refreshed_kind"] = only_kind
changes = (
    ("backend", "unsliced-data", 'for vs in accessible_vector_stores[page_start : page_start + page_size]', 'for vs in accessible_vector_stores'),
    ("backend", "unstable-order", 'key=lambda store: store.get("vector_store_id", "")', 'key=lambda store: ""'),
    ("backend", "incorrect-page-offset", 'page_start: Final = (page - 1) * page_size', 'page_start: Final = page * page_size'),
    ("backend", "accept-page-zero", '    if page < 1:\n', '    if page < 0:\n'),
    ("backend", "count-inaccessible-stores", 'total_count: Final = len(accessible_vector_stores)', 'total_count: Final = len(vector_store_map)'),
    ("frontend", "omit-last-page", 'page <= firstPage.total_pages', 'page < firstPage.total_pages'),
    ("frontend", "repeat-first-page", 'query: { page, page_size: 100 }', 'query: { page: 1, page_size: 100 }'),
    ("frontend", "duplicate-legacy-catalog", ' && data.length < firstPage.total_count', ''),
    ("frontend", "wrong-management-target", 'apiClient.get<VectorStoreListResponse>', 'gatewayApiClient.get<VectorStoreListResponse>'),
)
try:
    for kind, name, old, new in changes:
        if only_kind and kind != only_kind:
            continue
        path = backend_path if kind == "backend" else frontend_path
        source = originals[path].decode()
        assert source.count(old) == 1, (name, source.count(old))
        path.write_text(source.replace(old, new))
        output_path = root / f"mutation-{name}.runner.log"
        with output_path.open("w") as output:
            result = subprocess.run(
                [sys.executable, str(root / "run-focused.py"), kind, f"mutation-{name}"],
                cwd=repo, stdout=output, stderr=subprocess.STDOUT,
            )
        log = re.sub(r"\x1b\[[0-9;]*m", "", (root / f"{kind}-mutation-{name}.log").read_text())
        matches = re.findall(r"(\d+) failed", log)
        item = {"kind": kind, "name": name, "returncode": result.returncode, "failed_cases": int(matches[-1]) if matches else 0}
        report["mutations"].append(item)
        print(json.dumps(item), flush=True)
        assert result.returncode == 1 and item["failed_cases"] > 0, item
        path.write_bytes(originals[path])
finally:
    for path, original in originals.items():
        path.write_bytes(original)
    report["source_restored_exactly"] = all(path.read_bytes() == original for path, original in originals.items())
    report["restored_sha256"] = {str(path.relative_to(repo)): hashlib.sha256(original).hexdigest() for path, original in originals.items()}
    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    (root / "mutation-report.json").write_text(json.dumps(report, indent=2) + "\n")
