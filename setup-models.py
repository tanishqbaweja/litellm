
import hashlib,json,os,subprocess,time
from pathlib import Path
import httpx
root=Path('/qa/litellm-26170')
model=Path('/opt/qa-models/Qwen3.5-0.8B-Q4_0.gguf')
with model.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
assert digest=='57d1997790d1744fba5b40a7317df71ea5e2acee28c47e78f0cce39c0703f8cf'
env={**os.environ,'OLLAMA_HOST':'http://127.0.0.1:11434','OLLAMA_MODELS':str(root/'ollama-models')}
cli='/opt/qa-ollama-0.40.11/bin/ollama'
for name,command in [('create-chat-model',[cli,'create','qa-qwen3.5-0.8b','-f',str(root/'Modelfile')]),('pull-embedding-model',[cli,'pull','qwen3-embedding:0.6b'])]:
 r=subprocess.run(command,env=env,capture_output=True,text=True)
 (root/f'{name}.log').write_text(r.stdout+r.stderr)
 assert r.returncode==0,(name,r.stderr[-1500:])
 print(name,'complete',flush=True)
with httpx.Client(base_url='http://127.0.0.1:11434',timeout=120) as api:
 tags=api.get('/api/tags');tags.raise_for_status()
 version=api.get('/api/version');version.raise_for_status()
 report={'ollama':version.json(),'models':tags.json(),'chat_gguf_sha256':digest,'chat_gguf_bytes':model.stat().st_size}
 (root/'live-models.json').write_text(json.dumps(report,indent=2)+'\n')
 for name,body in [('chat',{'model':'qa-qwen3.5-0.8b','messages':[{'role':'user','content':'Reply with only: Routing works.'}],'think':False,'stream':False}),('embed',{'model':'qwen3-embedding:0.6b','input':'hello','options':{'num_ctx':1024,'num_thread':4}})]:
  r=api.post('/api/'+name,json=body)
  (root/f'direct-{name}.json').write_text(json.dumps({'status':r.status_code,'body':r.json()},indent=2)+'\n')
  r.raise_for_status()
  data=r.json()
  print(json.dumps({'endpoint':name,'status':r.status_code,'content':data.get('message'),'embedding_dimensions':len(data.get('embeddings',[[]])[0]),'prompt_eval_count':data.get('prompt_eval_count')}),flush=True)
print(json.dumps(report),flush=True)
