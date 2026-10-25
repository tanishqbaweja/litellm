import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

qa = Path('/qa/litellm-36095')
source = Path('/opt/litellm-36095')
dashboard = source / 'ui/litellm-dashboard'
build = qa / 'dashboard-deps-linux'
product = json.loads((qa / 'product.json').read_text())
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip() == product['head']
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=source, text=True).strip()
assert build.resolve().is_relative_to(qa.resolve())
assert (build / 'node_modules').is_dir()
assert (build / 'package-lock.json').read_bytes() == (dashboard / 'package-lock.json').read_bytes()
files = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', 'HEAD', 'ui/litellm-dashboard'], cwd=source, text=True).splitlines()
hashes = {}
for name in files:
    original = source / name
    relative = original.relative_to(dashboard)
    target = build / relative
    assert target.resolve().is_relative_to(build.resolve())
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(original, target)
    hashes[relative.as_posix()] = hashlib.sha256(original.read_bytes()).hexdigest()
    assert target.read_bytes() == original.read_bytes()
report = {
    'source_sha': product['head'],
    'started_at': datetime.now(timezone.utc).isoformat(),
    'source': str(dashboard),
    'build_directory': str(build),
    'tracked_files_copied_and_verified': len(hashes),
    'command': ['npm', 'run', 'build'],
    'node_version': subprocess.check_output(['/opt/contri-node/bin/node', '--version'], text=True).strip(),
    'tracked_file_hashes': hashes,
}
(qa / 'ui-build.json').write_text(json.dumps(report, indent=2) + '\n')
env = {
    **os.environ,
    'PATH': '/opt/contri-node/bin:' + os.environ['PATH'],
    'NEXT_TELEMETRY_DISABLED': '1',
    'NODE_OPTIONS': '--max-old-space-size=6144',
    'RAYON_NUM_THREADS': '2',
}
with (qa.parent / 'logs/litellm-36095-ui-build.log').open('w') as output:
    result = subprocess.run(report['command'], cwd=build, env=env, stdout=output, stderr=subprocess.STDOUT)
report['returncode'] = result.returncode
report['completed_at'] = datetime.now(timezone.utc).isoformat()
report['build_changed_tracked_files'] = [name for name, expected in hashes.items() if hashlib.sha256((build / name).read_bytes()).hexdigest() != expected]
report['product_tree_clean'] = not subprocess.check_output(['git', 'status', '--porcelain'], cwd=source, text=True).strip()
(qa / 'ui-build.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({key: value for key, value in report.items() if key != 'tracked_file_hashes'}, indent=2))
assert report['product_tree_clean']
raise SystemExit(result.returncode)
