
import hashlib,json,os,re,subprocess
from datetime import datetime,timezone
from pathlib import Path
root=Path('/opt/litellm-26170')
qa=Path('/qa/litellm-26170')
main=root/'litellm/main.py'
provider=root/'litellm/litellm_core_utils/get_llm_provider_logic.py'
original={p:p.read_bytes() for p in (main,provider)}
common=['/opt/litellm-venv/bin/python','-m','pytest','tests/unit/test_main.py','-k','ollama_requests_respect_api_base_precedence','-q','--tb=short']
env={**os.environ,'PYTHONPATH':str(root),'LITELLM_LOCAL_MODEL_COST_MAP':'true'}
main_text=original[main].decode()
provider_text=original[provider].decode()
old='api_base = api_base or litellm.api_base or get_secret("OLLAMA_API_BASE") or "http://localhost:11434"'
wrong='api_base = litellm.api_base or api_base or get_secret("OLLAMA_API_BASE") or "http://localhost:11434"'
assert main_text.count(old)==2
first=main_text.find(old);second=main_text.find(old,first+len(old))
mutations=[
 ('generate-global-shadows-explicit',main,main_text[:first]+main_text[first:].replace(old,wrong,1)),
 ('chat-global-shadows-explicit',main,main_text[:second]+main_text[second:].replace(old,wrong,1)),
 ('embedding-global-shadows-explicit',main,main_text.replace('api_base = api_base or litellm.api_base or get_secret_str("OLLAMA_API_BASE")','api_base = litellm.api_base or api_base or get_secret_str("OLLAMA_API_BASE")',1)),
 ('provider-drops-global-fallback',provider,provider_text.replace(old,'api_base = api_base or get_secret("OLLAMA_API_BASE") or "http://localhost:11434"',1)),
]
report={'started_at':datetime.now(timezone.utc).isoformat(),'cases':[]}
try:
 for name,path,mutant in mutations:
  assert mutant!=original[path].decode(),name
  path.write_text(mutant)
  result=subprocess.run(common,cwd=root,env=env,capture_output=True,text=True)
  (Path('/qa/logs')/f'litellm-26170-mutation-{name}.log').write_text(result.stdout+result.stderr)
  failed=re.findall(r'(\d+) failed',result.stdout)
  assert result.returncode==1 and failed,(name,result.returncode,result.stdout[-1500:])
  item={'name':name,'exit_code':result.returncode,'failed_cases':int(failed[-1])}
  report['cases'].append(item)
  print(json.dumps(item),flush=True)
  path.write_bytes(original[path])
finally:
 for path,data in original.items():path.write_bytes(data)
 report['restored']=all(p.read_bytes()==data for p,data in original.items())
 report['restored_sha256']={str(p.relative_to(root)):hashlib.sha256(data).hexdigest() for p,data in original.items()}
 (qa/'mutation-report.json').write_text(json.dumps(report,indent=2)+'\n')
assert report['restored']
result=subprocess.run(['/opt/litellm-venv/bin/python','-m','pytest','tests/unit/test_main.py','tests/unit/litellm_core_utils/test_get_llm_provider_logic.py','tests/unit/llms/ollama','-q','--tb=short'],cwd=root,env=env,capture_output=True,text=True)
Path('/qa/logs/litellm-26170-tests-final.log').write_text(result.stdout+result.stderr)
print(result.stdout[-500:],flush=True)
result.check_returncode()
