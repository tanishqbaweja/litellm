const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const {chromium, expect} = require('/repo/tests/e2e/ui/node_modules/@playwright/test');

const root = __dirname;
const revision = process.argv[2];
assert(['baseline','fixed'].includes(revision));
const baseURL = 'http://127.0.0.1:41479';
const receiver = 'http://127.0.0.1:41480';
const output = path.join(root,'output','playwright',`visual-${revision}-${Date.now()}`);
const visible = locator => locator.filter({visible:true}).first();

async function main() {
  await fs.mkdir(output,{recursive:true});
  const privateData = JSON.parse(await fs.readFile(path.join(root,`live-${revision}.private.json`),'utf8'));
  const source = JSON.parse(await fs.readFile(path.join(root,`proxy-source-${revision}.json`),'utf8'));
  assert.equal(await fs.realpath(`/proc/${source.pid}/cwd`),source.source);
  const secrets = new Set([privateData.master_key]);
  function redact(value) {
    if(Array.isArray(value)) return value.map(redact);
    if(value && typeof value==='object') return Object.fromEntries(Object.entries(value).map(([name,item])=>[name,['key','token','hashed_key','key_id'].includes(name)&&typeof item==='string'?'<QA_KEY>':redact(item)]));
    if(typeof value==='string') {let result=value; for(const secret of secrets) result=result.split(secret).join('<QA_KEY>'); return result;}
    return value;
  }
  const report={revision,sourceSha:source.sha,uiSourceSha:source.ui_source_sha,uiSourceUnchanged:true,output,startedAt:new Date().toISOString(),provider:'Local real Qwen3.5 0.8B inference through Ollama',hostedSlackNotTested:true,credentialRevealPanelMasked:true,viewports:[]};
  const browser=await chromium.launch({headless:false});
  report.browser=browser.version();
  try {
    for(const viewport of [{name:'desktop',width:1440,height:900},{name:'phone',width:390,height:844}]) {
      const context=await browser.newContext({baseURL,viewport:{width:viewport.width,height:viewport.height},isMobile:viewport.name==='phone',hasTouch:viewport.name==='phone',colorScheme:'light',recordVideo:{dir:path.join(output,'raw-video'),size:{width:viewport.width,height:viewport.height}}});
      const page=await context.newPage();
      page.setDefaultTimeout(25000);
      const video=page.video();
      const alias=`qa35800-${viewport.name}`;
      let key;
      let deleted=false;
      const result={viewport,alias,startedAt:new Date().toISOString(),steps:[],mutations:[],readbacks:[],inferenceCalls:[],pageErrors:[],consoleErrors:[],failedResponses:[]};
      report.viewports.push(result);
      const activate=locator=>viewport.name==='phone'?locator.tap():locator.click();
      const capture=async(name)=>{
        if(name.includes('budget')) {
          const field=page.getByLabel('Soft Budget (USD)',{exact:true});
          await field.evaluate(element=>element.scrollIntoView({block:'center',inline:'nearest',behavior:'instant'}));
          await expect(field).toBeInViewport({ratio:1});
        }
        await page.mouse.move(1,1);
        await page.waitForTimeout(650);
        const screenshot=`${viewport.name}-${name}.png`;
        await page.screenshot({path:path.join(output,screenshot),fullPage:false,scale:'css'});
        result.steps.push({name,screenshot,at:new Date().toISOString()});
        console.log(JSON.stringify({revision,viewport:viewport.name,step:name}));
      };
      const mutate=async(route,action)=>{
        const [response]=await Promise.all([
          page.waitForResponse(response=>new URL(response.url()).pathname===route&&response.request().method()==='POST'),
          action(),
        ]);
        const body=await response.json();
        if(route==='/key/generate' && response.status()===200) {key=body.key; secrets.add(key);}
        result.mutations.push({path:route,status:response.status(),request:redact(response.request().postDataJSON()),response:redact(body)});
        assert.equal(response.status(),200,JSON.stringify(redact(body)));
        return body;
      };
      const readInfo=async()=>{
        const response=await page.request.get('/key/info',{headers:{Authorization:`Bearer ${privateData.master_key}`},params:{key}});
        assert.equal(response.status(),200);
        const info=(await response.json()).info;
        const value={alias:info.key_alias,spend:info.spend,softBudget:info.soft_budget??info.litellm_budget_table?.soft_budget??null,maxBudget:info.max_budget,teamId:info.team_id,models:info.models,rpmLimit:info.rpm_limit,tpmLimit:info.tpm_limit};
        result.readbacks.push(value);
        return value;
      };
      const edit=async()=>{
        await activate(page.getByRole('tab',{name:'Settings',exact:true}));
        await activate(page.getByRole('button',{name:'Edit Settings',exact:true}));
        const field=page.getByLabel('Soft Budget (USD)',{exact:true});
        await expect(field).toBeVisible();
        return field;
      };
      page.on('pageerror',error=>result.pageErrors.push(redact(error.message)));
      page.on('console',event=>{if(event.type()==='error')result.consoleErrors.push(redact(event.text()));});
      page.on('response',response=>{if(response.status()>=400)result.failedResponses.push({path:new URL(response.url()).pathname,status:response.status()});});
      try {
        await page.goto('/ui/login');
        await page.getByPlaceholder('Enter your username').fill('admin');
        const password=page.getByPlaceholder('Enter your password');
        await expect(password).toHaveAttribute('type','password');
        await password.fill(privateData.master_key);
        await activate(page.getByRole('button',{name:'Login',exact:true}));
        await expect(page.getByRole('button',{name:'Launch Aria Agent'})).toBeVisible({timeout:30000});
        await page.goto('/ui/?page=api-keys');
        const dismiss=page.getByText("Don't ask me again");
        if(await dismiss.isVisible())await activate(dismiss);
        await expect(page.getByRole('heading',{name:'Virtual Keys',exact:true})).toBeVisible();
        await page.addStyleTag({content:'[role="dialog"] pre { visibility: hidden !important; }'});
        await activate(visible(page.getByRole('button',{name:/Create New Key/})));
        await page.getByLabel(/Key Name/).fill(alias);
        await capture('create-form');
        await mutate('/key/generate',()=>activate(page.getByRole('button',{name:'Create Key',exact:true})));
        const saved=page.getByRole('dialog',{name:'Save your Key',exact:true});
        await expect(saved).toBeVisible();
        await activate(saved.getByRole('button',{name:'Close',exact:true}));
        await activate(page.getByText(alias,{exact:true}));
        const initial=await readInfo();
        assert.equal(initial.maxBudget,null);
        assert.equal(initial.teamId,null);
        const firstSoft=await edit();
        await firstSoft.fill('0.01');
        await firstSoft.scrollIntoViewIfNeeded();
        await capture('set-soft-budget');
        await mutate('/key/update',()=>activate(visible(page.getByRole('button',{name:'Save Changes',exact:true}))));
        const configured=await readInfo();
        assert.deepEqual(configured,{...initial,softBudget:0.01});
        await page.reload();
        const storedSoft=await edit();
        await expect(storedSoft).toHaveValue('0.01');
        await storedSoft.scrollIntoViewIfNeeded();
        await capture('soft-budget-persisted');
        await activate(visible(page.getByRole('button',{name:'Cancel',exact:true})));
        let totalCost=0;
        for(let index=0;index<3;index++) {
          const response=await page.request.post('/v1/chat/completions',{headers:{Authorization:`Bearer ${key}`},data:{model:'qa-alert-model',messages:[{role:'user',content:`Say hi. ${alias} request ${index+1}`}],max_tokens:8,cache:{'no-cache':true}},timeout:120000});
          const body=await response.json();
          assert.equal(response.status(),200,JSON.stringify(redact(body)));
          const cost=Number(response.headers()['x-litellm-response-cost']);
          assert(cost>0 && body.usage.total_tokens>0);
          totalCost+=cost;
          result.inferenceCalls.push({status:response.status(),usage:body.usage,cost});
          if(index===0)await expect.poll(async()=> (await readInfo()).spend,{timeout:40000,intervals:[200,400,800]}).toBeGreaterThanOrEqual(0.01);
        }
        await expect.poll(async()=>Math.abs((await readInfo()).spend-totalCost),{timeout:40000,intervals:[200,400,800]}).toBeLessThan(1e-8);
        await page.waitForTimeout(16000);
        const alertsResponse=await page.request.get(receiver+'/messages',{params:{alias}});
        assert.equal(alertsResponse.status(),200);
        result.alerts=await alertsResponse.json();
        assert.equal(result.alerts.count,revision==='fixed'?1:0);
        const afterSpend=await readInfo();
        assert(Math.abs(afterSpend.spend-totalCost)<1e-8);
        assert.deepEqual({...afterSpend,spend:configured.spend},configured);
        await page.reload();
        await activate(page.getByRole('tab',{name:'Overview',exact:true}));
        await capture('spend-crossed');
        const raised=await edit();
        await expect(raised).toHaveValue('0.01');
        await raised.fill('1000');
        await raised.scrollIntoViewIfNeeded();
        await capture('raise-soft-budget');
        await mutate('/key/update',()=>activate(visible(page.getByRole('button',{name:'Save Changes',exact:true}))));
        assert.deepEqual(await readInfo(),{...afterSpend,softBudget:1000});
        await page.reload();
        const persisted=await edit();
        await expect(persisted).toHaveValue('1000');
        await persisted.scrollIntoViewIfNeeded();
        await capture('raised-budget-persisted');
        await activate(visible(page.getByRole('button',{name:'Cancel',exact:true})));
        await activate(page.getByRole('button',{name:'More key actions',exact:true}));
        await activate(page.getByRole('menuitem',{name:'Delete Key',exact:true}));
        const confirmation=page.getByRole('dialog',{name:'Delete Key',exact:true});
        await confirmation.getByRole('textbox').fill(alias);
        await mutate('/key/delete',()=>activate(confirmation.getByRole('button',{name:'Delete',exact:true})));
        deleted=true;
        await expect(page.getByRole('heading',{name:'Virtual Keys',exact:true})).toBeVisible();
        await expect(page.getByText(alias,{exact:true})).toHaveCount(0);
        await capture('deleted-key');
        const revoked=await page.request.post('/v1/chat/completions',{headers:{Authorization:`Bearer ${key}`},data:{model:'qa-alert-model',messages:[{role:'user',content:'revocation control'}],max_tokens:8}});
        result.revokedKeyStatus=revoked.status();
        assert.equal(revoked.status(),401);
        assert.deepEqual(result.pageErrors,[]);
        assert.deepEqual(result.failedResponses.filter(response=>response.status>=500),[]);
        result.result='passed';
      } catch(error) {
        result.error=redact(String(error));
        await page.screenshot({path:path.join(output,`${viewport.name}-failure.png`),fullPage:true});
        throw error;
      } finally {
        if(key && !deleted) {
          const cleanup=await page.request.post('/key/delete',{headers:{Authorization:`Bearer ${privateData.master_key}`},data:{keys:[key]}});
          result.cleanupStatus=cleanup.status();
        }
        result.completedAt=new Date().toISOString();
        await context.close();
        const destination=path.join(output,`${viewport.name}.webm`);
        await video.saveAs(destination);
        result.video=destination;
        await fs.writeFile(path.join(root,`ui-report-${revision}.json`),JSON.stringify(redact(report),null,2)+'\n');
      }
    }
    report.result='passed';
  } finally {
    await browser.close();
    await fs.writeFile(path.join(root,`ui-secrets-${revision}.private.json`),JSON.stringify(Array.from(secrets))+'\n');
    report.completedAt=new Date().toISOString();
    await fs.writeFile(path.join(root,`ui-report-${revision}.json`),JSON.stringify(redact(report),null,2)+'\n');
  }
  console.log(JSON.stringify({revision,result:report.result,output}));
}
main().catch(error=>{console.error(String(error));process.exitCode=1;});
